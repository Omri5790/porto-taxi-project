"""
Generate the Stage 3 demonstration notebook for Colab Enterprise.

The notebook is generated rather than hand-edited so that it can never drift
away from the results files: every number and every map is computed from
``stage3_subroutes.json`` at run time.  The previous notebook hard-coded its
own summary table, which is how it ended up disagreeing with both the README
and the data.

    python tools/build_stage3_notebook.py --out notebooks/stage3_colab_enterprise.ipynb
"""

from __future__ import annotations

import argparse
import json


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


CELLS = []

CELLS.append(md("""# Stage 3 — Popular Long Sub-Routes in Porto

**Cloud Computing for Big Data — final project**

This notebook is the demonstration required by the brief: the top popular long
sub-routes, drawn on a map, at each of the six minimum-distance configurations.

It is designed to run in **Colab Enterprise** (Vertex AI → Colab Enterprise →
Notebooks), reading the results the Dataproc job wrote to GCS. It also runs
unchanged on a local checkout by pointing `RESULTS` at a local path.

Every figure below is computed from the results file at run time. Nothing in
this notebook is transcribed by hand, so it cannot disagree with the data.
"""))

CELLS.append(code("""# Colab Enterprise images ship without folium; h3 is needed to draw cell outlines.
!pip install -q folium h3 2>/dev/null

import json, math, os
import folium
import h3
from IPython.display import HTML, display

print("folium", folium.__version__, "| h3", h3.__version__)"""))

CELLS.append(md("""## 1. Load the results

Point `RESULTS` at the output directory of the Dataproc run. The bucket path is
the one `run_pipeline_dataproc.sh` printed when the job finished — the results
live in the bucket, not on the cluster, so they are still there after the
cluster was deleted.
"""))

CELLS.append(code('''# Either a gs:// prefix from the cluster run, or a local directory.
RESULTS = os.environ.get("STAGE3_RESULTS", "gs://porto-taxi-project-bf990986/results/stage3/latest")

def load(name):
    path = f"{RESULTS.rstrip('/')}/{name}"
    if path.startswith("gs://"):
        from google.cloud import storage
        bucket_name, blob_name = path[5:].split("/", 1)
        blob = storage.Client().bucket(bucket_name).blob(blob_name)
        return json.loads(blob.download_as_text())
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

data = load("stage3_subroutes.json")
bench = load("stage3_benchmark.json")

meta = data["metadata"]
print(f"trips analysed        : {meta['total_trips']:,}")
print(f"mining support floor  : {meta['mining_support_pct']}%  "
      f"({meta['mining_min_support_trips']:,} trips)")
print(f"max cells inside a hole: {meta['max_gap_cells']}")
print(f"generated             : {meta['generated_utc']}")
print()
print("support definition:")
print(" ", meta["support_definition"])'''))

CELLS.append(md("""## 2. What is achievable at all

Before looking at what the algorithms found, it is worth knowing what *could*
be found. A trip can only traverse a corridor of length **L** if the trip itself
is at least **L** long, so the trip-length distribution puts a hard ceiling on
the popularity of any long corridor — no algorithm can beat it.

This is the honest answer to "why are there no 40 km corridors": Porto's
bounding box is roughly 25 × 22 km and the median trip is under 4 km.
"""))

CELLS.append(code('''ceiling = data["length_ceiling"]
rows = "".join(
    f"<tr><td>&ge; {r['min_length_km']:.0f} km</td>"
    f"<td style='text-align:right'>{r['trips_at_least_this_long']:,}</td>"
    f"<td style='text-align:right'>{r['max_possible_support_pct']:.4f}%</td></tr>"
    for r in ceiling)
display(HTML(f"""
<table style="border-collapse:collapse;font-family:system-ui;font-size:14px">
<thead><tr style="background:#eef2f4">
  <th style="padding:6px 14px;text-align:left">corridor length</th>
  <th style="padding:6px 14px">trips at least this long</th>
  <th style="padding:6px 14px">max possible support</th>
</tr></thead><tbody>{rows}</tbody></table>
"""))'''))

CELLS.append(md("""## 3. Choosing X — the support threshold

The brief asks us to experiment with the minimum share of trips **X%** that must
traverse a sub-route for it to count as popular, while maximising the
sub-route's length. The two pull against each other: raising X leaves only short
corridors, lowering it admits long ones that few trips actually use.

Support is anti-monotone in X — anything frequent at a high threshold is also
frequent at a lower one — so the pipeline mines **once** at the lowest threshold
and derives the whole sweep by filtering measured supports. One cluster run,
the entire experiment.
"""))

