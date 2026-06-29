-- =============================================================================
-- queries.sql  –  10 Analytical SQL Queries
-- Database: bluestock_mf.db  |  Schema: Star Schema (dim + fact tables)
-- =============================================================================

-- ─── Query 1: Top 5 Funds by AUM ─────────────────────────────────────────────
-- Ranks all funds by their AUM in crores (descending order).
SELECT
    fa.scheme_code,
    fa.scheme_name,
    df.fund_house,
    df.category,
    fa.aum_cr,
    RANK() OVER (ORDER BY fa.aum_cr DESC) AS aum_rank
FROM fact_aum fa
JOIN dim_fund df ON fa.fund_id = df.rowid
ORDER BY fa.aum_cr DESC
LIMIT 5;


-- ─── Query 2: Average NAV per Month (across all funds) ───────────────────────
-- Shows how the average NAV across all funds trended each month.
SELECT
    dd.year,
    dd.month,
    dd.month_name,
    ROUND(AVG(fn.nav), 2) AS avg_nav,
    COUNT(DISTINCT fn.amfi_code) AS funds_in_month
FROM fact_nav fn
JOIN dim_date dd ON fn.date_id = dd.rowid
WHERE dd.is_weekend = 0               -- business days only
GROUP BY dd.year, dd.month
ORDER BY dd.year, dd.month;


-- ─── Query 3: SIP YoY Growth (total SIP amount per year) ─────────────────────
-- Compares total SIP inflows year-over-year using LAG().
SELECT
    dd.year,
    ROUND(SUM(ft.amount), 2)  AS total_sip_amount,
    COUNT(*)                   AS sip_count,
    ROUND(
        100.0 * (SUM(ft.amount) - LAG(SUM(ft.amount)) OVER (ORDER BY dd.year))
             / NULLIF(LAG(SUM(ft.amount)) OVER (ORDER BY dd.year), 0),
        2
    ) AS yoy_growth_pct
FROM fact_transactions ft
JOIN dim_date dd ON ft.date_id = dd.rowid
WHERE ft.transaction_type = 'SIP'
GROUP BY dd.year
ORDER BY dd.year;


-- ─── Query 4: Transactions by State ──────────────────────────────────────────
-- Shows which states drive the most investment activity and total amounts.
SELECT
    state,
    COUNT(*)                                AS total_transactions,
    ROUND(SUM(amount), 2)                   AS total_amount,
    ROUND(AVG(amount), 2)                   AS avg_amount,
    COUNT(DISTINCT investor_id)             AS unique_investors,
    SUM(CASE WHEN transaction_type = 'SIP' THEN 1 ELSE 0 END)        AS sip_count,
    SUM(CASE WHEN transaction_type = 'Lumpsum' THEN 1 ELSE 0 END)    AS lumpsum_count,
    SUM(CASE WHEN transaction_type = 'Redemption' THEN 1 ELSE 0 END) AS redemption_count
FROM fact_transactions
GROUP BY state
ORDER BY total_amount DESC;


-- ─── Query 5: Funds with Expense Ratio < 1% ──────────────────────────────────
-- Lists direct-plan funds that are cost-efficient (ER < 1%).
SELECT
    df.scheme_code,
    df.scheme_name,
    df.fund_house,
    df.category,
    df.subcategory,
    df.expense_ratio_direct   AS expense_ratio_pct,
    fa.aum_cr,
    fa.return_1y
FROM dim_fund df
JOIN fact_aum fa ON df.rowid = fa.fund_id
WHERE df.expense_ratio_direct < 1.0
  AND df.expense_ratio_direct IS NOT NULL
ORDER BY df.expense_ratio_direct ASC;


-- ─── Query 6: Best Performing Funds by 1-Year Return ─────────────────────────
-- Ranks funds by 1-year return (most recent year in fact_performance).
SELECT
    fp.scheme_code,
    df.scheme_name,
    df.fund_house,
    df.category,
    fp.year,
    fp.return_1y,
    fp.return_3y,
    fp.sharpe_ratio,
    RANK() OVER (PARTITION BY fp.year ORDER BY fp.return_1y DESC) AS perf_rank
