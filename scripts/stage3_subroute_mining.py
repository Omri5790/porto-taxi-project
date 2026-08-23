"""
Porto Taxi Trajectory Project – Stage 3: Sub-Route Mining Engine
================================================================
This script extracts frequent continuous sub-sequences (n-grams) from 1.62M H3-encoded
trips across Resolution 8, Resolution 9, and Resolution 10.
It aggregates sub-route support, merges sub-paths, calculates trip speed/duration stats,
and outputs the Top 20 Frequent Sub-Routes in Porto.
"""

import sys
import os
import json
import time
from datetime import datetime

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

from config import (
    LOCAL_H3_PARQUET, LOCAL_SAMPLE_FRACTION
)

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_SUBROUTES_PARQUET = "output/top_20_subroutes.parquet"
OUTPUT_SUBROUTES_JSON = "output/top_20_subroutes.json"
OUTPUT_SUBROUTES_REPORT = "output/stage3_subroute_report.json"

MODE = "local"
SAMPLE = False

if "--mode" in sys.argv:
    idx = sys.argv.index("--mode")
    if idx + 1 < len(sys.argv):
        MODE = sys.argv[idx + 1]

if "--sample" in sys.argv:
    SAMPLE = True


def create_spark_session():
    builder = SparkSession.builder.appName("PortoTaxi_Stage3_SubRouteMining")
    
    if MODE == "local":
        builder = builder.master("local[*]")
        builder = builder.config("spark.driver.memory", "6g")
        builder = builder.config("spark.executor.memory", "6g")
        builder = builder.config("spark.sql.shuffle.partitions", "16")
    
    builder = builder.config("spark.sql.adaptive.enabled", "true")
    return builder.getOrCreate()


def extract_subroutes_partition(rows):
    """
    Extract continuous sub-sequences of length 3 to 6 H3 cells from trajectories.
    Yields ((res_level, tuple_of_h3_cells), (1, duration_sec, distance_km))
    """
    for row in rows:
        duration = row.duration_sec
        distance = row.distance_km
        
        # Process Resolution 8, 9, 10
        for res_name, cells in [("res8", row.h3_res8), ("res9", row.h3_res9), ("res10", row.h3_res10)]:
            if not cells or len(cells) < 3:
                continue
                
            n = len(cells)
            # Extract n-grams of length 3, 4, 5
            for k in [3, 4, 5]:
                if n >= k:
                    for i in range(n - k + 1):
                        sub_seq = tuple(cells[i : i + k])
                        yield ((res_name, sub_seq), (1, duration, distance))


