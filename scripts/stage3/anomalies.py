"""
Anomalous route detection -- "how do we spot unusual trips?"
============================================================

The brief opens with four questions the transport company wants answered.
Popular corridors and activity hotspots are the first two; this module is the
third: **which trips do not look like the others?**

The idea is the mirror image of the corridor mining.  Once we know which cell
transitions the city's traffic actually uses, a trip is unusual exactly to the
extent that it uses transitions nobody else does.

    novelty(trip) = |transitions not seen frequently| / |transitions|

Why a Bloom filter and not a set
--------------------------------
The frequent-transition set has hundreds of thousands of entries.  Broadcasting
it as Python tuples of H3 strings costs tens of megabytes on every executor and
is re-serialised for every task; the same information in a Bloom filter at 1%
error is a few hundred kilobytes.  The trade is exactly right for this job: a
false positive means one unusual transition is mistaken for a common one, which
slightly *lowers* a trip's novelty score, and there are no false negatives at
all.  We are ranking trips, so a 1% dilution changes nothing that matters.

A second signal: taxi diversity
-------------------------------
A cell can carry heavy traffic from very few vehicles -- a depot approach, a
single driver's habit, a hotel shuttle loop.  We count *distinct taxis* per cell
with a HyperLogLog and compare it against raw traversals.

Two lists come out of that, and keeping them apart matters.  ``busiest_cells``
is simply the heaviest traffic, which is the brief's second question -- where
the activity hotspots are.  ``concentrated_cells`` is the structural signal:
heavy use by *few* vehicles.

The second one needs the fleet cap to mean anything.  Ranked by
traversals-per-taxi alone it returned cells crossed by 423-429 of the 440
taxis -- the distinct count saturates on every busy cell, so the ranking
collapsed into "sort by traversals" and reported the busiest cells while
calling them the least diverse.  Excluding cells the whole fleet uses is what
makes the ratio informative.
"""

from __future__ import annotations

import time

from .corridors import dedup_consecutive
from .sketches import HyperLogLog

MIN_TRIP_CELLS = 8
TOP_N = 100

#: A cell crossed by more than this share of the fleet is a hotspot, not a
#: concentration.  Without the cap the distinct-taxi count saturates -- every
#: busy cell in Porto sees 96-98% of the 440 taxis -- and ranking by
#: traversals-per-taxi degenerates into ranking by traversals.
MAX_FLEET_SHARE = 0.5


def run(sc, base_rdd, total_trips: int, bc_bloom, top_n: int = TOP_N,
        min_cells: int = MIN_TRIP_CELLS, total_taxis: int = 0):
    """Score every trip for novelty and return the most anomalous ones.

    Parameters
    ----------
    base_rdd : RDD of ``(trip_id, cells, taxi_id, duration_sec, distance_km)``
    bc_bloom : broadcast Bloom filter over frequent cell transitions (gate k=2)

    Returns ``(elapsed_sec, {...}, stats)``.
    """
    t0 = time.time()

    def score(rows):
        bloom = bc_bloom.value
        for trip_id, cells, taxi_id, duration_sec, distance_km in rows:
            seq = dedup_consecutive(cells)
            if len(seq) < min_cells:
                continue
            trans = [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]
            unseen = sum(1 for t in trans if t not in bloom)
            yield {
                "trip_id": trip_id,
                "taxi_id": taxi_id,
                "n_cells": len(seq),
                "duration_sec": duration_sec,
                "distance_km": distance_km,
                "rare_transitions": unseen,
                "novelty": round(unseen / len(trans), 4),
                "h3_sequence": [str(c) for c in seq],
            }

    scored = base_rdd.mapPartitions(score).cache()

    n_scored = scored.count()
    # Rank by novelty, breaking ties toward longer trips (a 9-cell oddity is
    # less interesting than a 60-cell one).
    top = scored.takeOrdered(top_n, key=lambda r: (-r["novelty"], -r["n_cells"]))

    buckets = (scored
               .map(lambda r: (round(r["novelty"], 1), 1))
               .reduceByKey(lambda a, b: a + b)
               .sortByKey()
               .collect())
    scored.unpersist()

    # Taxi diversity per cell, with a HyperLogLog per cell instead of a set.
    def cell_taxis(rows):
        for trip_id, cells, taxi_id, _d, _k in rows:
            for c in set(dedup_consecutive(cells)):
                yield (c, taxi_id)

    def seq_op(acc, taxi_id):
        hll, n = acc
        hll.add(taxi_id)
        return (hll, n + 1)

    def comb_op(a, b):
        return (a[0].merge(b[0]), a[1] + b[1])

    # (cell, distinct taxis, traversals, traversals per taxi)
    per_cell = (base_rdd
                .mapPartitions(cell_taxis)
                .aggregateByKey((HyperLogLog(b=8), 0), seq_op, comb_op)
                .mapValues(lambda v: (v[0].count(), v[1]))
                .filter(lambda kv: kv[1][1] >= 200)
                .map(lambda kv: (kv[0], kv[1][0], kv[1][1],
                                 round(kv[1][1] / max(kv[1][0], 1), 2)))
                .cache())

    # The busiest cells -- the answer to "which areas are activity hotspots".
    busiest = per_cell.takeOrdered(50, key=lambda r: -r[2])

    # Cells used heavily by *few* vehicles.  Ranking by traversals-per-taxi alone
    # does not find these: every busy cell in Porto is crossed by almost the
    # whole 440-taxi fleet, so the distinct count saturates and the ranking
    # collapses into "sort by traversals" -- it returned the busiest cells while
    # calling them the least diverse.  The concentration signal only means
    # something once cells the whole fleet uses are excluded.
    fleet_cap = int(total_taxis * MAX_FLEET_SHARE) if total_taxis else 0
    concentrated = (per_cell
                    .filter(lambda r: fleet_cap == 0 or r[1] <= fleet_cap)
                    .takeOrdered(50, key=lambda r: -r[3]))
    per_cell.unpersist()

    elapsed = time.time() - t0
    result = {
        "top_anomalous_trips": top,
        "novelty_histogram": [{"novelty_bin": b, "trips": n} for b, n in buckets],
        "busiest_cells": [
            {"cell": str(c), "distinct_taxis_hll": t,
             "traversals": n, "traversals_per_taxi": ratio}
            for c, t, n, ratio in busiest
        ],
        "concentrated_cells": [
            {"cell": str(c), "distinct_taxis_hll": t,
             "traversals": n, "traversals_per_taxi": ratio}
            for c, t, n, ratio in concentrated
        ],
        "concentrated_cells_note": (
            f"cells crossed by at most {int(MAX_FLEET_SHARE*100)}% of the fleet, "
            f"ranked by traversals per taxi: heavy use by few vehicles rather "
            f"than heavy use by everyone"),
    }
    stats = {
        "algorithm": "Bloom-filtered transition novelty + HyperLogLog taxi diversity",
        "approximate_structures": [
            f"Bloom filter over frequent transitions "
            f"({bc_bloom.value.memory_bytes() / 1024:.1f} KB, "
            f"p~{bc_bloom.value.expected_fp_rate():.4f}) broadcast instead of the exact set",
            "HyperLogLog (b=8, 256 B per cell) for distinct taxis per cell",
        ],
        "trips_scored": n_scored,
        "min_trip_cells": min_cells,
        "top_n": top_n,
        "runtime_sec": round(elapsed, 2),
        "distributed": True,
    }
    return elapsed, result, stats
