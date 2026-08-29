"""
The frequent-n-gram gate: where the approximate structures actually pay.
=======================================================================

Every method here faces the same wall.  A trip of n H3 cells contains n-k+1
k-grams, so the stream is roughly the size of the dataset itself.  Measured on
the encoded Porto trips: 1,622,765 trips, 27,424,663 res-9 cells, 16.9 cells per
trip on average, giving 24.2M 3-gram positions -- of which only a handful are
frequent enough to matter.  Shuffling all of them to find out which is the
single most expensive thing the pipeline could do.

The gate avoids that shuffle:

  **Pass 1 — Count-Min Sketch, no shuffle at all.**
  Each partition folds its n-grams into a local sketch; ``treeAggregate`` merges
  the sketches pairwise up a tree.  What crosses the network is a fixed number
  of megabytes of counters, *not* the n-grams.  Because the sketch never
  underestimates, ``estimate(g) < min_support`` is a **proof** that ``g`` is
  infrequent -- so everything the gate drops here is genuinely infrequent.  No
  false negatives, which is the whole reason this is safe to put in front of an
  exact algorithm.

  **Pass 2 — exact counts, but only for survivors.**
  The few n-grams the sketch could not rule out are shuffled and counted
  exactly, which removes the sketch's false positives.  The result is an exact
  frequent set obtained without ever shuffling the full stream.

  **Broadcast — Bloom filter.**
  Downstream methods need to ask "is this n-gram frequent?" inside a map task.
  Shipping the exact set as Python strings costs tens of megabytes per executor;
  a Bloom filter at 1% error costs a fraction of that and, again, has no false
  negatives -- the 1% error only lets a few infrequent n-grams through, and
  those die at the next exact count.

Anti-monotonicity is what makes the gate useful beyond its own n-gram length:
if a 3-gram is infrequent, **every** longer sequence containing it is also
infrequent.  So a Bloom filter of frequent 3-grams prunes suffixes, windows and
extension candidates alike.
"""

from __future__ import annotations

import time

from .sketches import BloomFilter, CountMinSketch


def ngrams_of_trip(cells, k: int):
    """Distinct k-grams of one trip.

    Deduplicated within the trip so that a count of 1 per occurrence makes the
    sketch estimate *the number of trips containing the n-gram*, which is the
    support definition the brief uses ("X% of the trips traversed it").
    """
    n = len(cells)
    if n < k:
        return ()
    return {tuple(cells[i:i + k]) for i in range(n - k + 1)}


def build_gate(sc, trips_rdd, k: int, min_support: int,
               expected_mass: int = 25_000_000,
               cms_memory_mb: float = 32.0,
               bloom_error: float = 0.01,
               depth_tree: int = 4):
    """Build the exact frequent k-gram set and a Bloom filter over it.

    Returns
    -------
    (frequent_dict, bloom_broadcast, stats)
        ``frequent_dict`` maps k-gram tuple -> exact distinct-trip support.
    """
    t0 = time.time()

    sketch_proto = CountMinSketch.for_budget(expected_mass, min_support,
                                             max_memory_mb=cms_memory_mb)

    emitted = sc.accumulator(0)

    def seq_op(cms, row):
        _trip_id, cells = row
        for g in ngrams_of_trip(cells, k):
            cms.add(g)
        return cms

    def comb_op(a, b):
        return a.merge(b)

    cms = trips_rdd.treeAggregate(sketch_proto, seq_op, comb_op, depth=depth_tree)
    t_cms = time.time() - t0

    bc_cms = sc.broadcast(cms)

    def survivors(rows):
        sk = bc_cms.value
        for trip_id, cells in rows:
            for g in ngrams_of_trip(cells, k):
                emitted.add(1)
                if sk.estimate(g) >= min_support:
                    yield (g, trip_id)

    # Cached so that the two actions below do not recompute the map stage --
    # which would also double-count the `emitted` accumulator.
    exact = (trips_rdd
             .mapPartitions(survivors)
             .distinct()
             .map(lambda kv: (kv[0], 1))
             .reduceByKey(lambda a, b: a + b)
             .cache())

    candidates = exact.count()
    frequent = dict(exact.filter(lambda kv: kv[1] >= min_support).collect())
    exact.unpersist()

    bloom = BloomFilter(capacity=max(len(frequent), 1), error_rate=bloom_error)
    for g in frequent:
        bloom.add(g)
    bc_bloom = sc.broadcast(bloom)

    elapsed = time.time() - t0
    total = emitted.value
    stats = {
        "k": k,
        "min_support_trips": min_support,
        "ngrams_streamed": total,
        "cms": cms.error_report(min_support),
        "cms_memory_mb": round(cms.memory_bytes() / 1024 / 1024, 2),
        "cms_build_sec": round(t_cms, 2),
        "candidates_after_cms": candidates,
        "exact_frequent": len(frequent),
        "pruned_before_shuffle_pct": (
            round(100.0 * (1.0 - candidates / total), 4) if total else None),
        "cms_false_positive_pct": (
            round(100.0 * (candidates - len(frequent)) / candidates, 3)
            if candidates else None),
        "bloom_bits": bloom.m,
        "bloom_hashes": bloom.k,
        "bloom_memory_kb": round(bloom.memory_bytes() / 1024, 1),
        "bloom_observed_fp_rate": round(bloom.expected_fp_rate(), 5),
        "runtime_sec": round(elapsed, 2),
    }
    bc_cms.destroy()
    return frequent, bc_bloom, stats
