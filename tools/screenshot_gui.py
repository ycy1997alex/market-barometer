"""Capture every desktop tab in a separate GUI process for end-to-end QA.

Usage: python tools/screenshot_gui.py [--site market|research]
Images and the run log stay under STOCKDATA_ROOT/build/gui_qa, outside git.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import traceback
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
REPOS = REPO.parent
PYTHONPATH = [REPOS / "market-barometer" / "src", REPOS / "stock-research" / "src"]


def capture(site: str, output: Path) -> int:
    import ttkbootstrap as bs
    from PIL import ImageGrab
    from barometer import config
    from barometer.storage.sqlite_repo import SqliteRepo

    if site == "market":
        from barometer.app import main as app
        from barometer.app.presenters.dashboard import DashboardPresenter
        from barometer.app.views.dashboard import DashboardWindow, TAB_TITLES
        make_view = lambda root, repo: DashboardWindow(root, DashboardPresenter(repo, app._refresher))
    else:
        from research.app import main as app
        from research.app.presenters.dashboard import StockPresenter, TAB_TITLES
        from research.app.views.dashboard import StockDashboardWindow
        make_view = lambda root, repo: StockDashboardWindow(root, StockPresenter(repo))

    errors: list[str] = []
    saved: list[str] = []
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    app._set_taskbar_identity()
    scale = app._enable_dpi_awareness()
    root = bs.Window(themename=app.THEME, iconphoto=None)
    if scale != 1.0:
        root.tk.call("tk", "scaling", scale * 96 / 72)
    app._apply_icon(root)
    root.attributes("-topmost", True)

    def callback_error(kind, value, tb):
        errors.append("".join(traceback.format_exception(kind, value, tb)))
        root.after_idle(root.destroy)

    root.report_callback_exception = callback_error
    try:
        view = make_view(root, repo)

        def finish():
            try:
                view.on_close()
            except Exception:
                root.destroy()

        def snapshot(index: int):
            try:
                if index == len(TAB_TITLES):
                    finish()
                    return
                key, title = TAB_TITLES[index]
                view.nb.select(index)
                root.update_idletasks()
                root.lift()
                root.attributes("-topmost", True)

                def take():
                    x, y = root.winfo_rootx(), root.winfo_rooty()
                    width, height = root.winfo_width(), root.winfo_height()
                    if width < 400 or height < 300:
                        raise RuntimeError(f"Window not rendered: {width}x{height}")
                    path = output / f"{index + 1:02d}_{key}.png"
                    ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True).save(path)
                    saved.append(str(path))
                    print(f"captured {title}: {path}", flush=True)
                    root.after(350, lambda: snapshot(index + 1))

                root.after(450, take)
            except Exception as exc:
                callback_error(type(exc), exc, exc.__traceback__)

        def poll_ready(attempt: int = 0):
            try:
                if root.winfo_viewable() and len(view.nb.tabs()) == len(TAB_TITLES):
                    snapshot(0)
                    return
                if attempt >= 60:
                    raise TimeoutError("GUI tabs did not become visible within 12 seconds")
                root.after(200, lambda: poll_ready(attempt + 1))
            except Exception as exc:
                callback_error(type(exc), exc, exc.__traceback__)

        root.after(200, poll_ready)
        root.after(20000, lambda: callback_error(TimeoutError, TimeoutError("GUI capture timed out"), None)
                   if len(saved) != len(TAB_TITLES) else None)
        root.mainloop()
    finally:
        repo.close()

    if errors or len(saved) != len(TAB_TITLES):
        for error in errors:
            print(error, file=sys.stderr)
        print(f"Captured {len(saved)}/{len(TAB_TITLES)} tabs", file=sys.stderr)
        return 1
    print(f"Zero callback exceptions; captured {len(saved)} tabs", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=("market", "research"), default="market")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = Path(os.environ.get("STOCKDATA_ROOT") or r"D:\Repo\_stockdata")
    output = args.output or root / "build" / "gui_qa" / f"{args.site}_{dt.datetime.now():%Y%m%d_%H%M%S}"
    output.mkdir(parents=True, exist_ok=True)
    if args.child:
        return capture(args.site, output)

    environment = os.environ.copy()
    environment["STOCKDATA_ROOT"] = str(root)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in PYTHONPATH)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", "--site", args.site,
         "--output", str(output)],
        cwd=REPOS / ("market-barometer" if args.site == "market" else "stock-research"),
        env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    (output / "qa.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout, end="")
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
    print(f"QA artifacts: {output}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
