-- ToDo §3.5：六張扁平表，零 JOIN，payload 直接塞 JSON。刻意不上 ORM。
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS price_daily (
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,          -- ISO YYYY-MM-DD
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume_shares REAL,                   -- 一律「股」，顯示層才換算成張
    source        TEXT NOT NULL,          -- shioaji / yfinance / yf_only / stale
    as_of         TEXT NOT NULL,
    stale         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS price_conflict (
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,
    field         TEXT NOT NULL,
    shioaji_value REAL,
    yf_value      REAL,
    taken         TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    PRIMARY KEY (symbol, date, field, as_of)
);

CREATE TABLE IF NOT EXISTS macro_cache (
    key          TEXT PRIMARY KEY,
    series_json  TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    data_date    TEXT,
    stale_reason TEXT
);

CREATE TABLE IF NOT EXISTS score_history (
    scope          TEXT NOT NULL,         -- macro_world / macro_tw / index / stock
    symbol         TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    score          REAL NOT NULL,
    subscores_json TEXT NOT NULL,
    price_version  TEXT NOT NULL,         -- 用哪一版價格算的（§3.5）
    PRIMARY KEY (scope, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS adjustment_event (
    symbol        TEXT NOT NULL,
    detected_at   TEXT NOT NULL,
    event_date    TEXT,
    ratio         REAL,
    rows_affected INTEGER,
    note          TEXT,
    PRIMARY KEY (symbol, detected_at)
);

CREATE TABLE IF NOT EXISTS run_log (
    run_id      TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL,
    counts_json TEXT,
    quota_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_symbol_date ON price_daily (symbol, date);
CREATE INDEX IF NOT EXISTS idx_score_scope_symbol ON score_history (scope, symbol, as_of);

-- Day 26 第 2 項：市場級籌碼面。一天一列，payload 直接塞 JSON（§3.2 零 JOIN）。
-- 欄位還會變 —— 市場級的融資「維持率」至今找不到公開來源，只有餘額 ——
-- 塞 JSON 就不必為了加一個欄位改 schema。
CREATE TABLE IF NOT EXISTS chip_daily (
    date         TEXT PRIMARY KEY,      -- ISO YYYY-MM-DD
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL
);
