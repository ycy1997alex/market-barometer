r"""發布：明文 → 加密 → 寫 docs/（ToDo §3.4、§5.4、§9 Day 27 第 3 項）。

**三條紅線都在這支腳本上**：

  1. 明文只寫進 `STOCKDATA_ROOT\build\`，**永遠不進 git**（§5.4 第 2 條）
  2. 每次發布重新產生 salt / IV / CEK —— 由 crypto/envelope.py 保證，
     這裡連一個常數都不傳（§5.4 第 1 條）
  3. 密碼不在這支腳本裡，從 secrets/publish.json 讀（§5.1）

還有 §2.1：產出的明文先過 lint，命中行動字眼就**讓發布失敗**，不是印警告。

用法：
    python tools/publish.py            # 產生並寫 docs/
    python tools/publish.py --dry-run  # 只產明文與密文，不動 docs/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.crypto import credentials, envelope, shell  # noqa: E402
from barometer.pipeline import build_page, publish_gate  # noqa: E402
from barometer.pipeline.runlog import RunLog  # noqa: E402
from barometer.render import page  # noqa: E402

SITE = credentials.MARKET_BAROMETER
TITLE = "market-barometer"
TAGLINE = "世界與台灣總經、台美大盤與 ETF 的評分儀表，只出分數，不出建議"

DOCS = _HERE / "docs"


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    force = "--force" in argv
    log = RunLog(task="publish_mb")
    config.ensure_dirs()

    # --- 1. 明文 ---
    tabs = build_page.build_tabs()
    # enforce_lint=True：market-barometer 不得出現任何行動字眼（§2.1）
    html = page.render(tabs, title=TITLE, tagline=TAGLINE, enforce_lint=True,
                       last_run_at=build_page.last_fetch_at())

    plain_path = config.build_dir() / "market-barometer.plain.html"
    plain_path.write_text(html, encoding="utf-8")
    print(f"明文  {plain_path}（{len(html):,} 字元）")
    print("      明文只落在 build/，在兩個 repo 之外 —— 永遠不進 git")

    rows = sum(len(t.rows) for t in tabs)
    log.set_count("tabs", len(tabs))
    log.set_count("rows", rows)

    # --- 1.5 閘門：資料沒變就不動 docs/（§1 第 6 條、§9 Day 28 第 3 項） ---
    # 判斷放在封裝**之前** —— 密文每次都不一樣是刻意的（§5.4 第 1 條），
    # 拿它去比會每天多一筆只有隨機數不同的 commit。
    gate = publish_gate.Gate(config.build_dir() / "market-barometer.gate.json")
    decision = gate.should_publish(html, force=force)
    print(f"閘門  {decision.reason}")
    if not decision.publish and not dry:
        log.note(decision.reason)
        log.set_count("skipped_unchanged", 1)
        log.finish("ok")
        log.append()
        print("\n沒有變，docs/ 一個字都沒動 —— 也就不會有 commit。")
        return 0

    # --- 2. 加密 ---
    creds = credentials.load(SITE)
    env = envelope.seal(html, creds.materials, slot_ids=creds.slot_ids)
    print(f"密文  pub_id={env['pub_id']}  {len(creds)} 組憑證  "
          f"PBKDF2 {env['kdf']['iter']:,} 次")

    sealed = shell.wrap(env, title=TITLE, mode=creds.mode)
    log.set_count("credentials", len(creds))
    log.set_count("pub_id", env["pub_id"])

    # --- 3. 自我驗收：每一組憑證都要真的解得開（§5.5） ---
    for material, slot in zip(creds.materials, creds.slot_ids):
        got = envelope.open_envelope(env, material)
        assert got == html, "解出來的明文跟原本的不一樣"
        assert envelope.which_slot(env, material) == slot, "槽位代號錯位了"
    print(f"驗收  {len(creds)} 組憑證逐一解開、槽位代號沒有錯位")

    if dry:
        out = config.build_dir() / "market-barometer.sealed.html"
        out.write_text(sealed, encoding="utf-8")
        print(f"\n--dry-run：密文寫到 {out}，docs/ 沒有動")
        log.finish("ok")
        log.append()
        return 0

    # --- 4. 寫 docs/（只有密文） ---
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(sealed, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"\n寫出  {DOCS / 'index.html'}（{len(sealed):,} 字元）")

    # pub_id 留一份在本機，Day 28 要比對「資料沒變就不 commit」
    gate.record(html)
    (config.build_dir() / "market-barometer.pubid.json").write_text(
        json.dumps({"pub_id": env["pub_id"], "rows": rows}, ensure_ascii=False),
        encoding="utf-8",
    )

    log.finish("ok")
    log.append()
    print("\n下一步：跑 tools/verify_publish.py 過 §5.5 的七項驗收")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
