"""總結句（ToDo §7.3、§9 第八批 8-9）。純函式、零 I/O。

**這裡只能產生算術陳述。** 可以數數、可以把值跟門檻比大小，不可以下判斷。

  可以：「世界層 25 項中有 3 項警示：原油近遠月曲線、…」
        「VIX 28.0，高於 25 的警示門檻」
  不行：「偏向謹慎」「風險偏高，宜留意」「環境不利」

⚠️ 為什麼這一段只能是算術：這個系統的分數是**量測**不是指示（§2.1）。
「4 項警示」是讀數，「風險偏高」是處置描述 —— 後者需要一個「多高算高」的標準，
而那個標準這裡沒有，寫出來就是憑空多發明一把尺。

`render/lint.py` 的 `JUDGEMENT_WORDS` 是這條規則的防護網：六個月後有人手改
一行文案，lint 會擋下來。
"""
from __future__ import annotations


def layer_sentence(layer_name: str, alerts: dict[str, bool],
                   names: dict[str, str]) -> str:
    """「<層> N 項中有 M 項警示：<逐項名稱>。」—— 數數，不解讀。"""
    if not alerts:
        return f"{layer_name}沒有任何可用指標。"
    hit = [key for key, value in alerts.items() if value]
    body = f"{layer_name} {len(alerts)} 項中有 {len(hit)} 項警示"
    if not hit:
        return body + "。"
    listed = "、".join(names.get(key, key) for key in hit)
    return f"{body}：{listed}。"


def reading_sentence(name: str, value: float, threshold: float, fmt: str) -> str:
    """「<名稱> <值>，高於／低於 <門檻> 的警示門檻。」"""
    side = "高於" if value > threshold else "低於"
    return f"{name} {fmt.format(value)}，{side} {threshold:g} 的警示門檻。"
