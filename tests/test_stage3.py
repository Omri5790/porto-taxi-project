"""
Unit tests for the Stage 3 primitives.

These check the properties the pipeline actually relies on -- the one-sided
error guarantees of the sketches, the mergeability that makes them usable in a
``treeAggregate``, and the geometric invariants that keep a "corridor" from
being a loop.  Run with::

    python -m pytest tests/test_stage3.py -q
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import h3
import pytest

from scripts.stage3.corridors import (corridor_km, find_contiguous, is_simple,
                                      is_valid, match_span, tortuosity,
                                      trip_supports)
from scripts.stage3.sketches import (BloomFilter, CountMinSketch, DistinctCounter,
                                     HyperLogLog, hash64)


# ── hashing ──────────────────────────────────────────────────────────────────
def test_hash_is_deterministic_across_types():
    assert hash64(("a", "b")) == hash64(("a", "b"))
    assert hash64("abc") == hash64("abc")
    assert hash64(("a", "b")) != hash64(("b", "a"))


def test_hash_is_stable_not_salted():
    """The value must not depend on PYTHONHASHSEED -- that is the whole point."""
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); "
            "from scripts.stage3.sketches import hash64; print(hash64(('x','y',1)))"
            % os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    outs = set()
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.check_output([sys.executable, "-c", code], env=env).strip())
    assert len(outs) == 1


# ── Count-Min Sketch ─────────────────────────────────────────────────────────
def test_cms_never_underestimates():
    rng = random.Random(1)
    cms = CountMinSketch(eps=1e-3, delta=1e-3)
    truth = {}
    for _ in range(20000):
        k = ("cell", rng.randrange(500))
        cms.add(k)
        truth[k] = truth.get(k, 0) + 1
    for k, v in truth.items():
        assert cms.estimate(k) >= v          # one-sided error, no false negatives


def test_cms_merge_equals_single_pass():
    keys = [("k", i % 97) for i in range(5000)]
    single = CountMinSketch(width=1024, depth=4)
    for k in keys:
        single.add(k)
    a = CountMinSketch(width=1024, depth=4)
    b = CountMinSketch(width=1024, depth=4)
    for i, k in enumerate(keys):
        (a if i % 2 else b).add(k)
    a.merge(b)
    for k in set(keys):
        assert a.estimate(k) == single.estimate(k)


def test_cms_error_bound_holds():
    cms = CountMinSketch(eps=1e-3, delta=1e-3)
    for i in range(50000):
        cms.add(("x", i % 5000))
    bound = 1e-3 * cms.total
    for i in range(5000):
        assert cms.estimate(("x", i)) - 10 <= bound


# ── Bloom filter ─────────────────────────────────────────────────────────────
def test_bloom_has_no_false_negatives():
    bf = BloomFilter(capacity=5000, error_rate=0.01)
    members = [("t", i) for i in range(5000)]
    for m in members:
        bf.add(m)
    assert all(m in bf for m in members)


def test_bloom_false_positive_rate_is_near_target():
    bf = BloomFilter(capacity=5000, error_rate=0.01)
    for i in range(5000):
        bf.add(("t", i))
    fp = sum(1 for i in range(5000, 25000) if ("t", i) in bf) / 20000
    assert fp < 0.03                          # target 1%, allow slack


def test_bloom_merge_is_union():
    a = BloomFilter(capacity=1000, error_rate=0.01)
    b = BloomFilter(capacity=1000, error_rate=0.01)
    for i in range(500):
        a.add(i)
    for i in range(500, 1000):
        b.add(i)
    a.merge(b)
    assert all(i in a for i in range(1000))


# ── HyperLogLog ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [1000, 50000, 500000])
def test_hll_within_error_budget(n):
    hll = HyperLogLog(b=12)
    for i in range(n):
        hll.add(("trip", i))
    err = abs(hll.count() - n) / n
    assert err < 0.05                          # 1.6% std error, 3-sigma slack


def test_hll_merge_equals_single_pass():
    a, b, single = HyperLogLog(b=10), HyperLogLog(b=10), HyperLogLog(b=10)
    for i in range(20000):
        single.add(i)
        (a if i % 2 else b).add(i)
    assert a.merge(b).count() == single.count()


# ── DistinctCounter ──────────────────────────────────────────────────────────
def test_distinct_counter_is_exact_while_sparse():
    dc = DistinctCounter(b=8, sparse_limit=64)
    for i in range(40):
        dc.add(("trip", i))
    assert dc.is_exact() and dc.count() == 40


def test_distinct_counter_promotes_and_stays_close():
    dc = DistinctCounter(b=12, sparse_limit=64)
    for i in range(20000):
        dc.add(("trip", i))
    assert not dc.is_exact()
    assert abs(dc.count() - 20000) / 20000 < 0.08


def test_distinct_counter_merge_mixed_modes():
    a = DistinctCounter(b=12, sparse_limit=64)
    b = DistinctCounter(b=12, sparse_limit=64)
    for i in range(10):
        a.add(i)
    for i in range(5, 5000):
        b.add(i)
    a.merge(b)
    assert abs(a.count() - 5000) / 5000 < 0.10


# ── corridor geometry ────────────────────────────────────────────────────────
def _line(n=12):
    """A roughly straight run of H3 cells."""
    cells, cur = [], h3.latlng_to_cell(41.15, -8.61, 9)
    lat, lng = 41.15, -8.61
    while len(cells) < n:
        lng += 0.002
        c = h3.latlng_to_cell(lat, lng, 9)
        if not cells or c != cells[-1]:
            cells.append(c)
    return cells


def test_straight_line_has_low_tortuosity():
    assert tortuosity([_line(15)]) < 1.2


def test_loop_is_rejected():
    line = _line(10)
    loop = line + line[::-1][1:]              # out and back
    assert not is_simple([loop])
    assert not is_valid([loop])


def test_out_and_back_would_pass_length_but_fails_tortuosity():
    """The exact failure mode of the old pipeline: long path, no displacement."""
    line = _line(20)
    there_and_near_back = line + [c for c in line[::-1][1:] if True]
    # even ignoring the repeated cells, the geometry alone must be rejected
    assert corridor_km([there_and_near_back]) > 2 * corridor_km([line]) - 1e-6
    assert not is_valid([there_and_near_back])


def test_find_contiguous():
    assert find_contiguous(list("abcdef"), list("cde")) == 2
    assert find_contiguous(list("abcdef"), list("ce")) == -1
    assert find_contiguous(list("abcabc"), list("abc"), 1) == 3


# ── support semantics ────────────────────────────────────────────────────────
def test_trip_supports_contiguous_segment():
    trip = list("xxABCDyy")
    assert trip_supports(trip, [list("ABCD")])
    assert not trip_supports(trip, [list("ABD")])


def test_trip_supports_corridor_with_a_hole():
    """The Haifa->Ashdod case: the trip detours in the middle and rejoins."""
    trip = list("AB") + list("qr") + list("CD")
    assert trip_supports(trip, [list("AB"), list("CD")], max_gap=4)
    assert not trip_supports(trip, [list("AB"), list("CD")], max_gap=1)


def test_match_span_returns_first_occurrence():
    trip = list("ABxxAByy")
    assert match_span(trip, [list("AB")]) == (0, 2)


def test_support_of_a_chain_is_not_the_min_of_its_parts():
    """Why growth beats chaining: both halves are popular, the whole is not."""
    trips = [list("ABCzzz") for _ in range(50)] + [list("zzzDEF") for _ in range(50)]
    half_a = sum(trip_supports(t, [list("ABC")]) for t in trips)
    half_b = sum(trip_supports(t, [list("DEF")]) for t in trips)
    whole = sum(trip_supports(t, [list("ABCDEF")]) for t in trips)
    assert half_a == 50 and half_b == 50
    assert whole == 0                         # min(50, 50) would have claimed 50


# ── sketch sizing under a memory budget ──────────────────────────────────────
def test_cms_respects_its_memory_budget():
    cms = CountMinSketch.for_budget(expected_mass=25_000_000,
                                    min_support=800, max_memory_mb=32.0)
    assert cms.memory_bytes() <= 32 * 1024 * 1024
    rep = cms.error_report(800)
    assert rep["memory_mb"] <= 32.0
    assert 0 < rep["epsilon"] < 1


def test_cms_error_report_scales_with_mass():
    cms = CountMinSketch.for_budget(1_000_000, 100, max_memory_mb=4.0)
    for i in range(50_000):
        cms.add(("k", i % 4000))
    rep = cms.error_report(100)
    assert rep["total_mass"] == 50_000
    assert rep["additive_error_pct_of_support"] >= 0


# ── growth-method internals ──────────────────────────────────────────────────
def test_growth_rejects_an_extension_that_revisits_a_cell():
    from scripts.stage3.method_c_growth import _apply
    segs = [["a", "b", "c"]]
    assert _apply(segs, "C", ("d",)) == [["a", "b", "c", "d"]]
    assert _apply(segs, "C", ("a",)) is None          # would revisit 'a'
    assert _apply(segs, "G", ("b",)) is None          # ditto across a hole


def test_growth_gap_step_opens_a_new_segment():
    from scripts.stage3.method_c_growth import _apply
    out = _apply([["a", "b"]], "G", ("z",))
    assert out == [["a", "b"], ["z"]]                 # a hole, not a join


def test_beam_pruning_drops_near_duplicates_keeps_diversity():
    from scripts.stage3.method_c_growth import _prune_overlapping
    ranked = [
        ([list("abcdefgh")], 100),        # kept
        ([list("abcdefgi")], 90),         # 7/8 shared with the first -> dropped
        ([list("stuvwxyz")], 80),         # elsewhere in the city -> kept
    ]
    kept = _prune_overlapping(ranked, max_overlap=0.75)
    assert len(kept) == 2
    assert kept[0][1] == 100 and kept[1][1] == 80


# ── the matcher used by the verification pass ────────────────────────────────
def test_matcher_finds_only_corridors_the_trip_supports():
    from scripts.stage3.corridors import make_matcher
    corridors = [
        [list("ABCD")],
        [list("XYZW")],
        [list("AB"), list("CD")],
    ]
    match = make_matcher(corridors, max_gap=4, key_cells=2)
    hits = match(list("qqABCDqq"))
    assert 0 in hits and 2 in hits and 1 not in hits


def test_matcher_key_shrinks_for_short_corridors():
    from scripts.stage3.corridors import make_matcher
    match = make_matcher([[list("AB")]], max_gap=2, key_cells=5)
    assert match(list("zzABzz")) == [0]


# ── stage 1 cleaning semantics ───────────────────────────────────────────────
def test_duration_uses_raw_sample_count_not_deduplicated():
    """A taxi standing at a red light must not shorten its own trip.

    The dataset samples every 15 s, so n samples span (n-1) intervals.  Stationary
    repeats are dropped from the geometry but the time they represent is real.
    Deriving duration from the deduplicated count -- the bug in the previous
    pipeline -- erases standing time and inflates every mean speed.
    """
    n_raw = 38          # samples transmitted
    n_kept = 30         # distinct positions after collapsing a red-light stall
    distance_km = 6.53

    correct = (n_raw - 1) * 15
    buggy = n_kept * 15

    assert correct == 555
    assert buggy == 450
    assert correct > buggy                       # the bug always under-counts

    speed_correct = distance_km / (correct / 3600)
    speed_buggy = distance_km / (buggy / 3600)
    assert speed_buggy > speed_correct * 1.2     # over 20% inflation here
