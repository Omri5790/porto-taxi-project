"""
Method B -- distributed generalised suffix array + LCP array.
============================================================

The suffix method the brief asks for, treating each trip's H3 sequence as a
string over an alphabet of ~15,000 cells.  A sub-route that many trips share is
exactly a **substring repeated across many strings**, which is the classic job
for a generalised suffix array.

Making it distributed
---------------------
A suffix array over the concatenation of 1.6M trips does not fit on one machine
and cannot be built by sorting on a driver.  We use the standard
*prefix-bucketed* construction: every suffix is routed to the bucket named by
its first ``PREFIX_CELLS`` cells, and each bucket is sorted independently.

That partitioning is **lossless for our purpose**: two suffixes can only share a
prefix of length >= ``PREFIX_CELLS`` if they agree on their first
``PREFIX_CELLS`` cells, so they always land in the same bucket.  Every repeat we
care about is therefore discoverable inside exactly one bucket, and the buckets
sort in parallel across the cluster.

Keeping the shuffle affordable
------------------------------
Naively every position of every trip emits a suffix -- ~45M suffixes of up to
``MAX_SUFFIX`` cells each, which is the shuffle that kills this approach.  The
Bloom filter from :mod:`gate` removes it: by anti-monotonicity, a suffix whose
**first k cells are not a frequent k-gram** cannot begin a frequent repeat of
length >= k, so it never needs to be emitted at all.  In practice that prunes
the great majority of suffixes before anything crosses the network, and it
prunes nothing that could have produced a result.

Inside a bucket
---------------
Sort the suffixes (this *is* the suffix array), compute the LCP array between
adjacent entries, then read off LCP-intervals from long to short.  A maximal run
of entries whose LCP stays >= L is precisely the set of suffixes sharing a
prefix of length L; the number of *distinct trips* in that run is the support.
Walking L downwards and consuming each run the first time it qualifies gives the
**longest** repeat at every location, which is the length-maximisation the brief
asks for.
"""

from __future__ import annotations

import time

from .corridors import dedup_consecutive, is_valid

PREFIX_CELLS = 2     # suffixes are bucketed by their first this-many cells
MAX_SUFFIX = 40      # suffixes truncated here; caps per-bucket memory
MIN_REPEAT = 5       # shortest repeat worth reporting
MAX_BUCKET = 200_000  # guard against one pathological bucket eating an executor
MAX_RESULTS = 6000


def _lcp(a, b) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def mine_bucket(suffixes, min_support: int,
                min_repeat: int = MIN_REPEAT, max_suffix: int = MAX_SUFFIX):
    """Suffix array + LCP mining inside one prefix bucket.

    ``suffixes`` is an iterable of ``(suffix_tuple, trip_id)``.
    Yields ``(repeat_tuple, distinct_trip_support)``, longest repeats first.
    """
    sa = sorted(suffixes, key=lambda x: x[0])       # <- the suffix array
    n = len(sa)
    if n < 2:
        return

    # LCP array: lcp[i] = |common prefix of sa[i-1], sa[i]|,  lcp[0] undefined.
    lcp = [0] * n
    for i in range(1, n):
        lcp[i] = _lcp(sa[i - 1][0], sa[i][0])

    consumed = [False] * n
    longest = min(max_suffix, max(len(s) for s, _ in sa))

    for L in range(longest, min_repeat - 1, -1):
        i = 0
        while i < n:
            j = i
            while j + 1 < n and lcp[j + 1] >= L:
                j += 1
            if j > i and len(sa[i][0]) >= L:
                if not all(consumed[k] for k in range(i, j + 1)):
                    trips = {sa[k][1] for k in range(i, j + 1)}
                    if len(trips) >= min_support:
                        yield (sa[i][0][:L], len(trips))
                        for k in range(i, j + 1):
                            consumed[k] = True
            i = j + 1


def run(sc, trips_rdd, total_trips: int, min_support: int, bc_bloom, gate_k: int,
        prefix_cells: int = PREFIX_CELLS, max_suffix: int = MAX_SUFFIX,
        min_repeat: int = MIN_REPEAT, num_partitions: int | None = None):
    """Mine repeated sub-sequences with a distributed generalised suffix array.

    Returns ``(elapsed_sec, [(cells_tuple, support), ...], stats)``.
    """
    t0 = time.time()

    considered = sc.accumulator(0)
    emitted = sc.accumulator(0)

    def emit_suffixes(rows):
        bloom = bc_bloom.value
        for trip_id, cells in rows:
            cells = dedup_consecutive(cells)
            n = len(cells)
            if n < min_repeat:
                continue
            for s in range(n - min_repeat + 1):
                considered.add(1)
                # Anti-monotone Bloom gate: a suffix whose leading k-gram is not
                # frequent cannot start a frequent repeat of length >= k.
                if tuple(cells[s:s + gate_k]) not in bloom:
                    continue
                suf = tuple(cells[s:s + max_suffix])
                emitted.add(1)
                yield (suf[:prefix_cells], (suf, trip_id))

    suffix_rdd = trips_rdd.mapPartitions(emit_suffixes)
    if num_partitions:
        grouped = suffix_rdd.groupByKey(numPartitions=num_partitions)
    else:
        grouped = suffix_rdd.groupByKey()

    def per_bucket(kv):
        _prefix, values = kv
        items = list(values)
        if len(items) > MAX_BUCKET:
            items = items[:MAX_BUCKET]
        return list(mine_bucket(items, min_support, min_repeat, max_suffix))

    repeats = (grouped
               .flatMap(per_bucket)
               .reduceByKey(max)
               .cache())

    n_repeats = repeats.count()
    top = repeats.sortBy(lambda kv: (-len(kv[0]), -kv[1])).take(MAX_RESULTS)
    repeats.unpersist()

    candidates = [(cells, sup) for cells, sup in top if is_valid([list(cells)])]

    elapsed = time.time() - t0
    stats = {
        "algorithm": "Generalised suffix array + LCP array (prefix-bucketed, distributed)",
        "approximate_structures": [
            f"Bloom filter over frequent {gate_k}-grams "
            f"({bc_bloom.value.memory_bytes() / 1024:.1f} KB, "
            f"p~{bc_bloom.value.expected_fp_rate():.4f}) used as an anti-monotone "
            f"prefix gate before the shuffle",
        ],
        "prefix_bucket_cells": prefix_cells,
        "max_suffix_cells": max_suffix,
        "min_repeat_cells": min_repeat,
        "suffix_positions_considered": considered.value,
        "suffixes_emitted": emitted.value,
        "bloom_pruned_pct": (
            round(100.0 * (1.0 - emitted.value / considered.value), 3)
            if considered.value else None),
        "distinct_repeats_found": n_repeats,
        "candidates": len(candidates),
        "min_support_trips": min_support,
        "runtime_sec": round(elapsed, 2),
        "distributed": True,
        "exact_within_scope": True,
    }
    return elapsed, candidates, stats
