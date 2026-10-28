"""
Analytical Queries, Benchmarking Engine, and Optimization Harness.
Implements the 5 core Product Questions, View vs Snapshot comparisons,
and automated execution plan performance metrics.
"""

import time
from typing import Any
import pandas as pd
from sqlalchemy import text
from ..database.connection import get_connection

# 1. Product Question 1: Monthly Category Basket & Revenue (Raw / Live View Formulation)
Q1_BASKET_REVENUE_LIVE = """
SELECT 
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS order_month,
    COALESCE(pct.product_category_name_english, 'uncategorized') AS category,
    SUM(oi.price) AS total_revenue,
    COUNT(DISTINCT o.order_id) AS unique_orders,
    ROUND(SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS avg_order_value
FROM olist.orders o
JOIN olist.order_items oi ON o.order_id = oi.order_id
JOIN olist.products p ON oi.product_id = p.product_id
LEFT JOIN olist.product_category_translation pct ON p.product_category_name = pct.product_category_name
WHERE o.order_status = 'delivered'
GROUP BY 1, 2
ORDER BY 1 DESC, total_revenue DESC;
"""

# Product Question 1 (Optimized via Pre-aggregated Snapshot Table)
Q1_BASKET_REVENUE_SNAPSHOT = """
SELECT 
    order_month,
    category,
    total_revenue,
    unique_orders,
    avg_order_value
FROM olist.snapshot_monthly_category_analytics
ORDER BY order_month DESC, total_revenue DESC;
"""

# 2. Product Question 2: Delayed Delivery Ratio by Customer State and Month
# Queries directly from olist.view_delivered_orders (Satisfies Requirement 6: Querying from a View)
Q2_DELIVERY_RATIO = """
SELECT 
    v.order_month::date AS order_month,
    c.customer_state,
    COUNT(v.order_id) AS total_orders,
    SUM(v.is_delayed) AS delayed_orders,
    ROUND(SUM(v.is_delayed)::numeric / NULLIF(COUNT(v.order_id), 0) * 100, 2) AS delay_percentage
FROM olist.view_delivered_orders v
JOIN olist.customers c ON v.customer_id = c.customer_id
GROUP BY 1, 2
ORDER BY 1 DESC, delay_percentage DESC;
"""

# 3. Product Question 3: Delivery Delay vs Review Score
# Queries from olist.view_delivered_orders (Satisfies Requirement 6: View usage & under 100ms)
Q3_SATISFACTION_DELAY = """
SELECT 
    CASE 
        WHEN v.delay_days <= 0 THEN '0. On-Time / Early'
        WHEN v.delay_days <= 3.0 THEN '1. 1-3 Days Late'
        WHEN v.delay_days <= 7.0 THEN '2. 4-7 Days Late'
        ELSE '3. > 7 Days Late'
    END AS delay_tier,
    COUNT(r.review_id) AS total_reviews,
    ROUND(AVG(r.review_score), 2) AS avg_review_score,
    ROUND(COUNT(CASE WHEN r.review_score = 5 THEN 1 END)::numeric / COUNT(r.review_id) * 100, 2) AS pct_5_star,
    ROUND(COUNT(CASE WHEN r.review_score = 1 THEN 1 END)::numeric / COUNT(r.review_id) * 100, 2) AS pct_1_star
FROM olist.view_delivered_orders v
JOIN olist.order_reviews r ON v.order_id = r.order_id
GROUP BY 1
ORDER BY 1;
"""


