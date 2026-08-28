"""
Method A -- MinHash + LSH clustering of trajectory segments.
============================================================

This is the *clustering* method the brief asks for, and the clustering is the
point: two taxis that drive the same corridor down parallel one-way streets, or
that clip a roundabout differently, produce H3 sequences that are **similar but
not identical**.  Counting exact n-grams splits those into separate, weaker
patterns.  Clustering merges them, so the corridor's true popularity shows up.

How it works
------------
1.  **Shingle** each fixed-length window of a trip into its set of consecutive
    cell pairs.  Two windows over the same road share almost all their pairs.

2.  **MinHash** that set into a signature of ``BANDS * ROWS`` integers.  The
    probability that two signatures agree in any one position is exactly the
    Jaccard similarity of the underlying sets, so the signature is a compact
    stand-in for the set (32 integers instead of an unbounded set).

3.  **LSH banding** splits the signature into ``BANDS`` bands of ``ROWS`` rows
    and hashes each band.  Two windows share a bucket when any whole band
    matches, which happens with probability

        P(collide | Jaccard = s) = 1 - (1 - s^ROWS)^BANDS

    an S-curve whose midpoint sits near ``(1/BANDS)^(1/ROWS)``.  With the
    defaults below that threshold is ~0.60: windows more similar than that
    almost always meet, windows less similar than that almost never do.  This
    is what turns an all-pairs comparison into a single shuffle.

4.  **Cluster support** is the number of *distinct trips* in a bucket, which we
    accumulate with a :class:`DistinctCounter` -- exact while a bucket is cold,
    HyperLogLog once it grows past 64 trips.  Holding an exact ``set()`` of trip
    ids for every bucket is the memory blow-up that pushes people into
    ``groupByKey``; holding a full 4 KB HLL for every bucket is just as bad when
    almost every bucket is cold.  The adaptive counter pays only for the hot
    ones, and stays exact exactly where the support decision is made.

5.  The **medoid** of each surviving bucket -- the window with the highest mean
    Jaccard to its bucket-mates -- becomes the cluster representative.

The output is a set of popular corridor *segments*.  Turning them into long
corridors, and replacing the HyperLogLog estimate with an exact verified count,
is the orchestrator's job; nothing here is reported to the user as final.
"""

from __future__ import annotations

import time

from .corridors import dedup_consecutive, is_valid
from .sketches import DistinctCounter, hash64

# LSH geometry.  BANDS*ROWS signature entries; see the S-curve above.
BANDS = 8
ROWS = 4
NUM_HASHES = BANDS * ROWS

WINDOW = 12          # cells per window (~2 km at H3 res 9)
STRIDE = 3           # window start step; 3 keeps 4x fewer windows than stride 1
SHINGLE = 2          # consecutive-cell pairs
BUCKET_SAMPLE = 12   # windows retained per bucket for medoid selection
MAX_REPRESENTATIVES = 4000

_P = (1 << 61) - 1
_MAXH = (1 << 32) - 1


def lsh_threshold(bands: int = BANDS, rows: int = ROWS) -> float:
    """Jaccard similarity at which the S-curve crosses 50%."""
    return (1.0 / bands) ** (1.0 / rows)


def _hash_params(seed: int = 42):
    import random
    rng = random.Random(seed)
    return [(rng.randrange(1, _P), rng.randrange(0, _P)) for _ in range(NUM_HASHES)]


def _shingles(window) -> set:
    """Set of consecutive cell tuples, hashed to ints."""
    return {hash64((window[i], window[i + 1])) & 0xFFFFFFFF
            for i in range(len(window) - SHINGLE + 1)}