CELLS.append(code('''sweep = data["support_sweep"]
cols = ["support_pct", "min_trips", "corridors", "mean_length_km", "max_length_km",
        "ge_1km", "ge_3km", "ge_5km", "ge_10km", "ge_20km", "ge_40km"]
head = "".join(f"<th style='padding:6px 12px'>{c}</th>" for c in cols)
body = ""
for row in sweep:
    tint = "#fff6f6" if row.get("below_mining_floor") else "white"
    body += f"<tr style='background:{tint}'>" + "".join(
        f"<td style='padding:6px 12px;text-align:right'>{row.get(c, '-')}</td>" for c in cols) + "</tr>"
display(HTML(f"""
<table style="border-collapse:collapse;font-family:system-ui;font-size:13px">
<thead><tr style="background:#eef2f4">{head}</tr></thead><tbody>{body}</tbody></table>
<p style="font-family:system-ui;font-size:12px;color:#667">
Rows tinted red sit below the mining floor, so their counts are limited by what
was mined, not by the threshold itself.</p>
"""))'''))

CELLS.append(md("""## 4. The three methods, compared

All three were scored the same way: whatever a method estimated while mining,
its corridors were re-measured against 100% of the trips afterwards.
`support overstated by` is the gap between the two — it is the price of the
approximation each method uses, measured rather than asserted.
"""))

CELLS.append(code('''card = bench["methods"]["per_method_scorecard"]
cols = ["corridors_verified", "max_length_km", "mean_length_km", "mean_cells",
        "mean_support", "with_holes", "mean_tortuosity", "support_overestimate_pct"]
head = "<th style='padding:6px 12px;text-align:left'>method</th>" + "".join(
    f"<th style='padding:6px 12px'>{c}</th>" for c in cols)
body = ""
for name, s in card.items():
    body += (f"<tr><td style='padding:6px 12px'><b>{name}</b></td>"
             + "".join(f"<td style='padding:6px 12px;text-align:right'>{s.get(c,'-')}</td>"
                       for c in cols) + "</tr>")
display(HTML(f"<table style='border-collapse:collapse;font-family:system-ui;font-size:13px'>"
             f"<thead><tr style='background:#eef2f4'>{head}</tr></thead><tbody>{body}</tbody></table>"))

print()
for name in ("gate", "method_a_lsh_clustering", "method_b_suffix_array", "method_c_growth"):
    s = bench["methods"].get(name)
    if not s:
        continue
    print(f"--- {name}")
    for key in ("algorithm", "runtime_sec", "pruned_before_shuffle_pct",
                "bloom_pruned_pct", "cms_memory_mb", "bloom_memory_kb",
                "cms_false_positive_pct", "rounds_run", "windows_hashed",
                "lsh_similarity_threshold"):
        if key in s:
            print(f"      {key:<28s} {s[key]}")
    for line in s.get("approximate_structures", []):
        print(f"      structure: {line}")
    print()'''))

CELLS.append(md("""## 5. The maps

One map per configuration. Segments of the same corridor share a colour; where a
corridor carries a **hole** — a stretch where trips split between alternatives
and rejoin — the hole is drawn as a dashed line, because no trip is claimed to
have driven it.
"""))

CELLS.append(code('''PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
           "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324",
           "#800000", "#aaffc3", "#000075", "#a9a9a9"]

def draw(routes, title, max_routes=100):
    m = folium.Map(location=[41.1580, -8.6290], zoom_start=12,
                   tiles="CartoDB positron")
    for i, r in enumerate(routes[:max_routes]):
        colour = PALETTE[i % len(PALETTE)]
        tip = (f"#{r.get('rank','?')} &middot; {r['length_km']:.2f} km &middot; "
               f"{r['trip_support']:,} trips ({r['support_pct']:.3f}%) &middot; "
               f"{r['n_cells']} cells, {r['n_holes']} hole(s) &middot; {r['method']}")
        prev_end = None
        for seg in r["segment_coordinates"]:
            pts = [(p["lat"], p["lng"]) for p in seg]
            folium.PolyLine(pts, color=colour, weight=4, opacity=0.85,
                            tooltip=tip).add_to(m)
            if prev_end is not None:
                folium.PolyLine([prev_end, pts[0]], color=colour, weight=2,
                                opacity=0.65, dash_array="6,8",
                                tooltip="hole: trips diverge here").add_to(m)
            prev_end = pts[-1]
        first = r["segment_coordinates"][0][0]
        folium.CircleMarker((first["lat"], first["lng"]), radius=3,
                            color=colour, fill=True, fill_opacity=1).add_to(m)
    folium.map.Marker(
        [41.212, -8.72],
        icon=folium.DivIcon(html=(
            "<div style='font:600 14px system-ui;background:rgba(255,255,255,.92);"
            "border:1px solid #ccc;border-radius:3px;padding:5px 10px'>"
            f"{title}</div>"))).add_to(m)
    return m'''))

