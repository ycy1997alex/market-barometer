"""FRED 走金鑰版 API（作者 2026-09-07 決定改用）。

原本走的是 `fredgraph.csv` 免金鑰端點。改用官方 API 之後有兩件事要守：

1. **金鑰絕不出現在任何會被看到的地方** —— 不進 repo、不進 run log、
   不進例外訊息。FRED 的錯誤訊息會把整個 query string 回顯出來，
   而 query string 裡就有 `api_key=` —— 這是最容易外洩的一條路徑，
   所以錯誤訊息一律先遮罩。
2. **沒有金鑰也要能跑** —— 退回免金鑰的 CSV 端點。金鑰是拿來換額度的
   （30 → 120 req/min），不是必要條件。這也是 Day 28「讀取型金鑰」那段
   要講的：它可撤銷、唯讀，沒有它系統只是慢一點。
"""
from __future__ import annotations

import json

import pytest

from barometer.datasources import fred_src

FAKE_KEY = "abcdef0123456789abcdef0123456789"


# ---------------- 金鑰載入 ----------------

def test_key_from_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    assert fred_src.load_api_key() == FAKE_KEY


def test_key_read_from_a_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    d = tmp_path / "Key"
    d.mkdir()
    (d / "FRED API Key.txt").write_text(f"  {FAKE_KEY}\n", encoding="utf-8")
    assert fred_src.load_api_key(search=[d]) == FAKE_KEY


def test_key_file_with_a_label_line_is_parsed(monkeypatch, tmp_path):
    """Shioaji 那個檔案是「標題行 + 值」的格式，FRED 的也可能是。"""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    d = tmp_path / "Key"
    d.mkdir()
    (d / "FRED API Key.txt").write_text(
        f"API Key\n{FAKE_KEY}\n", encoding="utf-8")
    assert fred_src.load_api_key(search=[d]) == FAKE_KEY


def test_no_key_anywhere_is_none_not_an_error(monkeypatch, tmp_path):
    """沒有金鑰是一種正常狀態，不是故障。"""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert fred_src.load_api_key(search=[tmp_path / "nope"]) is None


def test_a_string_that_is_not_a_key_is_rejected(monkeypatch, tmp_path):
    """FRED 金鑰是 32 個小寫英數。撿到一句說明文字就當成金鑰會很難查。"""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    d = tmp_path / "Key"
    d.mkdir()
    (d / "FRED API Key.txt").write_text("請到 fred.stlouisfed.org 申請\n",
                                        encoding="utf-8")
    assert fred_src.load_api_key(search=[d]) is None


# ---------------- 端點選擇 ----------------

def test_with_a_key_it_uses_the_official_api():
    url = fred_src.build_url("CPIAUCSL", api_key=FAKE_KEY)
    assert url.startswith(fred_src.API_BASE)
    assert "series_id=CPIAUCSL" in url
    assert "file_type=json" in url


def test_without_a_key_it_falls_back_to_the_keyless_csv():
    url = fred_src.build_url("CPIAUCSL", api_key=None)
    assert url.startswith(fred_src.CSV_BASE)
    assert "api_key" not in url


def test_the_api_url_asks_only_for_what_is_needed():
    """只要最後 N 筆，不要把整條 1947 年至今的序列拉回來。"""
    url = fred_src.build_url("CPIAUCSL", api_key=FAKE_KEY, tail=30)
    assert "sort_order=desc" in url
    assert "limit=30" in url


# ---------------- 遮罩：這一條是紅線 ----------------

def test_the_key_never_appears_in_an_error_message():
    url = fred_src.build_url("CPIAUCSL", api_key=FAKE_KEY)
    masked = fred_src.redact(f"連線失敗: {url}")
    assert FAKE_KEY not in masked
    assert "api_key=***" in masked


def test_redaction_survives_other_query_params_after_the_key():
    url = fred_src.build_url("CPIAUCSL", api_key=FAKE_KEY)
    masked = fred_src.redact(url)
    assert FAKE_KEY not in masked
    assert "series_id=CPIAUCSL" in masked   # 其他參數要留著，不然錯誤訊息沒用


def test_redaction_is_a_no_op_without_a_key():
    plain = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
    assert fred_src.redact(plain) == plain


# ---------------- 解析 ----------------

def test_parses_the_json_observations_oldest_first():
    payload = json.dumps({"observations": [
        {"date": "2026-07-01", "value": "330.1"},
        {"date": "2026-06-01", "value": "329.0"},
    ]})
    got = fred_src.parse_api(payload)
    assert got == [("2026-06-01", 329.0), ("2026-07-01", 330.1)]


def test_json_missing_marker_is_skipped_not_zero():
    """FRED 用 '.' 表示缺值。當成 0 會在圖上憑空造出一次崩跌。"""
    payload = json.dumps({"observations": [
        {"date": "2026-06-01", "value": "."},
        {"date": "2026-07-01", "value": "330.1"},
    ]})
    assert fred_src.parse_api(payload) == [("2026-07-01", 330.1)]


def test_json_without_observations_is_an_error():
    with pytest.raises(fred_src.FetchError):
        fred_src.parse_api(json.dumps({"error_message": "Bad Request"}))


def test_the_csv_parser_still_works_for_the_keyless_path():
    csv_text = "DATE,CPIAUCSL\n2026-06-01,329.0\n2026-07-01,330.1\n"
    assert fred_src.parse_csv(csv_text) == [
        ("2026-06-01", 329.0), ("2026-07-01", 330.1)
    ]
