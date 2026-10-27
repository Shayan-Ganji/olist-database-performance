"""
Data Ingestion and Schema Initialization Orchestrator.
Applies clean DDL contracts, resolves foreign key and category translation anomalies,
and leverages PostgreSQL COPY protocol for ultra-fast bulk ingestion across all 9 Olist tables
plus Stage 1 NYC 311 curated data.
"""

import io
import os
import sys
import time
from pathlib import Path
import pandas as pd
from sqlalchemy import text

from .connection import get_engine, DEFAULT_DB_URL

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_OLIST_DIR = BASE_DIR / "data" / "raw" / "olist"
DDL_PATH = BASE_DIR / "sql" / "ddl" / "01_create_olist_schema.sql"
STAGE_1_PARQUET = BASE_DIR.parent / "stage-1-shayan-ganji" / "data" / "curated" / "nyc_311_dot_curated.parquet"


def stream_df_to_postgres(df: pd.DataFrame, schema: str, table_name: str, engine=None) -> int:
    """Stream pandas DataFrame into PostgreSQL using in-memory COPY FROM STDIN."""
    if engine is None:
        engine = get_engine()

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        buffer = io.StringIO()
        df.to_csv(buffer, index=False, header=False, na_rep="\\N")
        buffer.seek(0)

        columns_str = ", ".join(f'"{col}"' for col in df.columns)
        copy_sql = f'COPY {schema}."{table_name}" ({columns_str}) FROM STDIN WITH (FORMAT CSV, NULL \'\\N\')'
        cursor.copy_expert(sql=copy_sql, file=buffer)
        raw_conn.commit()
        cursor.close()
        return len(df)
    except Exception as exc:
        raw_conn.rollback()
        raise RuntimeError(f"Bulk load failed for {schema}.{table_name}: {exc}") from exc
    finally:
        raw_conn.close()


def initialize_schema(engine=None) -> None:
    """Execute DDL script to establish schemas, tables, and relational constraints."""
    if engine is None:
        engine = get_engine()

    print("[DDL] Executing 01_create_olist_schema.sql...")
    with open(DDL_PATH, "r", encoding="utf-8") as f:
        ddl_sql = f.read()

    with engine.connect() as conn:
        conn.execute(text(ddl_sql))
        conn.commit()
    print("[DDL] Schema 'olist' initialized successfully.")


