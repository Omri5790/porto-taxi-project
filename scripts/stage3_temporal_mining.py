"""
Porto Taxi Trajectory Project – Stage 3: Temporal Dynamic Sub-Route & Ridge Mining Engine
========================================================================================
This script categorizes 1.62M trips into 3 distinct Time Windows:
- 🌅 Morning Rush (07:00 - 10:00)
- 🌇 Evening Rush (16:00 - 19:00)
- 🌙 Nightlife Dynamics (23:00 - 04:00)

It mines H3 cell frequencies, density ridges, and Top 10 active sub-routes for EACH
time window separately, saving results to `output/temporal_subroutes.json`.
"""

import sys
import os
import json
import time
from datetime import datetime
from collections import Counter

# Ensure user site packages are in python path for H3
user_site = os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages")
if os.path.exists(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import h3
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    LongType, DoubleType, ArrayType
)

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_TEMPORAL_JSON = "output/temporal_subroutes.json"
OUTPUT_TEMPORAL_REPORT = "output/stage3_temporal_report.json"

MODE = "local"


def create_spark_session():
    builder = SparkSession.builder.appName("PortoTaxi_Stage3_TemporalMining")
    if MODE == "local":
        builder = builder.master("local[*]")
        builder = builder.config("spark.driver.memory", "6g")
        builder = builder.config("spark.executor.memory", "6g")
        builder = builder.config("spark.sql.shuffle.partitions", "16")
    return builder.getOrCreate()


def extract_temporal_subroutes_partition(rows):
    """
    Classify each trip by hour_of_day:
    - Morning: 7 <= hour <= 10
    - Evening: 16 <= hour <= 19
    - Night: hour >= 23 or hour <= 4
    Extract sub-sequences for each window.
    """
    for row in rows:
        hour = row.hour_of_day
        window = None
        if 7 <= hour <= 10:
            window = "morning"
        elif 16 <= hour <= 19:
            window = "evening"
        elif hour >= 23 or hour <= 4:
            window = "night"
        else:
            continue
            
        duration = row.duration_sec
        distance = row.distance_km
        
        # Extract Res 8, 9, 10 cells for this window
        cells_r9 = row.h3_res9
        if cells_r9 and len(cells_r9) >= 3:
            n = len(cells_r9)
            for k in [3, 4]:
                if n >= k:
                    for i in range(n - k + 1):
                        sub_seq = tuple(cells_r9[i : i + k])
                        yield ((window, "res9", sub_seq), (1, duration, distance))


def main():
    start_time = time.time()
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Temporal Dynamic Mining Engine         ║")
    print("║  Time Windows: 🌅 Morning (7-10) | 🌇 Evening (16-19) | 🌙 Night (23-4) ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        print(f"\nSTEP 1: Reading H3-encoded dataset from {INPUT_H3_PARQUET}...")
        df_h3 = spark.read.parquet(INPUT_H3_PARQUET)
        total_input = df_h3.count()
        print(f"  ✓ Loaded {total_input:,} H3-encoded trips.")
        
        print("\nSTEP 2: Mining Temporal Window Sub-Routes in PySpark...")
        temporal_rdd = df_h3.rdd.mapPartitions(extract_temporal_subroutes_partition)
        
        reduced_rdd = temporal_rdd.reduceByKey(
            lambda a, b: (a[0] + b[0], a[1] + b[1], a[2] + b[2])
        )
        
        MIN_SUPPORT = 50
        filtered_rdd = reduced_rdd.filter(lambda x: x[1][0] >= MIN_SUPPORT)
        
        def format_output(item):
            (window, res_name, sub_seq), (count, sum_dur, sum_dist) = item
            avg_dur = float(round(sum_dur / count, 1))
            avg_dist = float(round(sum_dist / count, 2))
            avg_speed = float(round((avg_dist / (avg_dur / 3600.0)), 1)) if avg_dur > 0 else 0.0
            
            cell_coords = []
            for cell in sub_seq:
                try:
                    lat, lng = h3.cell_to_latlng(cell)
                    cell_coords.append({"cell": cell, "lat": round(lat, 6), "lng": round(lng, 6)})
                except Exception:
                    pass
                    
            return (
                window,
                res_name,
                list(sub_seq),
                int(count),
                avg_dur,
                avg_speed,
                cell_coords
            )
            
        results_list = filtered_rdd.map(format_output).collect()
        print(f"  ✓ Mined {len(results_list):,} sub-routes across temporal windows.")
        
        # Organize results by window
        temporal_data = {
            "morning": [],
            "evening": [],
            "night": []
        }
        
        for row in results_list:
            w, res, seq, count, dur, speed, coords = row
            temporal_data[w].append({
                "window": w,
                "res_level": res,
                "h3_sequence": seq,
                "trip_support": count,
                "avg_duration_sec": dur,
                "avg_speed_kmh": speed,
                "cell_coordinates": coords
            })
            
        # Sort each window by support descending and take top 10
        for w in ["morning", "evening", "night"]:
            temporal_data[w] = sorted(temporal_data[w], key=lambda x: x["trip_support"], reverse=True)[:10]
            print(f"  • {w.capitalize()} Window: Top {len(temporal_data[w])} Sub-Routes mined. Top support: {temporal_data[w][0]['trip_support'] if temporal_data[w] else 0:,} trips.")
            
        os.makedirs(os.path.dirname(OUTPUT_TEMPORAL_JSON), exist_ok=True)
        with open(OUTPUT_TEMPORAL_JSON, "w", encoding="utf-8") as f:
            json.dump(temporal_data, f, indent=2, ensure_ascii=False)
        print(f"\n  ✓ Saved Temporal Sub-Routes JSON to {OUTPUT_TEMPORAL_JSON}")
        
        elapsed = time.time() - start_time
        print(f"\n{'=' * 70}")
        print(f"  ✅ Stage 3 Temporal Dynamic Mining completed in {elapsed:.1f} seconds")
        print(f"{'=' * 70}")
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
