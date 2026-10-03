"""發布驗收第 1 項：git 裡的 docs/ 不得有明文版本 —— 偵測不能只靠 `<table>`（2026-10-03）。

stock-research 改版後，分頁內容由那一側自己畫（`Tab.body`），表格都帶 class，
明文裡一個 `<table>` 都沒有。原本的偵測只找 `<table>`：誤 commit 一份明文進
docs/ 也會被當成密文放過 —— 防線還在，卻安靜地失效了。
"""
import importlib.util
from pathlib import Path

from barometer.crypto import envelope, shell
from barometer.render import page

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_publish", ROOT / "tools" / "verify_publish.py")
assert SPEC and SPEC.loader
verify_publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_publish)


def test_plaintext_drawn_with_custom_tab_bodies_is_still_caught():
    html = page.render([page.Tab(key="tw", title="台股", group="評分",
                                 body='<table class="stocks"><tbody></tbody></table>')],
                       title="stock-research")
    assert "<table>" not in html
    assert verify_publish.looks_like_plaintext(html)


def test_default_table_plaintext_is_caught():
    html = page.render([page.Tab(key="w", title="世界",
                                 rows=[page.Row("美國 CPI", "330.1", "2026-07-01")])], title="t")
    assert verify_publish.looks_like_plaintext(html)


def test_sealed_page_is_not_mistaken_for_plaintext(monkeypatch):
    monkeypatch.setattr(envelope, "ITERATIONS", 1000)
    plain = page.render([page.Tab(key="tw", title="台股", body="<p>內容</p>")], title="t")
    sealed = shell.wrap(envelope.seal(plain, [b"test-only"]), title="t", mode="one")
    assert not verify_publish.looks_like_plaintext(sealed)
