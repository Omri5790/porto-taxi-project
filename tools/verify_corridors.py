"""
Verify the corridor model, its geometry guards, and the final verification pass.

Everything the project publishes passes through here.  A corridor's support, its
length, whether it is a route at all rather than a loop -- all of it is decided
by ``scripts/stage3/corridors.py``, and all three mining methods defer to it.  So
this is the last place an error can hide before a number reaches the report.

Three things are checked, each against something independent:

  1. ``trip_supports`` -- against a deliberately slow, obviously-correct
     reimplementation, over random corridors and trips.

  2. ``make_matcher`` -- the fast inverted-index path used in the verification
     pass -- must return exactly what ``trip_supports`` returns.  An index that
     quietly misses matches would under-report support and look like a finding.

  3. The geometry guards, on the shape that produced the old pipeline's
     "66 km routes": fragments chained into something that doubles back.

    python tools/verify_corridors.py
"""

from __future__ import annotations

import argparse
import itertools
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import h3  # noqa: E402

from scripts.stage3.corridors import (  # noqa: E402
    DEFAULT_MAX_GAP, MAX_TORTUOSITY, corridor_km, end_to_end_km, is_simple,
    is_valid, make_matcher, match_span, tortuosity, trip_supports,
)

LAT0, LNG0 = 41.1500, -8.6100


# ─────────────────────────────────────────────────────────────────────────────
#  1.  trip_supports against an obviously-correct reimplementation
# ─────────────────────────────────────────────────────────────────────────────
def slow_supports(trip, segments, max_gap=DEFAULT_MAX_GAP) -> bool:
    """Every placement of every segment, checked exhaustively.

    Deliberately written for clarity rather than speed: find every position each
    segment could occupy, then ask whether some choice of positions is in order
    and respects the gap.  If this and the real implementation ever disagree,
    the real one is wrong.
    """
    places = []
    for seg in segments:
        hits = [i for i in range(len(trip) - len(seg) + 1)
                if list(trip[i:i + len(seg)]) == list(seg)]
        if not hits:
            return False
        places.append(hits)

    for combo in itertools.product(*places):
        ok = True
        cursor = None
        for idx, seg in zip(combo, segments):
            if cursor is not None:
                if idx < cursor or (idx - cursor) > max_gap:
                    ok = False
                    break
            cursor = idx + len(seg)
        if ok:
            return True
    return False


def random_case(rng):
    alphabet = [f"c{i}" for i in range(14)]
    trip = [rng.choice(alphabet) for _ in range(rng.randint(4, 22))]
    n_seg = rng.randint(1, 3)
    segments = []
    for _ in range(n_seg):
        if rng.random() < 0.6 and len(trip) > 3:
            i = rng.randrange(0, len(trip) - 2)
            segments.append(list(trip[i:i + rng.randint(1, 3)]))
        else:
            segments.append([rng.choice(alphabet) for _ in range(rng.randint(1, 3))])
    return trip, segments


def check_supports(trials: int) -> bool:
    rng = random.Random(17)
    disagree = 0
    supported = 0
    for _ in range(trials):
        trip, segments = random_case(rng)
        fast = trip_supports(trip, segments)
        slow = slow_supports(trip, segments)
        supported += fast
        if fast != slow:
            disagree += 1
            if disagree <= 3:
                print(f"      trip={trip}")
                print(f"      segments={segments}  fast={fast} slow={slow}")
    print(f"    {trials:,} random cases ({supported:,} supported)")
    print(f"    disagreements with the slow reference: {disagree}   "
          f"{'ok' if disagree == 0 else '*** BUG ***'}")
    return disagree == 0