FROM fact_performance fp
JOIN dim_fund df ON fp.fund_id = df.rowid
WHERE fp.return_1y IS NOT NULL
ORDER BY fp.year DESC, fp.return_1y DESC;


-- ─── Query 7: Monthly Net Flow (Inflow – Outflow) per Fund ───────────────────
-- Net investment activity: SIP + Lumpsum inflows minus Redemption outflows.
SELECT
    df.scheme_name,
    dd.year,
    dd.month,
    dd.month_name,
    ROUND(SUM(CASE WHEN ft.transaction_type IN ('SIP','Lumpsum') THEN ft.amount ELSE 0 END), 2) AS inflow,
    ROUND(SUM(CASE WHEN ft.transaction_type = 'Redemption' THEN ft.amount ELSE 0 END), 2)       AS outflow,
    ROUND(
        SUM(CASE WHEN ft.transaction_type IN ('SIP','Lumpsum') THEN ft.amount ELSE 0 END)
      - SUM(CASE WHEN ft.transaction_type = 'Redemption' THEN ft.amount ELSE 0 END),
    2) AS net_flow
FROM fact_transactions ft
JOIN dim_date dd ON ft.date_id = dd.rowid
JOIN dim_fund df ON ft.fund_id = df.rowid
GROUP BY df.scheme_name, dd.year, dd.month
ORDER BY dd.year, dd.month, net_flow DESC;


-- ─── Query 8: KYC Status Distribution Among Investors ────────────────────────
-- Analyses KYC compliance across the investor base.
SELECT
    kyc_status,
    COUNT(DISTINCT investor_id) AS unique_investors,
    COUNT(*)                    AS total_transactions,
    ROUND(SUM(amount), 2)       AS total_amount,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_transactions
FROM fact_transactions
GROUP BY kyc_status
ORDER BY total_transactions DESC;


-- ─── Query 9: Fund Category Performance Comparison ───────────────────────────
-- Compares average returns across Equity, Debt, and Hybrid categories.
SELECT
    df.category,
    df.subcategory,
    ROUND(AVG(fp.return_1m), 2)  AS avg_return_1m,
    ROUND(AVG(fp.return_3m), 2)  AS avg_return_3m,
    ROUND(AVG(fp.return_1y), 2)  AS avg_return_1y,
    ROUND(AVG(fp.return_3y), 2)  AS avg_return_3y,
    ROUND(AVG(fp.sharpe_ratio), 2) AS avg_sharpe,
    ROUND(AVG(fp.expense_ratio), 2) AS avg_expense_ratio,
    COUNT(DISTINCT fp.scheme_code) AS num_schemes
FROM fact_performance fp
JOIN dim_fund df ON fp.fund_id = df.rowid
GROUP BY df.category, df.subcategory
ORDER BY avg_return_1y DESC;


-- ─── Query 10: Investor Cohort Analysis – High-Value vs Regular SIP ──────────
-- Segments investors by SIP ticket size: Premium (≥5000), Regular (1000-4999), Micro (<1000).
SELECT
    CASE
        WHEN ft.amount >= 5000 THEN 'Premium SIP (≥₹5000)'
        WHEN ft.amount >= 1000 THEN 'Regular SIP (₹1000–₹4999)'
        ELSE                        'Micro SIP (<₹1000)'
    END AS sip_tier,
    COUNT(DISTINCT ft.investor_id)  AS unique_investors,
    COUNT(*)                         AS total_sips,
    ROUND(AVG(ft.amount), 2)         AS avg_sip_amount,
    ROUND(SUM(ft.amount), 2)         AS total_invested,
    ft.state,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_all_sips
FROM fact_transactions ft
WHERE ft.transaction_type = 'SIP'
GROUP BY sip_tier, ft.state
ORDER BY total_invested DESC
LIMIT 30;
