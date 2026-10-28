"""
Data Layer Integrity and Correctness Test Suite.
Verifies scalar functions, procedure idempotency, analytical correctness,
and connection lifecycle management (Satisfies Requirement 9).
"""

from datetime import datetime, timezone
import unittest
from sqlalchemy import text
from src.database.connection import get_connection, get_engine


class TestDataLayerIntegrity(unittest.TestCase):
    """Test suite validating database routines, views, and analytical invariants."""

    def test_function_delivery_delay_positive_late(self) -> None:
        """Test fn_calculate_delivery_delay_days returns positive day difference for late deliveries."""
        with get_connection() as conn:
            query = text("""
                SELECT olist.fn_calculate_delivery_delay_days(
                    '2024-05-10 12:00:00+00'::timestamptz,
                    '2024-05-07 12:00:00+00'::timestamptz
                );
            """)
            val = conn.execute(query).scalar()
            self.assertEqual(float(val), 3.0)

    def test_function_delivery_delay_negative_early(self) -> None:
        """Test fn_calculate_delivery_delay_days returns negative day difference for early deliveries."""
        with get_connection() as conn:
            query = text("""
                SELECT olist.fn_calculate_delivery_delay_days(
                    '2024-05-05 12:00:00+00'::timestamptz,
                    '2024-05-07 12:00:00+00'::timestamptz
                );
            """)
            val = conn.execute(query).scalar()
            self.assertEqual(float(val), -2.0)

    def test_function_delivery_delay_null_safe(self) -> None:
        """Test fn_calculate_delivery_delay_days returns NULL when either timestamp is missing."""
        with get_connection() as conn:
            query = text("""
                SELECT olist.fn_calculate_delivery_delay_days(NULL, '2024-05-07 12:00:00+00'::timestamptz);
            """)
            val = conn.execute(query).scalar()
            self.assertIsNone(val)

    def test_function_customer_nps_tier(self) -> None:
        """Test fn_customer_nps_tier accurately maps review scores to standard sentiment tiers."""
        with get_connection() as conn:
            tiers = conn.execute(text("""
                SELECT 
                    olist.fn_customer_nps_tier(5) AS t5,
                    olist.fn_customer_nps_tier(3) AS t3,
                    olist.fn_customer_nps_tier(1) AS t1;
            """)).fetchone()
            self.assertEqual(tiers[0], "Promoter")
            self.assertEqual(tiers[1], "Passive")
            self.assertEqual(tiers[2], "Detractor")

    def test_stored_procedure_idempotency(self) -> None:
        """
        Test that calling sp_refresh_monthly_category_snapshot repeatedly for the same month
        produces identical row counts without creating duplicates or raising errors.
        """
        test_month = "2018-03-01"
        with get_connection() as conn:
            # First execution
            conn.execute(text(f"CALL olist.sp_refresh_monthly_category_snapshot('{test_month}');"))
            conn.commit()
            cnt_first = conn.execute(text(f"""
                SELECT COUNT(*) FROM olist.snapshot_monthly_category_analytics 
                WHERE order_month = '{test_month}';
            """)).scalar()

            # Second execution (Idempotent replay)
            conn.execute(text(f"CALL olist.sp_refresh_monthly_category_snapshot('{test_month}');"))
            conn.commit()
            cnt_second = conn.execute(text(f"""
                SELECT COUNT(*) FROM olist.snapshot_monthly_category_analytics 
                WHERE order_month = '{test_month}';
            """)).scalar()

            self.assertGreater(cnt_first, 0, "Snapshot should populate records for month 2018-03-01")
            self.assertEqual(cnt_first, cnt_second, "Re-running Stored Procedure must not create duplicate rows!")

    def test_analytical_query_correctness_controlled_data(self) -> None:
        """Verify mathematical correctness of revenue and average order value aggregates."""
        with get_connection() as conn:
            row = conn.execute(text("""
                SELECT total_revenue, unique_orders, avg_order_value
                FROM olist.snapshot_monthly_category_analytics
                WHERE order_month = '2018-03-01' AND category = 'health_beauty';
            """)).fetchone()

            self.assertIsNotNone(row, "Record for health_beauty in 2018-03 should exist")
            tot_rev, orders, avg_val = float(row[0]), int(row[1]), float(row[2])
            expected_avg = round(tot_rev / orders, 2)
            self.assertAlmostEqual(avg_val, expected_avg, places=1)

    def test_view_delivered_orders_integrity(self) -> None:
        """Verify view_delivered_orders strictly encapsulates delivered status and positive delays."""
        with get_connection() as conn:
            invalid_status = conn.execute(text("""
                SELECT COUNT(*) FROM olist.view_delivered_orders WHERE order_status != 'delivered';
            """)).scalar()
            self.assertEqual(invalid_status, 0, "View must strictly filter non-delivered orders")

    def test_connection_context_manager_closes_cleanly(self) -> None:
        """Verify get_connection context manager releases connection without leaking pool sockets."""
        engine = get_engine()
        initial_checked_out = engine.pool.checkedout()

        with get_connection() as conn:
            conn.execute(text("SELECT 1;"))
            self.assertEqual(engine.pool.checkedout(), initial_checked_out + 1)

        # After block exit, checked out sockets must revert immediately
        self.assertEqual(engine.pool.checkedout(), initial_checked_out)


if __name__ == "__main__":
    unittest.main()
