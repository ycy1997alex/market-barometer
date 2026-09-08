"""桌面儀表板的 View（ToDo §9 Day 27 第 1 項）。

**這一層只認 Presenter，不認 SQLite、不認 yfinance**
（tests/test_layer_boundary.py 用 AST 掃描守著 §3.2）。
所以這支檔案裡連 import 都看不到 storage 或 datasources 這兩個字。

畫面上刻意把**兩種時間**分開講，不合成一個：

  1. 每一列自己帶**資料日期**與頻率 —— 那是這條序列的值屬於哪一天
  2. 狀態列列的是「幾條序列、幾種資料日期」，加上下一次自動更新會抓哪幾條

因為那 21 條序列本來就不是同一天的：央行停在 2024-03-22、CPI 是 7 月、
利差是昨天。把它們壓成一個「最後更新時間」是最順手也最不誠實的做法
（§9 Day 25 第 3 項）。網頁那一側同樣處理：標頭有「最後一次抓取」，
但明寫它是**管線執行時間**，不是任何一條序列的資料日期。

四個分頁跟網頁端一致：世界總經、台灣總經、台股大盤與 ETF、美股大盤與 ETF。
大盤那兩頁**只讀 `score_history`，不重算** —— 桌面自己算一次的話，數字就
可能跟網頁上的對不起來，同一個問題兩個答案比沒有答案更難查。

---

**三件跟 tkinter 本身有關、不做就會出事的事：**

1. **視窗尺寸依螢幕解析度換算**（由上到下 3%~87%、由左到右 3%~97%），
   算式在 `app/geometry.py`，是純函式而且有測試。寫死像素在 4K 上會變成
   角落一個小方塊，在 1366×768 的筆電上又會超出畫面。

2. **更新走背景執行緒。** 一次 refresh 要打十幾個網路請求，跑在主執行緒上
   等於整個視窗凍住十幾秒，使用者只會覺得它當掉了。所以工作丟到 daemon
   執行緒，結果透過 `queue.Queue` 回傳，主執行緒用 `after()` 輪詢。
   **背景執行緒一律不碰任何 widget。**

3. **關窗要攔。** `WM_DELETE_WINDOW` 攔下來之後依序：取消所有排程中的
   `after` callback、要求背景執行緒停下並 join、才 destroy。
   少了第一步，關窗後那些 callback 會炸 `invalid command name`；
   少了第二步，抓資料抓到一半的執行緒會變成孤兒。

widget 一律用 ttkbootstrap，不跟原生 `tk.*` 混用（混用的樣式會對不起來）。
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as bs
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y

from barometer.app.geometry import shrink_for_frame, window_box
from barometer.app.presenters.dashboard import DashboardPresenter

TAB_TITLES = (("world", "世界總體經濟"), ("tw", "台灣總體經濟"),
              ("tw_index", "台股大盤與 ETF"), ("us_index", "美股大盤與 ETF"))
COLUMNS = (("label", "指標／標的", 220), ("value", "最新值／分數", 120),
           ("data_date", "資料日期", 120), ("freq", "頻率", 80),
           ("note", "備註", 560))

POLL_MS = 120            # 輪詢背景結果的間隔
JOIN_TIMEOUT_S = 5.0     # 關窗時等背景執行緒的上限
# 每隔多久檢查一次「有沒有序列到期」。檢查本身不打網路，只讀本機快取，
# 所以可以排得密一點；真正打網路的是「有東西到期」那一刻。
AUTO_CHECK_MS = 10 * 60 * 1000


class DashboardWindow:
    def __init__(self, root: tk.Misc, presenter: DashboardPresenter) -> None:
        self.root = root
        self.presenter = presenter

        self._result: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._after_ids: set[str] = set()
        self._closing = False

        root.title("market-barometer —— 總經與大盤儀表")
        self._box = window_box(root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(self._box.as_geometry())
        root.minsize(720, 480)

        top = bs.Frame(root, padding=(10, 8))
        top.pack(fill=X)
        # 兩種更新，行為刻意不同（Day 27 第 1 項驗收）：
        #   自動 —— 背景每 10 分鐘檢查一次，**只有真的有序列到期才打網路**
        #   強制 —— 按下去一定打網路，而且忽略快取重新掃一次
        # 切分頁一律只讀本機快取，一次網路都不打。
        self.btn = bs.Button(top, text="強制重抓（忽略快取）", bootstyle="primary",
                             command=self._on_force)
        self.btn.pack(side=LEFT)
        self.auto_label = bs.Label(top, text="")
        self.auto_label.pack(side=LEFT, padx=12)

        self.nb = bs.Notebook(root)
        self.nb.pack(fill=BOTH, expand=True, padx=10, pady=(4, 6))
        self.trees: dict[str, bs.Treeview] = {}
        for key, title in TAB_TITLES:
            frame = bs.Frame(self.nb)
            self.nb.add(frame, text=title)
            self.trees[key] = self._make_tree(frame)

        self.status = bs.Label(root, text="", anchor="w", padding=(10, 4))
        self.status.pack(fill=X)

        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._reload_current())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._reload_all()
        self._refresh_auto_label()
        self._fit_outer_edges()
        self._schedule(AUTO_CHECK_MS, self._auto_tick)

    def _fit_outer_edges(self) -> None:
        """把標題列與邊框的厚度扣掉，讓**看得到的邊界**落在 3%~87% / 3%~97%。

        外框有多厚只有視窗實際開出來之後才量得到，所以這一步必須在
        `update_idletasks()` 之後做，而且只做一次。
        """
        try:
            self.root.update_idletasks()
            outer_w = self.root.winfo_width()
            outer_h = self.root.winfo_height()
            # winfo_rootx/y 是內容區的螢幕座標，winfo_x/y 是外框的
            frame_w = max(0, self.root.winfo_rootx() - self.root.winfo_x()) * 2
            frame_h = max(0, self.root.winfo_rooty() - self.root.winfo_y()) + frame_w // 2
            if frame_w == 0 and frame_h == 0:
                return
            fixed = shrink_for_frame(self._box, frame_w, frame_h)
            self.root.geometry(fixed.as_geometry())
        except tk.TclError:
            pass  # 量不到就維持原本的尺寸，不值得為了幾個 pixel 讓視窗開不起來

    # ---------------- 版面 ----------------

    def _make_tree(self, parent) -> bs.Treeview:
        cols = [c[0] for c in COLUMNS]
        tree = bs.Treeview(parent, columns=cols, show="headings")
        for name, title, width in COLUMNS:
            tree.heading(name, text=title)
            tree.column(name, width=width, anchor="w")
        vs = bs.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill=Y)
        return tree

    def _current_key(self) -> str:
        idx = self.nb.index(self.nb.select()) if self.nb.tabs() else 0
        return TAB_TITLES[idx][0]

    def _fill(self, key: str) -> None:
        tree = self.trees[key]
        tree.delete(*tree.get_children())
        for r in self.presenter.load(key):
            tree.insert("", "end", values=(
                r.label, r.value or "—", r.data_date or "—", r.freq, r.note,
            ))

    def _reload_current(self) -> None:
        if self._closing:
            return
        self._fill(self._current_key())
        self.status.config(text=self.presenter.status())

    def _reload_all(self) -> None:
        for key, _ in TAB_TITLES:
            self._fill(key)
        self.status.config(text=self.presenter.status())

    # ---------------- 更新：背景執行緒 + queue ----------------

    def _schedule(self, ms: int, fn) -> None:
        """排一個 after，並記住 id —— 關窗時要把它們全部取消。"""
        if self._closing:
            return
        self._after_ids.add(self.root.after(ms, fn))

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _start(self, job, busy_text: str) -> None:
        """把 job 丟到背景執行緒跑，結果走 queue 回來。"""
        if self._busy():
            return  # 已經在跑了，不要疊第二個
        self.btn.config(state="disabled", text=busy_text)
        self.status.config(text=f"{busy_text}，正在打網路…")

        def work() -> None:
            # **這裡不准碰任何 widget** —— 結果一律走 queue 回主執行緒
            try:
                self._result.put(("ok", job()))
            except Exception as exc:  # noqa: BLE001
                self._result.put(("error", exc))

        self._worker = threading.Thread(target=work, daemon=True,
                                        name="barometer-refresh")
        self._worker.start()
        self._schedule(POLL_MS, self._poll)

    def _on_force(self) -> None:
        """「強制重抓」：忽略快取，真的重新掃一次有沒有更新。"""
        self._start(self.presenter.force_refresh, "強制重抓中…")

    def _auto_tick(self) -> None:
        """每 10 分鐘檢查一次有沒有序列到期。

        **檢查本身不打網路** —— 它只讀本機快取的資料日期，跟各序列自己的
        公布頻率比。真的有東西到期才會叫 auto_refresh() 出去抓。
        """
        if self._closing:
            return
        self._refresh_auto_label()
        if self.presenter.due_keys() and not self._busy():
            self._start(self.presenter.auto_refresh, "自動更新中…")
        self._schedule(AUTO_CHECK_MS, self._auto_tick)

    def _refresh_auto_label(self) -> None:
        self.auto_label.config(text=f"自動更新：{self.presenter.due_summary()}")

    def _poll(self) -> None:
        try:
            kind, payload = self._result.get_nowait()
        except queue.Empty:
            self._schedule(POLL_MS, self._poll)
            return

        self._reload_all()
        self._refresh_auto_label()
        if kind == "error":
            self.status.config(text=f"更新失敗，畫面維持快取：{payload}")
        elif not payload.ok:
            # 失敗不清空畫面 —— 舊值留著，狀態列說明停在哪裡
            self.status.config(text=payload.message)
        self.btn.config(state="normal", text="強制重抓（忽略快取）")

    # ---------------- 關窗 ----------------

    def on_close(self) -> None:
        """攔下關窗，把背景的東西收乾淨再 destroy。

        順序不能換：先取消 after（不然 destroy 之後那些 callback 會炸
        `invalid command name`），再等執行緒，最後才 destroy。
        """
        busy = self._worker is not None and self._worker.is_alive()
        if busy and not messagebox.askyesno(
            "更新還沒跑完",
            "正在抓資料，現在關掉的話這一輪會中斷（已經寫進資料庫的不受影響）。要關嗎？",
            parent=self.root,
        ):
            return

        self._closing = True
        for aid in self._after_ids:
            try:
                self.root.after_cancel(aid)
            except tk.TclError:
                pass
        self._after_ids.clear()

        if busy and self._worker is not None:
            # daemon 執行緒，join 不過也不會卡住行程結束
            self._worker.join(timeout=JOIN_TIMEOUT_S)

        self.root.destroy()
