"""
Render the Stage 3 corridors as one standalone interactive map.

Replaces the earlier per-threshold map generators, which read a results schema
that no longer exists.  Like the notebook and the deck, this reads the results
file and nothing else, so it cannot show numbers the data does not contain.

    python tools/build_subroute_maps.py \
        --results output/stage3_subroutes.json \
        --out     output/stage3_subroutes_map.html
"""

from __future__ import annotations

import argparse
import json

import folium
from folium.plugins import GroupedLayerControl

PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
           "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324",
           "#800000", "#aaffc3", "#000075", "#a9a9a9"]


def add_routes(group, routes, max_routes=100):
    for i, r in enumerate(routes[:max_routes]):
        colour = PALETTE[i % len(PALETTE)]
        tip = (f"#{r.get('rank', '?')} &middot; {r['length_km']:.2f} km &middot; "
               f"{r['trip_support']:,} trips ({r['support_pct']:.3f}%) &middot; "
               f"{r['n_cells']} cells, {r['n_holes']} hole(s) &middot; {r['method']}")
        prev_end = None
        for seg in r["segment_coordinates"]:
            pts = [(p["lat"], p["lng"]) for p in seg]
            folium.PolyLine(pts, color=colour, weight=4, opacity=0.85,
                            tooltip=tip).add_to(group)
            if prev_end is not None:
                # Bridged holes are drawn dashed: nothing was observed there.
                folium.PolyLine([prev_end, pts[0]], color=colour, weight=2,
                                opacity=0.6, dash_array="6,8",
                                tooltip="hole: trips diverge here").add_to(group)
            prev_end = pts[-1]
        head = r["segment_coordinates"][0][0]
        folium.CircleMarker((head["lat"], head["lng"]), radius=3, color=colour,
                            fill=True, fill_opacity=1, tooltip=tip).add_to(group)


def build(results_path: str, out_path: str) -> None:
    with open(results_path, encoding="utf-8") as fh:
        data = json.load(fh)

    meta = data["metadata"]
    m = folium.Map(location=[41.158, -8.629], zoom_start=12,
                   tiles="CartoDB positron", control_scale=True)

    groups = []
    for key in ("1", "3", "5", "10", "20", "40"):
        bucket = data["by_threshold_km"].get(key)
        if not bucket:
            continue
        label = (f"&ge; {key} km &mdash; {bucket['found']} corridors "
                 f"(X = {bucket['support_pct_used']}%)")
        fg = folium.FeatureGroup(name=label, show=(key == "1"))
        add_routes(fg, bucket["routes"])
        fg.add_to(m)
        groups.append(fg)

    GroupedLayerControl(groups={"minimum corridor length": groups},
                        collapsed=False, exclusive_groups=False).add_to(m)

    ceiling_rows = "".join(
        f"<tr><td>&ge; {c['min_length_km']:.0f} km</td>"
        f"<td style='text-align:right;padding-left:10px'>"
        f"{c['max_possible_support_pct']:.3f}%</td></tr>"
        for c in data.get("length_ceiling", []))
    legend = f"""
    <div style="position:fixed;bottom:22px;left:22px;z-index:9999;
                background:rgba(255,255,255,.94);border:1px solid #c9d4d9;
                border-radius:4px;padding:12px 15px;font:12px/1.5 system-ui;
                max-width:305px;box-shadow:0 2px 10px rgba(0,0,0,.12)">
      <div style="font-weight:700;font-size:13px;margin-bottom:5px">
        Popular long sub-routes &middot; Porto</div>
      <div style="color:#5a6b75">
        {meta['total_trips']:,} trips &middot; H3 res 9 &middot;
        mined at X = {meta['mining_support_pct']}%<br>
        Solid = observed. <b>Dashed = a hole</b>, where trips diverge and rejoin.
      </div>
      <div style="margin-top:9px;font-weight:600">Ceiling on support</div>
      <table style="color:#5a6b75">{ceiling_rows}</table>
      <div style="margin-top:7px;color:#8494a0;font-size:11px">
        A trip can only traverse a corridor of length L if the trip is itself
        at least L long.</div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    m.save(out_path)
    total = sum(len(b["routes"]) for b in data["by_threshold_km"].values())
    print(f"wrote {out_path} ({len(groups)} layers, {total} route polylines)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="output/stage3_subroutes.json")
    ap.add_argument("--out", default="output/stage3_subroutes_map.html")
    a = ap.parse_args()
    build(a.results, a.out)
