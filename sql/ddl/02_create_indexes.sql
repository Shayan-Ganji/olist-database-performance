-- ==============================================================================
-- Index Optimization Script: Evidence-Backed B-Tree Indexes
-- Stage 2: Database Performance & Query Optimization
-- Author: Shayan Ganji
--
-- STRICT DBA PRINCIPLE: Every index must have an EXPLAIN ANALYZE justification.
-- Redundant or unverified indexes are explicitly prohibited to prevent write amplification.
-- ==============================================================================

-- 1. Index on orders(customer_id)
-- Justification: Accelerates customer-to-order joins in Q2 (Delivery Ratio by State).
CREATE INDEX IF NOT EXISTS idx_orders_customer_id 
ON olist.orders (customer_id);

-- 2. Composite Covering Index on orders(order_status, order_purchase_timestamp)
-- Justification: Enables index-range scan for date partitioning and eliminates Seq Scan on 99k orders.
CREATE INDEX IF NOT EXISTS idx_orders_status_purchase 
ON olist.orders (order_status, order_purchase_timestamp);

-- 3. Composite Covering Index on order_items(seller_id, order_id, price)
-- Justification: Drastically speeds up Q4 (Top 20 Sellers) from 392ms to 152ms by providing
-- pre-sorted seller revenue aggregates directly from the index tree without table heap fetches.
CREATE INDEX IF NOT EXISTS idx_order_items_seller_order_price 
ON olist.order_items (seller_id, order_id, price);

-- 4. Foreign Key Index on order_items(product_id)
-- Justification: Accelerates product joins in Q1 and category revenue aggregation.
CREATE INDEX IF NOT EXISTS idx_order_items_product 
ON olist.order_items (product_id);

-- 5. Foreign Key Index on products(product_category_name)
-- Justification: Accelerates joins between products and category translation in Q1.
CREATE INDEX IF NOT EXISTS idx_products_category 
ON olist.products (product_category_name);

-- 6. Foreign Key Index on order_reviews(order_id)
-- Justification: Speeds up satisfaction joins in Q3 and seller review aggregates in Q4.
CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id 
ON olist.order_reviews (order_id);

-- 7. Foreign Key Index on order_payments(order_id)
-- Justification: Accelerates order payment lookups and prevents Seq Scan in Q5.
CREATE INDEX IF NOT EXISTS idx_order_payments_order_id 
ON olist.order_payments (order_id);

-- 8. EXPERIMENTAL / PROVABLY REDUNDANT INDEX (For Section 4 Hidden Cost Analysis)
-- Justification: An index on order_status ALONE. Since 97% of orders are 'delivered',
-- selectivity is near zero (~0.97). The optimizer refuses to use this index and performs
-- a Seq Scan instead, rendering this index pure overhead that slows down writes.
-- We measure its write penalty and subsequently drop it with proof.
CREATE INDEX IF NOT EXISTS idx_orders_status_redundant 
ON olist.orders (order_status);
