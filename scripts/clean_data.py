"""
clean_data.py
=============
Cleans all raw CSVs and writes 10 processed files to data/processed/.

Cleaning steps per file:
  nav_history          – parse dates, sort by scheme_code+date, ffill missing NAV,
                         remove duplicates, validate NAV > 0
  investor_transactions – standardise transaction_type, validate amount > 0,
                          fix date formats, validate kyc_status enum
  scheme_performance   – coerce returns to numeric, flag anomalies,
                         check expense_ratio in [0.1, 2.5]
  fund_master          – drop duplicate scheme_codes, strip whitespace
  scheme_metadata      – parse dates, validate expense_ratio
  fund_performance     – validate return columns numeric, compute aum sanity
  portfolio_holdings   – validate weight_pct sums near 100 per scheme
  amfi_category_stats  – validate numeric columns
  benchmark_data       – validate return columns
  market_data          – parse dates, validate index values > 0
"""

import os
import sys
import pandas as pd
import numpy as np

BASE = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(BASE, "data", "raw")
PROC = os.path.join(BASE, "data", "processed")
os.makedirs(PROC, exist_ok=True)

VALID_KYC = {"KYC_VERIFIED", "KYC_PENDING", "KYC_REJECTED"}

# ─── helpers ──────────────────────────────────────────────────────────────────

def report(name, issues):
    """Print a summary of cleaning steps."""
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")
    for issue in issues:
        print(f"  • {issue}")


def safe_to_numeric(series, coerce=True):
    return pd.to_numeric(series, errors="coerce" if coerce else "raise")


def standardise_tx_type(val):
    v = str(val).strip().lower()
    if v in ("sip",):
        return "SIP"
    if v in ("lumpsum", "purchase"):
        return "Lumpsum"
    if v in ("redemption",):
        return "Redemption"
    return val.strip().title()


# ─── 1. nav_history.csv ───────────────────────────────────────────────────────

def clean_nav_history():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "nav_history.csv"))
    orig_len = len(df)

    # Parse date
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df["date"].isna().sum()
    if bad_dates:
        issues.append(f"Dropped {bad_dates} rows with unparseable dates")
        df = df.dropna(subset=["date"])

    # Validate NAV > 0
    df["nav"] = safe_to_numeric(df["nav"])
    bad_nav = (df["nav"] <= 0) | df["nav"].isna()
    if bad_nav.sum():
        issues.append(f"Removed {bad_nav.sum()} rows where NAV ≤ 0 or non-numeric")
        df = df[~bad_nav]

    # Sort by scheme_code + date
    df = df.sort_values(["scheme_code", "date"]).reset_index(drop=True)

    # Build a full date range per scheme and forward-fill
    full_ranges = []
    for sc, grp in df.groupby("scheme_code"):
        date_range = pd.date_range(grp["date"].min(), grp["date"].max(), freq="D")
        temp = pd.DataFrame({"date": date_range, "scheme_code": sc})
        temp = temp.merge(grp[["date", "nav"]], on="date", how="left")
        temp["nav"] = temp["nav"].ffill()
        full_ranges.append(temp)
    df_filled = pd.concat(full_ranges, ignore_index=True)
    issues.append(f"Forward-filled {len(df_filled) - len(df)} weekend/holiday rows")

    # Remove duplicates
    before = len(df_filled)
    df_filled = df_filled.drop_duplicates(subset=["scheme_code", "date"])
    if len(df_filled) < before:
        issues.append(f"Removed {before - len(df_filled)} duplicate rows")

    # Rename to match task spec column name
    df_filled = df_filled.rename(columns={"scheme_code": "amfi_code"})
    df_filled["date"] = df_filled["date"].dt.strftime("%Y-%m-%d")

    issues.append(f"Rows: {orig_len} raw → {len(df_filled)} processed")
    df_filled.to_csv(os.path.join(PROC, "nav_history.csv"), index=False)
    report("nav_history.csv", issues)
    return df_filled


# ─── 2. investor_transactions.csv ─────────────────────────────────────────────