def _signature(shingles: set, params) -> tuple:
    sig = [_MAXH] * NUM_HASHES
    for s in shingles:
        for i in range(NUM_HASHES):
            a, b = params[i]
            v = ((a * s + b) % _P) % _MAXH
            if v < sig[i]:
                sig[i] = v
    return tuple(sig)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def run(sc, trips_rdd, total_trips: int, min_support: int,
        window: int = WINDOW, stride: int = STRIDE, hll_b: int = 12):
    """Mine popular corridor segments by LSH clustering.

    Parameters
    ----------
    trips_rdd : RDD of ``(trip_id, tuple_of_cells)``
    min_support : minimum number of distinct trips for a cluster to survive

    Returns
    -------
    (elapsed_sec, list_of_segment_candidates, stats_dict)
        Each candidate is ``(segment_cells_tuple, approx_support)``.
    """
    t0 = time.time()
    params = sc.broadcast(_hash_params())

    n_windows = sc.accumulator(0)
    n_emissions = sc.accumulator(0)

    def emit_bands(rows):
        prm = params.value
        for trip_id, cells in rows:
            cells = dedup_consecutive(cells)
            if len(cells) < window:
                continue
            for i in range(0, len(cells) - window + 1, stride):
                win = tuple(cells[i:i + window])
                sh = _shingles(win)
                if len(sh) < SHINGLE:
                    continue
                n_windows.add(1)
                sig = _signature(sh, prm)
                for b in range(BANDS):
                    key = (b, hash64(sig[b * ROWS:(b + 1) * ROWS]))
                    n_emissions.add(1)
                    yield (key, (trip_id, win))

    banded = trips_rdd.mapPartitions(emit_bands)

    # Bounded aggregation: a sample of windows for the medoid, and an adaptive
    # distinct counter for support.  Memory per bucket is O(1), not O(trips).
    def seq_op(acc, value):
        sample, counter = acc
        trip_id, win = value
        if len(sample) < BUCKET_SAMPLE:
            sample.append(win)
        counter.add(trip_id)
        return (sample, counter)

    def comb_op(a, b):
        sa, ca = a
        sb, cb = b
        room = BUCKET_SAMPLE - len(sa)
        if room > 0:
            sa = sa + sb[:room]
        return (sa, ca.merge(cb))

    zero = ([], DistinctCounter(b=hll_b, sparse_limit=64))

    buckets = banded.aggregateByKey(zero, seq_op, comb_op)

    survivors = (buckets
                 .mapValues(lambda v: (v[0], v[1].count()))
                 .filter(lambda kv: kv[1][1] >= min_support))

    n_buckets_kept = survivors.count()

    # Medoid selection happens on the executor: the bucket sample is at most
    # BUCKET_SAMPLE windows, so this is O(BUCKET_SAMPLE^2) per bucket.
    def medoid(kv):
        _key, (sample, support) = kv
        if len(sample) == 1:
            return (sample[0], support)
        sets = [_shingles(w) for w in sample]
        best_i, best_score = 0, -1.0
        for i in range(len(sample)):
            score = sum(_jaccard(sets[i], sets[j])
                        for j in range(len(sample)) if j != i)
            if score > best_score:
                best_i, best_score = i, score
        return (sample[best_i], support)

    reps = (survivors
            .map(medoid)
            .reduceByKey(max)                       # same medoid from several bands
            .sortBy(lambda kv: -kv[1])
            .take(MAX_REPRESENTATIVES))

    candidates = [(seg, sup) for seg, sup in reps if is_valid([list(seg)])]

    elapsed = time.time() - t0
    stats = {
        "algorithm": "MinHash + LSH clustering of trajectory segments",
        "approximate_structures": [
            f"MinHash signature ({NUM_HASHES} hashes)",
            f"LSH banding ({BANDS} bands x {ROWS} rows, "
            f"similarity threshold ~{lsh_threshold():.2f})",
            f"DistinctCounter (exact <=64 trips, then HyperLogLog b={hll_b}, "
            f"~{1.04 / (1 << hll_b) ** 0.5 * 100:.1f}% error) for distinct-trip support",
        ],
        "window_cells": window,
        "stride": stride,
        "lsh_similarity_threshold": round(lsh_threshold(), 4),
        "windows_hashed": n_windows.value,
        "band_emissions": n_emissions.value,
        "buckets_above_support": n_buckets_kept,
        "representatives": len(candidates),
        "min_support_trips": min_support,
        "runtime_sec": round(elapsed, 2),
        "distributed": True,
    }
    return elapsed, candidates, stats
