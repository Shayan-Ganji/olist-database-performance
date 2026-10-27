-- ==============================================================================
-- Stored Procedures: Idempotent Analytical Snapshot Materializer
-- Stage 2: Database Performance, Index Optimization & Routines
-- Author: Shayan Ganji
--
-- GUARANTEES:
-- 1. Idempotency: Re-running for an existing month cleanly updates records without duplicates.
-- 2. Atomicity: In case of unhandled error, transactions are fully rolled back without partial data.
-- ==============================================================================

CREATE OR REPLACE PROCEDURE olist.sp_refresh_monthly_category_snapshot(
    p_month DATE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_date TIMESTAMPTZ;
    v_end_date TIMESTAMPTZ;
    v_inserted_rows INT := 0;
BEGIN
    -- Validate parameter
    IF p_month IS NULL THEN
        RAISE EXCEPTION 'Target month parameter cannot be NULL.';
    END IF;

    -- Normalize parameter to beginning of target month
    v_start_date := DATE_TRUNC('month', p_month::timestamp);
    v_end_date := v_start_date + INTERVAL '1 month';

    -- Step 1: Idempotent purge of existing snapshot for target month
    DELETE FROM olist.snapshot_monthly_category_analytics
    WHERE order_month = v_start_date::date;

    -- Step 2: Compute and insert aggregated snapshot metrics
    INSERT INTO olist.snapshot_monthly_category_analytics (
        order_month,
        category,
        total_revenue,
        unique_orders,
        avg_order_value,
        refreshed_at
    )
    SELECT 
        v_start_date::date AS order_month,
        COALESCE(pct.product_category_name_english, 'uncategorized') AS category,
        SUM(oi.price) AS total_revenue,
        COUNT(DISTINCT o.order_id) AS unique_orders,
        ROUND(SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS avg_order_value,
        CURRENT_TIMESTAMP AS refreshed_at
    FROM olist.orders o
    JOIN olist.order_items oi ON o.order_id = oi.order_id
    JOIN olist.products p ON oi.product_id = p.product_id
    LEFT JOIN olist.product_category_translation pct ON p.product_category_name = pct.product_category_name
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= v_start_date
      AND o.order_purchase_timestamp < v_end_date
    GROUP BY 1, 2;

    GET DIAGNOSTICS v_inserted_rows = ROW_COUNT;
    RAISE NOTICE 'Idempotent snapshot refreshed for month %: % rows inserted.', v_start_date::date, v_inserted_rows;

EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Transaction aborted during snapshot refresh for month %: %', p_month, SQLERRM;
END;
$$;
