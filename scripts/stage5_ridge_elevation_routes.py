"""
Porto Taxi Project – Stage 5: Topographic Ridge-Based Route Discovery
=====================================================================================
New algorithm requested by user:
1. Encode trips to high-resolution H3 cells (Res 11).
2. Elevate visited cells by +2.
3. Elevate their 6 immediate neighbors by +1 (to form "ridges").
4. The most crowded intersections become mountain peaks.
5. Extract the 100 paths walking along these highest ridges.
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
import h3
from pyspark.sql import SparkSession
from pyspark.sql import Row


INPUT_CSV = "data/train.csv"
OUTPUT_JSON = "output/ridge_elevation_routes.json"
H3_RESOLUTION = 11


def haversine_km(lat1, lng1, lat2, lng2):
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def compute_route_length_km(h3_cells):
    total = 0.0
    for i in range(len(h3_cells) - 1):
        try:
            lat1, lng1 = h3.cell_to_latlng(h3_cells[i])
            lat2, lng2 = h3.cell_to_latlng(h3_cells[i + 1])
            total += haversine_km(lat1, lng1, lat2, lng2)
        except Exception:
            pass
    return round(total, 2)


def process_trip_partition(partition):
    """
    Parse POLYLINE, encode to Res 11, emit (cell, score).
    Direct hit = +2. Neighbors = +1.
    """
    for row in partition:
        polyline_str = row.POLYLINE
        if not polyline_str or polyline_str == "[]":
            continue
        
        try:
            coords = json.loads(polyline_str)
        except Exception:
            continue
            
        if len(coords) < 3:
            continue
            
        visited_cells = set()
        for lng, lat in coords:
            try:
                cell = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
                visited_cells.add(cell)
            except Exception:
                pass
                
        if not visited_cells:
            continue
            
        # Emit +2 for visited cells
        for cell in visited_cells:
            yield (cell, 2)
            
        # Emit +1 for neighbors (only if they were not visited directly in this trip)
        for cell in visited_cells:
            try:
                neighbors = h3.grid_disk(cell, 1)
                for n in neighbors:
                    if n not in visited_cells:
                        yield (n, 1)
            except Exception:
                pass


def walk_ridge(peak_cell, global_elevation, used_cells, max_len=150):
    """
    Bi-directional greedy ridge walker starting from a peak.
    Always moves to the highest unvisited neighbor.
    """
    path = [peak_cell]
    current_used = set([peak_cell])
    
    # We walk in two directions from the peak to form a full continuous route.
    # First direction:
    curr = peak_cell
    while len(path) < max_len:
        try:
            neighbors = h3.grid_disk(curr, 1)
        except:
            break
            
        best_n = None
        best_e = -1
        for n in neighbors:
            if n != curr and n not in current_used and n not in used_cells:
                e = global_elevation.get(n, 0)
                if e > best_e:
                    best_e = e
                    best_n = n
                    
        # Stop if we hit a flat area / valley
        if best_n is None or best_e < global_elevation[peak_cell] * 0.05:
            break
            
        path.append(best_n)
        current_used.add(best_n)
        curr = best_n

    # Second direction (reverse path and walk the other way from peak)
    path.reverse()
    curr = peak_cell
    while len(path) < max_len * 2:
        try:
            neighbors = h3.grid_disk(curr, 1)
        except:
            break
            
        best_n = None
        best_e = -1
        for n in neighbors:
            if n != curr and n not in current_used and n not in used_cells:
                e = global_elevation.get(n, 0)
                if e > best_e:
                    best_e = e
                    best_n = n
                    
        if best_n is None or best_e < global_elevation[peak_cell] * 0.05:
            break
            
        path.append(best_n)
        current_used.add(best_n)
        curr = best_n
        
    # Mark as globally used so next routes don't overlap entirely
    for c in current_used:
        used_cells.add(c)
        
    return path


def main():
    t0 = time.time()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Stage 5: Topographic Ridge-Based Route Discovery           ║")
    print(f"║  Resolution: H3 Res {H3_RESOLUTION} (High-Precision Mapping)               ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    builder = SparkSession.builder.appName("Stage5_Ridge_Topography")
    builder = (builder.master("local[*]")
               .config("spark.driver.memory", "8g")
               .config("spark.executor.memory", "4g"))
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", type=str, default="data/train.csv")
    args, _ = parser.parse_known_args()
    input_csv = args.input_path

    try:
        print(f"\n[1/4] Reading raw GPS data from {input_csv} and applying topographic elevation...")
        # Use PySpark's built-in CSV reader which correctly handles quoted JSON arrays
        df_raw = spark.read.option("header", "true").option("escape", '"').csv(input_csv)
        
        print("[2/4] Building global elevation map (ReduceByKey)...")
        # Process partitions
        elevation_rdd = df_raw.rdd.mapPartitions(process_trip_partition)
        
        # Reduce by key to sum all elevations
        summed_elevation = elevation_rdd.reduceByKey(lambda a, b: a + b)
        
        # Collect to driver safely using Arrow toPandas() to avoid Py4J socket buffer errors on Mac
        spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
        df_elev = summed_elevation.toDF(["cell", "elevation"])
        pdf = df_elev.toPandas()
        global_elevation = dict(zip(pdf["cell"], pdf["elevation"]))
        
        print(f"  ✓ Built elevation map with {len(global_elevation):,} highly precise H3 cells.")
        
        # Identify the peaks (sort cells by elevation)
        print("\n[3/4] Locating peaks and walking ridges...")
        sorted_cells = sorted(global_elevation.items(), key=lambda x: -x[1])
        peaks = sorted_cells[:5000]
        
        print(f"  Top Peak Elevation: {peaks[0][1]:,} points")
        
        used_cells = set()
        routes = []
        
        for peak_cell, peak_elev in peaks:
            if peak_cell in used_cells:
                continue
                
            path = walk_ridge(peak_cell, global_elevation, used_cells, max_len=150)
            
            # Only keep substantial routes (e.g. > 15 cells)
            if len(path) > 15:
                # Calculate average elevation
                avg_elev = sum(global_elevation[c] for c in path) / len(path)
                routes.append({
                    "h3_sequence": path,
                    "sequence_length": len(path),
                    "avg_elevation": avg_elev,
                    "peak_elevation": peak_elev,
                    "peak_cell": peak_cell
                })
                
            if len(routes) >= 100:
                break
                
        print(f"  ✓ Extracted {len(routes)} high-elevation ridge routes.")
        
        print("\n[4/4] Formatting and saving results...")
        routes.sort(key=lambda x: -x["avg_elevation"])
        
        formatted_routes = []
        for i, r in enumerate(routes):
            seq = r["h3_sequence"]
            dist_km = compute_route_length_km(seq)
            coords = []
            for cell in seq:
                try:
                    lat, lng = h3.cell_to_latlng(cell)
                    coords.append({"cell": cell, "lat": round(lat, 6), "lng": round(lng, 6)})
                except:
                    pass
                    
            formatted_routes.append({
                "rank": i + 1,
                "h3_sequence": seq,
                "sequence_length": len(seq),
                "avg_distance_km": dist_km,
                "avg_elevation_score": int(r["avg_elevation"]),
                "peak_elevation_score": r["peak_elevation"],
                "start_h3": seq[0],
                "end_h3": seq[-1],
                "cell_coordinates": coords,
                "method": "ridge_elevation_walk"
            })
            
        # Add basic thresholds for comparison
        thresholds = [1.0, 3.0, 5.0, 10.0]
        by_threshold = {}
        for th in thresholds:
            filt = [sr for sr in formatted_routes if sr["avg_distance_km"] >= th]
            by_threshold[str(int(th))] = filt[:100]
            print(f"  >= {th:4.1f} km: {len(filt):3d} ridge routes")

        payload = {
            "master_top100": formatted_routes,
            "by_threshold_km": by_threshold,
            "metadata": {
                "h3_resolution": H3_RESOLUTION,
                "total_cells_mapped": len(global_elevation),
                "timestamp": datetime.now().isoformat()
            }
        }
        
        os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            
        print(f"✓ Saved ridge routes to {OUTPUT_JSON}")
        
        elapsed = time.time() - t0
        print(f"\n{'═' * 65}")
        print(f"  ✅ Stage 5 COMPLETE in {elapsed:.1f}s")
        print(f"  Top Ridge #1: {formatted_routes[0]['sequence_length']} cells, "
              f"{formatted_routes[0]['avg_distance_km']} km, "
              f"Elev Score: {formatted_routes[0]['avg_elevation_score']}")
        print(f"{'═' * 65}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
