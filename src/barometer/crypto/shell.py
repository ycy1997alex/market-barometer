"""把密文塞進解鎖殼（ToDo §5.3）。

殼是 `shell.html`，四個佔位字串用**字串取代**填 —— 不用 `str.format`、不用
任何模板引擎，因為殼裡有大量 JS 的 `{}`，格式化字串會在那裡爆掉，而且爆得
很難查。

輸出是一份自足的 HTML：內嵌 CSS、內嵌 JS、零外部相依。
"""
from __future__ import annotations

import json
from pathlib import Path

_SHELL = Path(__file__).with_name("shell.html")


def wrap(
    envelope_json: dict,
    title: str,
    mode: str = "one",
    telemetry_url: str | None = None,
) -> str:
    """產出可以直接放進 `docs/index.html` 的密文頁面。

    `telemetry_url` 是 §5.6 的選配 —— 給 None 就完全不送，殼裡也不會出現
    那一行揭露文字。**沒有它整套照樣運作。**
    """
    if mode not in ("one", "two"):
        raise ValueError(f"mode 只能是 one 或 two，收到 {mode!r}")

    html = _SHELL.read_text(encoding="utf-8")
    html = html.replace("__PAYLOAD__", json.dumps(envelope_json, separators=(",", ":")))
    html = html.replace("__MODE__", mode)
    html = html.replace("__TELEMETRY__", json.dumps(telemetry_url))
    html = html.replace("__TITLE__", title)

    if "__PAYLOAD__" in html or "__MODE__" in html:
        raise RuntimeError("殼的佔位字串沒有被填完 —— 發布中止")
    return html