def load_olist_data(engine=None) -> dict[str, int]:
    """Ingest and clean all 9 Olist CSV tables with strict integrity preservation."""
    if engine is None:
        engine = get_engine()

    counts = {}
    print("\n[INGESTION] Loading 9 Olist tables...")

    # 1. Product Category Translations (seed missing 2 categories)
    print("  -> Loading product_category_translation...")
    df_trans = pd.read_csv(RAW_OLIST_DIR / "product_category_name_translation.csv")
    missing_cats = pd.DataFrame([
        {"product_category_name": "pc_gamer", "product_category_name_english": "pc_gamer"},
        {
            "product_category_name": "portateis_cozinha_e_preparadores_de_alimentos",
            "product_category_name_english": "kitchen_and_food_prep_portables",
        },
    ])
    df_trans = pd.concat([df_trans, missing_cats], ignore_index=True).drop_duplicates()
    counts["product_category_translation"] = stream_df_to_postgres(
        df_trans, "olist", "product_category_translation", engine
    )

    # 2. Customers
    print("  -> Loading customers...")
    df_cust = pd.read_csv(RAW_OLIST_DIR / "olist_customers_dataset.csv")
    counts["customers"] = stream_df_to_postgres(df_cust, "olist", "customers", engine)

    # 3. Products (handle category nulls and integer columns)
    print("  -> Loading products...")
    df_prod = pd.read_csv(RAW_OLIST_DIR / "olist_products_dataset.csv")
    int_cols = [
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    for col in int_cols:
        df_prod[col] = df_prod[col].astype("Int64")
    counts["products"] = stream_df_to_postgres(df_prod, "olist", "products", engine)


    # 4. Sellers
    print("  -> Loading sellers...")
    df_sell = pd.read_csv(RAW_OLIST_DIR / "olist_sellers_dataset.csv")
    counts["sellers"] = stream_df_to_postgres(df_sell, "olist", "sellers", engine)

    # 5. Orders (parse timestamps)
    print("  -> Loading orders...")
    df_orders = pd.read_csv(RAW_OLIST_DIR / "olist_orders_dataset.csv")
    counts["orders"] = stream_df_to_postgres(df_orders, "olist", "orders", engine)

    # 6. Order Items
    print("  -> Loading order_items...")
    df_items = pd.read_csv(RAW_OLIST_DIR / "olist_order_items_dataset.csv")
    counts["order_items"] = stream_df_to_postgres(df_items, "olist", "order_items", engine)

    # 7. Order Payments
    print("  -> Loading order_payments...")
    df_pay = pd.read_csv(RAW_OLIST_DIR / "olist_order_payments_dataset.csv")
    counts["order_payments"] = stream_df_to_postgres(df_pay, "olist", "order_payments", engine)

    # 8. Order Reviews (handle composite key deduplication)
    print("  -> Loading order_reviews...")
    df_rev = pd.read_csv(RAW_OLIST_DIR / "olist_order_reviews_dataset.csv")
    df_rev = df_rev.drop_duplicates(subset=["review_id", "order_id"])
    counts["order_reviews"] = stream_df_to_postgres(df_rev, "olist", "order_reviews", engine)

    # 9. Geolocation (select columns matching table)
    print("  -> Loading geolocation (1,000,163 rows)...")
    df_geo = pd.read_csv(RAW_OLIST_DIR / "olist_geolocation_dataset.csv")
    counts["geolocation"] = stream_df_to_postgres(df_geo, "olist", "geolocation", engine)

    return counts


def load_stage_1_data(engine=None) -> int:
    """Load curated Stage 1 NYC 311 data into schema 'nyc_311' via data_factory package."""
    if engine is None:
        engine = get_engine()

    print("\n[STAGE 1 LINKAGE] Ingesting NYC 311 clean dataset into PostgreSQL...")
    if not STAGE_1_PARQUET.exists():
        raise FileNotFoundError(f"Stage 1 curated file not found at: {STAGE_1_PARQUET}")

    stage_1_dir = str(BASE_DIR.parent / "stage-1-shayan-ganji")
    if stage_1_dir not in sys.path:
        sys.path.insert(0, stage_1_dir)

    from src.data_factory.sinks import PostgresSink

    df_nyc = pd.read_parquet(STAGE_1_PARQUET)
    sink = PostgresSink(
        connection_url=DEFAULT_DB_URL,
        schema="nyc_311",
        table_name="service_requests",
        if_exists="replace",
    )
    sink.write_dataframe(df_nyc)
    meta = sink.finalize()
    print(f"  -> Successfully loaded {meta['record_count']:,} rows into nyc_311.service_requests.")
    return meta["record_count"]


def init_all() -> None:
    """Full database bootstrap: schema DDL, Olist 9 tables, and Stage 1 linkage."""
    start_time = time.time()
    engine = get_engine()

    initialize_schema(engine)
    olist_counts = load_olist_data(engine)
    nyc_count = load_stage_1_data(engine)

    elapsed = time.time() - start_time
    print("\n==================================================================")
    print(f" DATABASE INITIALIZATION COMPLETED IN {elapsed:.2f} SECONDS")
    print("==================================================================")
    for tbl, cnt in olist_counts.items():
        print(f" - olist.{tbl:30s} : {cnt:>10,} rows")
    print(f" - nyc_311.service_requests               : {nyc_count:>10,} rows")
    print("==================================================================")


if __name__ == "__main__":
    init_all()
