"""
Command Line Interface (CLI) for Stage 2 Database Performance.
Enables command-line execution of database bootstrapping, benchmarks, and test diagnostics.
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.loader import init_all
from src.database.populate_snapshot import populate_all_months
from src.analytics.queries import (
    Q1_BASKET_REVENUE_SNAPSHOT,
    Q1_BASKET_REVENUE_LIVE,
    Q2_DELIVERY_RATIO,
    Q3_SATISFACTION_DELAY,
    Q4_TOP_SELLERS_SURGICAL,
    Q5_PAYMENT_INSTALLMENTS,
    run_benchmark_cycle,
)
from src.analytics.hidden_cost import measure_index_storage, measure_write_amplification, drop_redundant_index


def run_benchmarks():
    """Run full benchmark cycle across all 5 product queries."""
    benchmarks = {
        "Q1 (Monthly Basket & Revenue)": Q1_BASKET_REVENUE_SNAPSHOT,
        "Q1 (Live View Comparison)": Q1_BASKET_REVENUE_LIVE,
        "Q2 (Delivery Delay Ratio)": Q2_DELIVERY_RATIO,
        "Q3 (Satisfaction vs Delay)": Q3_SATISFACTION_DELAY,
        "Q4 (Top 20 Sellers by Revenue)": Q4_TOP_SELLERS_SURGICAL,
        "Q5 (Payment & Installments)": Q5_PAYMENT_INSTALLMENTS,
    }

    print("=" * 88)
    print(" BENCHMARK RESULTS: 5 PRODUCT QUERIES VS 200 MS BUDGET (MEDIAN OF 5 RUNS)")
    print("=" * 88)
    for name, sql in benchmarks.items():
        res = run_benchmark_cycle(sql, runs=5)
        med = res["median_ms"]
        if "Comparison" in name:
            status = "COMPARISON (>200ms | Proves Snapshot Need)"
        else:
            status = "PASS (<200ms)" if med < 200 else "FAIL (>200ms)"
        print(f"{name:32s} | Rows: {res['rows']:>6,} | Median: {med:>7.2f} ms | {status}")
    print("=" * 88)


def main():
    parser = argparse.ArgumentParser(description="Stage 2 DBA & Performance CLI Harness")
    parser.add_argument("--init-all", action="store_true", help="Initialize DDL schema and load all datasets")
    parser.add_argument("--populate-snapshot", action="store_true", help="Populate analytical monthly snapshot")
    parser.add_argument("--benchmark", action="store_true", help="Run 5-query performance benchmark against 200ms budget")
    parser.add_argument("--hidden-cost", action="store_true", help="Measure index disk storage and write amplification")

    args = parser.parse_args()

    if args.init_all:
        init_all()
        populate_all_months()
    elif args.populate_snapshot:
        populate_all_months()
    elif args.benchmark:
        run_benchmarks()
    elif args.hidden_cost:
        print("=== INDEX STORAGE FOOTPRINT ===")
        for item in measure_index_storage():
            print(f"{item['table']:25s} | Table: {item['table_size']:>10s} | Index: {item['index_size']:>10s} | Ratio: {item['ratio_pct']:>6.1f}%")
        print("\n=== WRITE AMPLIFICATION BENCHMARK ===")
        res = measure_write_amplification()
        print(f"Unindexed: {res['unindexed_seconds']}s | Indexed: {res['indexed_seconds']}s | Slowdown: {res['slowdown_factor']}x")
        print("\n=== DROPPING REDUNDANT INDEX ===")
        print(drop_redundant_index())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
