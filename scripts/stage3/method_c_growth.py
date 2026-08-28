"""
Method C -- Count-Min-pruned level-wise growth with verified support.
=====================================================================

The brief asks for a third method that is *neither* clustering nor suffix
based.  This one is a level-wise, Apriori-style search: start from short
frequent seeds and grow them one step at a time, re-measuring support against
the whole dataset at every step, until no extension survives.

Why grow instead of chain
-------------------------
The tempting shortcut is to mine frequent short n-grams once and then chain
overlapping ones into long routes, assigning the chain the minimum of its
parts' supports.  That number is an **upper bound that is almost never
attained**: anti-monotonicity says the support of a chain is at most the
minimum, and in practice it collapses far below it.  Chaining fifty 5-grams
that 4,000 trips each traversed can easily produce a corridor that *zero* trips
traversed end to end -- and, without a geometric guard, one that doubles back
through the same cells three times.

Growing instead of chaining removes the problem by construction.  A corridor
only reaches length L if a pass over the data actually found ``min_support``
trips that traverse all L cells, so **every support number this method reports
is measured, not inferred**.

Growing rightwards only
-----------------------
Corridors are extended forwards only, which halves the work, and it costs
nothing: by anti-monotonicity every k-gram inside a frequent corridor is itself
frequent, so the corridor's own leading k-gram is in the seed set.  Growing
right from *that* seed reconstructs the whole corridor.  A separate leftward
pass would only rediscover corridors the leftmost seed already produces.

Where the sketches pay
----------------------
The seeds come from :mod:`gate`, whose Count-Min Sketch removes >99% of n-grams
before any shuffle, and whose Bloom filter then gates extension candidates: by
anti-monotonicity an extension whose trailing k-gram is not frequent cannot
itself be frequent, so it dies in the map task rather than crossing the network.

Holes
-----
Each round tries two kinds of step from the end of a corridor:

* **contiguous** -- the next 1..``MAX_STEP`` cells the trip actually visits;
* **gap** -- skip up to ``max_gap`` trip cells and resume, opening a new
  segment.  This is the Haifa->Ashdod case: trips diverge for a stretch and
  rejoin, and the corridor carries the hole instead of being truncated at it.

Both kinds are verified identically, so a corridor with a hole is held to the
same evidential standard as one without.
"""

from __future__ import annotations

import time

from .corridors import (DEFAULT_MAX_GAP, MAX_TORTUOSITY, dedup_consecutive,
                        flatten, is_valid, make_matcher, match_span)

MAX_STEP = 4          # cells a corridor may gain per round
BRANCH = 2            # genuinely distinct extension branches kept per corridor
MAX_FRONTIER = 600    # corridors carried into the next round (beam width)
MAX_OVERLAP = 0.75    # two beam entries sharing more than this are near-duplicates
MAX_ROUNDS = 45
MAX_CELLS = 220


