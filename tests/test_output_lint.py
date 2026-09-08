"""§2.1 / §12 紅線第 6 條：輸出層擋住買賣建議，不靠自律。

「輸出層要擋住，不要靠自律：掃描產出的明文 HTML，命中上表右欄的字詞就讓
發布失敗（§5.5 驗收有這一項）。」
"""
from __future__ import annotations

import pytest

from barometer.render.lint import (
    OutputLintError,
    assert_clean,
    lint,
)


class TestAllowed:
    """§2.1 左欄：這些**可以**出現。"""

    @pytest.mark.parametrize("html", [
        "<p>目前分數 62，五日內由 71 下滑</p>",
        "<p>RSI 落在 70 以上記為負分，理由是超買區的續漲機率下降</p>",
        "<p>年化波動度 18.4%，距 52 週高點回撤 -6.2%</p>",
        "<p>台股那組差 13.8 個百分點、美股那組差 0.1 個百分點</p>",
        "<p>五個交易日只有五個點，一律標定性觀察</p>",
        "<p>評分機制的說明與侷限：這把尺是自己硬定的</p>",
    ])
    def test_measurements_pass(self, html):
        assert lint(html) == []
        assert_clean(html)  # 不該丟

    def test_describing_the_rule_itself_passes(self):
        """README 與說明段落會寫「不產生買賣建議」—— 那是在講規則，不是在給建議。"""
        html = "<p>market-barometer 完全不產生買賣建議與短中長線建議</p>"
        assert lint(html) == []

    def test_multiple_negation_forms(self):
        for html in (
            "<p>這一側不放買賣建議</p>",
            "<p>刻意不做買進賣出的判斷</p>",
            "<p>頁面不會有進場出場的字眼</p>",
        ):
            assert lint(html) == [], html


class TestBlocked:
    """§2.1 右欄：這些**必須**擋下來。"""

    @pytest.mark.parametrize("term,html", [
        ("買進", "<p>今天 0050 評分 82 分，可以買進</p>"),
        ("賣出", "<p>建議賣出部分部位</p>"),
        ("加碼", "<td>加碼</td>"),
        ("減碼", "<p>分數轉弱，考慮減碼</p>"),
        ("觀望", "<p>短期觀望</p>"),
        ("進場", "<p>分數這麼高可以進場</p>"),
        ("出場", "<p>該出場了</p>"),
    ])
    def test_action_words_are_caught(self, term, html):
        findings = lint(html)
        assert any(f.term == term for f in findings), f"沒抓到「{term}」"
        with pytest.raises(OutputLintError):
            assert_clean(html)

    @pytest.mark.parametrize("label", [
        "短線建議", "中線建議", "長線建議", "操作建議", "買賣建議",
    ])
    def test_advice_labels_are_caught(self, label):
        html = f"<th>{label}</th><td>—</td>"
        assert any(f.term == label for f in lint(html))

    @pytest.mark.parametrize("html", [
        "<p>分數低於 40 應減碼</p>",
        "<p>低於 55 分建議提高現金比重</p>",
    ])
    def test_rule_statements_are_caught(self, html):
        assert any(f.kind == "rule_statement" for f in lint(html))

    def test_error_message_names_the_offending_term(self):
        with pytest.raises(OutputLintError, match="買進"):
            assert_clean("<p>可以買進</p>")

    def test_reports_every_hit_not_just_the_first(self):
        html = "<p>買進</p><p>賣出</p><p>加碼</p>"
        assert len(lint(html)) >= 3


class TestScoringOutputIsClean:
    """實際跑一次評分，確認它產出的東西本來就過得了 lint。"""

    def test_summarize_output_passes_lint(self):
        from barometer.domain.scoring_macro import LayerScore, summarize

        out = summarize(
            LayerScore(score=20.0, valid=8, alert_keys=["vix", "cpi"]),
            LayerScore(score=30.0, valid=6, alert_keys=["sox"]),
        )
        assert lint(repr(out)) == []

    def test_alert_messages_pass_lint(self):
        """警示說明是描述，不是指示 —— 它們必須本來就乾淨。"""
        from barometer.domain.scoring_macro import ALERT_FUNCS

        series = [(f"2026-0{i + 1}-01", 50.0 + i) for i in range(31)]
        for key, fn in ALERT_FUNCS.items():
            _, msg = fn(series)
            assert lint(msg) == [], f"{key} 的說明含行動字眼：{msg}"


# ---------------- §13 的固定收尾不得被自己擋下來 ----------------

MANDATORY_DISCLAIMER = "本頁不構成投資建議。"


def test_the_mandatory_disclaimer_itself_passes_the_lint():
    """§13 要求每一頁掛「不構成投資建議」，而「投資建議」是 ADVICE_LABELS 裡的字。

    兩條硬規定在頁尾正面對撞：lint 會擋掉它自己要求掛上的那句免責聲明。
    這是實際 render 一次才撞到的，不是想出來的。
    """
    assert lint(f"<footer>{MANDATORY_DISCLAIMER}</footer>") == []


def test_the_real_action_word_next_to_a_disclaimer_is_still_caught():
    """白名單只放行「在講規則」的用法，不是放行整段文字。"""
    html = f"<p>{MANDATORY_DISCLAIMER}</p><p>今天 0050 可以進場</p>"
    findings = lint(html)
    assert [f.term for f in findings] == ["進場"]