def main():
    start_time = time.time()
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Stage 3: Sub-Route Mining Engine       ║")
    print(f"║  Mode: {MODE:<10s}  Full Dataset: {str(not SAMPLE):<6s}                 ║")
    print(f"║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<20s}                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        input_parquet = INPUT_H3_PARQUET if os.path.exists(INPUT_H3_PARQUET) else LOCAL_H3_PARQUET
        print(f"\nSTEP 1: Reading H3-encoded trips dataset from {input_parquet}...")
        df_h3 = spark.read.parquet(input_parquet)
        
        if MODE == "local" and SAMPLE:
            print(f"  Sampling {LOCAL_SAMPLE_FRACTION * 100}% for local testing...")
            df_h3 = df_h3.sample(fraction=LOCAL_SAMPLE_FRACTION, seed=42)
            
        total_input = df_h3.count()
        print(f"  ✓ Loaded {total_input:,} H3-encoded trips for sub-route mining.")
        
        print("\nSTEP 2: Mining Frequent Sub-Sequences (N-Grams) in PySpark mapPartitions...")
        
        subroutes_rdd = df_h3.rdd.mapPartitions(extract_subroutes_partition)
        
        # Aggregate (count, sum_duration, sum_distance)
        reduced_rdd = subroutes_rdd.reduceByKey(
            lambda a, b: (a[0] + b[0], a[1] + b[1], a[2] + b[2])
        )
        
        # Filter subroutes with support >= 300 trips
        MIN_SUPPORT = 300
        filtered_rdd = reduced_rdd.filter(lambda x: x[1][0] >= MIN_SUPPORT)
        
        def format_output(item):
            (res_name, sub_seq), (count, sum_dur, sum_dist) = item
            avg_dur = float(round(sum_dur / count, 1))
            avg_dist = float(round(sum_dist / count, 2))
            avg_speed = float(round((avg_dist / (avg_dur / 3600.0)), 1)) if avg_dur > 0 else 0.0
            
            # Pre-compute centroid lat/lng coordinates for each H3 cell in sequence
            cell_coords = []
            for cell in sub_seq:
                try:
                    lat, lng = h3.cell_to_latlng(cell)
                    cell_coords.append({"cell": cell, "lat": round(lat, 6), "lng": round(lng, 6)})
                except Exception:
                    pass
                    
            return (
                res_name,
                list(sub_seq),
                len(sub_seq),
                int(count),
                avg_dur,
                avg_dist,
                avg_speed,
                sub_seq[0],
                sub_seq[-1],
                cell_coords
            )
            
        formatted_rdd = filtered_rdd.map(format_output)
        
        schema = StructType([
            StructField("res_level", StringType(), True),
            StructField("h3_sequence", ArrayType(StringType()), True),
            StructField("sequence_length", IntegerType(), True),
            StructField("trip_support", IntegerType(), True),
            StructField("avg_duration_sec", DoubleType(), True),
            StructField("avg_distance_km", DoubleType(), True),
            StructField("avg_speed_kmh", DoubleType(), True),
            StructField("start_h3", StringType(), True),
            StructField("end_h3", StringType(), True),
            StructField("cell_coordinates", ArrayType(
                StructType([
                    StructField("cell", StringType(), True),
                    StructField("lat", DoubleType(), True),
                    StructField("lng", DoubleType(), True)
                ])
            ), True)
        ])
        
        df_subroutes = spark.createDataFrame(formatted_rdd, schema=schema)
        
        print("\nSTEP 3: Ranking and Extracting Top 20 Sub-Routes in Porto...")
        # Order by trip support descending
        df_top20 = df_subroutes.orderBy(F.col("trip_support").desc()).limit(20)
        df_top20 = df_top20.persist()
        
        top20_count = df_top20.count()
        print(f"  ✓ Successfully extracted Top {top20_count} Sub-Routes!")
        df_top20.select("res_level", "sequence_length", "trip_support", "avg_duration_sec", "avg_speed_kmh").show(20, truncate=False)
        
        # Save Parquet
        print(f"\nSTEP 4: Saving Top 20 Sub-Routes Parquet to {OUTPUT_SUBROUTES_PARQUET}...")
        df_top20.write.mode("overwrite").parquet(OUTPUT_SUBROUTES_PARQUET)
        print("  ✓ Parquet saved successfully!")
        
        # Save JSON
        top20_list = [row.asDict(recursive=True) for row in df_top20.collect()]
        
        os.makedirs(os.path.dirname(OUTPUT_SUBROUTES_JSON), exist_ok=True)
        with open(OUTPUT_SUBROUTES_JSON, "w", encoding="utf-8") as f:
            json.dump(top20_list, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Saved Top 20 Sub-Routes JSON to {OUTPUT_SUBROUTES_JSON}")
        
        # Save Report JSON
        subroute_report = {
            "summary": {
                "top_subroutes_mined": top20_count,
                "min_trip_support": MIN_SUPPORT,
                "top_subroute_support": top20_list[0]["trip_support"] if top20_list else 0,
                "timestamp": datetime.now().isoformat()
            }
        }
        with open(OUTPUT_SUBROUTES_REPORT, "w", encoding="utf-8") as f:
            json.dump(subroute_report, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Sub-Route report saved to {OUTPUT_SUBROUTES_REPORT}")
        
        elapsed = time.time() - start_time
        print(f"\n{'=' * 70}")
        print(f"  ✅ Stage 3 Sub-Route Mining completed in {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
        print(f"{'=' * 70}")
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
