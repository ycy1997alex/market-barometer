"""輸出層 lint（ToDo §2.1、§12 紅線第 6 條）。

**market-barometer 完全不產生買賣建議。這條線畫在內容本身，不畫在鎖上。**

0050 與 SPY 是具名的可交易標的，提供它們的買賣與短中長線建議落在投顧業務
範圍。頁面加密降低了「對不特定人」的成分，但**降低不等於消除** ——
密碼會印在文章上給讀者用，而讀者是誰並不特定。

所以輸出層要擋住，不要靠自律：掃描產出的明文 HTML，命中就讓發布失敗。

⚠️ 這支 lint 只給 **market-barometer** 用。stock-research 那一側可以有建議。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# §2.1 右欄：不可以出現在 market-barometer 輸出裡的字眼
ACTION_WORDS: tuple[str, ...] = (
    "買進", "賣出", "加碼", "減碼", "觀望", "進場", "出場",
    "買入", "賣掉", "布局", "停損", "停利", "抄底", "追高",
)

# 「把分數翻譯成動作」的欄位名稱
ADVICE_LABELS: tuple[str, ...] = (
    "短線建議", "中線建議", "長線建議", "操作建議", "投資建議",
    "買賣建議", "建議動作",
)

# 規則陳述：「分數低於 N 應如何」
RULE_PATTERNS: tuple[str, ...] = (
    r"分數(低|高)於\s*\d+\s*[應該宜]",
    r"[低高]於\s*\d+\s*分.{0,6}(應|該|宜|建議)",
)

# 白名單：這些是**在講規則本身**，不是在給建議。
# 例如 README 與說明段落會寫「不產生買賣建議」「完全不放買賣建議」。
_NEGATION_CONTEXT = (
    "不產生", "不放", "不含", "不做", "沒有", "不提供", "不會有",
    "刻意不", "完全不", "不得", "不可以", "禁止",
    # §13 規定每一頁與每一篇都要掛「本頁不構成投資建議」，而「投資建議」正好
    # 是 ADVICE_LABELS 裡的字。兩條硬規定會在頁尾撞在一起 —— 少了「不構成」，
    # 這支 lint 會擋掉它自己要求掛上的那句免責聲明。
    "不構成",
)
_CONTEXT_WINDOW = 12  # 命中處往前看幾個字


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    term: str
    position: int
    excerpt: str


def _is_negated(text: str, pos: int) -> bool:
    """命中處前面若有否定語，視為在描述規則而不是在給建議。"""
    start = max(0, pos - _CONTEXT_WINDOW)
    window = text[start:pos]
    return any(neg in window for neg in _NEGATION_CONTEXT)


def lint(html: str) -> list[Finding]:
    """回傳所有命中。空 list = 通過。"""
    findings: list[Finding] = []

    for term in ACTION_WORDS + ADVICE_LABELS:
        kind = "action_word" if term in ACTION_WORDS else "advice_label"
        for m in re.finditer(re.escape(term), html):
            if _is_negated(html, m.start()):
                continue
            findings.append(
                Finding(
                    kind=kind,
                    term=term,
                    position=m.start(),
                    excerpt=_excerpt(html, m.start(), len(term)),
                )
            )

    for pat in RULE_PATTERNS:
        for m in re.finditer(pat, html):
            findings.append(
                Finding(
                    kind="rule_statement",
                    term=m.group(0),
                    position=m.start(),
                    excerpt=_excerpt(html, m.start(), len(m.group(0))),
                )
            )

    return findings


def _excerpt(text: str, pos: int, length: int, pad: int = 25) -> str:
    start = max(0, pos - pad)
    end = min(len(text), pos + length + pad)
    return text[start:end].replace("\n", " ")


class OutputLintError(RuntimeError):
    """發布中止 —— 明文 HTML 含有行動字眼（§2.1）。"""


def assert_clean(html: str) -> None:
    """發布前呼叫。命中就讓發布失敗，不是印個警告就放行。"""
    findings = lint(html)
    if not findings:
        return
    lines = [
        f"  [{f.kind}] 「{f.term}」@{f.position}  …{f.excerpt}…"
        for f in findings[:20]
    ]
    more = f"\n  （另有 {len(findings) - 20} 處）" if len(findings) > 20 else ""
    raise OutputLintError(
        "market-barometer 的輸出不得含買賣建議或行動字眼（§2.1）：\n"
        + "\n".join(lines)
        + more
    )
