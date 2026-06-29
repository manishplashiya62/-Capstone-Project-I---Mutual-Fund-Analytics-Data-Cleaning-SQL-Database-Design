-- =============================================================================
-- schema.sql  –  Bluestock Mutual Fund Analytics : Star Schema
-- =============================================================================
-- Dimension tables hold descriptive / reference data (slow-changing).
-- Fact tables hold measurements that change frequently.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ─── Dimension: dim_fund ─────────────────────────────────────────────────────
-- One row per unique mutual fund scheme
CREATE TABLE IF NOT EXISTS dim_fund (
    fund_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_code      INTEGER NOT NULL UNIQUE,        -- AMFI scheme code
    scheme_name      TEXT    NOT NULL,
    fund_house       TEXT    NOT NULL,               -- AMC name
    category         TEXT,                           -- Equity / Debt / Hybrid
    subcategory      TEXT,                           -- Large Cap / Mid Cap / …
    risk_grade       TEXT,                           -- Low / Moderate / High
    launch_date      TEXT,                           -- YYYY-MM-DD
    direct_plan_date TEXT,                           -- YYYY-MM-DD
    min_investment   REAL,                           -- INR
    expense_ratio_direct   REAL,                    -- %
    expense_ratio_regular  REAL                     -- %
);

-- ─── Dimension: dim_date ─────────────────────────────────────────────────────
-- Calendar lookup table for time-based analysis
CREATE TABLE IF NOT EXISTS dim_date (
    date_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    full_date       TEXT    NOT NULL UNIQUE,         -- YYYY-MM-DD
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,                -- 1-4
    month           INTEGER NOT NULL,                -- 1-12
    month_name      TEXT    NOT NULL,
    week            INTEGER NOT NULL,                -- ISO week number
    day_of_week     INTEGER NOT NULL,                -- 0=Mon … 6=Sun
    day_name        TEXT    NOT NULL,
    is_weekend      INTEGER NOT NULL DEFAULT 0,      -- 0/1 boolean
    is_month_end    INTEGER NOT NULL DEFAULT 0       -- 0/1 boolean
);

-- ─── Fact: fact_nav ──────────────────────────────────────────────────────────
-- Daily NAV per fund (after holiday forward-fill)
CREATE TABLE IF NOT EXISTS fact_nav (
    nav_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id     INTEGER NOT NULL REFERENCES dim_fund(fund_id),
    date_id     INTEGER NOT NULL REFERENCES dim_date(date_id),
    amfi_code   INTEGER NOT NULL,
    nav         REAL    NOT NULL CHECK(nav > 0),
    UNIQUE(amfi_code, date_id)
);

-- ─── Fact: fact_transactions ─────────────────────────────────────────────────
-- Investor buy / SIP / redemption transactions
CREATE TABLE IF NOT EXISTS fact_transactions (
    tx_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id     TEXT    NOT NULL UNIQUE,
    investor_id        TEXT    NOT NULL,
    investor_name      TEXT,
    state              TEXT,
    kyc_status         TEXT    CHECK(kyc_status IN ('KYC_VERIFIED','KYC_PENDING','KYC_REJECTED')),
    fund_id            INTEGER REFERENCES dim_fund(fund_id),
    date_id            INTEGER REFERENCES dim_date(date_id),
    scheme_code        INTEGER NOT NULL,
    transaction_type   TEXT    NOT NULL CHECK(transaction_type IN ('SIP','Lumpsum','Redemption')),
    transaction_date   TEXT    NOT NULL,
    amount             REAL    NOT NULL CHECK(amount > 0),
    units              REAL
);

-- ─── Fact: fact_performance ──────────────────────────────────────────────────
-- Annual scheme performance metrics
CREATE TABLE IF NOT EXISTS fact_performance (
    perf_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id         INTEGER REFERENCES dim_fund(fund_id),
    scheme_code     INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    return_1m       REAL,
    return_3m       REAL,
    return_6m       REAL,
    return_1y       REAL,
    return_3y       REAL,
    return_5y       REAL,
    expense_ratio   REAL,
    expense_ratio_flag INTEGER DEFAULT 0,           -- 1 = out of [0.1,2.5] range
    sharpe_ratio    REAL,
    alpha           REAL,
    beta            REAL,
    aum_cr          REAL,
    UNIQUE(scheme_code, year)
);

-- ─── Fact: fact_aum ──────────────────────────────────────────────────────────
-- Fund-level AUM snapshot (from fund_performance data)
CREATE TABLE IF NOT EXISTS fact_aum (
    aum_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id      INTEGER REFERENCES dim_fund(fund_id),
    scheme_code  INTEGER NOT NULL UNIQUE,
    scheme_name  TEXT,
    return_1m    REAL,
    return_3m    REAL,
    return_6m    REAL,
    return_1y    REAL,
    return_3y    REAL,
    aum_cr       REAL    CHECK(aum_cr >= 0)
);

-- ─── Additional: dim_benchmark ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_benchmark (
    benchmark_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_code  INTEGER NOT NULL UNIQUE,
    benchmark_name  TEXT    NOT NULL,
    return_1m       REAL,
    return_3m       REAL,
    return_6m       REAL,
    return_1y       REAL
);

-- ─── Additional: dim_category ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_category (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    subcategory     TEXT NOT NULL,
    num_funds       INTEGER,
    avg_aum_cr      REAL,
    avg_return_1y   REAL,
    UNIQUE(category, subcategory)
);

-- ─── Additional: fact_portfolio_holdings ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS fact_portfolio_holdings (
    holding_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id        INTEGER REFERENCES dim_fund(fund_id),
    scheme_code    INTEGER NOT NULL,
    holding_rank   INTEGER,
    company_name   TEXT,
    sector         TEXT,
    quantity_cr    REAL,
    weight_pct     REAL
);

-- ─── Indices for common query patterns ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_nav_fund_date    ON fact_nav(fund_id, date_id);
CREATE INDEX IF NOT EXISTS idx_nav_amfi_code    ON fact_nav(amfi_code);
CREATE INDEX IF NOT EXISTS idx_tx_investor      ON fact_transactions(investor_id);
CREATE INDEX IF NOT EXISTS idx_tx_fund_date     ON fact_transactions(fund_id, date_id);
CREATE INDEX IF NOT EXISTS idx_tx_type          ON fact_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_tx_state         ON fact_transactions(state);
CREATE INDEX IF NOT EXISTS idx_perf_fund_year   ON fact_performance(fund_id, year);
CREATE INDEX IF NOT EXISTS idx_date_year_month  ON dim_date(year, month);
