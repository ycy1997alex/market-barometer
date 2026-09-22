"""第八批 8-9：算術陳述的總結句 + lint 的防護網。

§7.3 的紅線：總結句**只能是算術**。
  可以：「世界層 25 項中有 3 項警示」「VIX 28.0，高於 25 的警示門檻」
  不行：「偏向謹慎」「風險偏高，宜留意」「環境不利」—— 那些是處置描述不是狀態描述。

§7.3 的殘留風險也在這裡收掉：`lint.py` 原本沒有這些詞的字典，
所以六個月後有人手改一行文案不會被擋。現在會。
"""
from __future__ import annotations

from barometer.domain import summary
from barometer.render import lint


def test_counts_alerts_and_names_them():
    text = summary.layer_sentence("世界層", {"vix": False, "oil_curve": True, "copper": True},
                                  {"oil_curve": "原油近遠月曲線", "copper": "工業金屬需求"})
    assert text == "世界層 3 項中有 2 項警示：原油近遠月曲線、工業金屬需求。"


def test_no_alerts_still_states_the_arithmetic():
    text = summary.layer_sentence("台灣層", {"sox": False, "usdtwd": False}, {})
    assert text == "台灣層 2 項中有 0 項警示。"


def test_an_empty_layer_says_so_instead_of_dividing():
    assert summary.layer_sentence("世界層", {}, {}) == "世界層沒有任何可用指標。"


def test_reading_sentence_states_value_against_threshold():
    assert summary.reading_sentence("VIX", 28.0, 25.0, "{:.1f}") == "VIX 28.0，高於 25 的警示門檻。"
    assert summary.reading_sentence("VIX", 18.0, 25.0, "{:.1f}") == "VIX 18.0，低於 25 的警示門檻。"


def test_generated_sentences_carry_no_judgement_words():
    text = summary.layer_sentence("世界層", {"a": True}, {"a": "原油近遠月曲線"})
    assert not lint.lint(text)


# ---------------- lint 的新字典 ----------------

def test_judgement_words_are_now_blocked():
    for phrase in ("偏向謹慎", "風險偏高，宜留意", "環境不利", "對股市有利"):
        assert lint.lint(phrase), phrase


def test_rate_words_are_not_false_positives():
    """「有利」「不利」是子字串陷阱：只有利率動了、不利率先反應 —— 都不是判斷。"""
    assert not lint.lint("這個月只有利率動了")
    assert not lint.lint("目前不利率先變動")


def test_existing_negation_whitelist_still_works():
    assert not lint.lint("本頁不構成投資建議")
    assert not lint.lint("這個系統不產生買賣建議")
