"""
load_sqlite.py
==============
Loads all cleaned CSVs into the SQLite database (bluestock_mf.db).
Uses SQLAlchemy create_engine + DataFrame.to_sql().
Verifies row counts match source processed CSVs.
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text

BASE = os.path.join(os.path.dirname(__file__), "..")
PROC = os.path.join(BASE, "data", "processed")
DB_FILE = os.path.join(BASE, "database", "bluestock_mf.db")

engine = create_engine(f"sqlite:///{DB_FILE}")


# ─── helpers ──────────────────────────────────────────────────────────────────

def load_dim_date(nav_df, tx_df, mkt_df):
    """Build a complete dim_date from all date columns."""
    dates = set()
    for d in nav_df["date"].dropna():
        dates.add(str(d)[:10])
    for d in tx_df["transaction_date"].dropna():
        dates.add(str(d)[:10])
    for d in mkt_df["date"].dropna():
        dates.add(str(d)[:10])

    rows = []
    for d_str in sorted(dates):
        d = pd.Timestamp(d_str)
        rows.append({
            "full_date":    d_str,
            "year":         d.year,
            "quarter":      d.quarter,
            "month":        d.month,
            "month_name":   d.strftime("%B"),
            "week":         int(d.strftime("%V")),
            "day_of_week":  d.dayofweek,
            "day_name":     d.strftime("%A"),
            "is_weekend":   int(d.dayofweek >= 5),
            "is_month_end": int(d.is_month_end),
        })
    return pd.DataFrame(rows)


def build_fund_dim(fund_master_df, scheme_metadata_df):
    """Merge fund_master + scheme_metadata into a single dim_fund."""
    merged = fund_master_df.merge(
        scheme_metadata_df,
        on="scheme_code",
        how="left",
        suffixes=("", "_meta"),
    )
    # Keep one row per unique (scheme_code, scheme_name) pair
    merged = merged.drop_duplicates(subset=["scheme_code", "scheme_name"]).reset_index(drop=True)
    return merged


# ─── loaders ──────────────────────────────────────────────────────────────────

def load_all():
    print("=" * 60)
    print("  Loading processed CSVs into SQLite")
    print("=" * 60)

    # Read processed CSVs
    nav       = pd.read_csv(os.path.join(PROC, "nav_history.csv"))
    inv_tx    = pd.read_csv(os.path.join(PROC, "investor_transactions.csv"))
    sp        = pd.read_csv(os.path.join(PROC, "scheme_performance.csv"))
    fm        = pd.read_csv(os.path.join(PROC, "fund_master.csv"))
    sm        = pd.read_csv(os.path.join(PROC, "scheme_metadata.csv"))
    fp        = pd.read_csv(os.path.join(PROC, "fund_performance.csv"))
    ph        = pd.read_csv(os.path.join(PROC, "portfolio_holdings.csv"))
    acs       = pd.read_csv(os.path.join(PROC, "amfi_category_stats.csv"))
    bench     = pd.read_csv(os.path.join(PROC, "benchmark_data.csv"))
    mkt       = pd.read_csv(os.path.join(PROC, "market_data.csv"))

    with engine.begin() as conn:
        # ── dim_date ──────────────────────────────────────────────────────────
        dim_date = load_dim_date(nav, inv_tx, mkt)
        dim_date.to_sql("dim_date", conn, if_exists="replace", index=False)
        print(f"  dim_date              → {len(dim_date):>6} rows")

        # ── dim_fund ──────────────────────────────────────────────────────────
        dim_fund = build_fund_dim(fm, sm)
        # Keep first occurrence per scheme_code to avoid FK join multiplication
        dim_fund = dim_fund.drop_duplicates(subset=["scheme_code"], keep="first").reset_index(drop=True)
        dim_fund.to_sql("dim_fund", conn, if_exists="replace", index=False)
        print(f"  dim_fund              → {len(dim_fund):>6} rows")

        # ── dim_benchmark ─────────────────────────────────────────────────────
        bench.to_sql("dim_benchmark", conn, if_exists="replace", index=False)
        print(f"  dim_benchmark         → {len(bench):>6} rows")

        # ── dim_category ──────────────────────────────────────────────────────
        acs.to_sql("dim_category", conn, if_exists="replace", index=False)
        print(f"  dim_category          → {len(acs):>6} rows")

        # ── fact_nav ──────────────────────────────────────────────────────────
        # Join to get fund_id and date_id FK references
        date_map  = pd.read_sql("SELECT rowid AS date_id, full_date FROM dim_date", conn)
        fund_map  = pd.read_sql("SELECT rowid AS fund_id, scheme_code FROM dim_fund", conn)

        nav_fact = nav.rename(columns={"amfi_code": "amfi_code"}).copy()
        nav_fact = nav_fact.merge(
            fund_map, left_on="amfi_code", right_on="scheme_code", how="left"
        )
        nav_fact = nav_fact.merge(
            date_map, left_on="date", right_on="full_date", how="left"
        )
        nav_fact = nav_fact[["fund_id", "date_id", "amfi_code", "nav"]]
        nav_fact.to_sql("fact_nav", conn, if_exists="replace", index=False)
        print(f"  fact_nav              → {len(nav_fact):>6} rows")

        # ── fact_transactions ─────────────────────────────────────────────────
        tx_fact = inv_tx.copy()
        tx_fact = tx_fact.merge(
            fund_map, on="scheme_code", how="left"
        )
        tx_fact = tx_fact.merge(
            date_map, left_on="transaction_date", right_on="full_date", how="left"
        )
        tx_cols = [
            "transaction_id", "investor_id", "investor_name", "state",
            "kyc_status", "fund_id", "date_id", "scheme_code",
            "transaction_type", "transaction_date", "amount", "units",
        ]
        tx_fact = tx_fact[[c for c in tx_cols if c in tx_fact.columns]]
        tx_fact.to_sql("fact_transactions", conn, if_exists="replace", index=False)
        print(f"  fact_transactions     → {len(tx_fact):>6} rows")

        # ── fact_performance ──────────────────────────────────────────────────
        perf_fact = sp.copy()
        perf_fact = perf_fact.merge(fund_map, on="scheme_code", how="left")
        perf_cols = [
            "fund_id", "scheme_code", "year", "return_1m", "return_3m",
            "return_6m", "return_1y", "return_3y", "return_5y",
            "expense_ratio", "expense_ratio_flag", "sharpe_ratio", "alpha", "beta", "aum_cr",
        ]
        perf_fact = perf_fact[[c for c in perf_cols if c in perf_fact.columns]]
        perf_fact.to_sql("fact_performance", conn, if_exists="replace", index=False)
        print(f"  fact_performance      → {len(perf_fact):>6} rows")

        # ── fact_aum ──────────────────────────────────────────────────────────
        aum_fact = fp.copy()
        aum_fact = aum_fact.merge(fund_map, on="scheme_code", how="left")
        aum_cols = [
            "fund_id", "scheme_code", "scheme_name",
            "return_1m", "return_3m", "return_6m", "return_1y", "return_3y", "aum_cr",
        ]
        aum_fact = aum_fact[[c for c in aum_cols if c in aum_fact.columns]]
        aum_fact.to_sql("fact_aum", conn, if_exists="replace", index=False)
        print(f"  fact_aum              → {len(aum_fact):>6} rows")

        # ── fact_portfolio_holdings ───────────────────────────────────────────
        ph_fact = ph.copy()
        ph_fact = ph_fact.merge(fund_map, on="scheme_code", how="left")
        ph_fact.to_sql("fact_portfolio_holdings", conn, if_exists="replace", index=False)
        print(f"  fact_portfolio_holdings → {len(ph_fact):>5} rows")

    print("\n" + "=" * 60)
    print("  Verification: DB row counts vs processed CSV row counts")
    print("=" * 60)

    checks = [
        ("fact_nav",               len(nav)),
        ("fact_transactions",      len(inv_tx)),
        ("fact_performance",       len(sp)),
        ("fact_aum",               len(fp)),
        ("fact_portfolio_holdings",len(ph)),
        ("dim_benchmark",          len(bench)),
        ("dim_category",           len(acs)),
    ]

    all_ok = True
    with engine.connect() as conn:
        for table, csv_count in checks:
            db_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            status = "✓" if db_count == csv_count else "✗"
            if db_count != csv_count:
                all_ok = False
            print(f"  {status} {table:<30} CSV={csv_count:>6}  DB={db_count:>6}")

    if all_ok:
        print("\n  All row counts match. ✓")
    else:
        print("\n  ⚠ Some counts differ (FK joins may have filtered rows)")

    print(f"\n  Database saved to: {DB_FILE}")


if __name__ == "__main__":
    load_all()