def clean_investor_transactions():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "investor_transactions.csv"))
    orig_len = len(df)

    # Fix date formats – handle both YYYY-MM-DD and DD-MM-YYYY
    def parse_date(val):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return pd.to_datetime(val, format=fmt)
            except Exception:
                pass
        return pd.NaT

    df["transaction_date"] = df["transaction_date"].apply(parse_date)
    bad_dates = df["transaction_date"].isna().sum()
    if bad_dates:
        issues.append(f"Dropped {bad_dates} rows with unparseable dates")
        df = df.dropna(subset=["transaction_date"])

    # Standardise transaction_type
    before_types = df["transaction_type"].unique().tolist()
    df["transaction_type"] = df["transaction_type"].apply(standardise_tx_type)
    after_types = df["transaction_type"].unique().tolist()
    issues.append(f"Standardised transaction_type: {before_types} → {after_types}")

    # Validate amount > 0
    df["amount"] = safe_to_numeric(df["amount"])
    bad_amount = df["amount"] <= 0
    if bad_amount.sum():
        issues.append(f"Removed {bad_amount.sum()} rows where amount ≤ 0")
        df = df[~bad_amount]

    # Validate KYC status enum
    invalid_kyc = ~df["kyc_status"].isin(VALID_KYC)
    if invalid_kyc.sum():
        issues.append(f"Found {invalid_kyc.sum()} invalid KYC values → set to KYC_PENDING")
        df.loc[invalid_kyc, "kyc_status"] = "KYC_PENDING"

    # Remove duplicates
    before = len(df)
    df = df.drop_duplicates(subset=["transaction_id"])
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate transaction_id rows")

    df["transaction_date"] = df["transaction_date"].dt.strftime("%Y-%m-%d")
    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "investor_transactions.csv"), index=False)
    report("investor_transactions.csv", issues)
    return df


# ─── 3. scheme_performance.csv ────────────────────────────────────────────────

def clean_scheme_performance():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "scheme_performance.csv"))
    orig_len = len(df)

    return_cols = ["return_1m", "return_3m", "return_6m", "return_1y",
                   "return_3y", "return_5y", "sharpe_ratio", "alpha", "beta"]

    # Coerce return columns to numeric
    for col in return_cols:
        if col in df.columns:
            before_nulls = df[col].isna().sum()
            df[col] = safe_to_numeric(df[col])
            after_nulls = df[col].isna().sum()
            new_nulls = after_nulls - before_nulls
            if new_nulls > 0:
                issues.append(f"Coerced {new_nulls} non-numeric values to NaN in '{col}'")

    # Expense ratio validation
    df["expense_ratio"] = safe_to_numeric(df["expense_ratio"])
    bad_er = df["expense_ratio"].isna()
    if bad_er.sum():
        issues.append(f"Coerced {bad_er.sum()} non-numeric expense_ratio → NaN")

    out_of_range = ((df["expense_ratio"] < 0.1) | (df["expense_ratio"] > 2.5)) & df["expense_ratio"].notna()
    if out_of_range.sum():
        issues.append(f"Flagged {out_of_range.sum()} rows with expense_ratio outside [0.1%, 2.5%]")
        df["expense_ratio_flag"] = out_of_range

    # Flag anomalous returns (e.g. return_1y > 100 or < -50 is suspicious)
    if "return_1y" in df.columns:
        anomaly = ((df["return_1y"] > 100) | (df["return_1y"] < -50)) & df["return_1y"].notna()
        if anomaly.sum():
            issues.append(f"Flagged {anomaly.sum()} rows with anomalous return_1y")
            df["return_1y_flag"] = anomaly

    # Remove duplicates
    before = len(df)
    df = df.drop_duplicates(subset=["scheme_code", "year"])
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "scheme_performance.csv"), index=False)
    report("scheme_performance.csv", issues)
    return df


# ─── 4. fund_master.csv ───────────────────────────────────────────────────────

def clean_fund_master():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "fund_master.csv"))
    orig_len = len(df)

    # Strip whitespace from string columns
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].str.strip()

    # Drop rows with null scheme_code
    before = len(df)
    df = df.dropna(subset=["scheme_code"])
    if len(df) < before:
        issues.append(f"Dropped {before - len(df)} rows with null scheme_code")

    # Drop duplicate scheme_code + scheme_name combos
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} fully duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "fund_master.csv"), index=False)
    report("fund_master.csv", issues)
    return df


# ─── 5. scheme_metadata.csv ───────────────────────────────────────────────────

def clean_scheme_metadata():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "scheme_metadata.csv"))
    orig_len = len(df)

    for dcol in ["launch_date", "direct_plan_date"]:
        df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
        bad = df[dcol].isna().sum()
        if bad:
            issues.append(f"Unparseable dates in '{dcol}': {bad}")

    for rcol in ["expense_ratio_direct", "expense_ratio_regular"]:
        df[rcol] = safe_to_numeric(df[rcol])
        out = ((df[rcol] < 0.1) | (df[rcol] > 2.5)) & df[rcol].notna()
        if out.sum():
            issues.append(f"Out-of-range expense_ratio in '{rcol}': {out.sum()} rows")

    df["launch_date"] = df["launch_date"].dt.strftime("%Y-%m-%d")
    df["direct_plan_date"] = df["direct_plan_date"].dt.strftime("%Y-%m-%d")

    before = len(df)
    df = df.drop_duplicates(subset=["scheme_code"])
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate scheme_code rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "scheme_metadata.csv"), index=False)
    report("scheme_metadata.csv", issues)
    return df


# ─── 6. fund_performance.csv ──────────────────────────────────────────────────

