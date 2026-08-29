"""
Verify Stage 2: the H3 encoding is the one thing everything downstream trusts.

Stage 3 never sees a coordinate.  It sees only the cell sequences this stage
produces, so a silent error here -- a dropped cell, a reordering, a collapse
that removes more than it should -- cannot be detected later.  It would just
look like the data.

Rather than assert that the encoding is right, this rebuilds the expected
sequence independently from the coordinates and compares it cell for cell:

    python tools/verify_stage2.py

The last section is not a check but a measurement: the same trips encoded at
resolutions 8, 9 and 10, so the choice of resolution 9 can be defended with
numbers instead of with a claim.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import h3  # noqa: E402

LAT0, LNG0 = 41.1500, -8.6100


def make_cleaned_parquet(spark, path: str, n_trips: int = 120, seed: int = 7):
    """Write a cleaned-trips parquet: Stage 2's actual input contract.

    Trips wander -- straight runs, turns, and a few fast stretches -- so that
    consecutive cells are sometimes adjacent and sometimes not.  An encoder that
    only ever sees straight lines is not being tested.
    """
    from pyspark.sql.types import (StructType, StructField, StringType, IntegerType,
                                   LongType, DoubleType, ArrayType)

    rng = random.Random(seed)
    rows = []
    for t in range(n_trips):
        lat, lng = LAT0 + rng.uniform(-0.03, 0.03), LNG0 + rng.uniform(-0.04, 0.04)
        heading = rng.uniform(0, 2 * math.pi)
        n_pts = rng.randint(8, 60)
        pts = []
        for i in range(n_pts):
            pts.append({"lng": round(lng, 6), "lat": round(lat, 6)})
            # a turn every so often, and a variable step: 60 m to 300 m per 15 s
            if rng.random() < 0.15:
                heading += rng.uniform(-1.2, 1.2)
            step_km = rng.uniform(0.06, 0.30)
            lat += (step_km / 111.0) * math.cos(heading)
            lng += (step_km / (111.0 * math.cos(math.radians(lat)))) * math.sin(heading)
        dist = sum(
            2 * 6371.0 * math.asin(math.sqrt(
                math.sin(math.radians(b["lat"] - a["lat"]) / 2) ** 2
                + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"]))
                * math.sin(math.radians(b["lng"] - a["lng"]) / 2) ** 2))
            for a, b in zip(pts, pts[1:]))
        rows.append((
            f"V{t:04d}", "A", "", "15", 20000000 + t, 1372636800 + t * 600, "A",
            "[]", pts, len(pts), (len(pts) - 1) * 15, round(dist, 4),
            pts[0]["lng"], pts[0]["lat"], pts[-1]["lng"], pts[-1]["lat"],
            round(dist / (((len(pts) - 1) * 15) / 3600.0), 2),
        ))

    schema = StructType([
        StructField("TRIP_ID", StringType()), StructField("CALL_TYPE", StringType()),
        StructField("ORIGIN_CALL", StringType()), StructField("ORIGIN_STAND", StringType()),
        StructField("TAXI_ID", IntegerType()), StructField("TIMESTAMP", LongType()),
        StructField("DAY_TYPE", StringType()), StructField("POLYLINE", StringType()),
        StructField("coordinates", ArrayType(StructType([
            StructField("lng", DoubleType()), StructField("lat", DoubleType())]))),
        StructField("num_points", IntegerType()), StructField("duration_sec", IntegerType()),
        StructField("distance_km", DoubleType()),
        StructField("start_lng", DoubleType()), StructField("start_lat", DoubleType()),
        StructField("end_lng", DoubleType()), StructField("end_lat", DoubleType()),
        StructField("avg_speed_kmh", DoubleType()),
    ])
    from pyspark.sql import functions as F
    df = spark.createDataFrame(rows, schema=schema)
    df = (df.withColumn("trip_datetime", F.from_unixtime(F.col("TIMESTAMP")))
            .withColumn("hour_of_day", F.hour(F.col("trip_datetime")))
            .withColumn("day_of_week", F.dayofweek(F.col("trip_datetime"))))
    df.write.mode("overwrite").parquet(path)
    return n_trips


def expected_sequence(coords, res: int) -> list:
    """What the sequence must be: every point mapped, consecutive repeats collapsed."""
    out = []
    for pt in coords:
        cell = h3.latlng_to_cell(pt["lat"], pt["lng"], res)
        if not out or cell != out[-1]:
            out.append(cell)
    return out


def check(spark, parquet: str) -> bool:
    rows = spark.read.parquet(parquet).collect()
    print(f"\n  read back {len(rows):,} encoded trips")

    bad_seq = bad_dedup = bad_ends = bad_len = bad_parent = 0
    grid_steps = {}
    per_res_cells = {8: 0, 9: 0, 10: 0}
    unique = {8: set(), 9: set(), 10: set()}

    for r in rows:
        coords = [{"lat": c["lat"], "lng": c["lng"]} for c in r["coordinates"]]
        for res in (8, 9, 10):
            got = list(r[f"h3_res{res}"])
            want = expected_sequence(coords, res)

            # A. the sequence itself, rebuilt independently from the coordinates
            if got != want:
                bad_seq += 1
            # B. no consecutive repeats survived the collapse
            if any(a == b for a, b in zip(got, got[1:])):
                bad_dedup += 1
            # C. the start/end columns agree with the sequence they summarise
            if got and (r[f"start_h3_res{res}"] != got[0] or r[f"end_h3_res{res}"] != got[-1]):
                bad_ends += 1
            # D. the stored length is the length
            if r[f"h3_res{res}_length"] != len(got):
                bad_len += 1

            per_res_cells[res] += len(got)
            unique[res].update(got)

        # E. how far apart are consecutive res-9 cells?  Not a pass/fail: a fast
        #    stretch legitimately skips a cell.  Reported so the number is known.
        seq9 = list(r["h3_res9"])
        for a, b in zip(seq9, seq9[1:]):
            try:
                d = h3.grid_distance(a, b)
            except Exception:
                d = -1
            grid_steps[d] = grid_steps.get(d, 0) + 1

        # F. NOT a check -- a measurement, and the reason all three resolutions
        #    are encoded from the coordinates instead of derived from each other.
        #    Hexagons cannot subdivide into hexagons, so H3's parent/child
        #    relation is approximate: a res-9 cell's res-8 parent is not always
        #    the res-8 cell the same point maps to.  Count how often they differ.
        parents = {h3.cell_to_parent(c, 8) for c in r["h3_res9"]}
        if not parents.issubset(set(r["h3_res8"])):
            bad_parent += 1

    print()
    checks = [
        ("sequence matches an independent re-encoding", bad_seq),
        ("no consecutive duplicate cells remain", bad_dedup),
        ("start/end columns agree with the sequence", bad_ends),
        ("stored lengths equal the real lengths", bad_len),
    ]
    ok = True
    for label, failures in checks:
        ok &= (failures == 0)
        print(f"  {label:<54}{'ok' if failures == 0 else str(failures) + ' TRIPS FAILED'}")

    print()
    print("  Step size between consecutive res-9 cells:")
    total_steps = sum(grid_steps.values()) or 1
    for d in sorted(grid_steps):
        label = {1: "adjacent (the normal case)", 2: "one cell skipped",
                 0: "same cell -- would be a dedup bug"}.get(d, f"{d} cells apart")
        print(f"    distance {d:>2}: {grid_steps[d]:>7,}  {100.0*grid_steps[d]/total_steps:>5.1f}%   {label}")
    if grid_steps.get(0):
        ok = False
        print("    *** distance 0 means the deduplication let a repeat through ***")

    print()
    print("  Why each resolution is encoded from the coordinates, not derived")
    print("  from the one below it:")
    print()
    print(f"    {bad_parent} of {len(rows)} trips have at least one res-9 cell whose")
    print("    res-8 parent is not the res-8 cell that same point maps to.")
    print("    That is a property of H3, not a bug: hexagons cannot be subdivided")
    print("    into hexagons, so the parent/child relation is approximate.  Deriving")
    print("    res 8 from res 9 would therefore put cells in the path that no taxi")
    print("    drove through.")

    print()
    print("  Why resolution 9 -- the same trips at all three resolutions:")
    print()
    print(f"    {'res':>4}{'edge':>9}{'area':>11}{'cells/trip':>12}{'unique cells':>14}")
    edge = {8: "461 m", 9: "174 m", 10: "66 m"}
    area = {8: "0.74 km2", 9: "0.11 km2", 10: "0.015 km2"}
    for res in (8, 9, 10):
        print(f"    {res:>4}{edge[res]:>9}{area[res]:>11}"
              f"{per_res_cells[res]/max(len(rows),1):>12.1f}{len(unique[res]):>14,}")
    print()
    print("    Res 8 is too coarse: two parallel streets fall in one cell, so")
    print("    distinct routes merge.  Res 10 is too fine: the same drive down the")
    print("    same street lands in different cells depending on which lane the")
    print("    car was in, so trips that should share a corridor no longer do.")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", type=int, default=120)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    from pyspark.sql import SparkSession
    work = tempfile.mkdtemp(prefix="verify_stage2_")
    cleaned = os.path.join(work, "cleaned.parquet")
    encoded = os.path.join(work, "h3.parquet")
    report = os.path.join(work, "report.json")

    print("=" * 66)
    print("  Stage 2 verification: H3 encoding rebuilt independently")
    print("=" * 66)

    spark = (SparkSession.builder.master("local[*]")
             .appName("verify_stage2_fixture").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        n = make_cleaned_parquet(spark, cleaned, n_trips=args.trips)
        print(f"  built {n} synthetic cleaned trips (turns and varying speed)")
    finally:
        spark.stop()

    cmd = [sys.executable, os.path.join(ROOT, "scripts", "stage2_spatial_encoding.py"),
           "--input_path", cleaned, "--output_path", encoded, "--report_path", report]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if not os.path.exists(os.path.join(encoded, "_SUCCESS")):
        print("\n  Stage 2 produced no output.  Its own output follows:\n")
        print(proc.stdout[-4000:]); print(proc.stderr[-4000:])
        shutil.rmtree(work, ignore_errors=True)
        return 2

    spark = (SparkSession.builder.master("local[*]")
             .appName("verify_stage2_check").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        ok = check(spark, encoded)
    finally:
        spark.stop()

    print()
    print("  The encoding is exactly what re-deriving it from the coordinates gives."
          if ok else "  *** The encoding does not match an independent re-derivation. ***")
    if args.keep:
        print(f"\n  work directory kept at {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    print("=" * 66)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
