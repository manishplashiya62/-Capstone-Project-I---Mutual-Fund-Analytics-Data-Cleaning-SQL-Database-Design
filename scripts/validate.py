"""
validate.py
===========
Post-load validation checks on the SQLite database.
Prints a pass/fail report for each check.
"""
import os
import sqlite3

BASE   = os.path.join(os.path.dirname(__file__), "..")
DB     = os.path.join(BASE, "database", "bluestock_mf.db")

conn   = sqlite3.connect(DB)
cursor = conn.cursor()

checks = []

def run(description, sql, expected_fn):
    cursor.execute(sql)
    result = cursor.fetchone()[0]
    ok = expected_fn(result)
    status = "PASS ✓" if ok else "FAIL ✗"
    checks.append((status, description, result))

# 1. No negative NAV
run("fact_nav: no NAV ≤ 0",
    "SELECT COUNT(*) FROM fact_nav WHERE nav <= 0",
    lambda x: x == 0)

# 2. No negative transaction amounts
run("fact_transactions: no amount ≤ 0",
    "SELECT COUNT(*) FROM fact_transactions WHERE amount <= 0",
    lambda x: x == 0)

# 3. All transaction_types are valid
run("fact_transactions: all types valid",
    "SELECT COUNT(*) FROM fact_transactions WHERE transaction_type NOT IN ('SIP','Lumpsum','Redemption')",
    lambda x: x == 0)

# 4. All KYC statuses are valid
run("fact_transactions: all KYC statuses valid",
    "SELECT COUNT(*) FROM fact_transactions WHERE kyc_status NOT IN ('KYC_VERIFIED','KYC_PENDING','KYC_REJECTED')",
    lambda x: x == 0)

# 5. expense_ratio_direct in [0.1, 2.5] (or NULL)
run("dim_fund: expense_ratio_direct in valid range",
    "SELECT COUNT(*) FROM dim_fund WHERE expense_ratio_direct IS NOT NULL AND (expense_ratio_direct < 0.1 OR expense_ratio_direct > 2.5)",
    lambda x: x == 0)

# 6. dim_date has no duplicate dates
run("dim_date: no duplicate full_date values",
    "SELECT COUNT(*) - COUNT(DISTINCT full_date) FROM dim_date",
    lambda x: x == 0)

# 7. fact_nav: no duplicate (amfi_code, date_id)
run("fact_nav: no duplicate (amfi_code, date_id)",
    "SELECT COUNT(*) - COUNT(DISTINCT amfi_code || '|' || date_id) FROM fact_nav",
    lambda x: x == 0)

# 8. fact_transactions: no duplicate transaction_id
run("fact_transactions: no duplicate transaction_id",
    "SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM fact_transactions",
    lambda x: x == 0)

# 9. dim_fund scheme_codes are unique
run("dim_fund: no duplicate scheme_code",
    "SELECT COUNT(*) - COUNT(DISTINCT scheme_code) FROM dim_fund",
    lambda x: x == 0)

# 10. All fact_nav rows have a valid fund_id
run("fact_nav: all fund_id FK resolvable",
    "SELECT COUNT(*) FROM fact_nav WHERE fund_id IS NULL",
    lambda x: x == 0)

# 11. Minimum table row counts
run("fact_transactions: ≥ 1000 rows",
    "SELECT COUNT(*) FROM fact_transactions",
    lambda x: x >= 1000)

run("fact_nav: ≥ 10 rows",
    "SELECT COUNT(*) FROM fact_nav",
    lambda x: x >= 10)

# ─── Print report ─────────────────────────────────────────────────────────────
print("=" * 60)
print("  Bluestock MF – Database Validation Report")
print("=" * 60)
total = len(checks)
passed = sum(1 for s, _, _ in checks if "PASS" in s)
for status, desc, result in checks:
    print(f"  {status}  {desc}  (value={result})")
print("─" * 60)
print(f"  {passed}/{total} checks passed")
if passed == total:
    print("  ✅ All checks passed! Database is clean and valid.")
else:
    print(f"  ⚠ {total - passed} check(s) failed. Review above.")

conn.close()
