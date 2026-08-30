"""
Stage 1 – Data Preparation (PySpark High-Performance MapPartitions Engine)
========================================================================
This script performs the full data preparation pipeline on the 1.71M Porto Taxi trips.
To avoid JVM GC heap memory exhaustion from creating 500+ million Java Array/Double objects,
this script leverages PySpark `mapPartitions` with C-accelerated Python math & JSON parsing.

Key Optimizations:
1. Zero JVM object allocation for raw GPS arrays (keeps JVM memory footprint <300MB).
2. Native C-level JSON parsing & Haversine distance per partition across all CPU cores.
3. Single-pass evaluation of all 8 cleaning checks (BBox, Duration, GPS Jumps, Consecutive Deduplication).
4. Direct Spark DataFrame creation & Parquet saving.
"""

import sys
import os
import json
import argparse
import math
import time
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    LongType, DoubleType, ArrayType
)

from scripts.stage3.io_utils import write_json
from config import (
    LOCAL_RAW_CSV, LOCAL_CLEANED_PARQUET, LOCAL_STATS_JSON,
    GCS_RAW_CSV, GCS_CLEANED_PARQUET,
    PORTO_BBOX, REGION_BBOX, MIN_POINTS, MAX_DURATION_SEC, MAX_JUMP_KM,
    MIN_TRIP_KM, MAX_TRIP_KM, LOCAL_SAMPLE_FRACTION
)

# Paths are arguments, not constants.  The previous version hard-coded local
# paths, which is why a Dataproc run wrote its output to the master node's own
# disk and lost it when the cluster was deleted.  Passing gs:// URIs here makes
# every stage cloud-native without a separate code path.
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--mode", default="local")
_ap.add_argument("--sample", action="store_true")
_ap.add_argument("--input_path", default=None, help="raw CSV (local path or gs://)")
_ap.add_argument("--output_path", default=None, help="cleaned parquet destination")
_ap.add_argument("--report_path", default=None, help="cleaning report JSON destination")
_args, _ = _ap.parse_known_args()

MODE = _args.mode
SAMPLE = _args.sample
INPUT_PATH = _args.input_path or (LOCAL_RAW_CSV if MODE == "local" else GCS_RAW_CSV)
OUTPUT_PATH = _args.output_path or (LOCAL_CLEANED_PARQUET if MODE == "local"
                                    else GCS_CLEANED_PARQUET)
REPORT_PATH = _args.report_path or LOCAL_STATS_JSON


def create_spark_session():
    builder = SparkSession.builder.appName("PortoTaxi_Stage1_PySparkEngine")
    
    if MODE == "local":
        builder = builder.master("local[*]")
        builder = builder.config("spark.driver.memory", "4g")
        builder = builder.config("spark.executor.memory", "4g")
        builder = builder.config("spark.sql.shuffle.partitions", "16")
    
    builder = builder.config("spark.sql.adaptive.enabled", "true")
    return builder.getOrCreate()


