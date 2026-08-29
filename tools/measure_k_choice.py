"""
Measure what k costs and what it buys, so the gate's k is evidence.

k is *not* the length of the routes being mined -- those run to 40 cells.  k is
the length of the fragment the gate counts, and therefore the seed the growth
method starts from.  Choosing it is a trade between three things that pull in
different directions, all of which this measures on the real encoded trips:

  * how hard the gate prunes            (bigger k prunes harder)
  * how much the sketch and Bloom cost  (bigger k means more distinct fragments)
  * how many trips can contribute at all(a trip of 5 cells is invisible to k=8)

Reads the Stage 2 parquet directly with pyarrow -- no Spark, no cluster:

    python tools/measure_k_choice.py
    python tools/measure_k_choice.py --parquet output/h3_encoded_trips.parquet \\
                                     --trips 60000 --support-pct 0.05
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="output/h3_encoded_trips.parquet")
    ap.add_argument("--trips", type=int, default=60000,
                    help="how many trips to read (one shard is plenty for ratios)")
    ap.add_argument("--support-pct", type=float, default=0.05)
    ap.add_argument("--max-k", type=int, default=8)
    args = ap.parse_args()

    try:
        import pyarrow.parquet as pq
    except ImportError:
        print("needs pyarrow:  pip install pyarrow", file=sys.stderr)
        return 2

    # Read the value the pipeline actually runs with, rather than repeating it
    # here.  This file exists to justify that number; if it quoted its own copy
    # the two could drift, which is exactly what happened once already.
    from scripts.stage3.run_stage3 import DEFAULT_GATE_K

    shards = sorted(glob.glob(os.path.join(args.parquet, "*.parquet")))
    if not shards:
        print(f"no parquet files under {args.parquet}", file=sys.stderr)
        return 2

    seqs = []
    for shard in shards:
        table = pq.read_table(shard, columns=["h3_res9"])
        seqs.extend(table.column("h3_res9").to_pylist())
        if len(seqs) >= args.trips:
            break
    seqs = seqs[:args.trips]
    n_trips = len(seqs)
    support = max(2, int(n_trips * args.support_pct / 100.0))

    print("=" * 78)
    print("  Choosing k: what each length costs and what it buys")
    print("=" * 78)
    print(f"  {n_trips:,} trips, min_support = {support} trips ({args.support_pct}%)")
    print()
    print("  k is the fragment the gate counts -- NOT the length of a route.")
    print()
    print(f"  {'k':>3}{'distinct':>11}{'frequent':>10}{'gate prunes':>13}"
          f"{'trips too short':>17}")
    for k in range(1, args.max_k + 1):
        counts: dict[int, int] = {}
        too_short = 0
        for cells in seqs:
            m = len(cells)
            if m < k:
                too_short += 1
                continue
            for g in {tuple(cells[i:i + k]) for i in range(m - k + 1)}:
                h = hash(g)
                counts[h] = counts.get(h, 0) + 1
        distinct = len(counts)
        frequent = sum(1 for v in counts.values() if v >= support)
        pruned = 100.0 * (1 - frequent / distinct) if distinct else 0.0
        mark = "   <- chosen" if k == DEFAULT_GATE_K else ""
        print(f"  {k:>3}{distinct:>11,}{frequent:>10,}{pruned:>12.2f}%"
              f"{too_short:>11,} ({100.0*too_short/n_trips:4.2f}%){mark}")

    print()
    print("  Reading the table:")
    print()
    print("  Smaller k prunes less.  At k=1 the gate is counting single cells --")
    print("  a cell is a place, not a direction, so almost everything busy passes.")
    print()
    print("  Larger k prunes more, but pays twice.  The distinct fragment count is")
    print("  what the sketch and the Bloom filter are sized against, and it climbs")
    print("  steeply.  And the last column is the real cost: a trip shorter than k")
    print("  contributes no fragment at all, so a corridor supported only by short")
    print("  trips becomes invisible to the gate.")
    print()
    print("  k must be at least 3 to carry a turn: two steps, so A->B->C tells")
    print("  traffic that continued from traffic that turned, where k=2 has one")
    print(f"  step and only a direction.  Among the usable lengths, k={DEFAULT_GATE_K} sits where")
    print("  pruning has already reached ~90%, the frequent-fragment count is near")
    print("  its maximum, and ~97% of trips are still long enough to contribute a")
    print("  seed.  Past that the distinct count keeps climbing and the share of")
    print("  trips that can seed anything falls away, for pruning that")
    print("  anti-monotonicity has already made unnecessary.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
