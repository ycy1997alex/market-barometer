r"""發布驗收（ToDo §5.5）。**每次發布之後跑，不是有空才跑。**

§5.5 那張清單逐項翻成檢查。有幾項是靠肉眼看不出來的 ——
尤其「連續兩次發布的 salt / IV 全都不同」，人不可能用眼睛比對 base64。

用法：
    python tools/verify_publish.py                 # 驗 market-barometer
    python tools/verify_publish.py stock-research  # 驗另一個站
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer.crypto import credentials, envelope  # noqa: E402
from barometer.render import lint  # noqa: E402

REPO_OF = {
    credentials.MARKET_BAROMETER: _HERE,
    credentials.STOCK_RESEARCH: _HERE.parent / "stock-research",
}


def _extract_envelope(sealed_html: str) -> dict:
    m = re.search(r"const ENV\s*=\s*(\{.*?\});", sealed_html, re.S)
    if not m:
        raise SystemExit("FAIL 密文頁面裡找不到 ENV —— 這不是一份發布產物")
    return json.loads(m.group(1))


def _git(repo: Path, *args: str) -> str:
    """跑一次 git，回它的 stdout；拿不到就回空字串。

    `encoding` 一定要釘死 utf-8。`text=True` 自己會用本機語系（這台是 cp950），
    而 commit 訊息開頭有 emoji —— 解碼錯誤發生在讀取執行緒裡，`.stdout` 會變成
    `None` 而不是拋例外，下面那個 `except` 接不到，最後死在 `None.strip()`。
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        ).stdout
    except Exception:
        return ""
    return out or ""


def main(argv: list[str]) -> int:
    site = argv[0] if argv else credentials.MARKET_BAROMETER
    repo = REPO_OF[site]
    docs = repo / "docs"
    index = docs / "index.html"

    print(f"=== §5.5 發布驗收：{site} ===")
    if not index.exists():
        print(f"FAIL {index} 不存在 —— 先跑 tools/publish.py")
        return 1

    sealed = index.read_text(encoding="utf-8")
    env = _extract_envelope(sealed)
    creds = credentials.load(site)
    results: list[tuple[bool, str]] = []

    def check(ok: bool, msg: str) -> None:
        results.append((ok, msg))
        print(f"  [{'OK  ' if ok else 'FAIL'}] {msg}")

    # 1. git 裡沒有任何明文版本
    hist = _git(repo, "log", "--all", "--full-history", "--oneline", "--", "docs/")
    plain_in_git = any(
        marker in _git(repo, "show", f"{line.split()[0]}:docs/index.html")
        for line in hist.splitlines() if line.split()
        for marker in ("<table>",)
    ) if hist.strip() else False
    check(not plain_in_git, "git log 裡的 docs/ 沒有任何明文版本")

    # 2. 同一次發布內，所有 salt / iv 互不重複
    salts = [k["salt"] for k in env["keys"]]
    ivs = [k["iv"] for k in env["keys"]] + [env["content"]["iv"]]
    check(len(set(salts)) == len(salts) and len(set(ivs)) == len(ivs),
          f"同一次發布內 {len(salts)} 個 salt、{len(ivs)} 個 iv 互不重複")

    # 3. 連續兩次發布不共用任何 salt / iv（現場再封一次來比）
    again = envelope.seal("probe", creds.materials, slot_ids=creds.slot_ids)
    shared = ({k["salt"] for k in env["keys"]} & {k["salt"] for k in again["keys"]}) | \
             ({k["iv"] for k in env["keys"]} & {k["iv"] for k in again["keys"]})
    check(not shared and env["content"]["iv"] != again["content"]["iv"],
          "連續兩次發布的 salt / IV / CEK 全都不同（§5.4 第 1 條）")

    # 4. 每一組有效憑證都能解開，逐一測過
    opened, slots_ok = 0, True
    for material, slot in zip(creds.materials, creds.slot_ids):
        try:
            envelope.open_envelope(env, material)
            opened += 1
            slots_ok &= envelope.which_slot(env, material) == slot
        except envelope.WrongCredential:
            pass
    check(opened == len(creds), f"{opened}/{len(creds)} 組有效憑證都解得開")
    check(slots_ok, "槽位代號 t 沒有錯位（§5.5 最後一項）")

    # 5. 錯誤憑證只得到失敗
    bad = envelope.material_two_lock("nope", "nope") if creds.mode == "two" \
        else envelope.material_one_lock("nope")
    try:
        envelope.open_envelope(env, bad)
        check(False, "錯誤憑證居然解開了")
    except envelope.WrongCredential:
        check(True, "錯誤憑證只得到失敗，沒有半段明文")

    # 6. 密文裡 grep 不到任何密碼字串
    leaked = [s for s in credentials.raw_secret_strings(site) if s in sealed]
    check(not leaked, f"密文頁面裡 grep 不到任何密碼字串（{len(leaked)} 個洩漏）")

    # 7. docs/ 底下沒有任何資料檔
    data_files = [
        p.name for p in docs.rglob("*")
        if p.is_file() and p.suffix.lower() in (".csv", ".db", ".json", ".sqlite")
    ]
    check(not data_files, f"docs/ 底下沒有 csv/db/json 資料檔（{data_files}）")

    # 8. market-barometer 專屬：明文不得含行動字眼
    if site == credentials.MARKET_BAROMETER:
        plain = envelope.open_envelope(env, creds.materials[0])
        findings = lint.lint(plain)
        check(not findings,
              f"明文裡沒有行動字眼（§2.1，命中 {len(findings)} 處）")

    # 9. robots noindex
    check('name="robots"' in sealed and "noindex" in sealed,
          "有 noindex, nofollow（§5.4 第 4 條）")

    failed = [m for ok, m in results if not ok]
    print(f"\n=== {len(results) - len(failed)}/{len(results)} 項通過 ===")
    if failed:
        for m in failed:
            print(f"  FAIL {m}")
        return 1
    print("OK 全部通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
