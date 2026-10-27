-- ==============================================================================
-- Schema Definition: olist (Brazilian E-Commerce Benchmark Schema)
-- Stage 2: Database Performance, Index Optimization & Execution Plan Analysis
-- Author: Shayan Ganji
-- ==============================================================================

DROP SCHEMA IF EXISTS olist CASCADE;
CREATE SCHEMA olist;

-- 1. Product Category Translations Reference Table
CREATE TABLE IF NOT EXISTS olist.product_category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100) NOT NULL
);

-- 2. Customers Table
CREATE TABLE IF NOT EXISTS olist.customers (
    customer_id CHAR(32) PRIMARY KEY,
    customer_unique_id CHAR(32) NOT NULL,
    customer_zip_code_prefix INT NOT NULL,
    customer_city VARCHAR(100) NOT NULL,
    customer_state CHAR(2) NOT NULL
);

-- 3. Products Table
CREATE TABLE IF NOT EXISTS olist.products (
    product_id CHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(100) REFERENCES olist.product_category_translation(product_category_name) ON DELETE SET NULL,
    product_name_lenght INT,
    product_description_lenght INT,
    product_photos_qty INT,
    product_weight_g INT,
    product_length_cm INT,
    product_height_cm INT,
    product_width_cm INT
);

-- 4. Sellers Table
CREATE TABLE IF NOT EXISTS olist.sellers (
    seller_id CHAR(32) PRIMARY KEY,
    seller_zip_code_prefix INT NOT NULL,
    seller_city VARCHAR(100) NOT NULL,
    seller_state CHAR(2) NOT NULL
);

-- 5. Orders Table (Central Fact / Coordinator Entity)
CREATE TABLE IF NOT EXISTS olist.orders (
    order_id CHAR(32) PRIMARY KEY,
    customer_id CHAR(32) NOT NULL REFERENCES olist.customers(customer_id),
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp TIMESTAMPTZ NOT NULL,
    order_approved_at TIMESTAMPTZ,
    order_delivered_carrier_date TIMESTAMPTZ,
    order_delivered_customer_date TIMESTAMPTZ,
    order_estimated_delivery_date TIMESTAMPTZ NOT NULL
);

-- 6. Order Items Table (Detailed Transactions)
CREATE TABLE IF NOT EXISTS olist.order_items (
    order_id CHAR(32) NOT NULL REFERENCES olist.orders(order_id) ON DELETE CASCADE,
    order_item_id INT NOT NULL,
    product_id CHAR(32) NOT NULL REFERENCES olist.products(product_id),
    seller_id CHAR(32) NOT NULL REFERENCES olist.sellers(seller_id),
    shipping_limit_date TIMESTAMPTZ NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    freight_value NUMERIC(10, 2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

-- 7. Order Payments Table (Payment Methods & Installments)
CREATE TABLE IF NOT EXISTS olist.order_payments (
    order_id CHAR(32) NOT NULL REFERENCES olist.orders(order_id) ON DELETE CASCADE,
    payment_sequential INT NOT NULL,
    payment_type VARCHAR(20) NOT NULL,
    payment_installments INT NOT NULL CHECK (payment_installments >= 0),
    payment_value NUMERIC(10, 2) NOT NULL CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

-- 8. Order Reviews Table (Composite PK prevents duplicate review_id crash)
CREATE TABLE IF NOT EXISTS olist.order_reviews (
    review_id CHAR(32) NOT NULL,
    order_id CHAR(32) NOT NULL REFERENCES olist.orders(order_id) ON DELETE CASCADE,
    review_score INT NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMPTZ NOT NULL,
    review_answer_timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (review_id, order_id)
);

-- 9. Geolocation Table (Coordinates & Zip code metadata)
CREATE TABLE IF NOT EXISTS olist.geolocation (
    geolocation_id BIGSERIAL PRIMARY KEY,
    geolocation_zip_code_prefix INT NOT NULL,
    geolocation_lat DOUBLE PRECISION NOT NULL,
    geolocation_lng DOUBLE PRECISION NOT NULL,
    geolocation_city VARCHAR(100) NOT NULL,
    geolocation_state CHAR(2) NOT NULL
);
