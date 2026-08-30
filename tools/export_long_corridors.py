"""
Export the >= 20 km corridors that exist below the pipeline's support floor.

Stage 3 mines at X = 0.002% (33 trips) and reports nothing at >= 20 km.  That is
correct but incomplete: it says no 20 km corridor is *popular*, not that none
exists.  ``tools/probe_long_corridors.py`` settles the existence question by
exhaustion -- over the 25,223 trips that are themselves >= 20 km, at a support
of two trips, which is as low as the word "shared" can go.

This writes those corridors out so they can be drawn and shown, with their real
support attached to every one.  They are kept in a separate file, never merged
into ``stage3_subroutes.json``, because they did not come from the distributed
pipeline and their support is two or three trips -- presenting them beside the
mined corridors without that label would be dishonest.

    python tools/export_long_corridors.py \\
        --trips output/long_trips_20km.json \\
        --out   output/long_corridors_probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.probe_long_corridors import longest_shared          # noqa: E402
from scripts.stage3.corridors import is_valid, tortuosity      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", default="output/long_trips_20km.json")
    ap.add_argument("--out", default="output/long_corridors_probe.json")
    ap.add_argument("--min-km", type=float, default=20.0)
    ap.add_argument("--top", type=int, default=100)
    args = ap.parse_args()

    import h3

    raw = json.load(open(args.trips, encoding="utf-8"))
    trips = [r["cells"] for r in raw]

    best = longest_shared(trips, 2, args.min_km)
    valid = [b for b in best if is_valid([b[2]])]
    valid.sort(key=lambda x: (-x[1], -x[0]))       # support first, then length

    # Count every distinct corridor first, so the reported total is the real
    # one and not merely however many --top asked for.
    distinct_total = len({tuple(p[:6]) for _km, _s, p in valid})

    seen, out = set(), []
    for km, support, path in valid:
        sig = tuple(path[:6])
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "length_km": round(km, 3),
            "support_trips": support,
            "support_pct": round(100.0 * support / 1_616_575, 8),
            "n_cells": len(path),
            "tortuosity": round(tortuosity([path]), 3),
            "cells": path,
            "coordinates": [{"lat": round(a, 6), "lng": round(o, 6)}
                            for a, o in (h3.cell_to_latlng(c) for c in path)],
        })
        if len(out) >= args.top:
            break

    payload = {
        "note": ("Corridors of >= %.0f km that exist below the pipeline's support "
                 "floor. Found by exhaustive search over the %d trips that are "
                 "themselves long enough to contain one, at a support of two "
                 "trips. These are NOT pipeline output and are NOT popular: "
                 "read support_trips on every one." % (args.min_km, len(trips))),
        "method": "generalised suffix array over the long-trip subset, support >= 2",
        "long_trips_searched": len(trips),
        "total_trips_in_dataset": 1_616_575,
        "mining_floor_trips": 33,
        "distinct_valid_found": distinct_total,
        "max_support_trips": max((r["support_trips"] for r in out), default=0),
        "corridors": out,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(payload, open(args.out, "w", encoding="utf-8"))

    print(f"searched {len(trips):,} trips of >= {args.min_km:.0f} km")
    print(f"  {distinct_total} distinct valid corridors, wrote {len(out)}")
    if out:
        print(f"  longest      : {max(r['length_km'] for r in out):.2f} km")
        print(f"  best support : {payload['max_support_trips']} trips "
              f"(pipeline floor is {payload['mining_floor_trips']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
