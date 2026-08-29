"""
The corridor data model, its geometry, and exact support verification.
=====================================================================

What is a "popular long sub-route"?
-----------------------------------
The brief is explicit that a sub-route is *not* a whole trip and *not* a single
busy junction, and that it may contain **holes**: the Haifa->Ashdod corridor is
popular along route 4 at both ends even though the middle section is split
between two alternatives, so the popular object is a *chain of segments* with a
gap between them.

We therefore model a corridor as an ordered list of **segments**, each segment
being a contiguous run of H3 cells:

    corridor = [ [c0, c1, c2], [c9, c10, c11] ]
                 ^ segment 0     ^ segment 1
                             ^^^ a hole: trips diverge here and rejoin

A trip **supports** the corridor when it contains every segment contiguously,
in order, and the number of trip cells it spends inside each hole is at most
``max_gap``.  This is the definition used everywhere -- by all three mining
methods and by the final verification pass -- so support numbers are always
comparable across methods.

Why the geometric guards matter
-------------------------------
Chaining frequent fragments end-to-end without constraints produces sequences
that double back on themselves: a "66 km route" whose endpoints are 3.8 km
apart is a loop, not a corridor, and no taxi ever drove it.  Two invariants
prevent that, and they are enforced at *every* place a corridor grows:

  * **simple path** -- a cell may not appear twice in a corridor;
  * **tortuosity cap** -- ``path_length / end_to_end_distance <= MAX_TORTUOSITY``.

A straight road has tortuosity 1.0; a realistic urban corridor sits under ~2;
a loop diverges to infinity.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from typing import Iterable, Sequence

import h3

EARTH_RADIUS_KM = 6371.0

#: A corridor may not wander more than this many times its straight-line extent.
MAX_TORTUOSITY = 2.5

#: Maximum number of trip cells a supporting trip may spend inside one hole.
#: At H3 resolution 9 (~174 m edge) eight cells is a detour of roughly 1.4 km,
#: which is the scale of the brief's own example -- trips leaving a corridor to
#: cross a city centre by two different routes and rejoining.  A generous gap is
#: safe here because support is *verified* under the same definition: gluing two
#: unrelated segments simply produces a corridor no trip supports.
DEFAULT_MAX_GAP = 8

#: Maximum number of H3 cells a hole may be bridged across when building.
DEFAULT_MAX_BRIDGE = 4


# ─────────────────────────────────────────────────────────────────────────────
#  Cell geometry (cached -- cell_to_latlng dominates runtime otherwise)
# ─────────────────────────────────────────────────────────────────────────────
_LATLNG_CACHE: dict = {}


def cell_latlng(cell) -> tuple:
    """Centroid of an H3 cell, accepting either the string or int form."""
    got = _LATLNG_CACHE.get(cell)
    if got is None:
        got = h3.cell_to_latlng(cell if isinstance(cell, str) else h3.int_to_str(cell))
        _LATLNG_CACHE[cell] = got
    return got


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2.0) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2.0) ** 2)
    return EARTH_RADIUS_KM * 2.0 * math.asin(min(1.0, math.sqrt(a)))


def cells_km(a, b) -> float:
    la1, ln1 = cell_latlng(a)
    la2, ln2 = cell_latlng(b)
    return haversine_km(la1, ln1, la2, ln2)


def segment_km(cells: Sequence) -> float:
    """Walked length of one contiguous run, centroid to centroid."""
    return sum(cells_km(cells[i], cells[i + 1]) for i in range(len(cells) - 1))


# ─────────────────────────────────────────────────────────────────────────────
#  Corridor geometry
# ─────────────────────────────────────────────────────────────────────────────
def flatten(segments: Sequence[Sequence]) -> list:
    out = []
    for seg in segments:
        out.extend(seg)
    return out


def corridor_km(segments: Sequence[Sequence]) -> float:
    """Total length: every segment walked, plus a straight bridge over each hole."""
    total = sum(segment_km(seg) for seg in segments)
    for i in range(len(segments) - 1):
        total += cells_km(segments[i][-1], segments[i + 1][0])
    return total


def covered_km(segments: Sequence[Sequence]) -> float:
    """Length actually observed in the data, excluding bridged holes."""
    return sum(segment_km(seg) for seg in segments)


def end_to_end_km(segments: Sequence[Sequence]) -> float:
    return cells_km(segments[0][0], segments[-1][-1])


def tortuosity(segments: Sequence[Sequence]) -> float:
    straight = end_to_end_km(segments)
    if straight < 1e-9:
        return float("inf")
    return corridor_km(segments) / straight


def is_simple(segments: Sequence[Sequence]) -> bool:
    """No cell may be visited twice anywhere in the corridor."""
    cells = flatten(segments)
    return len(set(cells)) == len(cells)


def is_valid(segments: Sequence[Sequence],
             max_tortuosity: float = MAX_TORTUOSITY,
             min_cells: int = 2) -> bool:
    """The single gate every corridor must pass before it can be reported."""
    if not segments or any(len(s) == 0 for s in segments):
        return False
    if sum(len(s) for s in segments) < min_cells:
        return False
    if not is_simple(segments):
        return False
    return tortuosity(segments) <= max_tortuosity


def dedup_consecutive(cells: Iterable) -> list:
    out = []
    for c in cells:
        if not out or c != out[-1]:
            out.append(c)
    return out


def bridge(a, b, max_bridge: int = DEFAULT_MAX_BRIDGE) -> list | None:
    """Cells strictly between ``a`` and ``b`` along the H3 grid line, or None.

    Returns ``[]`` when the cells are already adjacent.  Used only to *describe*
    a hole on the map; bridged cells are never counted as observed data.
    """
    try:
        d = h3.grid_distance(_s(a), _s(b))
    except Exception:
        return None
    if d <= 0 or d > max_bridge:
        return None
    try:
        path = h3.grid_path_cells(_s(a), _s(b))
    except Exception:
        return None
    inner = path[1:-1]
    return [h3.str_to_int(c) for c in inner] if not isinstance(a, str) else inner


def _s(cell) -> str:
    return cell if isinstance(cell, str) else h3.int_to_str(cell)


# ─────────────────────────────────────────────────────────────────────────────
#  Support verification
# ─────────────────────────────────────────────────────────────────────────────
def find_contiguous(trip: Sequence, pattern: Sequence, start: int = 0) -> int:
    """Index of the first contiguous occurrence of ``pattern`` in ``trip[start:]``."""
    n, m = len(trip), len(pattern)
    if m == 0 or m > n:
        return -1
    first = pattern[0]
    limit = n - m
    i = start
    while i <= limit:
        if trip[i] == first and all(trip[i + j] == pattern[j] for j in range(1, m)):
            return i
        i += 1
    return -1


def _greedy_span(trip: Sequence, segments: Sequence[Sequence], max_gap: int) -> tuple:
    """Take the earliest occurrence of each segment in turn.

    Fast, and when it succeeds the match it found is a real one -- so a success
    here is conclusive.  A failure is *not*: see :func:`_exact_span`.
    """
    cursor = 0
    start = -1
    for si, seg in enumerate(segments):
        hit = find_contiguous(trip, seg, cursor)
        if hit < 0:
            return (-1, -1)
        if si == 0:
            start = hit
        elif (hit - cursor) > max_gap:
            return (-1, -1)
        cursor = hit + len(seg)
    return (start, cursor)


def _exact_span(trip: Sequence, segments: Sequence[Sequence], max_gap: int) -> tuple:
    """Every placement of every segment, not just the earliest one.

    The greedy walk above is not the definition.  Taking the earliest occurrence
    of a segment can push the next one out of gap range when a *later*
    occurrence would have kept it inside, so greedy reports "not supported" for
    trips that do traverse the corridor.  Measured on random cases: it missed
    about 1 in 60 supporting trips.

    So this does the real thing.  For each segment it collects every occurrence,
    then sweeps forward carrying the set of reachable end positions; a segment
    occurrence at ``j`` is reachable when some earlier end ``e`` satisfies
    ``j - max_gap <= e <= j``.  Each reachable end remembers the earliest first
    -- segment start that gets there, so the span returned is still the earliest
    match, which keeps the double-traversal behaviour the callers rely on.
    """
    occurrences = []
    for seg in segments:
        hits, i = [], 0
        while True:
            k = find_contiguous(trip, seg, i)
            if k < 0:
                break
            hits.append(k)
            i = k + 1
        if not hits:
            return (-1, -1)
        occurrences.append(hits)

    # end position -> earliest first-segment start that can reach it
    reach: dict = {}
    first_len = len(segments[0])
    for s in occurrences[0]:
        end = s + first_len
        if end not in reach or s < reach[end]:
            reach[end] = s

    for si in range(1, len(segments)):
        seg_len = len(segments[si])
        ends = sorted(reach)
        nxt: dict = {}
        for j in occurrences[si]:
            lo = bisect_left(ends, j - max_gap)
            hi = bisect_right(ends, j)
            if lo >= hi:
                continue
            best = min(reach[e] for e in ends[lo:hi])
            end = j + seg_len
            if end not in nxt or best < nxt[end]:
                nxt[end] = best
        if not nxt:
            return (-1, -1)
        reach = nxt

    best_start = min(reach.values())
    best_end = min(e for e, s in reach.items() if s == best_start)
    return (best_start, best_end)


def trip_supports(trip: Sequence, segments: Sequence[Sequence],
                  max_gap: int = DEFAULT_MAX_GAP) -> bool:
    """Does one trip traverse this corridor?

    Every segment must occur contiguously, the segments must occur in order, and
    at most ``max_gap`` trip cells may sit inside each hole between them.
    """
    if _greedy_span(trip, segments, max_gap)[0] >= 0:
        return True                     # a greedy hit is a real hit
    return _exact_span(trip, segments, max_gap)[0] >= 0


def match_span(trip: Sequence, segments: Sequence[Sequence],
               max_gap: int = DEFAULT_MAX_GAP) -> tuple:
    """Earliest match of a corridor inside a trip.

    Returns ``(start, end)`` -- the index of the first matched cell and the
    index one past the last -- or ``(-1, -1)`` when the trip does not support
    the corridor.

    The match is the *earliest* one.  A trip that traverses the corridor twice
    contributes only its first traversal, so any support derived from this is a
    lower bound on the true support.  Under-counting is the safe direction: a
    corridor is never reported as more popular than it is.
    """
    span = _greedy_span(trip, segments, max_gap)
    if span[0] >= 0:
        return span
    return _exact_span(trip, segments, max_gap)


def make_matcher(corridors: Sequence[Sequence[Sequence]],
                 max_gap: int = DEFAULT_MAX_GAP,
                 key_cells: int = 3):
    """Build a fast "which of these corridors does a trip support?" closure.

    Broadcasting a few thousand corridors and testing each against 1.6M trips is
    only affordable because three cheap rejections run before the ordered scan:

      1. an inverted index keyed on each corridor's **leading k-gram**, not just
         its first cell.  Keying on a single cell degenerates badly here --
         popular corridors all start on the same few arterial cells -- whereas a
         3-cell key is selective enough that a trip typically considers a
         handful of corridors instead of hundreds;
      2. a subset test on the corridor's cell set, a necessary condition for the
         ordered match costing one hash lookup per cell;
      3. only then the ordered segment scan.
    """
    if not corridors:
        return lambda trip: []
    # A corridor shorter than the key would never be indexable, so the key
    # shrinks to the shortest leading segment present.
    key_cells = max(1, min(key_cells, min(len(c[0]) for c in corridors)))

    index: dict = {}
    cellsets = []
    for idx, segs in enumerate(corridors):
        head = tuple(segs[0][:key_cells])
        index.setdefault(head, []).append(idx)
        cellsets.append(frozenset(flatten(segs)))

    def match(trip: Sequence) -> list:
        n = len(trip)
        if n < key_cells:
            return []
        trip_set = set(trip)
        hits = []
        seen = set()
        for i in range(n - key_cells + 1):
            for idx in index.get(tuple(trip[i:i + key_cells]), ()):
                if idx in seen:
                    continue
                seen.add(idx)
                if not cellsets[idx] <= trip_set:
                    continue
                if trip_supports(trip, corridors[idx], max_gap):
                    hits.append(idx)
        return hits

    return match


# ─────────────────────────────────────────────────────────────────────────────
#  Reporting
# ─────────────────────────────────────────────────────────────────────────────
def describe(segments: Sequence[Sequence], support: int, total_trips: int,
             method: str, extra: dict | None = None) -> dict:
    """Serialise a corridor.

    Only measured quantities are emitted.  There is deliberately no
    ``avg_speed_kmh`` derived from an assumed cruising speed -- if a speed is
    reported anywhere it is aggregated from the supporting trips themselves.
    """
    segs = [[_s(c) for c in seg] for seg in segments]
    flat = flatten(segs)
    coords = []
    for seg in segs:
        coords.append([{"cell": c,
                        "lat": round(cell_latlng(c)[0], 6),
                        "lng": round(cell_latlng(c)[1], 6)} for c in seg])
    rec = {
        "segments": segs,
        "h3_sequence": flat,
        "n_segments": len(segs),
        "n_cells": len(flat),
        "n_holes": len(segs) - 1,
        "length_km": round(corridor_km(segments), 3),
        "covered_km": round(covered_km(segments), 3),
        "end_to_end_km": round(end_to_end_km(segments), 3),
        "tortuosity": round(tortuosity(segments), 3),
        "trip_support": int(support),
        "support_pct": round(100.0 * support / max(total_trips, 1), 4),
        "start_h3": flat[0],
        "end_h3": flat[-1],
        "segment_coordinates": coords,
        "method": method,
    }
    if extra:
        rec.update(extra)
    return rec


__all__ = [
    "MAX_TORTUOSITY", "DEFAULT_MAX_GAP", "DEFAULT_MAX_BRIDGE",
    "cell_latlng", "haversine_km", "cells_km", "segment_km",
    "flatten", "corridor_km", "covered_km", "end_to_end_km", "tortuosity",
    "is_simple", "is_valid", "dedup_consecutive", "bridge",
    "find_contiguous", "trip_supports", "match_span", "make_matcher", "describe",
]