def check_rules() -> bool:
    """The three properties the definition is supposed to have, spelled out."""
    trip = ["a", "b", "c", "d", "e", "f", "g", "h"]
    cases = [
        ("segments in order, no hole",        [["a", "b"], ["c", "d"]], True),
        ("segments out of order",             [["c", "d"], ["a", "b"]], False),
        ("hole of 3 cells (limit is 8)",      [["a", "b"], ["f", "g"]], True),
        ("segment not contiguous in the trip", [["a", "c"]],            False),
        ("segment present twice, still one match", [["a", "b"]],        True),
    ]
    ok = True
    for label, segments, expected in cases:
        got = trip_supports(trip, segments)
        ok &= (got == expected)
        print(f"    {label:<42}{str(got):>6}   {'ok' if got == expected else 'WRONG'}")

    long_trip = ["a", "b"] + ["z"] * 12 + ["c", "d"]
    got = trip_supports(long_trip, [["a", "b"], ["c", "d"]])
    ok &= (got is False)
    print(f"    {'hole of 12 cells (over the limit)':<42}{str(got):>6}   "
          f"{'ok' if got is False else 'WRONG'}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
#  2.  The fast matcher must not change the answer
# ─────────────────────────────────────────────────────────────────────────────
def check_matcher(n_corridors: int = 60, n_trips: int = 3000) -> bool:
    """make_matcher indexes corridors by their leading cells.  Does it lose any?"""
    rng = random.Random(23)
    alphabet = [f"c{i}" for i in range(40)]
    corridors = []
    for _ in range(n_corridors):
        base = [rng.choice(alphabet) for _ in range(rng.randint(4, 9))]
        if rng.random() < 0.4:
            cut = rng.randint(2, len(base) - 2) if len(base) > 3 else 2
            corridors.append([base[:cut], base[cut:]])
        else:
            corridors.append([base])

    matcher = make_matcher(corridors)
    mismatches = 0
    total_hits = 0
    for _ in range(n_trips):
        trip = [rng.choice(alphabet) for _ in range(rng.randint(6, 30))]
        if rng.random() < 0.5:                   # plant a corridor sometimes
            ci = rng.randrange(len(corridors))
            flat = [c for seg in corridors[ci] for c in seg]
            at = rng.randrange(0, max(1, len(trip) - 1))
            trip = trip[:at] + flat + trip[at:]

        fast = set(matcher(trip))
        slow = {i for i, corr in enumerate(corridors) if trip_supports(trip, corr)}
        total_hits += len(slow)
        if fast != slow:
            mismatches += 1
            if mismatches <= 2:
                print(f"      matcher {sorted(fast)} vs truth {sorted(slow)}")
    print(f"    {n_trips:,} trips against {n_corridors} corridors, "
          f"{total_hits:,} true matches")
    print(f"    trips where the index disagreed: {mismatches}   "
          f"{'ok' if mismatches == 0 else '*** THE INDEX LOSES MATCHES ***'}")
    return mismatches == 0


def check_span_undercounts() -> bool:
    """A trip that drives the corridor twice must be counted once, not twice."""
    corridor = [["a", "b", "c"]]
    trip = ["a", "b", "c", "x", "y", "a", "b", "c"]
    start, end = match_span(trip, corridor)
    ok = (start, end) == (0, 3)
    print(f"    trip traverses the corridor twice; match_span returns "
          f"({start}, {end})   {'ok -- the first only' if ok else 'WRONG'}")
    print("    Counting the earliest match only means support is a lower bound.")
    print("    Under-counting is the safe direction: nothing is ever reported as")
    print("    more popular than it is.")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
#  3.  The geometry guards, on the shape that caused the old bug
# ─────────────────────────────────────────────────────────────────────────────
def ring(n: int, radius_cells: int = 6):
    """A closed loop of real H3 cells -- the shape chained fragments produce."""
    import math
    centre = h3.latlng_to_cell(LAT0, LNG0, 9)
    cells = []
    for t in range(n):
        ang = 2 * math.pi * t / n
        lat = LAT0 + (radius_cells * 0.0016) * math.cos(ang)
        lng = LNG0 + (radius_cells * 0.0021) * math.sin(ang)
        c = h3.latlng_to_cell(lat, lng, 9)
        if not cells or c != cells[-1]:
            cells.append(c)
    return cells or [centre]


def straight(n: int):
    """A straight run of n *distinct* cells heading east.

    Stepping by a fixed number of degrees does not give distinct cells -- a
    res-9 cell is ~174 m across and a 0.0021 degree step is about the same, so
    consecutive points land in the same cell roughly half the time.  Walking
    until the cell changes is the only way to get a genuinely 40-cell road.
    """
    cells, lng = [], LNG0
    while len(cells) < n:
        c = h3.latlng_to_cell(LAT0, lng, 9)
        if not cells or c != cells[-1]:
            cells.append(c)
        lng += 0.0008
    return cells


def check_geometry() -> bool:
    road = [straight(40)]
    loop_cells = ring(40)
    loop = [loop_cells]
    revisit = [straight(20) + straight(20)[::-1]]     # out and back: repeats cells

    print(f"    {'shape':<34}{'km':>8}{'end to end':>12}{'tortuosity':>12}"
          f"{'simple':>8}{'valid':>7}")
    rows = [("a straight 40-cell road", road),
            ("a closed loop of 40 cells", loop),
            ("out and back along one road", revisit)]
    for label, corr in rows:
        t = tortuosity(corr)
        print(f"    {label:<34}{corridor_km(corr):>8.2f}{end_to_end_km(corr):>12.2f}"
              f"{t:>12.2f}{str(is_simple(corr)):>8}{str(is_valid(corr)):>7}")

    ok = is_valid(road) and not is_valid(loop) and not is_valid(revisit)
    print()
    print(f"    The cap is {MAX_TORTUOSITY}.  Note that a straight road does not measure")
    print("    1.00 but about 1.28: H3 cells tile a straight line as a zigzag, so")
    print("    centroid-to-centroid walking is always longer than the road.  That is")
    print("    why the cap is 2.5 and not something tighter -- a real urban corridor")
    print("    starts from 1.28, not from 1.0.")
    print()
    print("    A loop diverges because its end-to-end distance goes to zero while")
    print("    its length does not.  The old pipeline had neither guard, which is")
    print("    how it published a 66 km 'route' whose two ends were 3.8 km apart.")
    print()
    print(f"    all three verdicts correct: {ok}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4000)
    args = ap.parse_args()

    print("=" * 76)
    print("  Corridor model, geometry guards, and the verification pass")
    print("=" * 76)

    print()
    print("  1. Does trip_supports agree with an exhaustive reference?")
    print()
    ok1 = check_supports(args.trials)
    print()
    ok2 = check_rules()

    print()
    print("  2. Does the fast matcher return exactly what the slow one does?")
    print()
    ok3 = check_matcher()
    print()
    ok4 = check_span_undercounts()

    print()
    print("  3. Do the geometry guards reject what is not a route?")
    print()
    ok5 = check_geometry()

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    print()
    print("=" * 76)
    print("  Support means one thing everywhere, and the guards hold."
          if ok else "  *** The corridor model does not behave as documented. ***")
    print("=" * 76)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
