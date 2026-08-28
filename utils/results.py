"""
Read Stage 3 results in the flat shape the 3D map builders expect.

The map builders predate the Stage 3 rewrite.  They were written against a
result schema where a corridor was one flat list of cells; a corridor is now a
list of *segments* with holes between them, and the field names changed with it.

Rather than rewrite three large Deck.gl generators, this adapter presents the
new file in the old shape: segments are concatenated (the maps draw a single
polyline anyway) and the renamed fields are mapped across.  Anything the new
schema does not have -- the fabricated ``avg_speed_kmh`` of the old pipeline,
for instance -- comes back as ``None`` rather than as an invented number.
"""

from __future__ import annotations

import json
import os

DEFAULT_RESULTS = "output/stage3_subroutes.json"


def load_subroutes(path: str = DEFAULT_RESULTS, limit: int = 100) -> list:
    """Corridors as ``[{cell_coordinates, trip_support, avg_distance_km, ...}]``.

    Returns an empty list when the results file does not exist yet, so a map can
    still be built from the H3 density alone before Stage 3 has been run.
    """
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    routes = payload.get("top_100_longest") or []
    out = []
    for rec in routes[:limit]:
        # Segments are concatenated: the maps draw one polyline per corridor, and
        # the hole is visible anyway as the long straight hop between segments.
        coords = [pt for seg in rec.get("segment_coordinates", []) for pt in seg]
        if len(coords) < 2:
            continue
        out.append({
            "cell_coordinates": coords,
            "res_level": "res9",
            "trip_support": int(rec.get("trip_support", 0)),
            "avg_distance_km": float(rec.get("length_km", 0.0)),
            "covered_km": float(rec.get("covered_km", 0.0)),
            "sequence_length": int(rec.get("n_cells", len(coords))),
            "n_holes": int(rec.get("n_holes", 0)),
            "tortuosity": float(rec.get("tortuosity", 0.0)),
            # Measured from the supporting trips, or None -- never assumed.
            "avg_speed_kmh": rec.get("mean_trip_speed_kmh"),
            "avg_duration_sec": rec.get("mean_trip_duration_sec"),
            "method": rec.get("method", ""),
        })
    return out


__all__ = ["load_subroutes", "DEFAULT_RESULTS"]
