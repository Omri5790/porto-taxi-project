"""
Porto Taxi Trajectory Project – Stage 2: H3 Spatial Encoding Engine
===================================================================
This script performs Stage 2 Spatial Encoding on the 1.62M cleaned Porto Taxi trips.
It converts continuous GPS coordinates into discrete Uber H3 Hexagonal Cell sequences
at Resolution 8 (~0.73 km² neighborhood level) and Resolution 9 (~0.10 km² street level).

Optimizations:
1. High-Performance PySpark MapPartitions execution in native Python C-space.
2. Consecutive Cell Deduplication (collapses repeated stationary/traffic pings).
3. Parquet storage with schema validation.
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
    LOCAL_CLEANED_PARQUET, LOCAL_SAMPLE_FRACTION
)

OUTPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_H3_REPORT = "output/h3_encoding_report.json"

MODE = "local"
SAMPLE = False

if "--mode" in sys.argv:
    idx = sys.argv.index("--mode")
    if idx + 1 < len(sys.argv):
        MODE = sys.argv[idx + 1]

if "--sample" in sys.argv:
    SAMPLE = True


def create_spark_session():
    builder = SparkSession.builder.appName("PortoTaxi_Stage2_H3SpatialEncoding")
    
    if MODE == "local":
        builder = builder.master("local[*]")
        builder = builder.config("spark.driver.memory", "4g")
        builder = builder.config("spark.executor.memory", "4g")
        builder = builder.config("spark.sql.shuffle.partitions", "16")
    
    builder = builder.config("spark.sql.adaptive.enabled", "true")
    return builder.getOrCreate()


def encode_h3_partition(rows):
    """
    Process each partition: Map GPS points to Uber H3 Resolution 8 & 9 cells,
    and collapse consecutive identical cell pings (Consecutive Deduplication).
    """
    latlng_to_cell = h3.latlng_to_cell
    
    for row in rows:
        coords = row.coordinates
        if not coords or len(coords) < 2:
            continue
            
        h3_res8 = []
        h3_res9 = []
        h3_res10 = []
        
        prev_cell8 = None
        prev_cell9 = None
        prev_cell10 = None
        
        for pt in coords:
            lat = pt["lat"]
            lng = pt["lng"]
            
            # Resolution 8 (~0.73 km²)
            cell8 = latlng_to_cell(lat, lng, 8)
            if cell8 != prev_cell8:
                h3_res8.append(cell8)
                prev_cell8 = cell8
                
            # Resolution 9 (~0.10 km²)
            cell9 = latlng_to_cell(lat, lng, 9)
            if cell9 != prev_cell9:
                h3_res9.append(cell9)
                prev_cell9 = cell9

            # Resolution 10 (~0.015 km² / 66m edge)
            cell10 = latlng_to_cell(lat, lng, 10)
            if cell10 != prev_cell10:
                h3_res10.append(cell10)
                prev_cell10 = cell10
                
        if not h3_res8 or not h3_res9 or not h3_res10:
            continue
            
        start_h3_res8 = h3_res8[0]
        end_h3_res8 = h3_res8[-1]
        start_h3_res9 = h3_res9[0]
        end_h3_res9 = h3_res9[-1]
        start_h3_res10 = h3_res10[0]
        end_h3_res10 = h3_res10[-1]
        
        yield (
            str(row.TRIP_ID),
            str(row.CALL_TYPE),
            str(row.ORIGIN_CALL),
            str(row.ORIGIN_STAND),
            int(row.TAXI_ID),
            int(row.TIMESTAMP),
            str(row.DAY_TYPE),
            str(row.POLYLINE),
            coords,
            int(row.num_points),
            int(row.duration_sec),
            float(row.distance_km),
            float(row.start_lng),
            float(row.start_lat),
            float(row.end_lng),
            float(row.end_lat),
            float(row.avg_speed_kmh),
            str(row.trip_datetime),
            int(row.hour_of_day),
            int(row.day_of_week),
            h3_res8,
            h3_res9,
            h3_res10,
            start_h3_res8,
            end_h3_res8,
            start_h3_res9,
            end_h3_res9,
            start_h3_res10,
            end_h3_res10,
            len(h3_res8),
            len(h3_res9),
            len(h3_res10)
        )


def main():
    start_time = time.time()
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Stage 2: H3 Spatial Encoding Engine    ║")
    print("║  Resolutions: Res 8 (~0.73km²), Res 9 (~0.10km²), Res 10 (~0.015km²)║")
    print(f"║  Mode: {MODE:<10s}  Full Dataset: {str(not SAMPLE):<6s}                 ║")
    print(f"║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<20s}                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        input_parquet = LOCAL_CLEANED_PARQUET
        print(f"\nSTEP 1: Reading cleaned trips dataset from {input_parquet}...")
        df_clean = spark.read.parquet(input_parquet)
        
        if MODE == "local" and SAMPLE:
            print(f"  Sampling {LOCAL_SAMPLE_FRACTION * 100}% for local testing...")
            df_clean = df_clean.sample(fraction=LOCAL_SAMPLE_FRACTION, seed=42)
            
        total_input = df_clean.count()
        print(f"  ✓ Loaded {total_input:,} cleaned trips for H3 spatial encoding.")
        
        print("\nSTEP 2: Encoding trajectories into H3 Res 8, Res 9 & Res 10 in PySpark mapPartitions...")
        
        encoded_rdd = df_clean.rdd.mapPartitions(encode_h3_partition)
        
        encoded_schema = StructType([
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
            StructField("duration_sec", IntegerType(), True),
            StructField("distance_km", DoubleType(), True),
            StructField("start_lng", DoubleType(), True),
            StructField("start_lat", DoubleType(), True),
            StructField("end_lng", DoubleType(), True),
            StructField("end_lat", DoubleType(), True),
            StructField("avg_speed_kmh", DoubleType(), True),
            StructField("trip_datetime", StringType(), True),
            StructField("hour_of_day", IntegerType(), True),
            StructField("day_of_week", IntegerType(), True),
            StructField("h3_res8", ArrayType(StringType()), True),
            StructField("h3_res9", ArrayType(StringType()), True),
            StructField("h3_res10", ArrayType(StringType()), True),
            StructField("start_h3_res8", StringType(), True),
            StructField("end_h3_res8", StringType(), True),
            StructField("start_h3_res9", StringType(), True),
            StructField("end_h3_res9", StringType(), True),
            StructField("start_h3_res10", StringType(), True),
            StructField("end_h3_res10", StringType(), True),
            StructField("h3_res8_length", IntegerType(), True),
            StructField("h3_res9_length", IntegerType(), True),
            StructField("h3_res10_length", IntegerType(), True),
        ])
        
        df_encoded = spark.createDataFrame(encoded_rdd, schema=encoded_schema)
        
        # STEP 3: Write Parquet directly to avoid JVM heap cache thrashing
        print(f"\nSTEP 3: Saving H3-encoded Parquet directly to {OUTPUT_H3_PARQUET}...")
        df_encoded.write.mode("overwrite").parquet(OUTPUT_H3_PARQUET)
        print("  ✓ Saved H3 Parquet dataset successfully!")
        
        # STEP 4: Read encoded Parquet to verify and compute H3 Grid Analytics
        print("\nSTEP 4: Computing H3 Grid Analytics on saved Parquet...")
        df_saved = spark.read.parquet(OUTPUT_H3_PARQUET)
        total_encoded = df_saved.count()
        
        unique_h3_res8 = df_saved.select(F.explode("h3_res8").alias("cell")).distinct().count()
        unique_h3_res9 = df_saved.select(F.explode("h3_res9").alias("cell")).distinct().count()
        unique_h3_res10 = df_saved.select(F.explode("h3_res10").alias("cell")).distinct().count()
        
        print(f"  • Total Clean Trips H3-Encoded: {total_encoded:,}")
        print(f"  • Unique H3 Res 8 Cells Covered in Porto: {unique_h3_res8:,} cells (~0.73 km² each)")
        print(f"  • Unique H3 Res 9 Cells Covered in Porto: {unique_h3_res9:,} cells (~0.10 km² each)")
        print(f"  • Unique H3 Res 10 Cells Covered in Porto: {unique_h3_res10:,} cells (~0.015 km² / 66m edge)")
        
        df_saved.select("h3_res8_length", "h3_res9_length", "h3_res10_length").describe().show()
        
        h3_report = {
            "summary": {
                "total_trips_encoded": total_encoded,
                "unique_h3_res8_cells": unique_h3_res8,
                "unique_h3_res9_cells": unique_h3_res9,
                "unique_h3_res10_cells": unique_h3_res10,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        os.makedirs(os.path.dirname(OUTPUT_H3_REPORT), exist_ok=True)
        with open(OUTPUT_H3_REPORT, "w", encoding="utf-8") as f:
            json.dump(h3_report, f, indent=2, ensure_ascii=False)
        print(f"  ✓ H3 Encoding report saved to {OUTPUT_H3_REPORT}")
        
        elapsed = time.time() - start_time
        print(f"\n{'=' * 70}")
        print(f"  ✅ Stage 2 H3 Spatial Encoding completed in {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
        print(f"{'=' * 70}")
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
