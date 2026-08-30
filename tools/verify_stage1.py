"""
Verify Stage 1 against a raw CSV whose every row has a known verdict.

`pytest` covers Stage 3's internals; this covers the cleaning, which is the one
stage whose correctness cannot be argued from the code alone -- a rule that
silently never fires looks exactly like a rule that never had to.

Every trip in the generated CSV is built to trip exactly one rule, so the
cleaning report can be compared against arithmetic instead of against a
feeling.  Two trips are built to survive, one of which contains a stall: it is
there to demonstrate, rather than assert, why duration is taken from the
original sample count.

    python tools/verify_stage1.py
    python tools/verify_stage1.py --keep      # leave the work directory behind

Exits non-zero if any rule removed a different number of trips than expected.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import (PORTO_BBOX, REGION_BBOX, MIN_TRIP_KM, MAX_TRIP_KM,  # noqa: E402
                    MAX_DURATION_SEC)

LNG0, LAT0 = -8.6100, 41.1500   # comfortably inside the Porto box
STEP = 0.002                    # ~0.168 km per 15 s hop  ->  ~40 km/h
BIG = 0.005                     # ~0.42 km per hop, still under the 0.833 km jump limit

COLUMNS = ["TRIP_ID", "CALL_TYPE", "ORIGIN_CALL", "ORIGIN_STAND", "TAXI_ID",
           "TIMESTAMP", "DAY_TYPE", "MISSING_DATA", "POLYLINE"]


def _line(n: int, step: float = STEP) -> list:
    return [[round(LNG0 + i * step, 6), LAT0] for i in range(n)]


def _zigzag(n: int, step: float = BIG) -> list:
    """Cover more than MAX_TRIP_KM without ever leaving the bounding box."""
    # Turn round two hops short of each edge: the point is to exercise the
    # distance rule, and a zigzag that clips the boundary would be removed by
    # the bounding-box rule first and prove nothing.
    lo = PORTO_BBOX["min_lng"] + 2 * step
    hi = PORTO_BBOX["max_lng"] - 2 * step
    pts, lng, direction = [], lo, 1
    for _ in range(n):
        pts.append([round(lng, 6), LAT0])
        lng += direction * step
        if lng >= hi:
            direction = -1
        if lng <= lo:
            direction = 1
    return pts


def build_csv(path: str) -> dict:
    """Write the CSV; return the expected count per rule."""
    rows, expect = [], {}

    def add(trip_id, polyline, verdict, missing="False", raw_polyline=None):
        rows.append({
            "TRIP_ID": trip_id, "CALL_TYPE": "A", "ORIGIN_CALL": "",
            "ORIGIN_STAND": "15", "TAXI_ID": 20000001, "TIMESTAMP": 1372636800,
            "DAY_TYPE": "A", "MISSING_DATA": missing,
            "POLYLINE": raw_polyline if raw_polyline is not None else json.dumps(polyline),
        })
        expect[verdict] = expect.get(verdict, 0) + 1

    max_points = MAX_DURATION_SEC // 15

    add("T01", _line(10), "missing_data", missing="True")
    add("T02", [], "empty_polyline")
    add("T03", None, "bad_json", raw_polyline="[[-8.61,41.15],[-8.608,41.15]")  # unclosed
    add("T04", _line(1), "too_few_points")
    add("T05", [[LNG0, LAT0]] * (max_points + 1), "too_long")
    # Outside the REGION box now, not merely outside the study area: a point in
    # the next town is a journey, and only a satellite error is a rejection.
    add("T06", [[LNG0, LAT0], [REGION_BBOX["min_lng"] - 2.0, LAT0],
                [LNG0 + STEP, LAT0]], "out_of_bbox")
    add("T07", [[LNG0, LAT0], [LNG0 + 0.06, LAT0]], "gps_jump")          # ~5 km in 15 s
    add("T08", [[LNG0, LAT0]] * 5, "stationary")                          # dedups to one point
    add("T09", [[LNG0, LAT0], [LNG0 + 0.0005, LAT0]], "too_short_distance")
    add("T10", _zigzag(280), "too_long_distance")

    add("T11", _line(10), "kept")
    # 12 raw fixes, four of them the same fix repeated: a taxi stopped at a light.
    stall = (_line(4)
             + [[round(LNG0 + 3 * STEP, 6), LAT0]] * 4
             + [[round(LNG0 + (3 + i) * STEP, 6), LAT0] for i in range(1, 5)])
    add("T12", stall, "kept")

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in COLUMNS})

    return {"total_rows": len(rows), "per_rule": expect}


def compare(report: dict, expected: dict) -> bool:
    rules = ["missing_data", "empty_polyline", "bad_json", "too_few_points",
             "too_long", "out_of_bbox", "gps_jump", "stationary",
             "too_short_distance", "too_long_distance"]

    print()
    print(f"  {'rule':<22}{'expected':>9}{'actual':>8}   ")
    print(f"  {'-' * 45}")
    ok = True
    for key in rules:
        want = expected["per_rule"].get(key, 0)
        got = report["per_rule_removed"][key]["trips"]
        ok &= (want == got)
        print(f"  {key:<22}{want:>9}{got:>8}   {'ok' if want == got else 'MISMATCH'}")

    for key, want, got in [
        ("kept", expected["per_rule"]["kept"], report["summary"]["final_clean_trips"]),
        ("rows read", expected["total_rows"], report["summary"]["raw_trips_read"]),
    ]:
        ok &= (want == got)
        print(f"  {key:<22}{want:>9}{got:>8}   {'ok' if want == got else 'MISMATCH'}")
    return ok


def show_duration_effect(parquet: str) -> None:
    """Print what the old duration bug would have done to these two trips."""
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[1]")
             .appName("verify_stage1_duration").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        rows = (spark.read.parquet(parquet)
                .select("TRIP_ID", "num_points_raw", "num_points",
                        "duration_sec", "distance_km", "avg_speed_kmh")
                .orderBy("TRIP_ID").collect())
        print()
        print("  Why duration comes from the raw sample count:")
        print()
        print(f"  {'trip':<6}{'raw':>5}{'kept':>6}{'duration':>10}{'km':>8}"
              f"{'speed':>9}{'if from kept pts':>18}")
        for r in rows:
            bug_dur = (r.num_points - 1) * 15
            bug_speed = r.distance_km / (bug_dur / 3600.0) if bug_dur else 0.0
            print(f"  {r.TRIP_ID:<6}{r.num_points_raw:>5}{r.num_points:>6}"
                  f"{r.duration_sec:>9}s{r.distance_km:>8.3f}"
                  f"{r.avg_speed_kmh:>9.2f}{bug_speed:>18.2f}")
        print()
        print("  T12 is T11 with a stop at a light.  Taking duration after")
        print("  deduplication erases the stop, and the stalled trip then reports")
        print("  the same speed as the one that never stopped.")
    finally:
        spark.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="do not delete the work directory")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="verify_stage1_")
    raw = os.path.join(work, "raw_test.csv")
    parquet = os.path.join(work, "cleaned.parquet")
    report_path = os.path.join(work, "report.json")

    print("=" * 62)
    print("  Stage 1 verification against known-verdict input")
    print("=" * 62)
    expected = build_csv(raw)
    print(f"  wrote {expected['total_rows']} trips, one per rule, to {raw}")

    cmd = [sys.executable, os.path.join(ROOT, "scripts", "stage1_data_preparation.py"),
           "--input_path", raw, "--output_path", parquet, "--report_path", report_path]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if not os.path.exists(report_path):
        print("\n  Stage 1 did not produce a report.  Its output:\n")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        return 2

    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)

    ok = compare(report, expected)

    try:
        show_duration_effect(parquet)
    except Exception as exc:                      # the counts are the assertion
        print(f"\n  (could not read the parquet back: {exc})")

    print()
    if ok:
        print("  Every rule removed exactly the trips it was meant to remove.")
    else:
        print("  *** A rule removed a different number of trips than expected. ***")

    if args.keep:
        print(f"\n  work directory kept at {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