def run(sc, trips_rdd, total_trips: int, min_support: int,
        seeds, bc_bloom, gate_k: int,
        max_gap: int = DEFAULT_MAX_GAP, max_step: int = MAX_STEP,
        branch: int = BRANCH, max_frontier: int = MAX_FRONTIER,
        max_overlap: float = MAX_OVERLAP,
        max_rounds: int = MAX_ROUNDS, max_tortuosity: float = MAX_TORTUOSITY,
        log=print):
    """Grow frequent seeds into maximal corridors, verifying support each round.

    Parameters
    ----------
    seeds : iterable of ``(cells_tuple, support)`` -- frequent k-grams.

    Returns ``(elapsed_sec, [(segments, support), ...], stats)``.
    """
    t0 = time.time()

    frontier = []
    for cells, sup in sorted(seeds, key=lambda kv: -kv[1])[:max_frontier]:
        segs = [list(cells)]
        if is_valid(segs, max_tortuosity):
            frontier.append((segs, int(sup)))

    finished = []
    round_log = []
    total_extension_keys = 0

    for rnd in range(1, max_rounds + 1):
        if not frontier:
            break

        corridors = [segs for segs, _ in frontier]
        bc_corr = sc.broadcast(corridors)
        bc_cfg = sc.broadcast({"max_gap": max_gap, "max_step": max_step,
                               "gate_k": gate_k})

        def propose(rows):
            corr = bc_corr.value
            cfg = bc_cfg.value
            bloom = bc_bloom.value
            mg, ms, gk = cfg["max_gap"], cfg["max_step"], cfg["gate_k"]
            matcher = make_matcher(corr, mg)
            for trip_id, cells in rows:
                trip = dedup_consecutive(cells)
                if len(trip) < 2:
                    continue
                n = len(trip)
                for cid in matcher(trip):
                    segs = corr[cid]
                    _start, end = match_span(trip, segs, mg)
                    if end < 0 or end >= n:
                        continue
                    used = set(flatten(segs))
                    tail = segs[-1]

                    # ---- contiguous continuation ---------------------------
                    add = []
                    for step in range(1, ms + 1):
                        if end + step > n:
                            break
                        nxt = trip[end + step - 1]
                        if nxt in used or nxt in add:
                            break
                        add.append(nxt)
                        # Anti-monotone Bloom gate on the trailing k-gram.
                        window = (tuple(tail) + tuple(add))[-gk:]
                        if len(window) == gk and window not in bloom:
                            add.pop()
                            break
                        yield ((cid, "C", tuple(add)), trip_id)

                    # ---- continuation across a hole ------------------------
                    for skip in range(1, mg + 1):
                        j = end + skip
                        if j >= n:
                            break
                        nxt = trip[j]
                        if nxt in used:
                            continue
                        yield ((cid, "G", (nxt,)), trip_id)

        proposals = (trips_rdd
                     .mapPartitions(propose)
                     .distinct()
                     .map(lambda kv: (kv[0], 1))
                     .reduceByKey(lambda a, b: a + b)
                     .filter(lambda kv: kv[1] >= min_support)
                     .collect())

        bc_corr.destroy()
        bc_cfg.destroy()
        total_extension_keys += len(proposals)

        by_corridor: dict = {}
        for (cid, kind, add), sup in proposals:
            by_corridor.setdefault(cid, []).append((kind, add, sup))

        next_frontier: dict = {}
        extended = set()
        for cid, options in by_corridor.items():
            segs, _ = frontier[cid]
            # Ranking: support first, length second.  Preferring the longest
            # step looks right but quietly kills the hole handling -- a 4-cell
            # contiguous step always outranks the 1-cell step that crosses a
            # gap, so a corridor follows whichever branch the trips split into
            # and stops there.  Support-first prefers the step that keeps the
            # corridor able to grow, which is what maximising final length
            # actually requires.
            #
            # One branch slot is reserved for a gap step whenever one survives,
            # so the "trips diverge here and rejoin" case is always explored.
            options.sort(key=lambda o: (-o[2], -len(o[1])))
            contiguous = [o for o in options if o[0] == "C"]
            gapped = [o for o in options if o[0] == "G"]
            if gapped and branch > 1:
                ordered_options = ([contiguous[0]] if contiguous else []) \
                    + [gapped[0]] \
                    + contiguous[1:] + gapped[1:]
            else:
                ordered_options = options
            taken_heads = set()
            kept = 0
            for kind, add, sup in ordered_options:
                if kept >= branch:
                    break
                if add[0] in taken_heads:
                    continue
                new_segs = _apply(segs, kind, add)
                if new_segs is None:
                    continue
                if sum(len(s) for s in new_segs) > MAX_CELLS:
                    continue
                if not is_valid(new_segs, max_tortuosity):
                    continue
                taken_heads.add(add[0])
                key = tuple(tuple(s) for s in new_segs)
                prev = next_frontier.get(key)
                if prev is None or sup > prev[1]:
                    next_frontier[key] = (new_segs, int(sup))
                kept += 1
            if kept:
                extended.add(cid)

        # Corridors nothing could extend are maximal: report them.
        for cid, (segs, sup) in enumerate(frontier):
            if cid not in extended:
                finished.append((segs, sup))

        ranked = sorted(next_frontier.values(),
                        key=lambda x: (-sum(len(s) for s in x[0]), -x[1]))
        before_prune = len(ranked)
        ranked = _prune_overlapping(ranked, max_overlap)
        frontier = ranked[:max_frontier]

        round_log.append({
            "round": rnd,
            "frontier_in": len(corridors),
            "surviving_extensions": len(proposals),
            "distinct_children": len(next_frontier),
            "after_overlap_pruning": before_prune and len(ranked),
            "frontier_out": len(frontier),
            "maximal_so_far": len(finished),
        })
        log(f"    round {rnd:2d}: frontier {len(corridors):5d} -> {len(frontier):5d} "
            f"(from {len(proposals):6d} verified extensions), maximal {len(finished):5d}")

    finished.extend(frontier)

    elapsed = time.time() - t0
    stats = {
        "algorithm": "Count-Min pruned level-wise growth with per-round verified support",
        "approximate_structures": [
            "Count-Min Sketch (via the shared gate) removes infrequent seeds "
            "before any shuffle",
            f"Bloom filter over frequent {gate_k}-grams gates extension "
            f"candidates inside the map task (anti-monotone, no false negatives)",
        ],
        "seeds": len(seeds),
        "rounds_run": len(round_log),
        "growth_direction": "forward only (leftward growth is redundant by anti-monotonicity)",
        "max_step_cells": max_step,
        "branches_per_corridor": branch,
        "beam_width": max_frontier,
        "max_beam_overlap": max_overlap,
        "max_gap_cells": max_gap,
        "surviving_extension_keys": total_extension_keys,
        "corridors_returned": len(finished),
        "min_support_trips": min_support,
        "support_is_measured_each_round": True,
        "round_log": round_log,
        "runtime_sec": round(elapsed, 2),
        "distributed": True,
    }
    return elapsed, finished, stats


def _prune_overlapping(ranked, max_overlap: float):
    """Diversity pruning for the beam.

    Seeds starting one cell apart on the same arterial grow into corridors that
    are 95% identical, and a beam full of them explores one road instead of
    twenty.  Walking the beam best-first and dropping any entry that shares more
    than ``max_overlap`` of its cells with an entry already kept costs O(n^2)
    set intersections on the driver over a few hundred corridors, and keeps the
    beam pointed at genuinely different parts of the city.
    """
    kept = []
    kept_sets = []
    for segs, sup in ranked:
        cells = frozenset(flatten(segs))
        redundant = False
        for other in kept_sets:
            overlap = len(cells & other) / min(len(cells), len(other))
            if overlap > max_overlap:
                redundant = True
                break
        if not redundant:
            kept.append((segs, sup))
            kept_sets.append(cells)
    return kept


def _apply(segments, kind: str, add: tuple):
    """Return a new segment list with ``add`` attached, or None if illegal."""
    segs = [list(s) for s in segments]
    if kind == "C":
        segs[-1].extend(add)
    else:
        segs.append(list(add))
    cells = flatten(segs)
    if len(set(cells)) != len(cells):
        return None
    return segs
