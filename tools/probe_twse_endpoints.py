"""One-time live probe of official TWSE and TDCC response schemas.

Run from the repository root with the barometer Python environment. The script
prints metadata only and does not persist market data. Dates are fixed to the
verified 2026-09-18 session and the 0050 split window for reproducibility.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import requests


URLS = {
    "STOCK_DAY_ALL": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "BWIBBU_ALL": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "MI_INDEX": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260918&type=ALLBUT0999&response=json",
    "monthly_revenue": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "MI_QFIIS": "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date=20260918&response=json&selectType=ALLBUT0999",
    "TWTB4U": "https://www.twse.com.tw/exchangeReport/TWTB4U?date=20260918&response=json&selectType=All",
    "TWT93U": "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=20260918&response=json",
    "TWT49U": "https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=20250610&endDate=20250625&response=json",
    "TDCC_1-5": "https://openapi.tdcc.com.tw/v1/opendata/1-5",
}


def describe(payload: object) -> tuple[str, int, list[str]]:
    if isinstance(payload, list):
        rows = payload
        fields = list(rows[0]) if rows and isinstance(rows[0], Mapping) else []
        return "list", len(rows), fields
    if isinstance(payload, Mapping):
        rows = payload.get("data", [])
        fields = payload.get("fields", [])
        if not fields and rows and isinstance(rows[0], Mapping):
            fields = list(rows[0])
        if payload.get("tables"):
            fields = [table.get("title", "") for table in payload["tables"]]
        return str(payload.get("stat", "dict")), len(rows), fields
    return type(payload).__name__, 0, []


def symbols(name: str, payload: object) -> set[str]:
    if isinstance(payload, list):
        key = "公司代號" if name == "monthly_revenue" else "證券代號" if name == "TDCC_1-5" else "Code"
        return {str(row.get(key, "")).strip() for row in payload if isinstance(row, Mapping)}
    if isinstance(payload, Mapping):
        if name in {"MI_INDEX", "TWTB4U"}:
            tables = payload.get("tables", [])
            rows = next((table.get("data", []) for table in tables if "證券代號" in table.get("fields", [])), [])
            return {str(row[0]) for row in rows if row}
        index = 1 if name == "TWT49U" else 0
        return {str(row[index]) for row in payload.get("data", []) if len(row) > index}
    return set()


def main() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "market-barometer/0.1 (personal research; contact via GitHub)"
    failures: list[str] = []
    for name, url in URLS.items():
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            payload = response.json()
            status, count, fields = describe(payload)
            response.content.decode("utf-8")
            print(name, url)
            print("  response:", response.status_code, response.headers.get("Content-Type"), "UTF-8", len(response.content), "bytes", status, count, "rows")
            print("  fields:", fields)
            if isinstance(payload, Mapping) and payload.get("tables"):
                for table in payload["tables"]:
                    print("  table:", table.get("title"), table.get("fields"), len(table.get("data", [])))
                    if "漲跌證券數" in str(table.get("title")):
                        print("  breadth rows:", table.get("data", []))
            codes = symbols(name, payload)
            print("  symbol coverage:", {code: code in codes for code in ("2330", "8299", "0050")})
            if isinstance(payload, list) and payload:
                date_key = next((key for key in ("Date", "出表日期", "\ufeff資料日期") if key in payload[0]), None)
                print("  first date:", payload[0].get(date_key) if date_key else "not supplied")
            elif isinstance(payload, Mapping):
                print("  report date:", payload.get("date", "not supplied"))
            if name == "TWT49U" and isinstance(payload, Mapping):
                print("  0050 event count in split window:", sum(1 for row in payload.get("data", []) if len(row) > 1 and row[1] == "0050"))
        except Exception as exc:
            print(name, type(exc).__name__, str(exc)[:160])
            failures.append(name)
        time.sleep(0.7)
    if failures:
        raise SystemExit(f"Probe failed for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
