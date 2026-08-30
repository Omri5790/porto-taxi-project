"""
Regenerate stage3_anomalous_routes.json with the corrected cell labelling.

The cluster run 20260830T121916Z uploaded its code zip at 12:19; the commit
that separated ``busiest_cells`` from ``concentrated_cells`` landed at 13:11,
while stage 3 was still running.  So that run's anomaly output carries the old,
mislabelled ``low_diversity_cells`` list -- entries crossed by 429 of 440
taxis, which is the opposite of low diversity.

Rather than re-run eighty minutes of mining to fix one file, this reruns only
the anomaly block, with the same code path the pipeline uses (same module, same
RDD operations), against the same encoded parquet.  The output records that it
was regenerated and when, so the provenance stays legible.

    python tools/rerun_anomalies.py \\
        --input_path output/h3_encoded_trips.parquet \\
        --out        output/stage3_anomalous_routes.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_path", default="output/h3_encoded_trips.parquet")
    ap.add_argument("--out", default="output/stage3_anomalous_routes.json")
    ap.add_argument("--stats", default="output/anomalies_rerun_stats.json")
    args = ap.parse_args()

    from pyspark.sql import SparkSession
    from scripts.stage3 import anomalies, gate
    from scripts.stage3.run_stage3 import load_trips

    spark = (SparkSession.builder
             .appName("Stage3_Anomalies_Rerun")
             .config("spark.driver.memory", "6g")
             .config("spark.sql.shuffle.partitions", "32")
             .master("local[*]").getOrCreate())
    sc = spark.sparkContext
    sc.setLogLevel("ERROR")

    try:
        base_rdd, cell_col = load_trips(spark, args.input_path, None)
        base_rdd = base_rdd.cache()
        total_trips = base_rdd.count()
        trips_rdd = base_rdd.map(lambda r: (r[0], r[1])).cache()
        trips_rdd.count()
        print(f"loaded {total_trips:,} trips from {cell_col}")

        trans_support = max(20, int(total_trips * 0.0002))
        _f2, bc_bloom2, gate2 = gate.build_gate(sc, trips_rdd, 2, trans_support)
        total_taxis = base_rdd.map(lambda r: r[2]).distinct().count()
        print(f"fleet: {total_taxis} taxis; transition support {trans_support}")

        secs, anom, stats = anomalies.run(sc, base_rdd, total_trips, bc_bloom2,
                                          total_taxis=total_taxis)
        stats["fleet_size"] = total_taxis
        anom["regenerated"] = {
            "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "why": ("the cluster run's code zip predated the commit separating "
                    "busiest_cells from concentrated_cells; only this file is "
                    "affected, and only its cell lists"),
            "same_input": args.input_path,
            "tool": "tools/rerun_anomalies.py",
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(anom, fh)
        with open(args.stats, "w", encoding="utf-8") as fh:
            json.dump({**stats, "transition_gate": gate2}, fh, indent=2)
        print(f"scored {stats['trips_scored']:,} trips in {secs:.1f}s")
        print(f"wrote {args.out}")
        print("keys:", list(anom.keys()))
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
