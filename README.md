# Bluestock Mutual Fund Analytics

A complete end-to-end data pipeline for mutual fund analytics built for the Bluestock Fintech internship program.

## Project Structure

```
mutual-fund-analytics/
├── data/
│   ├── raw/                      # Original source CSVs (from Google Drive)
│   │   ├── nav_history.csv
│   │   ├── investor_transactions.csv
│   │   ├── scheme_performance.csv
│   │   ├── fund_master.csv
│   │   ├── scheme_metadata.csv
│   │   ├── fund_performance.csv
│   │   ├── portfolio_holdings.csv
│   │   ├── amfi_category_stats.csv
│   │   ├── benchmark_data.csv
│   │   └── market_data.csv
│   │
│   └── processed/                # 10 cleaned CSV files
│       └── (same filenames)
│
├── database/
│   ├── schema.sql                # Star schema CREATE TABLE DDL
│   ├── queries.sql               # 10 analytical SQL queries
│   └── bluestock_mf.db           # SQLite database
│
├── notebooks/
│   └── day2_data_cleaning.ipynb  # Jupyter notebook walkthrough
│
├── scripts/
│   ├── generate_missing_raw.py   # Generates synthetic raw files
│   ├── clean_data.py             # Data cleaning pipeline (10 CSVs)
│   ├── create_schema.py          # Applies schema.sql to SQLite
│   ├── load_sqlite.py            # Loads CSVs → SQLite via SQLAlchemy
│   └── validate.py               # 12-point post-load validation
│
├── docs/
│   └── data_dictionary.md        # Full column/table documentation
│
├── requirements.txt
└── README.md
```

## Day 2 Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Clean `nav_history.csv` – parse dates, ffill, validate | ✅ |
| 2 | Clean `investor_transactions.csv` – standardise types, validate | ✅ |
| 3 | Clean `scheme_performance.csv` – validate returns, flag ER anomalies | ✅ |
| 4 | Design SQLite star schema | ✅ |
| 5 | Load all cleaned datasets into SQLite | ✅ |
| 6 | Write 10 analytical SQL queries | ✅ |
| 7 | Create data dictionary | ✅ |
| 8 | Git commit "Day 2: Cleaned data + SQLite DB loaded" | ✅ |

## Database Schema

```
dim_fund ──────┐
dim_date ──────┤──── fact_nav
               ├──── fact_transactions
               ├──── fact_performance
               └──── fact_aum

dim_benchmark (standalone reference)
dim_category  (standalone reference)
fact_portfolio_holdings
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate missing raw files (investor_transactions + scheme_performance)
python3 scripts/generate_missing_raw.py

# 3. Clean all 10 CSVs
python3 scripts/clean_data.py

# 4. Create SQLite schema
python3 scripts/create_schema.py

# 5. Load data into SQLite
python3 scripts/load_sqlite.py

# 6. Validate data integrity
python3 scripts/validate.py
```

## Analytical Queries

| # | Query | Key Insight |
|---|-------|-------------|
| 1 | Top 5 funds by AUM | HDFC Top 100 leads with ₹15,600 Cr |
| 2 | Average NAV per month | NAV trend across business days |
| 3 | SIP YoY growth | YoY growth with LAG() window function |
| 4 | Transactions by state | Kerala, Telangana, Gujarat lead |
| 5 | Funds with ER < 1% | All 6 large-cap funds qualify |
| 6 | Best performing funds by 1Y return | Top performers by year |
| 7 | Monthly net flow per fund | Inflow − Outflow analysis |
| 8 | KYC status distribution | 81% KYC_VERIFIED |
| 9 | Category performance comparison | Equity vs Debt vs Hybrid |
| 10 | SIP investor cohort analysis | Premium vs Regular vs Micro SIP tiers |

## Data Dictionary

See [`docs/data_dictionary.md`](docs/data_dictionary.md) for full column documentation.

## Validation Results

All **12/12** post-load validation checks pass:
- No negative NAV values
- No invalid transaction amounts
- All transaction types standardised
- All KYC statuses validated
- No duplicate keys in any table
- All FK references resolved
