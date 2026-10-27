-- ==============================================================================
-- Views and Analytical Snapshots
-- Stage 2: Database Performance, Index Optimization & Reusability
-- Author: Shayan Ganji
-- ==============================================================================

-- 1. View 1: Single-Table View (Encapsulates status filters & derived temporal calculations)
CREATE OR REPLACE VIEW olist.view_delivered_orders AS
SELECT 
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    DATE_TRUNC('month', order_purchase_timestamp) AS order_month,
    CASE 
        WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1 
        ELSE 0 
    END AS is_delayed,
    ROUND(EXTRACT(EPOCH FROM (order_delivered_customer_date - order_estimated_delivery_date)) / 86400, 2) AS delay_days
FROM olist.orders
WHERE order_status = 'delivered' 
  AND order_delivered_customer_date IS NOT NULL;


-- 2. View 2: Multi-Table View (Encapsulates complex 4-way join across items, products, sellers, categories)
CREATE OR REPLACE VIEW olist.view_order_item_details AS
SELECT 
    oi.order_id,
    oi.order_item_id,
    oi.seller_id,
    s.seller_city,
    s.seller_state,
    oi.product_id,
    COALESCE(pct.product_category_name_english, 'uncategorized') AS category_english,
    oi.price,
    oi.freight_value,
    oi.shipping_limit_date
FROM olist.order_items oi
JOIN olist.products p ON oi.product_id = p.product_id
LEFT JOIN olist.product_category_translation pct ON p.product_category_name = pct.product_category_name
JOIN olist.sellers s ON oi.seller_id = s.seller_id;


-- 3. Analytical Snapshot Table (For Section 6 View vs Snapshot Performance Trade-off)
CREATE TABLE IF NOT EXISTS olist.snapshot_monthly_category_analytics (
    order_month DATE NOT NULL,
    category VARCHAR(100) NOT NULL,
    total_revenue NUMERIC(12, 2) NOT NULL,
    unique_orders INT NOT NULL,
    avg_order_value NUMERIC(10, 2) NOT NULL,
    refreshed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_month, category)
);
