r"""額度盤點（ToDo §6、§9 Day 28 第 5 項）。

驗收：**「§6 那張表逐項重核一次；Actions 分鐘、Pages 體積與流量、repo 體積
成長率都有數字」**。

**額度是會被用完的東西。** 而且 Shioaji 超流量的後果不是報錯，是行情查詢
直接回空值 —— 程式會以為「那天沒資料」。所以這張表不是好心提供，是必要的。

這支腳本只讀本機能算得出來的東西（run log、repo 體積、資料層體積）。
Actions 分鐘與 Pages 流量要去 GitHub 看，那兩格印出「去哪裡查」而不是瞎猜
一個數字 —— **算不出來就說算不出來**。
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline.runlog import read_runs  # noqa: E402

MB = 1024 * 1024
SYMBOL_ALERT = 200
RAW_FILE_ALERT = 750
GIT_OBJECT_ALERT = 100_000
GIT_BYTES_ALERT = 500 * MB
SHIOAJI_LIMIT = 500 * MB
SHIOAJI_REMAINING_ALERT = 100 * MB


@dataclass(frozen=True)
class Capacity:
    symbols: int | None
    raw_files: int | None
    git_objects: int | None
    git_bytes: int | None
    alerts: tuple[str, ...]


def _git_object_stats(repo: Path) -> tuple[int, int] | None:
    if not (repo / ".git").exists():
        return None
    try:
        result = subprocess.run(["git", "-c", f"safe.directory={repo.resolve().as_posix()}",
                                 "-C", str(repo), "count-objects", "-v"],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        values = dict(line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line)
        return (int(values["count"]) + int(values["in-pack"]),
                (int(values["size"]) + int(values["size-pack"])) * 1024)
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError):
        return None


def capacity_snapshot(stock_repo: Path, root: Path, *, git_stats=_git_object_stats) -> Capacity:
    """Count the tracked universe, raw files and loose+packed Git objects."""
    override = root / "research_symbols.json"
    bundled = stock_repo / "src" / "research" / "symbols.json"
    universe = override if override.exists() else bundled
    try:
        symbols = len(json.loads(universe.read_text(encoding="utf-8"))["symbols"])
    except (OSError, ValueError, KeyError, TypeError):
        symbols = None
    raw = root / "price_raw"
    raw_files = sum(path.is_file() for path in raw.rglob("*")) if raw.exists() else None
    git = git_stats(stock_repo)
    objects, git_bytes = git if git is not None else (None, None)
    alerts = []
    if symbols is not None and symbols >= SYMBOL_ALERT:
        alerts.append(f"標的數 {symbols} 達 {SYMBOL_ALERT} 檔監控門檻")
    if raw_files is not None and raw_files > RAW_FILE_ALERT:
        alerts.append(f"price_raw 檔案 {raw_files} 超過 {RAW_FILE_ALERT} 檔監控門檻")
    if objects is not None and objects >= GIT_OBJECT_ALERT:
        alerts.append(f"git 物件 {objects} 達 {GIT_OBJECT_ALERT} 個監控門檻")
    if git_bytes is not None and git_bytes >= GIT_BYTES_ALERT:
        alerts.append(f"git 物件體積 {git_bytes / MB:.1f} MB 達 {GIT_BYTES_ALERT / MB:.0f} MB 監控門檻")
    return Capacity(symbols, raw_files, objects, git_bytes, tuple(alerts))


# 這幾個目錄被 .gitignore 擋著，算進「repo 體積」會嚴重誤導 ——
# dist/ 裡一個打包好的 exe 就 50 MB，但它一個位元組都不會進 git。
IGNORED_DIRS = {"build", "dist", ".git", "__pycache__", ".pytest_cache"}


def _dir_size(path: Path, skip_ignored: bool = False) -> int:
    total = 0
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        if skip_ignored and IGNORED_DIRS & set(f.relative_to(path).parts):
            continue
        total += f.stat().st_size
    return total


def _repo_size(repo: Path) -> tuple[int, int]:
    """(工作目錄不含 .git, .git 本身)。repo 體積成長率靠這兩個數字追。"""
    if not repo.exists():
        return 0, 0
    git = repo / ".git"
    return _dir_size(repo, skip_ignored=True), _dir_size(git) if git.exists() else 0


def latest_shioaji_remaining(runs) -> int | None:
    """run log 裡最近一次記到的 `remaining_bytes`。抓不到回 `None`，**不是 0**。

    ⚠️ 實際寫進 run log 的是巢狀的 `quota.shioaji_usage.remaining_bytes`
    （`tools/crosscheck_tw.py` 的 `log.quota.setdefault("shioaji_usage", usage)`）；
    這張表本來讀平的 `quota.shioaji_remaining_bytes`，那個 key **從來沒有人寫過**，
    所以天天都印「沒有記到」（回補批 R-5）。兩種都讀，舊格式不會因此看不見。
    """
    found: int | None = None
    for run in runs:
        quota = run.get("quota")
        if not isinstance(quota, dict):
            continue
        usage = quota.get("shioaji_usage")
        value = usage.get("remaining_bytes") if isinstance(usage, dict) else None
        if value is None:
            value = quota.get("shioaji_remaining_bytes")
        if isinstance(value, int):
            found = value
    return found


def shioaji_alert(remaining: int | None) -> str | None:
    """剩餘流量低於門檻才回一句話。**不知道不算告警** —— 那是上面那格的事。"""
    if remaining is None or remaining >= SHIOAJI_REMAINING_ALERT:
        return None
    return (f"Shioaji 只剩 {remaining / MB:.1f} MB，低於 {SHIOAJI_REMAINING_ALERT / MB:.0f} MB "
            "監控門檻（08:00 重置前不要再排重抓）")


def main() -> int:
    print("=== Day 28 第 5 項：額度盤點 ===")
    ym = dt.date.today().strftime("%Y-%m")
    runs = read_runs(ym)

    # ---- 各來源當月的請求數 ----
    per_source: Counter[str] = Counter()
    tasks: Counter[str] = Counter()
    for r in runs:
        tasks[r.get("task", "?")] += 1
        for src, n in (r.get("quota", {}).get("requests") or {}).items():
            per_source[src] += n

    print(f"\n--- {ym} 的 run log（{len(runs)} 筆） ---")
    for task, n in sorted(tasks.items(), key=lambda kv: -kv[1]):
        print(f"  {task:<20}{n:>4} 次")

    print(f"\n--- 各來源請求數（本月累計，只算有記進 quota 的那幾筆） ---")
    if per_source:
        for src, n in sorted(per_source.items(), key=lambda kv: -kv[1]):
            print(f"  {src:<12}{n:>6} 次")
    else:
        print("  （run log 裡沒有 quota.requests —— 舊格式的那幾筆）")

    # ---- Shioaji 剩餘流量 ----
    latest = latest_shioaji_remaining(runs)
    print("\n--- Shioaji 日流量（上限 500MB，08:00 重置） ---")
    if latest is None:
        print("  未取得 —— 本月的 run log 裡沒有任何一筆 usage")
        print("  ！這格空著就等於不知道離上限多遠 —— 超流量會回空值不會報錯（§6）")
    else:
        print(f"  最近一次記到的 remaining_bytes：{latest:,}"
              f"（約 {latest / MB:.1f} MB，用掉約 {SHIOAJI_LIMIT / MB - latest / MB:.1f} MB）")
        alert = shioaji_alert(latest)
        if alert:
            print(f"  ！{alert}")

    # ---- repo 與資料層體積 ----
    print("\n--- 體積 ---")
    for name in ("market-barometer", "stock-research"):
        repo = _HERE.parent / name
        work, git = _repo_size(repo)
        docs = _dir_size(repo / "docs") if (repo / "docs").exists() else 0
        print(f"  {name:<18}會進 git 的 {work / MB:>7.2f} MB"
              f"  .git {git / MB:>6.2f} MB  docs/ {docs / MB:>5.2f} MB")
    root = config.stockdata_root()
    print(f"  {'_stockdata':<18}{_dir_size(root) / MB:>7.2f} MB"
          f"（不在任何 repo 內 —— 這一塊永遠不會撐大 git）")

    capacity = capacity_snapshot(_HERE.parent / "stock-research", root)
    print("\n--- 大 N 容量監控（研究站） ---")
    for label, value in (("標的數", capacity.symbols),
                         ("price_raw 檔案數", capacity.raw_files),
                         ("git 物件總量", capacity.git_objects)):
        print(f"  {label}：{value if value is not None else '資料不足'}")
    print(f"  git 物件體積：{capacity.git_bytes / MB:.2f} MB"
          if capacity.git_bytes is not None else "  git 物件體積：資料不足")
    for alert in capacity.alerts:
        print(f"  告警：{alert}")
    if not capacity.alerts and None in (capacity.symbols, capacity.raw_files,
                                        capacity.git_objects, capacity.git_bytes):
        print("  部分資料不足，無法確認是否達監控門檻")
    elif not capacity.alerts:
        print("  未達監控門檻")

    # ---- docs/ 的成長率：Pages 每次部署的實際大小 ----
    print("\n--- GitHub Pages ---")
    for name in ("market-barometer", "stock-research"):
        docs = _HERE.parent / name / "docs"
        size = _dir_size(docs) if docs.exists() else 0
        print(f"  {name:<18}docs/ {size / MB:.2f} MB"
              f"（軟上限 1 GB／站，每月 100 GB 流量）")
    print("  一天一次部署、每次不到 0.1 MB → 一年約 20 MB，離上限很遠")

    # ---- 查不到的就說查不到 ----
    print("\n--- 這台機器算不出來的（要去 GitHub 看） ---")
    print("  Actions 分鐘：Settings → Billing → Actions（public repo 免費不計費）")
    print("  Pages 流量  ：repo → Insights → Traffic（只給 14 天）")
    print("  GitHub API 未認證額度：60 req/hr（§11 第 9 項標為待確認，這裡不代為確認）")

    # ---- §6 那張表逐項 ----
    print("\n--- §6 逐項重核 ---")
    table = [
        ("FRED", "無金鑰 30 req/min", "固定節流 1 秒/次，退避 3 秒、重試 1 次"),
        ("Shioaji", "日 500MB／10 秒 50 次", "只在每日對帳抓一次，記 remaining_bytes"),
        ("yfinance", "無官方數字", "批次間 sleep 1 秒，禁用 threads=True"),
        ("TWSE", "無官方數字", "間隔 ≥ 0.6 秒，(dataset, 日期) 整檔快取"),
        ("期交所", "無官方數字", "同 TWSE：≥ 0.6 秒 + 快取"),
        ("國發會/主計總處", "無公布", "同輪共用一次下載，記憶體快取 1 小時"),
        ("GitHub API", "未認證 60 req/hr（待確認）", "一次撈完"),
    ]
    for src, limit, rule in table:
        used = per_source.get(
            {"期交所": "taifex", "TWSE": "twse", "FRED": "fred",
             "yfinance": "yfinance", "Shioaji": "shioaji"}.get(src, src), 0
        )
        print(f"  {src:<16}{limit:<24}{rule}")
        if used:
            print(f"  {'':16}本月已用 {used} 次")

    print("\nOK 逐項重核完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
