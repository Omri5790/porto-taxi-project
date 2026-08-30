"""
Pull out the trips that are themselves long enough to contain a long corridor.

This is the input to ``tools/probe_long_corridors.py`` and
``tools/export_long_corridors.py``.  It exists so that the long-configuration
argument is reproducible from the pipeline's own output rather than from a
one-off script: a trip can only traverse a corridor of length L if the trip is
itself at least L long, so restricting to these trips approximates nothing.

    python tools/extract_long_trips.py --min-km 20 \\
        --parquet output/h3_encoded_trips.parquet \\
        --out     output/long_trips_20km.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="output/h3_encoded_trips.parquet")
    ap.add_argument("--out", default="output/long_trips_20km.json")
    ap.add_argument("--min-km", type=float, default=20.0)
    args = ap.parse_args()

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        print(f"needs pyarrow: {exc}", file=sys.stderr)
        return 2

    shards = sorted(glob.glob(os.path.join(args.parquet, "*.parquet")))
    if not shards:
        print(f"no parquet under {args.parquet}", file=sys.stderr)
        return 2

    cols = ["TRIP_ID", "distance_km", "h3_res9"]
    out, total = [], 0
    for shard in shards:
        table = pq.read_table(shard, columns=cols)
        c = {k: table.column(k).to_pylist() for k in cols}
        for i in range(len(c["TRIP_ID"])):
            total += 1
            if c["distance_km"][i] >= args.min_km:
                out.append({"trip_id": c["TRIP_ID"][i],
                            "distance_km": round(c["distance_km"][i], 3),
                            "cells": c["h3_res9"][i]})

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print(f"scanned {total:,} trips, wrote {len(out):,} of >= {args.min_km:.0f} km "
          f"to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