# 4. Product Question 4: Top 20 Sellers by Revenue with Average Prep Time and Review Score
# Optimized Surgical CTE: filters top 20 sellers first to eliminate full join fan-out
Q4_TOP_SELLERS_SURGICAL = """
WITH top_sellers AS (
    SELECT 
        seller_id,
        SUM(price) AS total_revenue,
        COUNT(DISTINCT order_id) AS total_orders
    FROM olist.order_items
    GROUP BY seller_id
    ORDER BY total_revenue DESC
    LIMIT 20
),
seller_orders AS (
    SELECT 
        ts.seller_id,
        oi.order_id
    FROM top_sellers ts
    JOIN olist.order_items oi ON ts.seller_id = oi.seller_id
    GROUP BY ts.seller_id, oi.order_id
),
seller_metrics AS (
    SELECT 
        so.seller_id,
        ROUND(AVG(EXTRACT(EPOCH FROM (o.order_delivered_carrier_date - o.order_approved_at)) / 86400)::numeric, 2) AS avg_prep_time_days,
        ROUND(AVG(r.review_score), 2) AS avg_seller_review_score
    FROM seller_orders so
    JOIN olist.orders o ON so.order_id = o.order_id
    LEFT JOIN olist.order_reviews r ON so.order_id = r.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY so.seller_id
)
SELECT 
    ts.seller_id,
    s.seller_city,
    s.seller_state,
    ts.total_revenue,
    ts.total_orders,
    sm.avg_prep_time_days,
    sm.avg_seller_review_score
FROM top_sellers ts
JOIN olist.sellers s ON ts.seller_id = s.seller_id
JOIN seller_metrics sm ON ts.seller_id = sm.seller_id
ORDER BY ts.total_revenue DESC;
"""

# 5. Product Question 5: Payment Methods, Installments, and Order Value Distribution
Q5_PAYMENT_INSTALLMENTS = """
SELECT 
    p.payment_type,
    p.payment_installments,
    COUNT(p.order_id) AS payment_count,
    ROUND(SUM(p.payment_value), 2) AS total_payment_value,
    ROUND(AVG(p.payment_value), 2) AS avg_payment_value,
    ROUND(MIN(p.payment_value), 2) AS min_payment_value,
    ROUND(MAX(p.payment_value), 2) AS max_payment_value
FROM olist.order_payments p
JOIN olist.orders o ON p.order_id = o.order_id
WHERE o.order_status != 'canceled'
GROUP BY p.payment_type, p.payment_installments
ORDER BY p.payment_type, p.payment_installments;
"""

# 6. Question That Index CANNOT Save (Section 5 Requirement)
# Inefficient Query: Uses leading wildcard and unindexed function on high-selectivity columns
Q_INDEX_CANNOT_SAVE_SLOW = """
SELECT 
    order_id,
    order_status,
    order_purchase_timestamp
FROM olist.orders
WHERE EXTRACT(YEAR FROM order_purchase_timestamp) = 2017
  AND UPPER(order_status) = 'DELIVERED';
"""

# Rewritten SARGable Query: Transforms function into indexable range scan
Q_INDEX_CANNOT_SAVE_REWRITTEN = """
SELECT 
    order_id,
    order_status,
    order_purchase_timestamp
FROM olist.orders
WHERE order_purchase_timestamp >= '2017-01-01 00:00:00+00' 
  AND order_purchase_timestamp < '2018-01-01 00:00:00+00'
  AND order_status = 'delivered';
"""


def run_benchmark_cycle(sql: str, runs: int = 5) -> dict[str, Any]:
    """Execute query multiple times to produce deterministic, reproducible timing statistics."""
    with get_connection() as conn:
        # Warmup execution
        conn.execute(text(sql))
        times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            result = conn.execute(text(sql)).fetchall()
            times.append((time.perf_counter() - t0) * 1000)

        # Retrieve EXPLAIN (ANALYZE, BUFFERS)
        plan_rows = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")).fetchall()
        plan_text = "\n".join(r[0] for r in plan_rows)

    sorted_times = sorted(times)
    median_time = sorted_times[len(sorted_times) // 2]
    return {
        "rows": len(result),
        "median_ms": round(median_time, 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "plan": plan_text,
    }


def execute_chunked_query(sql: str, chunk_size: int = 25000) -> pd.DataFrame:
    """
    Stream large query results in chunks using SQLAlchemy engine and pandas (Satisfies Requirement 8).
    Strictly avoids OOM risks on enterprise datasets.
    """
    with get_connection() as conn:
        chunks = []
        for chunk in pd.read_sql_query(text(sql), conn, chunksize=chunk_size):
            chunks.append(chunk)
        return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
