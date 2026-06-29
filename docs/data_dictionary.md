# Data Dictionary — Bluestock Mutual Fund Analytics

> **Project:** Bluestock Fintech – Mutual Fund Analytics (Day 2)  
> **Database:** `bluestock_mf.db` (SQLite)  
> **Author:** Manish Patidar  
> **Date:** 2026-06-30  

---

## Table of Contents
1. [dim_fund](#1-dim_fund)
2. [dim_date](#2-dim_date)
3. [fact_nav](#3-fact_nav)
4. [fact_transactions](#4-fact_transactions)
5. [fact_performance](#5-fact_performance)
6. [fact_aum](#6-fact_aum)
7. [dim_benchmark](#7-dim_benchmark)
8. [dim_category](#8-dim_category)
9. [fact_portfolio_holdings](#9-fact_portfolio_holdings)
10. [Source CSV Reference](#10-source-csv-reference)
11. [Data Quality Notes](#11-data-quality-notes)

---

## 1. `dim_fund`

**Purpose:** Dimension table describing each unique mutual fund scheme.  
**Source:** `fund_master.csv` + `scheme_metadata.csv` (joined on `scheme_code`)  
**Primary Key:** `rowid` (SQLite auto)  
**Unique Constraint:** `scheme_code`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `scheme_code` | INTEGER | NOT NULL | AMFI-assigned unique numeric code for the scheme |
| `scheme_name` | TEXT | NOT NULL | Full name of the mutual fund scheme |
| `fund_house` | TEXT | NOT NULL | Asset Management Company (AMC) e.g. "SBI Mutual Fund" |
| `category` | TEXT | YES | SEBI classification: Equity / Debt / Hybrid |
| `subcategory` | TEXT | YES | Sub-classification: Large Cap / Mid Cap / Liquid / etc. |
| `risk_grade` | TEXT | YES | SEBI risk label: Low / Low-Moderate / Moderate / Moderate-High / High |
| `launch_date` | TEXT | YES | Original launch date of the scheme (YYYY-MM-DD) |
| `direct_plan_date` | TEXT | YES | Date from which Direct plan was available (YYYY-MM-DD) |
| `min_investment` | REAL | YES | Minimum lump-sum investment amount in INR |
| `expense_ratio_direct` | REAL | YES | Total Expense Ratio (TER) for Direct plan in % (valid range: 0.1–2.5) |
| `expense_ratio_regular` | REAL | YES | Total Expense Ratio (TER) for Regular plan in % |

---

## 2. `dim_date`

**Purpose:** Calendar dimension for time-based slicing and aggregation.  
**Source:** Derived from all date columns in `nav_history.csv`, `investor_transactions.csv`, and `market_data.csv`  
**Primary Key:** `rowid`  
**Unique Constraint:** `full_date`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `full_date` | TEXT | NOT NULL | Calendar date in ISO format YYYY-MM-DD |
| `year` | INTEGER | NOT NULL | Gregorian year (e.g. 2024) |
| `quarter` | INTEGER | NOT NULL | Quarter of year: 1, 2, 3, or 4 |
| `month` | INTEGER | NOT NULL | Month number: 1 (January) to 12 (December) |
| `month_name` | TEXT | NOT NULL | Full month name (e.g. "June") |
| `week` | INTEGER | NOT NULL | ISO week number (1–53) |
| `day_of_week` | INTEGER | NOT NULL | 0 = Monday … 6 = Sunday |
| `day_name` | TEXT | NOT NULL | Full day name (e.g. "Monday") |
| `is_weekend` | INTEGER | NOT NULL | Boolean flag: 1 if Saturday or Sunday, else 0 |
| `is_month_end` | INTEGER | NOT NULL | Boolean flag: 1 if last calendar day of the month, else 0 |

---

## 3. `fact_nav`

**Purpose:** Daily Net Asset Value per fund, including forward-filled holiday/weekend gaps.  
**Source:** `nav_history.csv` (raw) → cleaned in `clean_data.py`  
**Primary Key:** `nav_id` (auto)  
**Unique Constraint:** `(amfi_code, date_id)`  
**Foreign Keys:** `fund_id → dim_fund`, `date_id → dim_date`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `fund_id` | INTEGER | YES | FK to `dim_fund.rowid` |
| `date_id` | INTEGER | YES | FK to `dim_date.rowid` |
| `amfi_code` | INTEGER | NOT NULL | AMFI scheme code (also used as `scheme_code` in raw file) |
| `nav` | REAL | NOT NULL | Net Asset Value in INR per unit. Must be > 0 |

**Cleaning Applied:**
- Dates parsed to `datetime`, invalid dates dropped
- Sorted by `amfi_code` + `date` before forward-fill
- `ffill()` applied per `amfi_code` group to fill weekends/holidays
- Rows with `nav ≤ 0` removed
- Duplicates on `(amfi_code, date)` removed

---

## 4. `fact_transactions`

**Purpose:** Individual investor transactions (SIP, Lumpsum, Redemption).  
**Source:** `investor_transactions.csv` (synthetic, generated to spec)  
**Primary Key:** `tx_id` (auto)  
**Unique Constraint:** `transaction_id`  
**Foreign Keys:** `fund_id → dim_fund`, `date_id → dim_date`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `transaction_id` | TEXT | NOT NULL | Unique identifier for each transaction (e.g. "TX0000001") |
| `investor_id` | TEXT | NOT NULL | Unique investor identifier (e.g. "INV00042") |
| `investor_name` | TEXT | YES | Investor's display name |
| `state` | TEXT | YES | Indian state of the investor |
| `kyc_status` | TEXT | YES | KYC compliance status. Enum: `KYC_VERIFIED`, `KYC_PENDING`, `KYC_REJECTED` |
| `fund_id` | INTEGER | YES | FK to `dim_fund.rowid` |
| `date_id` | INTEGER | YES | FK to `dim_date.rowid` |
| `scheme_code` | INTEGER | NOT NULL | AMFI scheme code of the fund invested in |
| `transaction_type` | TEXT | NOT NULL | Standardised type. Enum: `SIP`, `Lumpsum`, `Redemption` |
| `transaction_date` | TEXT | NOT NULL | Date of the transaction (YYYY-MM-DD) |
| `amount` | REAL | NOT NULL | Transaction amount in INR. Must be > 0 |
| `units` | REAL | YES | Number of units allotted/redeemed |

**Cleaning Applied:**
- Multiple date formats (YYYY-MM-DD, DD-MM-YYYY) parsed and standardised
- Raw values like `sip`, `SIP`, `Sip`, `LUMPSUM`, `Purchase` → standardised to `SIP`, `Lumpsum`, `Redemption`
- `amount ≤ 0` rows removed (51 rows)
- Duplicate `transaction_id` rows removed (5 rows)
- Invalid `kyc_status` values corrected to `KYC_PENDING`

---

## 5. `fact_performance`

**Purpose:** Annual return and risk metrics per fund scheme.  
**Source:** `scheme_performance.csv` (synthetic, generated to spec)  
**Primary Key:** `perf_id` (auto)  
**Unique Constraint:** `(scheme_code, year)`  
**Foreign Keys:** `fund_id → dim_fund`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `fund_id` | INTEGER | YES | FK to `dim_fund.rowid` |
| `scheme_code` | INTEGER | NOT NULL | AMFI scheme code |
| `year` | INTEGER | NOT NULL | Year the performance metrics apply to |
| `return_1m` | REAL | YES | 1-month trailing return in % |
| `return_3m` | REAL | YES | 3-month trailing return in % |
| `return_6m` | REAL | YES | 6-month trailing return in % |
| `return_1y` | REAL | YES | 1-year trailing return in % |
| `return_3y` | REAL | YES | 3-year CAGR in % |
| `return_5y` | REAL | YES | 5-year CAGR in % (NULL if fund < 5 years old) |
| `expense_ratio` | REAL | YES | Expense ratio at time of reporting in % |
| `expense_ratio_flag` | INTEGER | YES | 1 if `expense_ratio` outside [0.1, 2.5] range; else 0 |
| `sharpe_ratio` | REAL | YES | Risk-adjusted return metric (higher = better) |
| `alpha` | REAL | YES | Excess return above benchmark |
| `beta` | REAL | YES | Market sensitivity (1.0 = benchmark-neutral) |
| `aum_cr` | REAL | YES | Assets Under Management in crores INR at year-end |

**Cleaning Applied:**
- Non-numeric return values (e.g. "N/A") coerced to `NULL`
- Non-numeric `expense_ratio` values (e.g. "n.a.") coerced to `NULL`
- `expense_ratio_flag` column added for out-of-range values
- Anomalous `return_1y > 100` or `< -50` flagged

---

## 6. `fact_aum`

**Purpose:** Fund-level AUM and trailing return snapshot.  
**Source:** `fund_performance.csv`  
**Primary Key:** `aum_id` (auto)  
**Unique Constraint:** `scheme_code`  
**Foreign Keys:** `fund_id → dim_fund`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `fund_id` | INTEGER | YES | FK to `dim_fund.rowid` |
| `scheme_code` | INTEGER | NOT NULL | AMFI scheme code |
| `scheme_name` | TEXT | YES | Fund scheme name |
| `return_1m` | REAL | YES | 1-month trailing return % |
| `return_3m` | REAL | YES | 3-month trailing return % |
| `return_6m` | REAL | YES | 6-month trailing return % |
| `return_1y` | REAL | YES | 1-year trailing return % |
| `return_3y` | REAL | YES | 3-year CAGR % |
| `aum_cr` | REAL | YES | AUM in crores INR. Must be ≥ 0 |

---

## 7. `dim_benchmark`

**Purpose:** Reference data for market benchmark indices.  
**Source:** `benchmark_data.csv`  
**Primary Key:** `benchmark_id` (auto)  
**Unique Constraint:** `benchmark_code`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `benchmark_code` | INTEGER | NOT NULL | Internal benchmark code |
| `benchmark_name` | TEXT | NOT NULL | Name e.g. "Nifty 50 TR", "CRISIL Liquid Fund Index" |
| `return_1m` | REAL | YES | 1-month return % |
| `return_3m` | REAL | YES | 3-month return % |
| `return_6m` | REAL | YES | 6-month return % |
| `return_1y` | REAL | YES | 1-year return % |

---

## 8. `dim_category`

**Purpose:** AMFI category-level aggregate statistics.  
**Source:** `amfi_category_stats.csv`  
**Primary Key:** `category_id` (auto)  
**Unique Constraint:** `(category, subcategory)`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `category` | TEXT | NOT NULL | Broad SEBI category: Equity / Debt / Hybrid |
| `subcategory` | TEXT | NOT NULL | SEBI sub-category: Large Cap / Liquid / etc. |
| `num_funds` | INTEGER | YES | Number of funds in this category/sub-category |
| `avg_aum_cr` | REAL | YES | Average AUM in crores across all funds in category |
| `avg_return_1y` | REAL | YES | Average 1-year return % across all funds |

---

## 9. `fact_portfolio_holdings`

**Purpose:** Top portfolio holdings (stocks/bonds) per fund.  
**Source:** `portfolio_holdings.csv`  
**Primary Key:** `holding_id` (auto)  
**Foreign Keys:** `fund_id → dim_fund`

| Column | Data Type | Nullable | Description |
|--------|-----------|----------|-------------|
| `fund_id` | INTEGER | YES | FK to `dim_fund.rowid` |
| `scheme_code` | INTEGER | NOT NULL | AMFI scheme code |
| `holding_rank` | INTEGER | YES | Rank of holding by weight (1 = largest) |
| `company_name` | TEXT | YES | Name of the company whose securities are held |
| `sector` | TEXT | YES | Sector classification (e.g. Banking, IT, FMCG) |
| `quantity_cr` | REAL | YES | Quantity held in crores INR |
| `weight_pct` | REAL | YES | Percentage of fund AUM represented by this holding |

---

## 10. Source CSV Reference

| Processed File | Raw Source | Rows (raw → clean) | Key Cleaning |
|---|---|---|---|
| `nav_history.csv` | Drive `raw/nav_history.csv` | 30 → 42 | ffill weekends, validate NAV>0 |
| `investor_transactions.csv` | Synthetic (generated) | 1809 → 1753 | standardise types, validate amount>0, dedup |
| `scheme_performance.csv` | Synthetic (generated) | 24 → 24 | coerce non-numeric, flag expense_ratio |
| `fund_master.csv` | Drive `raw/fund_master.csv` | 18 → 18 | strip whitespace, dedup |
| `scheme_metadata.csv` | Drive `raw/scheme_metadata.csv` | 6 → 6 | parse dates, validate ER |
| `fund_performance.csv` | Drive `raw/fund_performance.csv` | 6 → 6 | validate returns numeric |
| `portfolio_holdings.csv` | Drive `raw/portfolio_holdings.csv` | 10 → 10 | validate weight_pct sums |
| `amfi_category_stats.csv` | Drive `raw/amfi_category_stats.csv` | 9 → 9 | validate numeric cols |
| `benchmark_data.csv` | Drive `raw/benchmark_data.csv` | 5 → 5 | validate return cols |
| `market_data.csv` | Drive `raw/market_data.csv` | 5 → 5 | parse dates, validate indices |

---

## 11. Data Quality Notes

### NAV History
- Forward-fill adds **12 rows** for weekend/holiday gaps (weekends where markets are closed)
- All NAV values are validated to be positive (`> 0`)
- `scheme_code` in raw file renamed to `amfi_code` to match task specification

### Investor Transactions
- Raw data contained mixed date formats: `YYYY-MM-DD` and `DD-MM-YYYY`
- Transaction types appeared in 10 different raw representations → reduced to 3 canonical values
- Negative amounts (noise injection) removed: **51 rows**
- Duplicate transactions (by `transaction_id`): **5 rows** removed

### Scheme Performance
- Non-numeric return values coerced to `NULL` and flagged
- `expense_ratio_flag = 1` for values outside SEBI-permitted range [0.1%, 2.5%]: **3 rows**
- `return_5y` is `NULL` for more recent fund vintages (expected)

### Database Integrity
- All 12 post-load validation checks pass (see `scripts/validate.py`)
- FK joins on `scheme_code` may return `NULL` for funds in transactions not present in `dim_fund` (expected for synthetic data)

---

*Generated by `scripts/clean_data.py` and `scripts/load_sqlite.py`*
