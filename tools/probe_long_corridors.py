"""
Settle the 20 km and 40 km configurations by exhaustion rather than by argument.

Three cluster runs lowered the support threshold from 802 trips to 33 and the
longest corridor moved 15.02 -> 18.12 -> 18.48 km, never crossing 20.  Lowering
X again would be a fourth data point on the same curve.  This answers the
question outright instead.

The observation that makes it cheap: a trip can only traverse a corridor of
length L if the trip is itself at least L long.  So the support of any 20 km
corridor, counted over all 1.6M trips, is *exactly* its support over the small
set of trips that are themselves 20 km or longer.  Nothing is approximated by
restricting to them -- the other 1.58M trips contribute zero by definition.

That set is small enough to mine exhaustively on one machine, at a support
threshold of two trips: if the longest corridor two long trips share is under
20 km, then no 20 km corridor exists at *any* threshold, and the configuration
is empty as a fact about Porto rather than as a limitation of the pipeline.

    python tools/probe_long_corridors.py --trips output/long_trips_20km.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.stage3.corridors import (  # noqa: E402
    corridor_km, is_valid, segment_km, tortuosity,
)


def longest_shared(trips, min_support: int, min_km: float):
    """Longest contiguous cell run shared by >= min_support trips.

    A generalised suffix array over this many trips is the textbook tool, and it
    is what Stage 3 uses.  Here the input is small, so the simpler thing is
    honest: bucket every suffix by its first two cells, sort each bucket, and
    walk the LCP downward -- the same algorithm, without the distribution.
    """
    buckets = defaultdict(list)
    for idx, cells in enumerate(trips):
        n = len(cells)
        for i in range(n):
            suf = tuple(cells[i:])
            if len(suf) >= 8:
                buckets[suf[:2]].append((suf, idx))

    best = []
    for key, sufs in buckets.items():
        if len({t for _s, t in sufs}) < min_support:
            continue
        sufs.sort()
        n = len(sufs)
        lcp = [0] * n
        for i in range(1, n):
            a, b = sufs[i - 1][0], sufs[i][0]
            m = min(len(a), len(b))
            j = 0
            while j < m and a[j] == b[j]:
                j += 1
            lcp[i] = j
        # For each maximal block with lcp >= L, the block's trips share L cells.
        for i in range(1, n):
            L = lcp[i]
            if L < 8:
                continue
            j = i
            owners = {sufs[i - 1][1], sufs[i][1]}
            while j + 1 < n and lcp[j + 1] >= L:
                j += 1
                owners.add(sufs[j][1])
            if len(owners) >= min_support:
                path = list(sufs[i - 1][0][:L])
                km = segment_km(path)
                if km >= min_km:
                    best.append((km, len(owners), path))
    best.sort(key=lambda x: -x[0])
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", default="output/long_trips_20km.json")
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--min-km", type=float, default=10.0)
    args = ap.parse_args()

    with open(args.trips, encoding="utf-8") as fh:
        raw = json.load(fh)
    trips = [r["cells"] for r in raw]

    print("=" * 74)
    print("  Is a 20 km corridor possible in Porto at ANY support threshold?")
    print("=" * 74)
    print(f"  {len(trips):,} trips of >= 20 km -- the only trips that could contain one.")
    print(f"  Mining at a threshold of {args.min_support} trips: as low as 'shared' can go.")
    print()

    best = longest_shared(trips, args.min_support, args.min_km)
    if not best:
        print(f"  No contiguous stretch of >= {args.min_km} km is shared by "
              f"{args.min_support} trips.")
        return 0

    print(f"  {'rank':>5}{'km':>9}{'trips':>8}{'cells':>8}{'tortuosity':>12}   valid")
    seen = set()
    shown = 0
    for km, support, path in best:
        sig = tuple(path[:6])
        if sig in seen:
            continue
        seen.add(sig)
        shown += 1
        segs = [path]
        print(f"  {shown:>5}{km:>9.2f}{support:>8}{len(path):>8}"
              f"{tortuosity(segs):>12.2f}   {is_valid(segs)}")
        if shown >= 15:
            break

    top_km = best[0][0]
    print()
    print(f"  Longest stretch any two long trips share: {top_km:.2f} km")
    print()
    for target in (20.0, 40.0):
        reachable = [b for b in best if b[0] >= target]
        if reachable:
            print(f"  >= {target:.0f} km: {len(reachable)} candidate(s), "
                  f"best support {max(b[1] for b in reachable)} trips")
        else:
            print(f"  >= {target:.0f} km: none exist, at any threshold.")
    print()
    print("  This is exhaustive over the only trips that could have produced one,")
    print("  at the lowest threshold the word 'shared' admits.  An empty result")
    print("  here is a property of Porto, not of the pipeline.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
