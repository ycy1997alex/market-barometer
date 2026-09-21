-- ToDo §3.5：扁平表，零 JOIN，擴充欄位用 JSON payload；刻意不上 ORM。
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
    old_value     REAL,                   -- 4-2: stored value before a revision
    new_value     REAL,                   -- 4-2: freshly fetched value
    taken         TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    PRIMARY KEY (symbol, date, field, as_of)
);

CREATE TABLE IF NOT EXISTS macro_cache (
    key          TEXT PRIMARY KEY,
    series_json  TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    data_date    TEXT,
    stale_reason TEXT,
    source       TEXT NOT NULL DEFAULT '未記錄'
);

CREATE TABLE IF NOT EXISTS score_history (
    scope          TEXT NOT NULL,         -- macro_world / macro_tw / index / stock
    symbol         TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    score          REAL NOT NULL,
    comparable     REAL,
    native         REAL,
    strength       REAL,
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

-- Individual T86 rows. A stored NULL is a confirmed missing value, not zero.
CREATE TABLE IF NOT EXISTS stock_chip_daily (
    date         TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    PRIMARY KEY (date, symbol)
);

-- Derived total-return OHLCV, separate from the immutable raw audit.
CREATE TABLE IF NOT EXISTS price_adjusted (
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume_shares REAL,
    source        TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    stale         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);

-- TWSE daily stock fields A/E/F/G/H. All-market requests are stored once.
CREATE TABLE IF NOT EXISTS tw_stock_daily (
    date         TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    PRIMARY KEY (date, symbol)
);

-- TWSE market breadth B has no individual stock symbol.
CREATE TABLE IF NOT EXISTS tw_market_daily (
    date         TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL
);

-- TDCC shareholder distribution D is published weekly.
CREATE TABLE IF NOT EXISTS tw_stock_weekly (
    date         TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    PRIMARY KEY (date, symbol)
);

-- Revenue C belongs to a reporting month but has a separate release date.
CREATE TABLE IF NOT EXISTS tw_stock_monthly (
    period       TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    data_date    TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    PRIMARY KEY (period, symbol)
);

-- Institution / insider / analyst observations are separate local dimensions.
CREATE TABLE IF NOT EXISTS us_stock_local (
    date         TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    dimension    TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    PRIMARY KEY (date, symbol, dimension)
);

CREATE INDEX IF NOT EXISTS idx_stock_chip_symbol_date ON stock_chip_daily (symbol, date);
CREATE INDEX IF NOT EXISTS idx_adjusted_symbol_date ON price_adjusted (symbol, date);
CREATE INDEX IF NOT EXISTS idx_tw_stock_daily_symbol_date ON tw_stock_daily (symbol, date);
CREATE INDEX IF NOT EXISTS idx_tw_stock_weekly_symbol_date ON tw_stock_weekly (symbol, date);
CREATE INDEX IF NOT EXISTS idx_tw_stock_monthly_symbol_period ON tw_stock_monthly (symbol, period);
CREATE INDEX IF NOT EXISTS idx_us_stock_local_symbol_date ON us_stock_local (symbol, date);
