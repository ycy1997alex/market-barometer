"""Fetch Shioaji names/exchanges once and persist a labeled local directory."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config, secrets_store  # noqa: E402
from barometer.datasources import shioaji_src  # noqa: E402


def load_api():
    api_key, secret_key, simulation = secrets_store.shioaji_credentials()
    if not (api_key and secret_key):
        return None
    try:
        return shioaji_src._login(api_key, secret_key, simulation)
    except Exception:  # noqa: BLE001 — explicitly labeled fallback is safer than no directory
        return None


def build_directory(symbols: list[str]) -> dict[str, dict]:
    api = load_api()
    stamp = dt.datetime.now()
    try:
        out: dict[str, dict] = {}
        for symbol in sorted(set(symbols)):
            fallback = config.TW_CONTRACT_FALLBACK_NAMES.get(symbol, symbol)
            if api is None:
                market = "OTC" if symbol.endswith(".TWO") else "TSE"
                info = shioaji_src.ContractInfo(symbol, fallback, market, "fallback", stamp)
            else:
                info = shioaji_src.contract_info(
                    api, symbol, fallback_name=fallback, fetched_at=stamp)
            out[symbol] = {**asdict(info), "fetched_at": stamp.isoformat()}
    finally:
        if api is not None:
            try:
                api.logout()
            except Exception:  # noqa: BLE001
                pass
    path = config.stockdata_root() / "contract_directory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return out


def main() -> int:
    symbols = list(config.TW_SYMBOLS)
    if config.db_path().exists():
        with sqlite3.connect(config.db_path()) as conn:
            symbols.extend(row[0] for row in conn.execute(
                "SELECT DISTINCT symbol FROM price_daily WHERE symbol LIKE '%.TW' OR symbol LIKE '%.TWO'"))
    out = build_directory(symbols)
    fallback = sum(row["source"] == "fallback" for row in out.values())
    print(f"contract_directory: {len(out)} symbols, {fallback} fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
