"""Contract lookup must continue past a missing TSE entry and label fallback data."""
from types import SimpleNamespace

from barometer.datasources import shioaji_src
from tools import fetch_contract_directory


class Book(dict):
    def __getitem__(self, key):
        return self.get(key)


def test_otc_lookup_does_not_stop_on_none_from_tse():
    otc = SimpleNamespace(name="商之器", exchange="OTC", code="8299")
    api = SimpleNamespace(Contracts=SimpleNamespace(
        Stocks=SimpleNamespace(TSE=Book(), OTC=Book({"8299": otc}))))
    got = shioaji_src.contract_info(api, "8299.TW", fallback_name="設定名稱")
    assert got.name == "商之器"
    assert got.market == "OTC"
    assert got.source == "shioaji"


def test_fallback_is_explicit_when_directory_unavailable():
    api = SimpleNamespace(Contracts=SimpleNamespace(
        Stocks=SimpleNamespace(TSE=Book(), OTC=Book())))
    got = shioaji_src.contract_info(api, "8299.TWO", fallback_name="設定名稱")
    assert got.name == "設定名稱"
    assert got.market == "OTC"
    assert got.source == "fallback"


def test_directory_tool_persists_labeled_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    monkeypatch.setattr(fetch_contract_directory, "load_api", lambda: None)
    records = fetch_contract_directory.build_directory(["0050.TW", "8299.TWO"])
    assert records["0050.TW"]["source"] == "fallback"
    assert records["8299.TWO"]["market"] == "OTC"
    assert (tmp_path / "contract_directory.json").exists()
