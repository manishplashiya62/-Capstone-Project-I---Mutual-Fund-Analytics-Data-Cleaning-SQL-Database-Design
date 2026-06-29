"""
Generate synthetic raw CSV files that are missing from the Drive download:
  - investor_transactions.csv
  - scheme_performance.csv
These are written to data/raw/ alongside the existing files.
"""
import pandas as pd
import numpy as np
import os
import random
from datetime import date, timedelta

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
os.makedirs(RAW, exist_ok=True)

random.seed(42)
np.random.seed(42)

SCHEME_CODES = [119551, 120503, 118632, 119092, 120841, 125497]
SCHEME_NAMES = {
    119551: "SBI Bluechip Direct",
    120503: "ICICI Bluechip Direct",
    118632: "Nippon India Large Cap Direct",
    119092: "Axis Bluechip Direct",
    120841: "Kotak Bluechip Direct",
    125497: "HDFC Top 100 Direct",
}

STATES = [
    "Maharashtra", "Karnataka", "Delhi", "Tamil Nadu", "Gujarat",
    "Telangana", "Rajasthan", "West Bengal", "Uttar Pradesh", "Kerala",
]

KYC_STATUSES = ["KYC_VERIFIED", "KYC_PENDING", "KYC_REJECTED"]
TX_TYPES_RAW = [
    "sip", "SIP", "Sip",          # will be standardised
    "Lumpsum", "lumpsum", "LUMPSUM",
    "Redemption", "REDEMPTION", "redemption",
    "Purchase",                     # same as Lumpsum – noisy source
]

# ── investor_transactions.csv ─────────────────────────────────────────────────
rows = []
start = date(2023, 1, 1)
for i in range(1, 501):
    investor_id = f"INV{i:05d}"
    name = f"Investor_{i}"
    state = random.choice(STATES)
    kyc = random.choices(KYC_STATUSES, weights=[0.80, 0.15, 0.05])[0]
    n_tx = random.randint(1, 6)
    for _ in range(n_tx):
        sc = random.choice(SCHEME_CODES)
        tx_type = random.choice(TX_TYPES_RAW)
        tx_date = start + timedelta(days=random.randint(0, 548))
        if "redempt" in tx_type.lower():
            amount = round(random.uniform(500, 50000), 2)
        elif "sip" in tx_type.lower():
            amount = random.choice([500, 1000, 2000, 5000, 10000])
        else:
            amount = round(random.uniform(1000, 500000), 2)

        # Inject some noise
        if random.random() < 0.02:
            amount = -amount          # negative – will be flagged
        if random.random() < 0.01:
            tx_date_str = tx_date.strftime("%d-%m-%Y")  # wrong format
        else:
            tx_date_str = tx_date.strftime("%Y-%m-%d")

        rows.append({
            "transaction_id": f"TX{len(rows)+1:07d}",
            "investor_id": investor_id,
            "investor_name": name,
            "state": state,
            "kyc_status": kyc,
            "scheme_code": sc,
            "scheme_name": SCHEME_NAMES[sc],
            "transaction_type": tx_type,
            "transaction_date": tx_date_str,
            "amount": amount,
            "units": round(amount / random.uniform(100, 200), 4) if amount > 0 else 0,
        })

inv_df = pd.DataFrame(rows)
# Inject a few duplicates
dup = inv_df.sample(5, random_state=1)
inv_df = pd.concat([inv_df, dup], ignore_index=True)
out_path = os.path.join(RAW, "investor_transactions.csv")
inv_df.to_csv(out_path, index=False)
print(f"✓ investor_transactions.csv  → {len(inv_df)} rows")

# ── scheme_performance.csv ────────────────────────────────────────────────────
perf_rows = []
for sc in SCHEME_CODES:
    for yr in range(2021, 2025):
        perf_rows.append({
            "scheme_code": sc,
            "scheme_name": SCHEME_NAMES[sc],
            "year": yr,
            "return_1m": round(np.random.uniform(1.0, 5.0), 2),
            "return_3m": round(np.random.uniform(4.0, 12.0), 2),
            "return_6m": round(np.random.uniform(8.0, 20.0), 2),
            "return_1y": round(np.random.uniform(15.0, 35.0), 2),
            "return_3y": round(np.random.uniform(12.0, 25.0), 2),
            "return_5y": round(np.random.uniform(10.0, 22.0), 2) if yr <= 2022 else None,
            "expense_ratio": round(np.random.uniform(0.40, 2.80), 2),  # some will be out of range
            "sharpe_ratio": round(np.random.uniform(0.5, 2.5), 2),
            "alpha": round(np.random.uniform(-2.0, 5.0), 2),
            "beta": round(np.random.uniform(0.7, 1.3), 2),
            "aum_cr": round(np.random.uniform(3000, 20000), 0),
        })

# Inject non-numeric noise
perf_rows[3]["return_1m"] = "N/A"      # will be flagged
perf_rows[7]["expense_ratio"] = "n.a."  # will be flagged

perf_df = pd.DataFrame(perf_rows)
out_path = os.path.join(RAW, "scheme_performance.csv")
perf_df.to_csv(out_path, index=False)
print(f"✓ scheme_performance.csv     → {len(perf_df)} rows")

print("\nAll missing raw files generated successfully.")
