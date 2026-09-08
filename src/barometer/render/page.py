"""明文 HTML（ToDo §3.4、§9 Day 25 第 3 項、Day 27 第 3 項）。

產出是一份**自足**的 HTML —— 沒有外部字型、沒有 CDN、沒有圖片。它最後會被
塞進解鎖殼的 `<iframe srcdoc>` 裡，任何外部相依在那裡都只會變成破圖。

**這一層是表現層，不得 import `storage/` 或 `datasources/`**
（tests/test_layer_boundary.py 用 AST 掃描守著）。所以它只認 Row / Tab 這兩個
自己的 view model，資料怎麼來的它不知道。

---

**這支檔案最重要的一個設計決定：時間有兩種，不能混成一個。**

    最後一次**抓取**  管線什麼時候跑的  →  整頁一個，顯示在標頭
    **資料日期**      這條序列的值屬於哪一天  →  每一列各自一個

實測的結果是 24 項指標有 9 種資料日期：央行重貼現率停在 2024-03-22、
國發會是 2026-07、CPI 是 2026-07-01、台灣 GDP 是 2026Q2、美債利差是昨天。
管線 18:23 跑過，不代表 CPI 是 18:23 的數字 —— 它停在 7 月，而且下次要等
下個月。所以印一行「資料更新時間：2026-09-07 18:23」是假的。

**顯示執行時間可以，把它講成資料日期不行。** 標頭那一行明寫它是「最後一次
抓取」，並且附一句「不是任何一條序列的資料日期」；日期仍然掛在每一列上。
這件事寫成了測試（test_page_render.py），因為「順手把兩個時間合成一個」
是很自然的衝動。

---

§2.1：`enforce_lint=True` 時，產出含行動字眼就讓發布失敗。
market-barometer 一律開，stock-research 一律關 —— 同一支 render 兩種用法。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from barometer.render import lint, svg


@dataclass(frozen=True, slots=True)
class Row:
    """一列指標。`data_date` 是**這一列自己的**資料日期，不是抓取時間。"""

    label: str
    value: str | None
    data_date: str | None
    freq: str = "每日"
    series: list[tuple[str, float | None]] = field(default_factory=list)
    note: str = ""
    change: str | None = None


@dataclass(frozen=True, slots=True)
class Tab:
    key: str
    title: str
    rows: list[Row] = field(default_factory=list)
    intro: str = ""


_STYLE = """
:root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--fg:#e6e8ee;
      --muted:#8b93a7;--accent:#5b8def;--warn:#e0a44c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font-family:"Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
     font-size:14px;line-height:1.6}
.wrap{max-width:980px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}
.tagline{color:var(--muted);font-size:12.5px;margin:0 0 6px}
.fetched{color:var(--muted);font-size:12px;margin:0 0 16px}
.fetched time{color:var(--fg);font-variant-numeric:tabular-nums}
.fetched .note{display:inline;margin-left:6px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px}
nav button{background:var(--panel);border:1px solid var(--line);color:var(--muted);
           padding:7px 13px;border-radius:999px;font-size:13px;cursor:pointer}
nav button[aria-selected=true]{border-color:var(--accent);color:var(--fg)}
section[hidden]{display:none}
.intro{color:var(--muted);font-size:12.5px;margin:0 0 14px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);
      vertical-align:middle}
th{color:var(--muted);font-weight:400;font-size:12px}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.date{color:var(--muted);font-size:12px;white-space:nowrap}
.note{color:var(--muted);font-size:11.5px;display:block;margin-top:2px}
.spark .line{stroke:var(--accent);stroke-width:1.4;fill:none}
.spark .pt{fill:var(--accent)}
.spark .no-data{fill:var(--muted);font-size:11px}
.meter .track{fill:var(--line)}.meter .fill{fill:var(--accent)}
.meter .knob{fill:var(--fg)}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);
       color:var(--muted);font-size:11.5px;line-height:1.9}