def clean_fund_performance():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "fund_performance.csv"))
    orig_len = len(df)

    return_cols = ["return_1m", "return_3m", "return_6m", "return_1y", "return_3y"]
    for col in return_cols:
        if col in df.columns:
            df[col] = safe_to_numeric(df[col])

    df["aum_cr"] = safe_to_numeric(df["aum_cr"])
    negative_aum = (df["aum_cr"] < 0) & df["aum_cr"].notna()
    if negative_aum.sum():
        issues.append(f"Flagged {negative_aum.sum()} rows with negative aum_cr")

    before = len(df)
    df = df.drop_duplicates(subset=["scheme_code"])
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "fund_performance.csv"), index=False)
    report("fund_performance.csv", issues)
    return df


# ─── 7. portfolio_holdings.csv ────────────────────────────────────────────────

def clean_portfolio_holdings():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "portfolio_holdings.csv"))
    orig_len = len(df)

    df["weight_pct"] = safe_to_numeric(df["weight_pct"])
    df["quantity_cr"] = safe_to_numeric(df["quantity_cr"])

    # Check weight sums per scheme
    sums = df.groupby("scheme_code")["weight_pct"].sum()
    abnormal = sums[(sums < 10) | (sums > 110)]
    if not abnormal.empty:
        issues.append(f"Schemes with unusual total weight: {abnormal.to_dict()}")

    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "portfolio_holdings.csv"), index=False)
    report("portfolio_holdings.csv", issues)
    return df


# ─── 8. amfi_category_stats.csv ───────────────────────────────────────────────

def clean_amfi_category_stats():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "amfi_category_stats.csv"))
    orig_len = len(df)

    for col in ["num_funds", "avg_aum_cr", "avg_return_1y"]:
        df[col] = safe_to_numeric(df[col])
        neg = (df[col] < 0) & df[col].notna()
        if neg.sum():
            issues.append(f"Negative values in '{col}': {neg.sum()} rows")

    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "amfi_category_stats.csv"), index=False)
    report("amfi_category_stats.csv", issues)
    return df


# ─── 9. benchmark_data.csv ────────────────────────────────────────────────────

def clean_benchmark_data():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "benchmark_data.csv"))
    orig_len = len(df)

    for col in ["return_1m", "return_3m", "return_6m", "return_1y"]:
        df[col] = safe_to_numeric(df[col])

    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate rows")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "benchmark_data.csv"), index=False)
    report("benchmark_data.csv", issues)
    return df


# ─── 10. market_data.csv ──────────────────────────────────────────────────────

def clean_market_data():
    issues = []
    df = pd.read_csv(os.path.join(RAW, "market_data.csv"))
    orig_len = len(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df["date"].isna().sum()
    if bad_dates:
        issues.append(f"Dropped {bad_dates} rows with unparseable dates")
        df = df.dropna(subset=["date"])

    index_cols = ["sensex", "nifty50", "midcap_index", "smallcap_index", "market_volume_cr"]
    for col in index_cols:
        df[col] = safe_to_numeric(df[col])
        neg = (df[col] <= 0) & df[col].notna()
        if neg.sum():
            issues.append(f"Found {neg.sum()} non-positive values in '{col}'")

    df = df.sort_values("date").reset_index(drop=True)
    before = len(df)
    df = df.drop_duplicates(subset=["date"])
    if len(df) < before:
        issues.append(f"Removed {before - len(df)} duplicate date rows")

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    issues.append(f"Rows: {orig_len} raw → {len(df)} processed")
    df.to_csv(os.path.join(PROC, "market_data.csv"), index=False)
    report("market_data.csv", issues)
    return df


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Mutual Fund Analytics – Data Cleaning Pipeline")
    print("=" * 60)

    cleaned = {}
    cleaned["nav_history"] = clean_nav_history()
    cleaned["investor_transactions"] = clean_investor_transactions()
    cleaned["scheme_performance"] = clean_scheme_performance()
    cleaned["fund_master"] = clean_fund_master()
    cleaned["scheme_metadata"] = clean_scheme_metadata()
    cleaned["fund_performance"] = clean_fund_performance()
    cleaned["portfolio_holdings"] = clean_portfolio_holdings()
    cleaned["amfi_category_stats"] = clean_amfi_category_stats()
    cleaned["benchmark_data"] = clean_benchmark_data()
    cleaned["market_data"] = clean_market_data()

    print("\n")
    print("=" * 60)
    print("  Cleaning Complete – Row Counts")
    print("=" * 60)
    for name, df in cleaned.items():
        print(f"  {name:<30} {len(df):>6} rows")

    # Verify 10 processed CSVs
    processed_files = os.listdir(PROC)
    print(f"\n  Processed CSVs in data/processed/: {len(processed_files)}")
    for f in sorted(processed_files):
        print(f"    • {f}")
