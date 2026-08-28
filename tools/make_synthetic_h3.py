"""
Synthetic H3-encoded trips, for testing Stage 3 without the 1.7 GB dataset.
===========================================================================

Builds a small road network inside the Porto bounding box and plants a known
set of popular corridors on it, including one corridor with a deliberate
**hole** -- a stretch where trips split between two parallel alternatives and
rejoin -- so the gap handling has something real to find.

Because the ground truth is known, the Stage 3 pipeline can be checked for what
actually matters: does it recover the planted corridors, does it report their
support correctly, and does it refuse to emit the loops that a naive chaining
implementation produces?

Usage
-----
    python tools/make_synthetic_h3.py --trips 20000 --out output/synthetic_h3.parquet
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

import h3

PORTO = {"min_lng": -8.70, "max_lng": -8.52, "min_lat": 41.09, "max_lat": 41.22}
RES = 9


def interpolate(a, b, step_km=0.10):
    """Points every ``step_km`` along the segment a->b (lat, lng)."""
    la1, ln1 = a
    la2, ln2 = b
    d = math.hypot((la2 - la1) * 111.0, (ln2 - ln1) * 83.5)
    n = max(2, int(d / step_km))
    return [(la1 + (la2 - la1) * i / n, ln1 + (ln2 - ln1) * i / n) for i in range(n + 1)]


def polyline_cells(waypoints, jitter=0.0, rng=None):
    pts = []
    for i in range(len(waypoints) - 1):
        pts.extend(interpolate(waypoints[i], waypoints[i + 1]))
    cells = []
    for la, ln in pts:
        if jitter and rng:
            la += rng.gauss(0, jitter)
            ln += rng.gauss(0, jitter)
        c = h3.latlng_to_cell(la, ln, RES)
        if not cells or c != cells[-1]:
            cells.append(c)
    return cells


def build_network(rng):
    """A handful of arterials across the city plus a ring road."""
    lo, hi = PORTO["min_lat"], PORTO["max_lat"]
    wl, wr = PORTO["min_lng"], PORTO["max_lng"]
    mid_lat = (lo + hi) / 2
    mid_lng = (wl + wr) / 2

    arterials = {
        # a long west-east avenue through the centre
        "A1": [(mid_lat, wl + 0.005), (mid_lat + 0.004, mid_lng - 0.03),
               (mid_lat + 0.002, mid_lng), (mid_lat - 0.003, mid_lng + 0.04),
               (mid_lat - 0.001, wr - 0.005)],
        # a north-south corridor
        "A2": [(lo + 0.005, mid_lng - 0.01), (mid_lat - 0.02, mid_lng - 0.005),
               (mid_lat + 0.01, mid_lng + 0.004), (hi - 0.005, mid_lng + 0.012)],
        # a diagonal to the airport-ish north west
        "A3": [(mid_lat - 0.03, mid_lng + 0.05), (mid_lat, mid_lng + 0.01),
               (mid_lat + 0.03, wl + 0.02)],
        # a short but very busy river-side stretch
        "A4": [(lo + 0.02, mid_lng + 0.02), (lo + 0.025, mid_lng - 0.01),
               (lo + 0.035, mid_lng - 0.04)],
    }
    # A5 is the corridor with a hole: a long shared head and tail with a short
    # divergence in the middle where trips split between two parallel streets
    # and rejoin.  The divergence is deliberately ~5-6 cells wide, i.e. inside
    # DEFAULT_MAX_GAP, so a correct implementation reports ONE corridor carrying
    # a hole rather than two unrelated fragments.
    head = [(hi - 0.020, wl + 0.020), (hi - 0.040, wl + 0.060)]
    tail = [(hi - 0.052, wl + 0.078), (hi - 0.070, wl + 0.125)]
    mid_north = [(hi - 0.043, wl + 0.066), (hi - 0.047, wl + 0.073)]
    mid_south = [(hi - 0.049, wl + 0.065), (hi - 0.053, wl + 0.072)]
    arterials["A5_north"] = head + mid_north + tail
    arterials["A5_south"] = head + mid_south + tail

    return {k: polyline_cells(v) for k, v in arterials.items()}


def random_walk(rng, start_cell, steps):
    cells = [start_cell]
    cur = start_cell
    for _ in range(steps):
        ring = list(h3.grid_disk(cur, 1))
        ring = [c for c in ring if c != cur]
        cur = rng.choice(ring)
        if cur != cells[-1]:
            cells.append(cur)
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", type=int, default=20000)
    ap.add_argument("--out", default="output/synthetic_h3.parquet")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--popular-share", type=float, default=0.55,
                    help="fraction of trips that ride an arterial")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    net = build_network(rng)
    names = list(net)
    weights = {"A1": 0.30, "A2": 0.24, "A3": 0.16, "A4": 0.14,
               "A5_north": 0.09, "A5_south": 0.07}
    pool = [n for n in names for _ in range(int(weights.get(n, 0.05) * 100))]

    centre = h3.latlng_to_cell((PORTO["min_lat"] + PORTO["max_lat"]) / 2,
                               (PORTO["min_lng"] + PORTO["max_lng"]) / 2, RES)

    rows = []
    for i in range(args.trips):
        if rng.random() < args.popular_share:
            art = net[rng.choice(pool)]
            span = rng.randint(int(len(art) * 0.35), len(art))
            start = rng.randint(0, max(0, len(art) - span))
            cells = list(art[start:start + span])
            # local approach and egress legs, so trips are not pure arterial
            if rng.random() < 0.7:
                cells = random_walk(rng, cells[0], rng.randint(2, 6))[::-1] + cells
            if rng.random() < 0.7:
                cells = cells + random_walk(rng, cells[-1], rng.randint(2, 6))[1:]
            # occasional single-cell detour, the noise LSH is supposed to absorb
            if rng.random() < 0.25 and len(cells) > 8:
                j = rng.randint(3, len(cells) - 4)
                nb = [c for c in h3.grid_disk(cells[j], 1) if c not in cells]
                if nb:
                    cells.insert(j, rng.choice(nb))
        else:
            cells = random_walk(rng, centre, rng.randint(8, 45))

        clean = []
        for c in cells:
            if not clean or c != clean[-1]:
                clean.append(c)
        if len(clean) < 4:
            continue

        km = 0.0
        for a, b in zip(clean, clean[1:]):
            la1, ln1 = h3.cell_to_latlng(a)
            la2, ln2 = h3.cell_to_latlng(b)
            dlat = math.radians(la2 - la1)
            dlng = math.radians(ln2 - ln1)
            q = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(la1))
                 * math.cos(math.radians(la2)) * math.sin(dlng / 2) ** 2)
            km += 6371.0 * 2 * math.asin(min(1.0, math.sqrt(q)))
        dur = int(len(clean) * 15 * rng.uniform(0.9, 1.6))

        rows.append({
            "TRIP_ID": f"S{i:08d}",
            "h3_res9": clean,
            "TAXI_ID": rng.randint(1, 442),
            "duration_sec": dur,
            "distance_km": round(km, 4),
        })

    truth = {name: {"cells": len(cells),
                    "km": round(sum(
                        h3.great_circle_distance(h3.cell_to_latlng(a),
                                                 h3.cell_to_latlng(b), unit="km")
                        for a, b in zip(cells, cells[1:])), 2)}
             for name, cells in net.items()}

    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[*]")
             .appName("make_synthetic_h3")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    spark.createDataFrame(rows).write.mode("overwrite").parquet(args.out)
    spark.stop()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(os.path.splitext(args.out)[0] + "_truth.json", "w") as fh:
        json.dump({"arterials": truth, "trips": len(rows),
                   "popular_share": args.popular_share}, fh, indent=2)

    print(f"wrote {len(rows):,} synthetic trips to {args.out}")
    for name, t in truth.items():
        print(f"  planted {name}: {t['cells']} cells, {t['km']} km")


if __name__ == "__main__":
    main()
