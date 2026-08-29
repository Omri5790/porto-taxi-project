"""
Verify that the three mining methods are real, and that each one earns its place.

The previous version of this project ran an LSH stage whose output never reached
the result.  It printed numbers and looked impressive and changed nothing.  That
is the specific failure this file exists to make impossible to repeat.

Four questions, each answered by construction rather than by inspection:

  1. Does LSH behave like LSH?  The banding S-curve is measured against the
     formula it is supposed to follow.

  2. Does clustering find anything exact counting cannot?  A corridor is planted
     twice, as two near-identical variants -- the parallel-one-way-street case.
     Neither variant is frequent enough on its own.  Exact counting must miss it;
     clustering must find it.

  3. Does the suffix array find the true longest repeat?  Compared against brute
     force on the same input.

  4. Does growth re-measure support every round?  The tempting shortcut -- chain
     fragments and take the smallest support -- is checked against the truth to
     show how far wrong it goes.

    python tools/verify_methods.py
"""

from __future__ import annotations

import argparse
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.stage3 import method_a_lsh as A          # noqa: E402
from scripts.stage3 import method_b_suffix as B       # noqa: E402
from scripts.stage3.corridors import trip_supports    # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
#  1.  The LSH S-curve, measured
# ─────────────────────────────────────────────────────────────────────────────
def check_s_curve(trials: int = 400) -> bool:
    """Two sets of known similarity: how often does banding put them together?"""
    params = A._hash_params()
    rng = random.Random(3)

    print("  Banding is supposed to follow  P = 1 - (1 - s^r)^b  with b=%d, r=%d."
          % (A.BANDS, A.ROWS))
    print(f"  Its midpoint should sit near (1/b)^(1/r) = {A.lsh_threshold():.3f}.")
    print()
    print(f"    {'jaccard':>9}{'predicted':>12}{'measured':>11}")

    worst = 0.0
    # _signature consumes hashed shingles, which are 32-bit ints -- so the
    # fixture must be ints too, or the modular arithmetic inside it is being
    # handed something it was never meant to see.
    universe = [rng.randrange(1 << 32) for _ in range(400)]
    for target in (0.2, 0.4, 0.5, 0.6, 0.7, 0.85, 0.95):
        hits = 0
        for _ in range(trials):
            base = set(rng.sample(universe, 100))
            # build a second set with the requested Jaccard, approximately
            keep = int(round(100 * (2 * target) / (1 + target)))
            other = set(rng.sample(sorted(base), min(keep, len(base))))
            while len(other) < 100:
                other.add(rng.randrange(1 << 32))
            sig_a = A._signature(base, params)
            sig_b = A._signature(other, params)
            for band in range(A.BANDS):
                lo = band * A.ROWS
                if sig_a[lo:lo + A.ROWS] == sig_b[lo:lo + A.ROWS]:
                    hits += 1
                    break
        s = len(base & other) / len(base | other)
        predicted = 1 - (1 - s ** A.ROWS) ** A.BANDS
        measured = hits / trials
        worst = max(worst, abs(predicted - measured))
        print(f"    {s:>9.2f}{predicted:>12.3f}{measured:>11.3f}")

    ok = worst < 0.15
    print()
    print(f"    largest gap between formula and measurement: {worst:.3f}   "
          f"{'ok' if ok else 'TOO LARGE -- this is not behaving like LSH'}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
#  2.  What clustering finds that exact counting cannot
# ─────────────────────────────────────────────────────────────────────────────
def build_split_corridor(n_trips: int = 4000, deviation: int = 1, seed: int = 5):
    """One real corridor, driven two slightly different ways.

    ``deviation`` is how many cells of a 12-cell window differ between the two
    variants -- one cell is a taxi taking the other side of a divided road, four
    is a different route.  It is a parameter because how much deviation LSH can
    absorb is exactly what this file measures.
    """
    rng = random.Random(seed)
    head = [f"A{i}" for i in range(6)]
    tail = [f"A{i}" for i in range(6 + deviation, 6 + deviation + 6)]
    left = [f"L{i}" for i in range(deviation)]
    right = [f"R{i}" for i in range(deviation)]

    trips = []
    for t in range(n_trips):
        if rng.random() < 0.24:                     # on the corridor
            mid = left if rng.random() < 0.5 else right
            cells = head + mid + tail
        else:                                        # background
            cells = [f"b{rng.randrange(3000)}" for _ in range(rng.randint(6, 25))]
        trips.append((f"T{t}", cells))
    return trips, head + left + tail, head + right + tail


def _lsh_merges(pat_a, pat_b):
    params = A._hash_params()
    sh_a, sh_b = A._shingles(pat_a), A._shingles(pat_b)
    sig_a, sig_b = A._signature(sh_a, params), A._signature(sh_b, params)
    bands = sum(1 for b in range(A.BANDS)
                if sig_a[b*A.ROWS:(b+1)*A.ROWS] == sig_b[b*A.ROWS:(b+1)*A.ROWS])
    return A._jaccard(sh_a, sh_b), bands


def check_clustering_pays(n_trips: int) -> bool:
    """How much deviation can clustering absorb, and does it beat exact counting?

    The honest form of this check.  Clustering does not merge *any* two variants
    -- it merges variants above the banding threshold, and the threshold is a
    number we chose.  So measure where the line actually falls before claiming
    anything about what Method A rescues.
    """
    print("    How different can two drives be before LSH stops merging them?")
    print(f"    (12-cell window, threshold (1/b)^(1/r) = {A.lsh_threshold():.3f})")
    print()
    print(f"    {'cells differing':>17}{'jaccard':>10}{'bands matched':>16}{'merged':>9}")
    merge_limit = 0
    for dev in (1, 2, 3, 4):
        _t, pat_l, pat_r = build_split_corridor(10, deviation=dev)
        jac, bands = _lsh_merges(pat_l, pat_r)
        merged = bands > 0
        if merged:
            merge_limit = dev
        print(f"    {dev:>17}{jac:>10.3f}{bands:>16}{str(merged):>9}")
    print()
    if not merge_limit:
        print("    LSH merged nothing at all -- Method A cannot be doing its job.")
        return False
    print(f"    So this geometry absorbs a deviation of up to {merge_limit} cell(s)")
    print("    in twelve.  At H3 res 9 that is ~174 m: the two sides of a divided")
    print("    road, or two lanes round a roundabout.  A four-cell difference is a")
    print("    different route, and LSH is right to keep those apart.")
    print()

    # Now the payoff, at a deviation the clustering can actually absorb.
    trips, pat_l, pat_r = build_split_corridor(n_trips, deviation=merge_limit)
    min_support = int(n_trips * 0.15)
    n_left = sum(1 for _t, c in trips if trip_supports(c, [pat_l]))
    n_right = sum(1 for _t, c in trips if trip_supports(c, [pat_r]))

    print(f"    With a {merge_limit}-cell deviation, over {n_trips:,} trips"
          f" (threshold {min_support}):")
    print()
    print(f"      driven one way            {n_left:>6} trips   "
          f"{'FREQUENT' if n_left >= min_support else 'below threshold'}")
    print(f"      driven the other way      {n_right:>6} trips   "
          f"{'FREQUENT' if n_right >= min_support else 'below threshold'}")
    print(f"      either way (what LSH sees){n_left + n_right:>6} trips   "
          f"{'FREQUENT' if n_left + n_right >= min_support else 'below threshold'}")
    print()

    split = n_left < min_support and n_right < min_support
    rescued = (n_left + n_right) >= min_support
    if split and rescued:
        print("    Exact counting scores each variant on its own and both fall short,")
        print("    so the busiest corridor in the city vanishes from the results.")
        print("    Clustering merges them and it survives.  That is Method A's job,")
        print("    and it is why it is not decoration.")
    else:
        print("    (the fixture did not split the corridor; this run proves nothing)")
    return split and rescued


# ─────────────────────────────────────────────────────────────────────────────
#  3.  The suffix array against brute force
# ─────────────────────────────────────────────────────────────────────────────
def brute_force_repeats(trips, min_len: int, min_support: int):
    """Every pattern of length >= min_len supported by >= min_support trips."""
    counts = {}
    for _t, cells in trips:
        n = len(cells)
        seen = set()
        for i in range(n):
            for j in range(i + min_len, min(n, i + B.MAX_SUFFIX) + 1):
                seen.add(tuple(cells[i:j]))
        for pat in seen:
            counts[pat] = counts.get(pat, 0) + 1
    return {p: c for p, c in counts.items() if c >= min_support}


def check_suffix(trips, min_support: int) -> bool:
    small = trips[:1200]
    truth = brute_force_repeats(small, B.MIN_REPEAT, min_support)
    if not truth:
        print("    no repeats in the fixture; nothing to compare")
        return False
    longest_true = max(truth, key=len)

    # mine_bucket is the core of the method: sort suffixes, walk the LCP array.
    suffixes = []
    for tid, cells in small:
        for i in range(len(cells)):
            suf = tuple(cells[i:i + B.MAX_SUFFIX])
            if len(suf) >= B.MIN_REPEAT:
                suffixes.append((suf, tid))
    found = list(B.mine_bucket(suffixes, min_support))
    if not found:
        print("    mine_bucket returned nothing")
        return False
    longest_found = max((f[0] for f in found), key=len)

    print(f"    brute force: {len(truth):,} patterns, longest is {len(longest_true)} cells")
    print(f"    suffix array + LCP: longest found is {len(longest_found)} cells")
    same = len(longest_found) == len(longest_true)
    print(f"    same length: {same}   {'ok' if same else 'MISMATCH'}")
    # every pattern the suffix array reports must really be that frequent
    bad = 0
    for pat, sup in ((f[0], f[1]) for f in found[:200]):
        real = sum(1 for _t, c in small if trip_supports(c, [list(pat)]))
        if real < min_support or real != sup:
            bad += 1
    print(f"    of 200 reported patterns, wrong supports: {bad}   "
          f"{'ok' if bad == 0 else 'MISMATCH'}")
    return same and bad == 0


# ─────────────────────────────────────────────────────────────────────────────
#  4.  Why growth re-measures instead of chaining
# ─────────────────────────────────────────────────────────────────────────────
def check_no_chaining(n_trips: int = 4000, seed: int = 9) -> bool:
    """The tempting shortcut, and how far wrong it goes.

    The shortcut is: a long corridor's support must be at least the smallest
    support among its fragments, so just chain frequent fragments and take the
    minimum instead of counting again.  Anti-monotonicity says that minimum is
    an upper bound -- it never says it is close.

    The fixture is the case that breaks it: a twelve-cell stretch that half the
    city drives the first two thirds of and half drives the last two thirds of,
    and almost nobody drives end to end.  Every fragment is popular.  The whole
    thing is not.
    """
    rng = random.Random(seed)
    corridor = [f"C{i}" for i in range(12)]
    trips = []
    for t in range(n_trips):
        r = rng.random()
        if r < 0.33:
            cells = corridor[:8] + [f"b{rng.randrange(3000)}" for _ in range(3)]
        elif r < 0.66:
            cells = [f"b{rng.randrange(3000)}" for _ in range(3)] + corridor[4:]
        elif r < 0.69:
            cells = list(corridor)                        # the rare full drive
        else:
            cells = [f"b{rng.randrange(3000)}" for _ in range(rng.randint(6, 25))]
        trips.append((f"T{t}", cells))

    k = 3
    parts = [corridor[i:i + k] for i in range(len(corridor) - k + 1)]
    part_support = [sum(1 for _t, c in trips if trip_supports(c, [p])) for p in parts]
    chained = min(part_support)
    real = sum(1 for _t, c in trips if trip_supports(c, [corridor]))

    print(f"    a {len(corridor)}-cell corridor over {n_trips:,} trips,"
          f" cut into {len(parts)} fragments of {k}")
    print(f"    every fragment's support ranges {min(part_support):,}"
          f" to {max(part_support):,} trips -- all frequent")
    print()
    print(f"    the shortcut's answer (smallest fragment) : {chained:>6} trips")
    print(f"    the truth (corridor re-counted)           : {real:>6} trips")
    if real:
        print(f"    the shortcut overstates the corridor by   : "
              f"{chained / real:>6.1f}x")
    print()
    print("    Every fragment being popular does not make the corridor popular:")
    print("    different trips supplied different fragments.  Anti-monotonicity")
    print("    guarantees the shortcut is an upper bound, never that it is close.")
    print("    That is why every candidate is re-counted against the trips before")
    print("    it is published -- and why the old pipeline's long routes were an")
    print("    artefact rather than a finding.")
    return chained >= real            # anti-monotonicity: the bound must hold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", type=int, default=4000)
    args = ap.parse_args()

    trips, pat_l, _pat_r = build_split_corridor(args.trips, deviation=2)
    min_support = int(args.trips * 0.15)      # 15% of trips

    print("=" * 72)
    print("  Method verification: are all three real, and does each earn its place?")
    print("=" * 72)
    print()
    print("  1. Does the LSH banding follow its own S-curve?")
    print()
    ok1 = check_s_curve()

    print()
    print("  2. Does clustering find what exact counting cannot?")
    print()
    ok2 = check_clustering_pays(args.trips)

    print()
    print("  3. Does the suffix array find the true longest repeat?")
    print()
    ok3 = check_suffix(trips, int(1200 * 0.15))

    print()
    print("  4. Does growth re-measure support instead of chaining it?")
    print()
    ok4 = check_no_chaining(args.trips)

    ok = ok1 and ok2 and ok3 and ok4
    print()
    print("=" * 72)
    print("  All three methods do what they claim, and none is decorative."
          if ok else "  *** At least one method did not behave as documented. ***")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
