"""
Pull out the longest individual journeys, as context for the empty configurations.

This does **not** answer the brief.  The brief asks for popular sub-routes --
stretches that many different trips share -- and a list of long trips is a
different object entirely: one taxi each, no sharing, no support.

It is here because the difference between the two is the single thing hardest
to convey about the >= 20 km and >= 40 km results.  Drawn on a map, a hundred
long journeys fan out across the region in a hundred directions, and it becomes
obvious by eye why no 40 km stretch is shared by 33 of them.

Only genuine journeys are taken.  A trip that wanders and returns to where it
started accumulates distance without going anywhere, and the dataset is full of
them past 40 km -- meters that were never stopped.  See
tools/measure_trip_geometry.py for that measurement.

    python tools/extract_longest_trips.py \\
        --parquet output/h3_encoded_trips.parquet \\
        --out     output/longest_trips.json --top 100
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Same cap the corridors use: past this a path is not a journey between places.
MAX_TRIP_TORTUOSITY = 2.5


def haversine_km(lat1, lng1, lat2, lng2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lng2 - lng1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="output/h3_encoded_trips.parquet")
    ap.add_argument("--out", default="output/longest_trips.json")
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--max-cells", type=int, default=400,
                    help="drop the polyline detail past this, to keep the file small")
    args = ap.parse_args()

    try:
        import pyarrow.parquet as pq
        import h3
    except ImportError as exc:
        print(f"needs pyarrow and h3: {exc}", file=sys.stderr)
        return 2

    shards = sorted(glob.glob(os.path.join(args.parquet, "*.parquet")))
    if not shards:
        print(f"no parquet under {args.parquet}", file=sys.stderr)
        return 2

    cols = ["TRIP_ID", "distance_km", "duration_sec", "avg_speed_kmh", "h3_res9",
            "start_lat", "start_lng", "end_lat", "end_lng"]
    best = []
    total = 0
    wandering = 0
    for shard in shards:
        table = pq.read_table(shard, columns=cols)
        c = {k: table.column(k).to_pylist() for k in cols}
        for i in range(len(c["TRIP_ID"])):
            total += 1
            d = c["distance_km"][i]
            if d < 10.0:                      # nothing shorter can be in the top 100
                continue
            e2e = haversine_km(c["start_lat"][i], c["start_lng"][i],
                               c["end_lat"][i], c["end_lng"][i])
            if e2e <= 0.05 or d / e2e > MAX_TRIP_TORTUOSITY:
                wandering += 1
                continue
            best.append((d, i, shard, e2e))
        best.sort(key=lambda x: -x[0])
        best = best[:args.top * 3]            # keep a margin, trim at the end

    # Re-read only the shards the winners came from, to pull their cell paths.
    best = best[:args.top]
    by_shard = {}
    for d, i, shard, e2e in best:
        by_shard.setdefault(shard, []).append((d, i, e2e))

    out = []
    for shard, items in by_shard.items():
        table = pq.read_table(shard, columns=cols)
        c = {k: table.column(k).to_pylist() for k in cols}
        for d, i, e2e in items:
            cells = c["h3_res9"][i]
            step = max(1, len(cells) // args.max_cells)
            coords = [{"lat": round(la, 6), "lng": round(ln, 6)}
                      for la, ln in (h3.cell_to_latlng(x) for x in cells[::step])]
            out.append({
                "trip_id": c["TRIP_ID"][i],
                "distance_km": round(d, 3),
                "end_to_end_km": round(e2e, 3),
                "tortuosity": round(d / e2e, 3),
                "duration_sec": c["duration_sec"][i],
                "avg_speed_kmh": c["avg_speed_kmh"][i],
                "n_cells": len(cells),
                "coordinates": coords,
            })

    out.sort(key=lambda r: -r["distance_km"])
    payload = {
        "note": ("The longest individual journeys, not popular sub-routes. "
                 "One taxi each, no shared support. Included as context for the "
                 "long configurations: these are what a 40 km trip looks like, "
                 "and no 40 km stretch of them is shared."),
        "selection": (f"longest {len(out)} trips with tortuosity <= "
                      f"{MAX_TRIP_TORTUOSITY}; wandering trips excluded"),
        "trips_scanned": total,
        "trips_rejected_as_wandering": wandering,
        "trips": out,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    print(f"scanned {total:,} trips, dropped {wandering:,} as wandering")
    if out:
        print(f"wrote {len(out)} journeys to {args.out}")
        print(f"  longest {out[0]['distance_km']} km "
              f"(end to end {out[0]['end_to_end_km']} km, "
              f"tortuosity {out[0]['tortuosity']})")
        print(f"  shortest of the {len(out)}: {out[-1]['distance_km']} km")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