def make_cleaner(counters):
    """Build the per-partition cleaning function, wired to Spark accumulators.

    The rules are counted, not just applied.  The previous version could apply
    eight quality rules but could not answer "how many trips did each one
    remove?" -- which is the first thing anyone asks about a cleaning report.
    Each rule below increments its own accumulator, so the report is derived
    from the run rather than asserted alongside it.
    """
    def clean_partition(rows):
        # Validity is judged against the region; the study area is only used to
        # record how many trips leave it.  See REGION_BBOX in config.py for why.
        min_lng, max_lng = REGION_BBOX["min_lng"], REGION_BBOX["max_lng"]
        min_lat, max_lat = REGION_BBOX["min_lat"], REGION_BBOX["max_lat"]
        p_min_lng, p_max_lng = PORTO_BBOX["min_lng"], PORTO_BBOX["max_lng"]
        p_min_lat, p_max_lat = PORTO_BBOX["min_lat"], PORTO_BBOX["max_lat"]
        max_points = MAX_DURATION_SEC // 15
        max_jump = MAX_JUMP_KM

        rad, sin, cos, asin, sqrt = (math.radians, math.sin, math.cos,
                                     math.asin, math.sqrt)

        for row in rows:
            counters["read"].add(1)

            # ── Rule 1: the telemetry itself flagged the trip as incomplete ──
            missing = row.MISSING_DATA
            if missing and str(missing).upper() == "TRUE":
                counters["missing_data"].add(1)
                continue

            # ── Rule 2: empty or unparseable polyline ───────────────────────
            polyline_str = row.POLYLINE
            if not polyline_str or polyline_str in ("[]", ""):
                counters["empty_polyline"].add(1)
                continue
            try:
                coords = json.loads(polyline_str)
            except Exception:
                counters["bad_json"].add(1)
                continue

            # ── Rule 3: a single point is a location, not a route ───────────
            n_raw = len(coords)
            if n_raw < MIN_POINTS:
                counters["too_few_points"].add(1)
                continue

            # ── Rule 4: meter left running / hardware fault ─────────────────
            if n_raw > max_points:
                counters["too_long"].add(1)
                continue

            # ── Rule 5: any point outside the REGION box ────────────────────
            # Checked on every point, not just the endpoints: a mid-trip glitch
            # passes an endpoint-only check and then distorts that trip's
            # distance and its whole H3 sequence.
            #
            # The box is the region, not the city.  Judging against the city
            # removed 16,716 trips whose median length was 16 km -- journeys to
            # neighbouring towns, counted as satellite errors.
            out_of_box = False
            leaves_porto = False
            for c in coords:
                if not (min_lng <= c[0] <= max_lng and min_lat <= c[1] <= max_lat):
                    out_of_box = True
                    break
                if not (p_min_lng <= c[0] <= p_max_lng
                        and p_min_lat <= c[1] <= p_max_lat):
                    leaves_porto = True
            if out_of_box:
                counters["out_of_bbox"].add(1)
                continue
            if leaves_porto:
                counters["left_study_area"].add(1)

            # ── Rules 6 & 7: consecutive duplicates, and implausible jumps ──
            clean_coords = [coords[0]]
            total_dist_km = 0.0
            has_invalid_jump = False
            prev_lng, prev_lat = coords[0][0], coords[0][1]

            for i in range(1, n_raw):
                curr_lng, curr_lat = coords[i][0], coords[i][1]

                # A stationary taxi keeps transmitting the same fix; collapsing
                # those removes computational noise.  Note that the ELAPSED TIME
                # is preserved separately below -- the points are dropped, the
                # clock is not.
                if curr_lng == prev_lng and curr_lat == prev_lat:
                    continue

                dlat = rad(curr_lat - prev_lat)
                dlng = rad(curr_lng - prev_lng)
                a = (sin(dlat / 2.0) ** 2
                     + cos(rad(prev_lat)) * cos(rad(curr_lat)) * sin(dlng / 2.0) ** 2)
                step_dist_km = 2.0 * 6371.0 * asin(sqrt(a))

                if step_dist_km > max_jump:
                    has_invalid_jump = True
                    break

                total_dist_km += step_dist_km
                clean_coords.append([curr_lng, curr_lat])
                prev_lng, prev_lat = curr_lng, curr_lat

            if has_invalid_jump:
                counters["gps_jump"].add(1)
                continue

            # ── Rule 8: still a route after removing stationary duplicates ──
            if len(clean_coords) < MIN_POINTS:
                counters["stationary"].add(1)
                continue

            # ── Duration: from the ORIGINAL sample count ────────────────────
            # n samples at a fixed 15-second interval span (n-1) intervals.
            # Deriving this from the DEDUPLICATED count -- as the previous
            # version did -- silently erases every second a taxi spent at a red
            # light, which shortens the trip and inflates its mean speed.
            duration_sec = (n_raw - 1) * 15

            # ── Rule 9: a "trip" of a few metres is not a trip ──────────────
            if total_dist_km < MIN_TRIP_KM:
                counters["too_short_distance"].add(1)
                continue

            # ── Rule 10: implausibly long for a city 25 km across ───────────
            # These are meters left running while a taxi circles for hours.
            # They pass every rule above and then dominate the tail of the
            # distance distribution, which is how a P99 ends up equal to the
            # maximum.
            if total_dist_km > MAX_TRIP_KM:
                counters["too_long_distance"].add(1)
                continue

            avg_speed_kmh = (total_dist_km / (duration_sec / 3600.0)) if duration_sec > 0 else 0.0

            counters["kept"].add(1)
            struct_coords = [{"lng": pt[0], "lat": pt[1]} for pt in clean_coords]

            yield (
                str(row.TRIP_ID),
                str(row.CALL_TYPE) if row.CALL_TYPE else "",
                str(row.ORIGIN_CALL) if row.ORIGIN_CALL else "",
                str(row.ORIGIN_STAND) if row.ORIGIN_STAND else "",
                int(row.TAXI_ID) if row.TAXI_ID else 0,
                int(row.TIMESTAMP) if row.TIMESTAMP else 0,
                str(row.DAY_TYPE) if row.DAY_TYPE else "",
                polyline_str,
                struct_coords,
                len(clean_coords),
                int(n_raw),
                duration_sec,
                float(round(total_dist_km, 4)),
                float(round(coords[0][0], 6)),
                float(round(coords[0][1], 6)),
                float(round(coords[-1][0], 6)),
                float(round(coords[-1][1], 6)),
                float(round(avg_speed_kmh, 2))
            )

    return clean_partition