.scroll{overflow-x:auto}
"""

_SCRIPT = """
document.querySelectorAll('nav button').forEach(b=>{
  b.addEventListener('click',()=>{
    document.querySelectorAll('nav button').forEach(x=>
      x.setAttribute('aria-selected', String(x===b)));
    document.querySelectorAll('section[data-tab]').forEach(s=>
      s.hidden = s.dataset.tab !== b.dataset.tab);
  });
});
"""

# 每一頁固定掛的收尾（§13）。財經題材的硬性要求。
DEFAULT_FOOTER = (
    "單次執行的觀察一律標為<strong>定性觀察</strong>，不是統計證據。",
    "未經驗證的事實標「待確認」。",
    "<strong>本頁不構成投資建議。</strong>",
)

# 標頭那一行的措辭。刻意不用「資料更新時間」這種會被誤讀成資料日期的說法。
FETCH_LABEL = "最後一次抓取"
FETCH_CAVEAT = "（管線執行時間，不是各序列的資料日期）"

# 只有真的顯示了抓取時間，才在頁尾解釋它。沒有那一行就不必解釋一個不存在的東西。
FETCH_FOOTNOTE = (
    f"標頭的「{FETCH_LABEL}」是<strong>管線執行</strong>的時間，"
    "<strong>不是</strong>任何一條序列的資料日期 —— 每一列的資料日期各自標在該列。"
)


def _row_html(r: Row) -> str:
    value = escape(r.value) if r.value else "—"
    change = f'<span class="note">{escape(r.change)}</span>' if r.change else ""
    note = f'<span class="note">{escape(r.note)}</span>' if r.note else ""
    spark = svg.sparkline(r.series, freq=r.freq, label=r.label) if r.series else ""
    return (
        "<tr>"
        f"<td>{escape(r.label)}{note}</td>"
        f'<td class="num">{value}{change}</td>'
        f"<td>{spark}</td>"
        f'<td class="date">{escape(r.data_date or "—")}'
        f'<span class="note">{escape(r.freq)}</span></td>'
        "</tr>"
    )


def _tab_html(t: Tab, active: bool) -> str:
    intro = f'<p class="intro">{escape(t.intro)}</p>' if t.intro else ""
    rows = "".join(_row_html(r) for r in t.rows)
    hidden = "" if active else " hidden"
    return (
        f'<section data-tab="{escape(t.key)}"{hidden}>'
        f"{intro}"
        f'<div class="scroll"><table>'
        f"<thead><tr><th>指標</th><th>最新值</th><th>走勢</th>"
        f"<th>資料日期／頻率</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        f"</section>"
    )


def render(
    tabs: list[Tab],
    title: str,
    tagline: str = "",
    footer_notes: tuple[str, ...] = DEFAULT_FOOTER,
    enforce_lint: bool = False,
    last_run_at: str | None = None,
) -> str:
    """產出明文 HTML。

    `enforce_lint=True` 時掃描產出，命中 §2.1 的行動字眼就丟 OutputLintError
    讓發布失敗 —— **不是印個警告就放行**。這是輸出層擋住，不是靠自律。
    """
    nav = "".join(
        f'<button data-tab="{escape(t.key)}" '
        f'aria-selected="{str(i == 0).lower()}">{escape(t.title)}</button>'
        for i, t in enumerate(tabs)
    )
    sections = "".join(_tab_html(t, i == 0) for i, t in enumerate(tabs))

    # 沒有執行紀錄就整行不顯示 —— 寧可不寫，也不要瞎編一個時間。
    # 註腳跟著那一行一起出現或一起消失，不解釋一個不存在的東西。
    fetched = (
        f'<p class="fetched">{FETCH_LABEL}：<time>{escape(last_run_at)}</time>'
        f'<span class="note">{FETCH_CAVEAT}</span></p>'
        if last_run_at else ""
    )
    notes = ((FETCH_FOOTNOTE,) + tuple(footer_notes)) if last_run_at \
        else tuple(footer_notes)
    footer = "".join(f"<div>{n}</div>" for n in notes)

    html = (
        "<!DOCTYPE html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>"
        f'<div class="wrap"><h1>{escape(title)}</h1>'
        + (f'<p class="tagline">{escape(tagline)}</p>' if tagline else "")
        + fetched
        + f"<nav>{nav}</nav>{sections}"
        f"<footer>{footer}</footer></div>"
        f"<script>{_SCRIPT}</script></body></html>"
    )

    if enforce_lint:
        lint.assert_clean(html)
    return html
