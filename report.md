# Technical Architecture and Engineering Decision Report: Olist Database Performance & PostgreSQL Optimization
**Student:** Shayan Ganji  
**Laboratory:** Dotin Financial Technologies Lab - Term 3  
**Repository:** [https://github.com/Shayan-Ganji/olist-database-performance](https://github.com/Shayan-Ganji/olist-database-performance)  
**Language Toggle:** [English Version](report.md) | [نسخه فارسی](report.fa.md)  

---

## 1. Problem Formulation, Data Dimensions, and Boundary Assumptions

In this practical engineering challenge, acting in the capacity of a Database Administrator (DBA), the primary mandate was to design, implement, and benchmark a relational data platform capable of sustaining an enterprise e-commerce analytics workload under PostgreSQL 16. The production dataset comprises **1,847,423 records** partitioned across 10 relational tables: 9 normalized tables originating from the Brazilian e-commerce marketplace (Olist)—encompassing customer orders, order line items, payment gateways, review feedback, catalog products, sellers, and geospatial coordinates—alongside a curated dataset of municipal service requests (NYC 311, containing 297,899 records) injected directly from Stage 1 via an extensible sink adapter.

The engineering objective was to satisfy 5 analytical queries requested by the product team for an operational dashboard, within a **200 ms latency budget** per query. Without indexing and schema optimization, queries aggregating large tables experience high latency caused by sequential table scans, memory buffer pressure, and external merge sorts spilling to disk.

### Operational Boundary Assumptions:
- **Revenue Realization in Commercial Accounting:** Across all queries assessing Gross Merchandise Value (GMV), order counts, and Average Order Value (AOV), transactions were strictly filtered to delivered orders (`order_status = 'delivered'`). Incorporating canceled, unavailable, or in-process orders into liquidity metrics distorts cash-flow reporting and inflates historical revenue.
- **Relational Domain Isolation via Dedicated Schemas:** To prevent namespace collision between municipal civic telemetry and Brazilian commercial data within a single database (`olist_db`), strict schema segregation was established: `olist` encapsulates the commercial domain, while `nyc_311` isolates the public civic infrastructure dataset.
- **Foreign Key Integrity for Unmapped Catalog Categories:** Auditing raw product catalog translations revealed that two product categories (`pc_gamer` and small kitchen prep appliances) lacked English counterparts. To preserve strict foreign key relational integrity without discarding orphaned product records, missing category translations were deterministically seeded prior to dependent table loading.

---

## 2. Architectural Decisions and Human Engineering Rationale

### 2.1. Bulk Loading Engine: Low-Level COPY FROM STDIN vs. Naive ORM Insertion
When loading 1.84 million records into a newly initialized relational cluster, standard data engineering approaches typically rely on high-level dataframe methods such as Pandas `to_sql`. However, initial trial runs with standard row-by-row or batched `method='multi'` execution estimated total load times exceeding 15 minutes, accompanied by severe memory pressure as thousands of parameter-bound `INSERT INTO` statements were generated and parsed across the network socket.

To eliminate this ingestion bottleneck, an extensible `PostgresSink` adapter was engineered within the Stage 1 package using PostgreSQL's native streaming protocol via `COPY FROM STDIN` paired with an in-memory `io.StringIO` buffer. Records were formatted into tab-delimited streams in memory and piped directly into the database engine through psycopg2's low-level `copy_expert` interface. This architectural shift enabled ingesting the entire **1,847,423 records in exactly 23.76 seconds** (including streaming the 297k NYC 311 dataset in 5.95 seconds). The conscious engineering trade-off was abandoning automated ORM type validation in favor of manually managing raw memory buffers, handling string escaping, and casting nullable numeric dimensions to explicit 64-bit integers (`Int64`) to prevent malformed string serialization errors (such as `"40.0"`).

### 2.2. Preserving Customer Feedback: Composite Primary Key on Order Reviews
A critical data anomaly was uncovered during the schema design phase of the review dataset (`order_reviews`): the column `review_id` was not unique, exhibiting 814 duplicate keys across 99,224 rows. Forensic inspection revealed that when a customer purchases a multi-item bundle spanning multiple order entries, the marketplace platform assigns an identical `review_id` to each associated order.

Two naive workarounds presented themselves: deduplicating records by discarding subsequent occurrences, or introducing an artificial surrogate primary key (such as an auto-incrementing `SERIAL` ID). Discarding duplicates would irreversibly destroy genuine customer feedback for 814 orders, violating data auditability standards. Conversely, a surrogate key would decouple the table from its natural transactional domain. The decision was made to establish a compound primary key: `PRIMARY KEY (review_id, order_id)`. This preserved 100% of customer reviews without dropping a single row, guaranteed deterministic joins, and prevented unique constraint violations during ingestion. The trade-off was accepting a modest 17 MB expansion in the primary key B-Tree index footprint.

### 2.3. Dashboard Performance Under Heavy Joins: Analytical Snapshot Table vs. Dynamic Live View
Product Question 1 required computing monthly sales volume, Gross Merchandise Value (GMV), and Average Order Value (AOV) broken down by product category. Executing this calculation dynamically via a live database view (`view_order_item_details`) forced the database engine to perform a 4-way hash join across `orders`, `order_items`, `products`, and `product_category_translation`, processing over 110,000 line items on every dashboard request.

Benchmarking this dynamic view across 5 consecutive runs produced a median execution latency of **511.95 ms**—more than 2.5 times the 200 ms budget ceiling. To resolve this structural constraint, an analytical snapshot architecture was introduced: an idempotent stored procedure (`sp_refresh_monthly_category_snapshot`) precomputes monthly summary slices into a dedicated analytical table (`olist.snapshot_monthly_category_analytics`). Querying this precomputed snapshot reduced execution latency from 511.95 ms down to **2.55 ms**, well within the budget. The accepted architectural trade-off was sacrificing real-time streaming data freshness; newly arrived orders are only reflected after scheduled periodic execution of the snapshot procedure, a standard and widely accepted practice in operational business intelligence.

### 2.4. Eliminating External Disk Spills via Early CTE Filtering (Top 20 Sellers)
Product Question 4 demanded identifying the top 20 sellers by cumulative revenue, paired with their delivery delay rates and average review ratings. Formulating this query naively through a monolithic join across all 3,095 sellers, 110,000 items, and 99,000 reviews resulted in inefficient query execution plans: the optimizer performed global hash joins and aggregated across all sellers before sorting, causing an `External Merge Sort` that spilled 6.5 MB of temporary buffers to disk and took **392.9 ms**.

The query was restructured using an early-filtering CTE pattern: an initial lightweight Common Table Expression filters and ranks only the top 20 sellers by revenue directly from the indexed `order_items` table. Subsequent downstream joins for delivery latency and customer satisfaction were strictly constrained to those 20 pre-filtered seller identifiers. This structural refactoring reduced the row processing volume, eliminated disk spilling entirely, and reduced median execution time down to **152.25 ms**. The deliberate trade-off was increased SQL query verbosity and multi-stage query structure.

### 2.5. Covering Indexes and Quantifying the Hidden Cost of Indexing (Write Amplification)
To bring queries 2 through 5 safely under the 200 ms latency budget, strategic covering B-Tree indexes were deployed, including `idx_order_items_seller_order_price` and `idx_orders_status_purchase`. These indexes enabled index-only and bitmap scans, dropping median latency for Query 2 to **153.56 ms** and Query 5 to **53.22 ms**.

However, in enterprise database administration, every index introduces non-trivial operational costs in disk storage and write latency. A dedicated storage profiler revealed that on the `order_items` table, the raw data occupies 18 MB, whereas its supporting indexes consume **38 MB (210.5% of total table data size)**. Furthermore, empirical write-amplification profiling demonstrated that inserting a batch of 10,000 records took 0.028 seconds on an unindexed table compared to 0.118 seconds on the indexed table—a **4.19x write slowdown**. This empirical evidence confirmed the critical engineering necessity of continuous index pruning and disciplined schema governance.

---

## 3. Discarded Approaches and Empirical Failure Modes

### 3.1. The Low-Cardinality Index Illusion on Order Status
During early optimization iterations, an index was created on the order status column (`idx_orders_status`) to accelerate queries filtering for delivered orders. Surprisingly, repeated execution benchmarks showed zero performance gain.  
Analyzing the execution plan via `EXPLAIN (ANALYZE, BUFFERS)` revealed that the query planner completely bypassed the index, choosing a full sequential table scan (`Seq Scan`). The underlying root cause was low cardinality: over **97.02% of all orders** possessed the status `delivered`. When selectivity approaches 100%, random heap lookups through a B-Tree index impose far higher I/O overhead than linear block reads. The index consumed disk space and degraded write speeds without providing any read benefit; it was consequently dropped using `DROP INDEX olist.idx_orders_status_redundant`.

### 3.2. Context-Switching Penalties in Repeated PL/pgSQL Function Invocations
In the initial draft of Product Query 3 (satisfaction vs. delivery delay tier), the custom scalar function `fn_calculate_delivery_delay_days` was invoked three separate times within a conditional `CASE` expression for every processed order row. Switching execution context repeatedly between the SQL query executor and the PL/pgSQL procedural interpreter added substantial per-row overhead, pushing query latency to **202.6 ms** and breaching the budget. The issue was resolved by refactoring the computation into the underlying view (`view_delivered_orders`), calculating delay days once per row, which reduced latency to **98.19 ms**.

### 3.3. Expression-Wrapped Non-SARGable Filtering vs. SARGable Range Scans
An experimental query aimed at extracting orders placed in 2017 was formulated as:
```sql
SELECT order_id, order_status FROM olist.orders 
WHERE EXTRACT(YEAR FROM order_purchase_timestamp) = 2017 AND UPPER(order_status) = 'DELIVERED';
```
Wrapping indexed columns inside function expressions prevented the B-Tree index from matching search arguments (Non-SARGable), forcing a full sequential scan across all 99,441 rows taking **22.8 ms**. The query was restructured into a SARGable range scan:
```sql
SELECT order_id, order_status FROM olist.orders 
WHERE order_purchase_timestamp >= '2017-01-01 00:00:00+00' 
  AND order_purchase_timestamp < '2018-01-01 00:00:00+00' 
  AND order_status = 'delivered';
```
This enabled direct `Bitmap Index Scan` utilization, slashing latency to **3.1 ms (a 7.3x performance speedup)**.

---

## 4. Performance Benchmark Results Against the 200 ms Latency Budget

All queries were rigorously benchmarked using the median of 5 consecutive runs following buffer warmup:

| Query ID | Business Question / Analytical Focus | Target Budget | Actual Median Latency | Compliance Status |
| :--- | :--- | :---: | :---: | :---: |
| **Q1 (Production)** | Monthly Category GMV & Basket Size (Snapshot Table) | < 200 ms | **2.55 ms** |  **PASS** |
| **Q1 (Comparison)** | Monthly Category GMV (Dynamic Live View) | < 200 ms | **511.95 ms** | **BASELINE** (Proves Snapshot Necessity) |
| **Q2** | Delivery Delay Ratio by Geographic State | < 200 ms | **153.56 ms** |  **PASS** |
| **Q3** | Customer Satisfaction vs. Delay Tier Distribution | < 200 ms | **98.19 ms** |  **PASS** |
| **Q4** | Top 20 Sellers by Revenue & Rating (Early CTE Filtering) | < 200 ms | **152.25 ms** |  **PASS** |
| **Q5** | Payment Method Distribution & Installment Share | < 200 ms | **53.22 ms** |  **PASS** |

---

## 5. Production Operational Risks and Scalability Horizons

In an enterprise production deployment, two scalability challenges require proactive lifecycle management:
1. **Memory Pressure from Index Footprints:** Given that indexes occupy 210.5% of raw table size on `order_items`, scaling transaction volume to tens of millions of records will exceed available buffer pool memory (RAM). Future architectural iterations should implement declarative table partitioning by purchase year/quarter (`Table Partitioning`), allowing partition pruning to keep active B-Trees resident in memory.
2. **Snapshot Freshness Orchestration:** Relying on precomputed snapshots necessitates scheduling `sp_refresh_monthly_category_snapshot` through a reliable orchestrator (e.g., Apache Airflow or system cron) with alerting mechanisms to prevent serving stale telemetry during upstream pipeline failures.

---

## 6. Transparent AI Usage Disclosure

Implementation and code generation across most parts of this project (including data ingestion scripts, DDL schemas, SQL queries, database routines, and unit tests) were conducted using a vibe-coding workflow with an AI assistant (Antigravity). The assistant was also utilized for editing and refining the technical text of this report.

However, the hands-on engineering and practical database troubleshooting were driven directly by my own investigation on the actual data—from catching duplicate review records (`order_reviews`) that caused primary key violations, to diagnosing severe multi-table join latency on monthly cart aggregation and designing the precomputed snapshot table, evaluating `EXPLAIN ANALYZE` execution trees to prune redundant B-Tree indexes, and benchmarking runtimes to ensure all queries comfortably met budget constraints in a live PostgreSQL environment. I assume full personal responsibility for the final database architecture and delivered codebase.