def main():
    start_time = time.time()
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Stage 1: High-Performance PySpark      ║")
    print(f"║  Mode: {MODE:<10s}  Full Dataset: {str(not SAMPLE):<6s}                 ║")
    print(f"║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<20s}                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        csv_path = INPUT_PATH
        print(f"\nSTEP 1: Loading raw dataset from {csv_path}...")
        
        raw_schema = StructType([
            StructField("TRIP_ID", StringType(), True),
            StructField("CALL_TYPE", StringType(), True),
            StructField("ORIGIN_CALL", StringType(), True),
            StructField("ORIGIN_STAND", StringType(), True),
            StructField("TAXI_ID", IntegerType(), True),
            StructField("TIMESTAMP", LongType(), True),
            StructField("DAY_TYPE", StringType(), True),
            StructField("MISSING_DATA", StringType(), True),
            StructField("POLYLINE", StringType(), True),
        ])
        
        df_raw = spark.read.csv(
            csv_path, header=True, schema=raw_schema, quote='"', escape='"', multiLine=True
        )
        
        if SAMPLE:
            print(f"  Sampling {LOCAL_SAMPLE_FRACTION * 100}% for local development...")
            df_raw = df_raw.sample(fraction=LOCAL_SAMPLE_FRACTION, seed=42)
            
        print("\nSTEP 2: Processing 1.71M trips in PySpark mapPartitions across CPU cores...")
        
        rule_names = ["read", "missing_data", "empty_polyline", "bad_json",
                      "too_few_points", "too_long", "out_of_bbox", "gps_jump",
                      "stationary", "too_short_distance", "too_long_distance",
                      "left_study_area", "kept"]
        counters = {name: spark.sparkContext.accumulator(0) for name in rule_names}

        cleaned_rdd = df_raw.rdd.mapPartitions(make_cleaner(counters))
        
        clean_schema = StructType([
            StructField("TRIP_ID", StringType(), True),
            StructField("CALL_TYPE", StringType(), True),
            StructField("ORIGIN_CALL", StringType(), True),
            StructField("ORIGIN_STAND", StringType(), True),
            StructField("TAXI_ID", IntegerType(), True),
            StructField("TIMESTAMP", LongType(), True),
            StructField("DAY_TYPE", StringType(), True),
            StructField("POLYLINE", StringType(), True),
            StructField("coordinates", ArrayType(
                StructType([
                    StructField("lng", DoubleType(), True),
                    StructField("lat", DoubleType(), True)
                ])
            ), True),
            StructField("num_points", IntegerType(), True),
            StructField("num_points_raw", IntegerType(), True),
            StructField("duration_sec", IntegerType(), True),
            StructField("distance_km", DoubleType(), True),
            StructField("start_lng", DoubleType(), True),
            StructField("start_lat", DoubleType(), True),
            StructField("end_lng", DoubleType(), True),
            StructField("end_lat", DoubleType(), True),
            StructField("avg_speed_kmh", DoubleType(), True),
        ])
        
        df_clean = spark.createDataFrame(cleaned_rdd, schema=clean_schema)
        
        # Extract Datetime features
        df_clean = df_clean.withColumn("trip_datetime", F.from_unixtime(F.col("TIMESTAMP")))
        df_clean = df_clean.withColumn("hour_of_day", F.hour(F.col("trip_datetime")))
        df_clean = df_clean.withColumn("day_of_week", F.dayofweek(F.col("trip_datetime")))
        
        # Persist cleaned DataFrame
        df_clean = df_clean.persist()
        
        total_clean = df_clean.count()
        print(f"  ✓ Stage 1 Cleaning completed! Valid clean trips: {total_clean:,}")

        # Accumulators are only meaningful after an action, and they double-count
        # if the stage is recomputed -- so they are read once, here, immediately
        # after the count that materialised the persisted DataFrame.
        rules = {name: acc.value for name, acc in counters.items()}
        total_read = rules.pop("read")
        kept = rules.pop("kept")
        # Not a removal: trips that leave the study area but stay in the region
        # are KEPT.  Counted so the report can say how many there are.
        left_study_area = rules.pop("left_study_area")
        removed = total_read - kept

        RULE_LABELS = {
            "missing_data":       "1. MISSING_DATA flag set by the telemetry",
            "empty_polyline":     "2. empty POLYLINE (booking cancelled immediately)",
            "bad_json":           "2b. POLYLINE not valid JSON",
            "too_few_points":     "3. fewer than 2 GPS points",
            "too_long":           "4. duration over 24 hours (meter left running)",
            "out_of_bbox":        "5. a GPS point outside the wider region (satellite error)",
            "gps_jump":           "6. jump implying over 200 km/h (satellite error)",
            "stationary":         "7. under 2 distinct points after deduplication",
            "too_short_distance": f"8. shorter than {MIN_TRIP_KM} km (not a journey)",
            "too_long_distance":  f"9. longer than {MAX_TRIP_KM} km (implausible for this city)",
        }

        print("\n  Per-rule breakdown:")
        print(f"    {'rule':<62}{'trips':>10}{'share':>9}")
        for key, label in RULE_LABELS.items():
            n = rules.get(key, 0)
            pct = 100.0 * n / total_read if total_read else 0.0
            print(f"    {label:<62}{n:>10,}{pct:>8.3f}%")
        print(f"    {'-' * 81}")
        print(f"    {'removed':<62}{removed:>10,}{100.0 * removed / max(total_read, 1):>8.3f}%")
        print(f"    {'kept':<62}{kept:>10,}{100.0 * kept / max(total_read, 1):>8.3f}%")

        # STEP 3: Generate Summary Statistics
        print("\nSTEP 3: Generating Statistics...")
        num_taxis = df_clean.select("TAXI_ID").distinct().count()
        print(f"  Overview: {total_clean:,} trips, {num_taxis:,} unique taxis")

        df_clean.select("num_points", "num_points_raw", "duration_sec",
                        "distance_km", "avg_speed_kmh").describe().show()

        # relativeError 1e-4, not 1e-2.  At 1e-2 the reported P99 can land on the
        # maximum of a long-tailed distribution, which is what made the previous
        # report show "P99 = 617 km" -- a figure equal to the single most extreme
        # trip in the dataset.
        QS = [0.01, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
        percentiles = df_clean.approxQuantile("distance_km", QS, 1e-4)
        dur_pct = df_clean.approxQuantile("duration_sec", QS, 1e-4)
        labels = ["p1", "p25", "p50", "p75", "p90", "p95", "p99"]
        print("  Distance percentiles (km):")
        for lab, v in zip(labels, percentiles):
            print(f"    {lab:>4}: {v:8.3f} km")

        max_dist = df_clean.agg(F.max("distance_km")).first()[0]
        dedup_ratio = df_clean.agg(
            F.avg(F.col("num_points") / F.col("num_points_raw"))).first()[0]

        cleaning_report = {
            "summary": {
                "raw_trips_read": total_read,
                "final_clean_trips": kept,
                "removed_trips": removed,
                "removed_pct": round(100.0 * removed / max(total_read, 1), 4),
                "unique_taxis": num_taxis,
                "mean_points_kept_after_dedup": round(dedup_ratio, 4)
                if dedup_ratio is not None else None,
                "kept_trips_leaving_study_area": left_study_area,
                "kept_trips_leaving_study_area_pct": round(
                    100.0 * left_study_area / max(kept, 1), 4),
            },
            "per_rule_removed": {
                key: {"label": label, "trips": rules.get(key, 0),
                      "pct_of_raw": round(100.0 * rules.get(key, 0) / max(total_read, 1), 4)}
                for key, label in RULE_LABELS.items()
            },
            "thresholds": {
                "porto_bbox": PORTO_BBOX,
                "region_bbox": REGION_BBOX,
                "min_points": MIN_POINTS,
                "max_duration_sec": MAX_DURATION_SEC,
                "max_jump_km": round(MAX_JUMP_KM, 4),
                "min_trip_km": MIN_TRIP_KM,
                "max_trip_km": MAX_TRIP_KM,
            },
            "distance_percentiles_km": dict(zip(labels, [round(v, 4) for v in percentiles])),
            "duration_percentiles_sec": dict(zip(labels, [round(v, 1) for v in dur_pct])),
            "max_distance_km": round(max_dist, 4) if max_dist is not None else None,
            "notes": {
                "duration": "derived from the ORIGINAL sample count: (n_raw - 1) * 15 s. "
                            "Deduplication removes stationary points but not the time "
                            "they represent.",
                "quantiles": "approxQuantile with relativeError=1e-4.",
                "bounding_box": "Validity is judged against region_bbox. porto_bbox is "
                                "the study area; trips leaving it are kept and counted "
                                "as kept_trips_leaving_study_area. Judging validity "
                                "against the study area removed 16,716 trips of median "
                                "length 16 km -- journeys to neighbouring towns, not "
                                "satellite errors.",
            },
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        # STEP 4: Save Parquet & Statistics JSON
        output_path = OUTPUT_PATH
        report_path = REPORT_PATH
        
        print(f"\nSTEP 4: Saving Parquet to {output_path}...")
        df_clean.write.mode("overwrite").parquet(output_path)
        print(f"  ✓ Saved Parquet successfully!")
        
        write_json(spark, report_path, cleaning_report)
        print(f"  ✓ Cleaning report saved to {report_path}")
        
        elapsed = time.time() - start_time
        print(f"\n{'=' * 70}")
        print(f"  ✅ Stage 1 completed successfully in {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
        print(f"{'=' * 70}")
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
