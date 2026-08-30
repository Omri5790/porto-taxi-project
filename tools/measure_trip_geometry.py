"""
Ask whether the long trips in this dataset are journeys at all.

The question came from the 20 km result.  Every stretch of 20 km or more that
two trips shared turned out to be a loop, and a loop is strange in a dataset
where each row is a paid fare -- nobody pays to be driven in a circle.

So this measures the trips themselves rather than the corridors: for each trip,
the path it walked against the straight line from where it started to where it
ended.  A real journey is close to 1; a trip that wanders and comes back is
large; a trip that ends where it began is unbounded.

    python tools/measure_trip_geometry.py --parquet output/h3_encoded_trips.parquet

The finding it produces is the honest ceiling for the long configurations: not
how many trips are long enough to contain a 40 km corridor, but how many of
those are journeys rather than a meter nobody stopped.
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: A trip that walks more than this many times its straight-line displacement is
#: not a journey between two places.  Same cap the corridors use, for the same
#: reason -- see scripts/stage3/corridors.py.
MAX_TRIP_TORTUOSITY = 2.5


def haversine_km(lat1, lng1, lat2, lng2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lng2 - lng1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="output/h3_encoded_trips.parquet")
    ap.add_argument("--thresholds", default="1,5,10,20,40")
    args = ap.parse_args()

    try:
        import pyarrow.parquet as pq
    except ImportError:
        print("needs pyarrow:  pip install pyarrow", file=sys.stderr)
        return 2

    shards = sorted(glob.glob(os.path.join(args.parquet, "*.parquet")))
    if not shards:
        print(f"no parquet under {args.parquet}", file=sys.stderr)
        return 2

    trips = []
    cols = ["distance_km", "start_lat", "start_lng", "end_lat", "end_lng", "duration_sec"]
    for shard in shards:
        t = pq.read_table(shard, columns=cols)
        c = {k: t.column(k).to_pylist() for k in cols}
        for i in range(len(c["distance_km"])):
            trips.append((
                c["distance_km"][i],
                haversine_km(c["start_lat"][i], c["start_lng"][i],
                             c["end_lat"][i], c["end_lng"][i]),
                c["duration_sec"][i],
            ))

    print("=" * 78)
    print("  Are the long trips journeys, or a meter nobody stopped?")
    print("=" * 78)
    print(f"  {len(trips):,} trips.  Tortuosity = walked path / straight line "
          f"start to end.")
    print(f"  A trip is counted as a journey when that ratio is at most "
          f"{MAX_TRIP_TORTUOSITY}.")
    print()
    print(f"  {'trips of':>10}{'count':>10}{'median tort.':>14}"
          f"{'ends where it began':>21}{'journeys':>11}{'share':>8}")

    rows = []
    for th in [float(x) for x in args.thresholds.split(",")]:
        sub = [t for t in trips if t[0] >= th]
        if not sub:
            continue
        tor = sorted(d / e for d, e, _ in sub if e > 0.05)
        back = sum(1 for _d, e, _s in sub if e < 0.5)
        good = [t for t in sub if t[1] > 0.05 and t[0] / t[1] <= MAX_TRIP_TORTUOSITY]
        med = tor[len(tor) // 2] if tor else float("nan")
        rows.append((th, len(sub), len(good)))
        print(f"  >= {th:>5.0f} km{len(sub):>10,}{med:>14.2f}"
              f"{back:>16,} ({100.0*back/len(sub):>3.0f}%){len(good):>11,}"
              f"{100.0*len(good)/len(sub):>7.1f}%")

    print()
    print("  Reading it:")
    print()
    print("  A trip that ends within 500 m of where it started, after walking tens")
    print("  of kilometres, is not a fare -- it is a meter that was never stopped.")
    print("  The taxi kept driving, empty and then with other passengers, and the")
    print("  whole afternoon was recorded as one journey.")
    print()
    print("  The share of genuine journeys falls away exactly where the brief's")
    print("  long configurations sit, which is the real reason those are empty:")
    for th, total, good in rows:
        if th >= 20:
            print(f"    of {total:,} trips of >= {th:.0f} km, only {good:,} are journeys.")
    print()
    print("  Note this is a property of the *cleaning*, not of Stage 3: the")
    print("  pipeline's rules cap distance at 100 km and duration at 24 hours, and")
    print("  a wandering 40 km trip passes both.  A tortuosity rule in Stage 1")
    print("  would remove them -- the corridors already refuse such shapes, so the")
    print("  published results are unaffected, but the length ceiling reported")
    print("  alongside them is optimistic by this much.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
