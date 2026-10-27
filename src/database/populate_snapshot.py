"""
Script to populate the monthly category analytical snapshot table using the Stored Procedure.
"""

from sqlalchemy import text
from .connection import get_connection


def populate_all_months():
    with get_connection() as conn:
        months = conn.execute(text(
            "SELECT DISTINCT DATE_TRUNC('month', order_purchase_timestamp)::date "
            "FROM olist.orders WHERE order_status = 'delivered' ORDER BY 1;"
        )).fetchall()
        print(f"Executing sp_refresh_monthly_category_snapshot across {len(months)} months...")
        for m in months:
            m_str = m[0].strftime("%Y-%m-%d")
            conn.execute(text(f"CALL olist.sp_refresh_monthly_category_snapshot('{m_str}');"))
        conn.commit()

        cnt = conn.execute(text("SELECT COUNT(*) FROM olist.snapshot_monthly_category_analytics;")).scalar()
        print(f"Snapshot table successfully populated with {cnt:,} rows!")


if __name__ == "__main__":
    populate_all_months()