for km in (1, 3, 5, 10, 20, 40):
    CELLS.append(md(f"### ≥ {km} km"))
    CELLS.append(code(f'''bucket = data["by_threshold_km"]["{km}"]
routes = bucket["routes"]
status = "target met" if bucket["met_target"] else f"below the target of {{bucket['target']}}"
print(f"{{len(routes)}} corridors at >= {km} km, mined at X = {{bucket['support_pct_used']}}%  ({{status}})")
if routes:
    print(f"  longest {{max(r['length_km'] for r in routes):.2f}} km, "
          f"most popular {{max(r['trip_support'] for r in routes):,}} trips, "
          f"{{sum(1 for r in routes if r['n_holes'] > 0)}} carry holes")
    display(draw(routes, f"Popular sub-routes &ge; {km} km ({{len(routes)}} found)"))
else:
    cap = next(c for c in data["length_ceiling"] if c["min_length_km"] == {km}.0)
    print(f"  none found. At most {{cap['trips_at_least_this_long']:,}} trips "
          f"({{cap['max_possible_support_pct']:.4f}}%) are even {km} km long, so no corridor "
          f"of this length can be popular in this dataset.")'''))

CELLS.append(md("""## 6. Unusual routes

The brief's third question. A trip is unusual to the extent that it uses cell
transitions the rest of the fleet does not — measured against a Bloom filter of
the frequent transitions, which is small enough to broadcast to every executor.
"""))

CELLS.append(code('''anom = load("stage3_anomalous_routes.json")
top = anom["top_anomalous_trips"]
print(f"most unusual {len(top)} trips")
for r in top[:5]:
    print(f"  {r['trip_id']}  novelty {r['novelty']:.3f}  "
          f"{r['rare_transitions']}/{r['n_cells']-1} rare transitions  "
          f"{r['distance_km']:.2f} km")

m = folium.Map(location=[41.1580, -8.6290], zoom_start=12, tiles="CartoDB dark_matter")
for i, r in enumerate(top[:40]):
    pts = [h3.cell_to_latlng(c) for c in r["h3_sequence"]]
    folium.PolyLine(pts, color="#ff5c4d", weight=2.5, opacity=0.8,
                    tooltip=f"{r['trip_id']} &middot; novelty {r['novelty']:.3f}").add_to(m)
display(m)

print()
print("novelty distribution across the fleet:")
for b in anom["novelty_histogram"]:
    bar = "#" * max(1, int(60 * b["trips"] / max(x["trips"] for x in anom["novelty_histogram"])))
    print(f"  {b['novelty_bin']:.1f}  {b['trips']:>9,}  {bar}")'''))

CELLS.append(md("""## 7. Audit

The same checks that run after every cluster run, repeated here so the figures
above can be trusted without taking the pipeline's word for anything: no
corridor may visit a cell twice, the reported lengths must recompute from the
cells, and no column may be a constant masquerading as a measurement.
"""))

CELLS.append(code('''def audit(routes, total_trips, max_tortuosity=2.5):
    problems, speeds = [], set()
    for r in routes:
        flat = [c for s in r["segments"] for c in s]
        if len(set(flat)) != len(flat):
            problems.append(f"rank {r.get('rank')}: revisits cells (loop)")
        km = 0.0
        for seg in r["segments"]:
            for a, b in zip(seg, seg[1:]):
                km += h3.great_circle_distance(h3.cell_to_latlng(a), h3.cell_to_latlng(b), unit="km")
        for s1, s2 in zip(r["segments"], r["segments"][1:]):
            km += h3.great_circle_distance(h3.cell_to_latlng(s1[-1]), h3.cell_to_latlng(s2[0]), unit="km")
        if abs(km - r["length_km"]) > 0.05:
            problems.append(f"rank {r.get('rank')}: length {r['length_km']} vs recomputed {km:.2f}")
        e2e = h3.great_circle_distance(h3.cell_to_latlng(flat[0]), h3.cell_to_latlng(flat[-1]), unit="km")
        if e2e > 1e-9 and km / e2e > max_tortuosity + 1e-6:
            problems.append(f"rank {r.get('rank')}: tortuosity {km/e2e:.2f}")
        if r["trip_support"] > total_trips:
            problems.append(f"rank {r.get('rank')}: support exceeds trip count")
        if r.get("mean_trip_speed_kmh") is not None:
            speeds.add(r["mean_trip_speed_kmh"])
    if len(routes) > 5 and len(speeds) == 1:
        problems.append("every route reports the same speed - that is an assumption, not a measurement")
    return problems, speeds

problems, speeds = audit(data["top_100_longest"], meta["total_trips"])
print(f"audited {len(data['top_100_longest'])} corridors")
print(f"  distinct measured speeds: {len(speeds)}")
print(f"  corridors carrying holes: {sum(1 for r in data['top_100_longest'] if r['n_holes'] > 0)}")
print("  PASSED - no loops, lengths reproduce, no constant columns" if not problems
      else "  FAILED:\\n    " + "\\n    ".join(problems[:20]))'''))


def build(out_path: str) -> None:
    nb = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
            "colab": {"provenance": [], "toc_visible": True},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1, ensure_ascii=False)
    print(f"wrote {out_path} ({len(CELLS)} cells)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="notebooks/stage3_colab_enterprise.ipynb")
    build(ap.parse_args().out)
