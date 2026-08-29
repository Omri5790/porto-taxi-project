"""
Verify the Count-Min / Bloom gate -- the part of the project the brief is about.

The gate's job is to throw away almost everything before Spark shuffles it.  The
only property that makes that safe is that its error is **one-sided**: it may
keep something infrequent, but it can never drop something frequent.  If that
ever failed, the pipeline would quietly under-report and nothing downstream
would notice.

So this does not check that the gate runs.  It computes the frequent set twice
-- once by brute force with no gate at all, once through the gate -- and
requires them to be identical:

    python tools/verify_gate.py
    python tools/verify_gate.py --trips 40000 --memory-mb 1

``--memory-mb`` deliberately starves the sketch.  A smaller sketch must produce
*more* candidates and the *same* frequent set; if it ever produced fewer
frequent n-grams, the one-sided guarantee would be broken.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.stage3.gate import build_gate, ngrams_of_trip     # noqa: E402
from scripts.stage3.sketches import BloomFilter, CountMinSketch, hash64  # noqa: E402

K = 3


def make_trips(n_trips: int, seed: int = 11):
    """Trips over a small grid of cell ids, with a few genuinely popular runs.

    Real cell ids are opaque strings; using short synthetic ones keeps the
    ground-truth pass cheap without changing anything the gate does.
    """
    rng = random.Random(seed)
    arterials = [[f"c{100+i}" for i in range(12)],
                 [f"c{200+i}" for i in range(15)],
                 [f"c{300+i}" for i in range(9)]]
    trips = []
    for t in range(n_trips):
        r = rng.random()
        if r < 0.30:                      # rides an arterial for part of its length
            art = arterials[rng.randrange(len(arterials))]
            i = rng.randrange(0, max(1, len(art) - 5))
            j = rng.randrange(i + 5, len(art) + 1)
            cells = list(art[i:j])
        else:                             # background traffic
            cells = [f"r{rng.randrange(4000)}" for _ in range(rng.randint(4, 30))]
        # a little noise on either end of every trip
        cells = ([f"r{rng.randrange(4000)}" for _ in range(rng.randint(0, 3))]
                 + cells
                 + [f"r{rng.randrange(4000)}" for _ in range(rng.randint(0, 3))])
        trips.append((f"T{t}", cells))
    return trips


def ground_truth(trips, k: int, min_support: int):
    """The frequent set computed the expensive, obviously-correct way."""
    counts = {}
    for _tid, cells in trips:
        for g in ngrams_of_trip(cells, k):
            counts[g] = counts.get(g, 0) + 1
    return counts, {g: c for g, c in counts.items() if c >= min_support}


def check_hash_determinism() -> bool:
    """hash64 must be stable across processes; Python's hash() is not.

    This is not pedantry.  Sketches are built on one executor and merged on
    another; if the hash differs between them, the merged sketch is nonsense --
    and it fails silently, producing plausible wrong numbers.
    """
    snippet = textwrap.dedent("""
        import sys; sys.path.insert(0, %r)
        from scripts.stage3.sketches import hash64
        key = ("c101", "c102", "c103")
        print(hash64(key), hash(key))
    """) % ROOT
    outs = []
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", snippet],
                             capture_output=True, text=True, env=env, cwd=ROOT)
        outs.append(res.stdout.strip().split())
    ours = {o[0] for o in outs}
    builtin = {o[1] for o in outs}
    print()
    print("  Hashing must not depend on the interpreter's random seed:")
    print(f"    hash64  over 3 PYTHONHASHSEED values : {len(ours)} distinct value(s)"
          f"   {'ok' if len(ours) == 1 else 'BROKEN'}")
    print(f"    builtin hash() over the same         : {len(builtin)} distinct value(s)"
          f"   <- why we never use it")
    return len(ours) == 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", type=int, default=20000)
    ap.add_argument("--support-pct", type=float, default=0.5,
                    help="min support as a percentage of trips")
    ap.add_argument("--memory-mb", type=float, default=32.0)
    args = ap.parse_args()

    print("=" * 70)
    print("  Gate verification: Count-Min pre-filter + exact pass + Bloom")
    print("=" * 70)

    trips = make_trips(args.trips)
    min_support = max(2, int(args.trips * args.support_pct / 100.0))
    print(f"  {len(trips):,} trips, k={K}, min_support={min_support} trips "
          f"({args.support_pct}%), sketch budget {args.memory_mb} MB")

    exact_counts, truth = ground_truth(trips, K, min_support)
    print(f"  ground truth (brute force, no gate): {len(exact_counts):,} distinct "
          f"{K}-grams, {len(truth):,} frequent")

    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[*]")
             .appName("verify_gate").getOrCreate())
    sc = spark.sparkContext
    sc.setLogLevel("ERROR")
    try:
        rdd = sc.parallelize(trips, 8)
        frequent, bc_bloom, stats = build_gate(
            sc, rdd, k=K, min_support=min_support,
            expected_mass=sum(len(c) for _, c in trips),
            cms_memory_mb=args.memory_mb)
        bloom = bc_bloom.value

        # ── 1. the decisive check ────────────────────────────────────────────
        missing = set(truth) - set(frequent)
        extra = set(frequent) - set(truth)
        wrong = {g for g in set(truth) & set(frequent) if truth[g] != frequent[g]}

        print()
        print("  Does the gate change the answer?")
        print(f"    frequent n-grams, brute force        {len(truth):>8,}")
        print(f"    frequent n-grams, through the gate   {len(frequent):>8,}")
        print(f"    frequent ones the gate LOST          {len(missing):>8,}   "
              f"{'ok -- none' if not missing else '*** ONE-SIDED GUARANTEE BROKEN ***'}")
        print(f"    n-grams the gate wrongly kept        {len(extra):>8,}   "
              f"{'ok -- none' if not extra else 'BUG: exact pass failed'}")
        print(f"    supports that disagree               {len(wrong):>8,}   "
              f"{'ok -- none' if not wrong else 'BUG'}")

        # ── 2. what the gate saved ───────────────────────────────────────────
        print()
        print("  What the sketch saved before the shuffle:")
        print(f"    n-grams streamed                     {stats['ngrams_streamed']:>8,}")
        print(f"    survived the sketch (shuffled)       {stats['candidates_after_cms']:>8,}")
        print(f"    pruned before any shuffle            {stats['pruned_before_shuffle_pct']:>7.2f}%")
        print(f"    of the survivors, false positives    {stats['cms_false_positive_pct']:>7.2f}%")
        print(f"    sketch geometry                      {stats['cms']['geometry']}"
              f"  ({stats['cms_memory_mb']} MB)")

        # ── 3. the one-sided property, measured on every n-gram ──────────────
        cms = CountMinSketch.for_budget(
            sum(len(c) for _, c in trips), min_support, max_memory_mb=args.memory_mb)
        for _tid, cells in trips:
            for g in ngrams_of_trip(cells, K):
                cms.add(g)
        under = over = 0
        worst = 0
        for g, true_c in exact_counts.items():
            est = cms.estimate(g)
            if est < true_c:
                under += 1
            elif est > true_c:
                over += 1
                worst = max(worst, est - true_c)
        print()
        print(f"  Count-Min error direction over all {len(exact_counts):,} n-grams:")
        print(f"    underestimates  {under:>8,}   "
              f"{'ok -- the guarantee is that this is 0' if under == 0 else '*** GUARANTEE BROKEN ***'}")
        print(f"    overestimates   {over:>8,}   ({100.0*over/len(exact_counts):.2f}%), "
              f"worst overshoot {worst}")

        # ── 4. Bloom: no false negatives ─────────────────────────────────────
        fn = sum(1 for g in frequent if g not in bloom)
        non_members = [g for g in exact_counts if g not in frequent]
        fp = sum(1 for g in non_members if g in bloom)
        print()
        print("  Bloom filter (the broadcast form of the frequent set):")
        print(f"    false negatives among {len(frequent):,} members     {fn:>6}   "
              f"{'ok -- must be 0' if fn == 0 else '*** BROKEN ***'}")
        print(f"    false positives among {len(non_members):,} non-members {fp:>6}   "
              f"({100.0*fp/max(len(non_members),1):.2f}%, configured 1.00%)")
        print(f"    size {stats['bloom_memory_kb']} KB for {len(frequent):,} keys")

        ok = (not missing) and (not extra) and (not wrong) and under == 0 and fn == 0
    finally:
        spark.stop()

    ok &= check_hash_determinism()

    print()
    print("  The gate does not change which n-grams are frequent -- it only\n"
          "  changes how much data crosses the network to find that out."
          if ok else "  *** The gate changed the answer.  Do not trust the results. ***")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
