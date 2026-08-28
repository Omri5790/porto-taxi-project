"""
Porto Taxi Trajectory Project – 3D Gaussian Mountain Ridge Topography Engine
=============================================================================
Generates `output/h3_3d_ridges_map.html` with:
1. 3D Gaussian Smooth Density Ridges (Continuous Mountain Mesh Topography).
2. 3D Crest Line Extraction for Top 20 Sub-Routes (Glowing Crest Lines on Ridge Peaks).
3. Height Extrusion Slider (1.0x to 5.0x) and Layer Toggles.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from collections import Counter

import h3

# Project root on the path so `utils` is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.results import load_subroutes

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
INPUT_SUBROUTES_JSON = "output/stage3_subroutes.json"
OUTPUT_RIDGES_MAP = "output/h3_3d_ridges_map.html"


def get_cell_polygon_3d(cell, base_z):
    try:
        boundary = h3.cell_to_boundary(cell)
        return [[round(pt[1], 6), round(pt[0], 6), round(base_z, 2)] for pt in boundary]
    except Exception:
        return None


def generate_3d_ridges():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Gaussian Mountain Ridge Engine      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    if not os.path.exists(INPUT_H3_PARQUET):
        print(f"❌ Error: {INPUT_H3_PARQUET} not found.")
        return
        
    print(f"\n1. Reading H3-encoded dataset from {INPUT_H3_PARQUET}...")
    table = pq.read_table(
        INPUT_H3_PARQUET,
        columns=["h3_res8", "h3_res9", "h3_res10"]
    )
    df = table.to_pandas()
    total_trips = len(df)
    print(f"  ✓ Loaded {total_trips:,} trips.")
    
    print("\n2. Computing Gaussian Smooth Elevation Topography (Ridge Smoothing)...")
    res8_counter = Counter()
    res9_counter = Counter()
    res10_counter = Counter()
    
    for row in df["h3_res8"]:
        if row is not None:
            res8_counter.update(row)
            
    for row in df["h3_res9"]:
        if row is not None:
            res9_counter.update(row)

    for row in df["h3_res10"]:
        if row is not None:
            res10_counter.update(row)
            
    # Unit height scale (meters for 1.0 norm)
    UNIT_METERS = 220.0
    
    # Gaussian Kernel smoothing across H3 neighbors
    smooth_res8 = Counter()
    for cell, count in res8_counter.items():
        smooth_res8[cell] += count * 0.6
        try:
            # Spread 40% density to 1-ring H3 neighbors to create continuous mountain slopes
            neighbors = h3.grid_disk(cell, 1)
            for nbr in neighbors:
                if nbr != cell:
                    smooth_res8[nbr] += count * 0.066
        except Exception:
            pass
            
    smooth_res9 = Counter()
    for cell, count in res9_counter.items():
        smooth_res9[cell] += count * 0.6
        try:
            neighbors = h3.grid_disk(cell, 1)
            for nbr in neighbors:
                if nbr != cell:
                    smooth_res9[nbr] += count * 0.066
        except Exception:
            pass

    # 1. Res 8 Smooth Ridge Base Layer
    data_res8_ridges = []
    res8_height_map = {}
    max_res8 = float(smooth_res8.most_common(1)[0][1]) if smooth_res8 else 1.0
    
    for cell, count in smooth_res8.most_common(350):
        norm_val = round(count / max_res8, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res8_height_map[cell] = h_meters
        poly3d = get_cell_polygon_3d(cell, base_z=0.0)
        
        if poly3d:
            data_res8_ridges.append({
                "hex": cell,
                "count": int(count),
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": 0.0,
                "color": [0, 242, 254, int(140 + norm_val * 100)]
            })
            
    # 2. Res 9 Smooth Ridge Middle Layer (Stacked on Res 8 Parent)
    data_res9_ridges = []
    res9_height_map = {}
    max_res9 = float(smooth_res9.most_common(1)[0][1]) if smooth_res9 else 1.0
    
    for cell, count in smooth_res9.most_common(500):
        norm_val = round(count / max_res9, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res9_height_map[cell] = h_meters
        
        parent_res8 = h3.cell_to_parent(cell, 8)
        base_z = res8_height_map.get(parent_res8, 0.0)
        
        poly3d = get_cell_polygon_3d(cell, base_z=base_z)
        if poly3d:
            data_res9_ridges.append({
                "hex": cell,
                "count": int(count),
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": base_z,
                "color": [127, 0, 255, int(160 + norm_val * 90)]
            })

    # 3. Res 10 Intersection Peaks
    data_res10_peaks = []
    res10_height_map = {}
    max_res10 = float(res10_counter.most_common(1)[0][1]) if res10_counter else 1.0
    
    for cell, count in res10_counter.most_common(650):
        norm_val = round(count / max_res10, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res10_height_map[cell] = h_meters
        
        parent_res9 = h3.cell_to_parent(cell, 9)
        grandparent_res8 = h3.cell_to_parent(cell, 8)
        
        z_res8 = res8_height_map.get(grandparent_res8, 0.0)
        z_res9 = res9_height_map.get(parent_res9, 0.0)
        base_z = float(round(z_res8 + z_res9, 2))
        
        poly3d = get_cell_polygon_3d(cell, base_z=base_z)
        if poly3d:
            data_res10_peaks.append({
                "hex": cell,
                "count": count,
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": base_z,
                "color": [255, 215, 0, int(180 + norm_val * 75)]
            })
            
    # 4. Top 20 Ridge Crest Lines
    data_crestlines = []
    raw_subroutes = load_subroutes(INPUT_SUBROUTES_JSON, limit=20)
    if raw_subroutes:
        
        colors_rgb = [
            [255, 8, 68], [0, 242, 254], [0, 230, 118], [255, 215, 0],
            [127, 0, 255], [255, 145, 0], [224, 64, 251], [56, 189, 248]
        ]
        
        for idx, sr in enumerate(raw_subroutes):
            coords = sr.get("cell_coordinates", [])
            res_lvl = sr.get("res_level", "res9")
            
            if len(coords) < 2:
                continue
                
            path_3d = []
            for pt in coords:
                cell_id = pt["cell"]
                if res_lvl == "res8":
                    z_offset = res8_height_map.get(cell_id, 40.0)
                elif res_lvl == "res9":
                    parent_res8 = h3.cell_to_parent(cell_id, 8)
                    z_offset = res8_height_map.get(parent_res8, 0.0) + res9_height_map.get(cell_id, 40.0)
                else:
                    parent_res9 = h3.cell_to_parent(cell_id, 9)
                    grandparent_res8 = h3.cell_to_parent(cell_id, 8)
                    z_offset = res8_height_map.get(grandparent_res8, 0.0) + res9_height_map.get(parent_res9, 0.0) + res10_height_map.get(cell_id, 40.0)
                    
                path_3d.append([round(pt["lng"], 6), round(pt["lat"], 6), round(z_offset + 30.0, 2)])
                
            data_crestlines.append({
                "rank": idx + 1,
                "support": sr["trip_support"],
                "speed": sr.get("avg_speed_kmh") or 0.0,
                "duration": sr.get("avg_duration_sec") or 0.0,
                "res_level": res_lvl,
                "path": path_3d,
                "color": colors_rgb[idx % len(colors_rgb)]
            })
            
    print(f"  ✓ Processed 3D Gaussian Smooth Ridges and {len(data_crestlines)} Crest Lines.")
    
    print(f"\n3. Building 3D Gaussian Mountain Ridge Web App (`{OUTPUT_RIDGES_MAP}`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D Gaussian Mountain Ridge Topography</title>
    <!-- Deck.gl & MapLibre GL -->
    <script src="https://unpkg.com/deck.gl@8.9.0/dist.min.js"></script>
    <script src="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css" rel="stylesheet" />
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: #090d16;
            color: #f0f4f8;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
        }}
        #container {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; }}
        
        .control-panel {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 10;
            background: rgba(15, 23, 42, 0.92);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 1.5rem;
            width: 360px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
        }}
        
        .panel-title {{
            font-size: 1.25rem;
            font-weight: 700;
            background: linear-gradient(135deg, #00f2fe, #ff0844);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.4rem;
        }}

        .panel-sub {{
            font-size: 0.82rem;
            color: #94a3b8;
            margin-bottom: 1.2rem;
            line-height: 1.4;
        }}

        .layer-toggle {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255,255,255,0.04);
            padding: 10px 12px;
            border-radius: 10px;
            margin-bottom: 8px;
            border: 1px solid rgba(255,255,255,0.08);
        }}

        .layer-toggle.highlight {{
            background: rgba(255, 8, 68, 0.12);
            border: 1px solid rgba(255, 8, 68, 0.4);
        }}

        .layer-label {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.85rem;
            font-weight: 600;
        }}

        .color-dot {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}

        .dot-res8 {{ background: #00f2fe; box-shadow: 0 0 8px #00f2fe; }}
        .dot-res9 {{ background: #7f00ff; box-shadow: 0 0 8px #7f00ff; }}
        .dot-res10 {{ background: #ffd700; box-shadow: 0 0 8px #ffd700; }}
        .dot-subroutes {{ background: #ff0844; box-shadow: 0 0 10px #ff0844; }}

        .switch {{
            position: relative;
            display: inline-block;
            width: 38px;
            height: 22px;
        }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #334155; transition: .3s; border-radius: 22px;
        }}
        .slider:before {{
            position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px;
            background-color: white; transition: .3s; border-radius: 50%;
        }}
        input:checked + .slider {{ background-color: #00f2fe; }}
        input:checked + .slider:before {{ transform: translateX(16px); }}

        .slider-container {{
            margin-top: 1rem;
            background: rgba(255,255,255,0.04);
            padding: 12px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .slider-title {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            font-weight: 600;
            margin-bottom: 6px;
            color: #cbd5e1;
        }}
        input[type=range] {{
            width: 100%;
            accent-color: #00f2fe;
            cursor: pointer;
        }}

        .instruction-box {{
            background: rgba(0, 242, 254, 0.08);
            border-left: 3px solid #00f2fe;
            padding: 0.75rem;
            border-radius: 0 8px 8px 0;
            font-size: 0.8rem;
            color: #cbd5e1;
            margin-top: 1rem;
            line-height: 1.4;
        }}

        .tooltip-custom {{
            position: absolute;
            z-index: 100;
            pointer-events: none;
            background: rgba(11, 15, 25, 0.95);
            border: 1px solid #00f2fe;
            border-radius: 8px;
            padding: 10px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #fff;
            box-shadow: 0 10px 25px rgba(0,0,0,0.8);
            display: none;
        }}
    </style>
</head>
<body>
    <div id="container"></div>

    <div class="control-panel">
        <div class="panel-title">3D Gaussian Mountain Ridges</div>
        <div class="panel-sub">Continuous Density Ridge Extraction • Gaussian Smooth Mountain Slopes & Crest Lines</div>

        <div class="layer-toggle highlight">
            <div class="layer-label">
                <div class="color-dot dot-subroutes"></div>
                🏔️ 3D Ridge Crest Lines (Top 20 Corridors)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-crestlines" checked onchange="updateLayers()">
                <span class="slider" style="background-color:#ff0844;"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res8"></div>
                Res 8 Mountain Slopes (Base Density)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res8" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res9"></div>
                Res 9 Mid Ridges (Stacked Slopes)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res9" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res10"></div>
                Res 10 High Peaks (Intersection Points)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res10" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="slider-container">
            <div class="slider-title">
                <span>3D Ridge Height Multiplier</span>
                <span id="scale-val">1.0x</span>
            </div>
            <input type="range" id="height-scale" min="1.0" max="5.0" step="0.1" value="1.0" oninput="updateHeightScale(this.value)">
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Camera Controls:</strong><br>
            • <strong>Ctrl + Drag / Right Click:</strong> Tilt Pitch & Rotate Camera.<br>
            • <strong>Scroll:</strong> Zoom in/out.<br>
            • <strong>Hover:</strong> Inspect Mountain Slopes & Crest Lines.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8_ridges)};
        const dataRes9 = {json.dumps(data_res9_ridges)};
        const dataRes10 = {json.dumps(data_res10_peaks)};
        const dataCrestlines = {json.dumps(data_crestlines)};

        let currentScale = 1.0;

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                
                if (info.object.rank) {{
                    tooltip.innerHTML = `
                        <div style="color:#ff0844; font-weight:700; font-size:1rem;">🏔️ 3D Ridge Crest Line #${{info.object.rank}}</div>
                        <div>Trip Volume: <strong>${{info.object.support.toLocaleString()}}</strong></div>
                        <div>Avg Speed: <strong>${{info.object.speed}} km/h</strong></div>
                        <div>Duration: <strong>${{(info.object.duration / 60.0).toFixed(1)}} min</strong></div>
                    `;
                }} else {{
                    tooltip.innerHTML = `
                        <div style="color:#00f2fe; font-weight:700;">H3 Ridge Cell: ${{info.object.hex}}</div>
                        <div>Smooth Density: <strong>${{info.object.count.toLocaleString()}}</strong></div>
                        <div>Ridge Base Z: <strong>${{(info.object.base_z * currentScale).toFixed(1)}}m</strong></div>
                    `;
                }}
            }} else {{
                tooltip.style.display = 'none';
            }}
        }}

        // Bulletproof Dark Raster Tiles
        const darkTileStyle = {{
            version: 8,
            sources: {{
                'carto-dark': {{
                    type: 'raster',
                    tiles: ['https://basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png'],
                    tileSize: 256,
                    attribution: '&copy; CartoDB'
                }}
            }},
            layers: [{{
                id: 'carto-dark-layer',
                type: 'raster',
                source: 'carto-dark',
                minzoom: 0,
                maxzoom: 20
            }}]
        }};

        function getLayers() {{
            const layers = [];

            // Layer 1: Res 8 Mountain Slopes
            if (document.getElementById('check-res8').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-ridges-res8',
                    data: dataRes8,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon,
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [0, 242, 254, 80],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 2: Res 9 Mid Ridges
            if (document.getElementById('check-res9').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-ridges-res9',
                    data: dataRes9,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 100],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 3: Res 10 Peaks
            if (document.getElementById('check-res10').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-ridges-res10',
                    data: dataRes10,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 140],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 4: 3D Ridge Crest Lines (Top 20 Active Paths)
            if (document.getElementById('check-crestlines').checked) {{
                layers.push(new deck.PathLayer({{
                    id: 'layer-path-crestlines',
                    data: dataCrestlines,
                    pickable: true,
                    widthScale: 1,
                    widthMinPixels: 5,
                    getPath: d => d.path.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                    getColor: d => d.color,
                    getWidth: d => d.rank <= 3 ? 14 : d.rank <= 10 ? 9 : 6,
                    onHover: updateTooltip
                }}));
            }}

            return layers;
        }}

        const deckgl = new deck.DeckGL({{
            container: 'container',
            mapStyle: darkTileStyle,
            initialViewState: {{
                longitude: -8.6291,
                latitude: 41.1579,
                zoom: 13.0,
                pitch: 60,
                bearing: 28
            }},
            controller: true,
            layers: getLayers()
        }});

        function updateLayers() {{
            deckgl.setProps({{ layers: getLayers() }});
        }}

        function updateHeightScale(val) {{
            currentScale = parseFloat(val);
            document.getElementById('scale-val').innerText = currentScale.toFixed(1) + 'x';
            updateLayers();
        }}
    </script>
</body>
</html>
"""

    with open(OUTPUT_RIDGES_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Gaussian Mountain Ridge Map to {OUTPUT_RIDGES_MAP}")

if __name__ == "__main__":
    generate_3d_ridges()
