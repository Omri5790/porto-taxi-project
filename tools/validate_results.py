"""
Independent audit of a Stage 3 results file.
============================================

This does not trust the pipeline.  It re-reads the published JSON and re-derives
every geometric claim from the H3 cells themselves, so the checks below hold
whatever the mining code did:

  * no corridor visits a cell twice (the failure that turned "66 km routes" into
    loops within a 4 km box);
  * the reported length matches the length recomputed from the cell centroids;
  * tortuosity is inside the configured bound;
  * support never exceeds the number of trips, and the reported support
    percentage matches the support and the trip count;
  * no field carries a constant that looks like an assumption rather than a
    measurement -- in particular, a speed column that is identical on every row.

Run it after every cluster run, and again before the defence::

    python tools/validate_results.py output/stage3_subroutes.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys

import h3

MAX_TORTUOSITY = 2.5
LENGTH_TOLERANCE_KM = 0.05


def haversine_km(a, b):
    la1, ln1 = a
    la2, ln2 = b
    dlat = math.radians(la2 - la1)
    dlng = math.radians(ln2 - ln1)
    q = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(la1))
         * math.cos(math.radians(la2)) * math.sin(dlng / 2) ** 2)
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(q)))


def recompute_km(segments):
    total = 0.0
    for seg in segments:
        for a, b in zip(seg, seg[1:]):
            total += haversine_km(h3.cell_to_latlng(a), h3.cell_to_latlng(b))
    for s1, s2 in zip(segments, segments[1:]):
        total += haversine_km(h3.cell_to_latlng(s1[-1]), h3.cell_to_latlng(s2[0]))
    return total


def audit(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    total_trips = data.get("metadata", {}).get("total_trips", 0)
    routes = list(data.get("top_100_longest", []))
    for bucket in data.get("by_threshold_km", {}).values():
        routes.extend(bucket.get("routes", []))

    if not routes:
        print("no routes in file")
        return 1

    failures = []
    speeds = set()

    for r in routes:
        rid = r.get("rank", "?")
        segs = r["segments"]
        flat = [c for s in segs for c in s]

        if len(set(flat)) != len(flat):
            dup = len(flat) - len(set(flat))
            failures.append(f"rank {rid}: revisits {dup} cell(s) -- this is a loop, not a route")

        km = recompute_km(segs)
        if abs(km - r["length_km"]) > LENGTH_TOLERANCE_KM:
            failures.append(f"rank {rid}: length_km {r['length_km']} but recomputes to {km:.3f}")

        e2e = haversine_km(h3.cell_to_latlng(flat[0]), h3.cell_to_latlng(flat[-1]))
        tort = km / e2e if e2e > 1e-9 else float("inf")
        if tort > MAX_TORTUOSITY + 1e-6:
            failures.append(f"rank {rid}: tortuosity {tort:.2f} exceeds {MAX_TORTUOSITY}")

        if total_trips and r["trip_support"] > total_trips:
            failures.append(f"rank {rid}: support {r['trip_support']} > {total_trips} trips")

        if total_trips:
            pct = 100.0 * r["trip_support"] / total_trips
            if abs(pct - r["support_pct"]) > 0.01:
                failures.append(f"rank {rid}: support_pct {r['support_pct']} != {pct:.4f}")

        if r.get("mean_trip_speed_kmh") is not None:
            speeds.add(r["mean_trip_speed_kmh"])

    if len(routes) > 5 and len(speeds) == 1:
        failures.append(
            f"every route reports the same speed ({speeds.pop()}) -- that is an "
            f"assumed constant, not a measurement")

    uniq = {" ".join(c for s in r["segments"] for c in s) for r in routes}
    print(f"audited {len(routes)} route records ({len(uniq)} distinct paths) from {path}")
    if total_trips:
        print(f"  dataset: {total_trips:,} trips")
    print(f"  longest: {max(r['length_km'] for r in routes):.2f} km")
    print(f"  max tortuosity: {max(recompute_km(r['segments']) / max(haversine_km(h3.cell_to_latlng(r['segments'][0][0]), h3.cell_to_latlng(r['segments'][-1][-1])), 1e-9) for r in routes):.2f}")
    print(f"  with holes: {sum(1 for r in routes if r.get('n_holes', 0) > 0)}")
    print(f"  distinct measured speeds: {len(speeds)}")

    if failures:
        print(f"\nFAILED {len(failures)} check(s):")
        for f in failures[:40]:
            print(f"  - {f}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", default="output/stage3_subroutes.json")
    sys.exit(audit(ap.parse_args().results))
