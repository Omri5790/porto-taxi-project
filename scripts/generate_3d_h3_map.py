"""
Porto Taxi Trajectory Project – 3D Stacked Pyramid + 100 Popular Long Sub-Routes Engine
========================================================================================
Generates `output/h3_3d_map.html` with:
1. Res 8, Res 9, Res 10 3D Cumulative Stepped Hexagon Pyramids.
2. 100 Mined Popular Long Sub-Routes rendered as a High-Visibility 3D Floating Path Layer.
   Elevated ABOVE 3D columns so lines are never occluded!
3. Interactive Distance Threshold Filters (All 100, ≥1km, ≥3km, ≥5km, ≥10km, ≥20km, ≥40km).
4. Dedicated "Focus 100 Sub-Routes" preset toggle button.
"""

import os
import sys
import json
import pandas as pd
import pyarrow.parquet as pq
from collections import Counter

# Ensure user site packages are in python path for H3
user_site = os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages")
if os.path.exists(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

import h3

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
INPUT_100_SUBROUTES_JSON = "output/popular_long_subroutes_100.json"
OUTPUT_3D_MAP = "output/h3_3d_map.html"


def get_cell_polygon_3d(cell, base_z):
    try:
        boundary = h3.cell_to_boundary(cell)
        return [[round(pt[1], 6), round(pt[0], 6), round(base_z, 2)] for pt in boundary]
    except Exception:
        return None


def generate_3d_map():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Pyramid + 100 Sub-Routes Engine     ║")
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
    
    print("\n2. Computing Parent-Child Cumulative Spatial Step Elevations...")
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
            
    # Base height in meters for 1.0 norm
    UNIT_METERS = 180.0
    
    # 1. Base Layer: Res 8
    data_res8 = []
    res8_height_map = {}
    max_res8 = float(res8_counter.most_common(1)[0][1]) if res8_counter else 1.0
    
    for cell, count in res8_counter.most_common(250):
        norm_val = round(count / max_res8, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res8_height_map[cell] = h_meters
        poly3d = get_cell_polygon_3d(cell, base_z=0.0)
        
        if poly3d:
            data_res8.append({
                "hex": cell,
                "count": count,
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": 0.0,
                "color": [0, 242, 254, int(150 + norm_val * 90)]
            })
            
    # 2. Middle Layer: Res 9
    data_res9 = []
    res9_height_map = {}
    max_res9 = float(res9_counter.most_common(1)[0][1]) if res9_counter else 1.0
    
    for cell, count in res9_counter.most_common(500):
        norm_val = round(count / max_res9, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res9_height_map[cell] = h_meters
        
        parent_res8 = h3.cell_to_parent(cell, 8)
        base_z = float(round(res8_height_map.get(parent_res8, 0.0), 2))
        
        poly3d = get_cell_polygon_3d(cell, base_z=base_z)
        if poly3d:
            data_res9.append({
                "hex": cell,
                "count": count,
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": base_z,
                "color": [127, 0, 255, int(170 + norm_val * 70)]
            })

    # 3. Peak Layer: Res 10
    data_res10 = []
    res10_height_map = {}
    max_res10 = float(res10_counter.most_common(1)[0][1]) if res10_counter else 1.0
    
    for cell, count in res10_counter.most_common(600):
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
            data_res10.append({
                "hex": cell,
                "count": count,
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": base_z,
                "color": [255, 215, 0, int(200 + norm_val * 55)]
            })
            
    # 4. Load 100 Popular Long Sub-Routes for High-Visibility 3D Floating Path Layer
    data_subroutes_100 = []
    start_end_points = []
    
    # Vibrant high-contrast neon palette with full opacity [r, g, b, 255]
    colors_neon = [
        [255, 8, 68, 255], [0, 242, 254, 255], [0, 230, 118, 255], [255, 215, 0, 255],
        [127, 0, 255, 255], [255, 145, 0, 255], [224, 64, 251, 255], [56, 189, 248, 255],
        [52, 211, 153, 255], [244, 63, 94, 255], [251, 191, 36, 255], [167, 139, 250, 255],
        [45, 212, 191, 255], [251, 113, 133, 255], [129, 140, 248, 255], [74, 222, 128, 255]
    ]
    
    if os.path.exists(INPUT_100_SUBROUTES_JSON):
        with open(INPUT_100_SUBROUTES_JSON, "r", encoding="utf-8") as f:
            payload = json.load(f)
            raw_100 = payload.get("master_top100", [])
            
        for idx, sr in enumerate(raw_100):
            coords = sr.get("cell_coordinates", [])
            if len(coords) < 2:
                continue
                
            path_3d = []
            color = colors_neon[idx % len(colors_neon)]
            
            for pt in coords:
                cell_id = pt.get("cell")
                # Ensure Z height is elevated ABOVE 3D extruded columns (min height 120m to 250m)
                if cell_id:
                    try:
                        res = h3.get_resolution(cell_id)
                        if res >= 8:
                            parent_res8 = h3.cell_to_parent(cell_id, 8)
                        else:
                            parent_res8 = cell_id
                    except Exception:
                        parent_res8 = cell_id
                    h_col = res8_height_map.get(parent_res8, 50.0)
                    z_elevated = max(180.0, h_col * 1.5 + 80.0)
                else:
                    z_elevated = 200.0
                    
                path_3d.append([round(pt["lng"], 6), round(pt["lat"], 6), round(z_elevated, 2)])
                
            data_subroutes_100.append({
                "rank": idx + 1,
                "support": sr["trip_support"],
                "speed": sr["avg_speed_kmh"],
                "distance": sr["avg_distance_km"],
                "duration": sr["avg_duration_sec"],
                "seq_len": sr["sequence_length"],
                "path": path_3d,
                "color": color
            })
            
            # Start & End markers for top 25 routes
            if idx < 25:
                start_end_points.append({
                    "rank": idx + 1,
                    "type": "Start",
                    "position": path_3d[0],
                    "color": [255, 255, 255, 255],
                    "radius": 15
                })
                start_end_points.append({
                    "rank": idx + 1,
                    "type": "End",
                    "position": path_3d[-1],
                    "color": color,
                    "radius": 18
                })
            
    print(f"  ✓ Processed {len(data_subroutes_100)} 100 Popular Long Sub-Routes for High-Visibility 3D PathLayer.")
    
    print("\n3. Building 3D Deck.gl Stepped Pyramid + 100 Sub-Routes App (`output/h3_3d_map.html`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D H3 Pyramid & 100 Popular Long Sub-Routes Map</title>
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
            background: rgba(15, 23, 42, 0.94);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 16px;
            padding: 1.5rem;
            width: 380px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.7);
            max-height: 90vh;
            overflow-y: auto;
        }}
        
        .panel-title {{
            font-size: 1.25rem;
            font-weight: 700;
            background: linear-gradient(135deg, #00f2fe, #ffd700);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }}

        .panel-sub {{
            font-size: 0.82rem;
            color: #94a3b8;
            margin-bottom: 1.2rem;
            line-height: 1.4;
        }}

        .preset-bar {{
            display: flex;
            gap: 8px;
            margin-bottom: 1rem;
        }}
        .preset-btn {{
            flex: 1;
            padding: 8px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.06);
            color: #fff;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }}
        .preset-btn.active {{
            background: linear-gradient(135deg, #ff0844, #7f00ff);
            border-color: #ff0844;
            box-shadow: 0 0 12px rgba(255, 8, 68, 0.5);
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
            background: rgba(255, 215, 0, 0.15);
            border: 1px solid rgba(255, 215, 0, 0.5);
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

        .filter-section {{
            margin-top: 12px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 12px;
        }}
        .filter-title {{
            font-size: 0.82rem;
            font-weight: 700;
            color: #ffd700;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }}
        .filter-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .dist-btn {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            color: #cbd5e1;
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .dist-btn.active {{
            background: linear-gradient(135deg, #00f2fe, #7f00ff);
            color: #fff;
            border-color: #00f2fe;
            box-shadow: 0 0 10px rgba(0, 242, 254, 0.4);
        }}

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
        <div class="panel-title">3D H3 Pyramid & 100 Long Sub-Routes</div>
        <div class="panel-sub">3D Stepped Hexagon Columns + 100 Mined Popular Corridors</div>

        <!-- Quick View Presets -->
        <div class="preset-bar">
            <button class="preset-btn active" id="preset-all" onclick="applyPreset('all')">🌐 Both (Hex + 100 Sub-Routes)</button>
            <button class="preset-btn" id="preset-subroutes" onclick="applyPreset('subroutes')">🔥 Focus 100 Sub-Routes</button>
        </div>

        <div class="layer-toggle highlight">
            <div class="layer-label">
                <div class="color-dot dot-subroutes"></div>
                🔥 100 Popular Long Sub-Routes (3D Paths)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-subroutes" checked onchange="updateLayers()">
                <span class="slider" style="background-color:#ffd700;"></span>
            </label>
        </div>

        <!-- Distance Threshold Filter -->
        <div class="filter-section">
            <div class="filter-title">
                <span>📏 Distance Length Filter:</span>
                <span id="active-filter-label" style="color:#00f2fe;">All 100</span>
            </div>
            <div class="filter-buttons">
                <button class="dist-btn active" onclick="setDistFilter(0, 'All 100', this)">All 100</button>
                <button class="dist-btn" onclick="setDistFilter(1.0, '≥ 1.0 km', this)">≥ 1 km</button>
                <button class="dist-btn" onclick="setDistFilter(3.0, '≥ 3.0 km', this)">≥ 3 km</button>
                <button class="dist-btn" onclick="setDistFilter(5.0, '≥ 5.0 km', this)">≥ 5 km</button>
                <button class="dist-btn" onclick="setDistFilter(10.0, '≥ 10 km', this)">≥ 10 km</button>
                <button class="dist-btn" onclick="setDistFilter(20.0, '≥ 20 km', this)">≥ 20 km</button>
                <button class="dist-btn" onclick="setDistFilter(40.0, '≥ 40 km', this)">≥ 40 km</button>
            </div>
        </div>

        <div class="layer-toggle" style="margin-top:12px;">
            <div class="layer-label">
                <div class="color-dot dot-res8"></div>
                Res 8 Base Layer (Z = 0)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res8" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res9"></div>
                Res 9 Middle (Stacked on Res 8)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res9" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res10"></div>
                Res 10 Peak (Stacked on Res 9)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res10" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="slider-container">
            <div class="slider-title">
                <span>3D Column Height Scale</span>
                <span id="scale-val">1.0x</span>
            </div>
            <input type="range" id="height-scale" min="0.1" max="3.0" step="0.1" value="1.0" oninput="updateHeightScale(this.value)">
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Controls:</strong><br>
            • <strong>Right Click / Ctrl+Drag:</strong> Tilt Pitch & Rotate Camera.<br>
            • <strong>Scroll:</strong> Zoom in/out.<br>
            • <strong>Hover:</strong> Inspect Hexagons or Sub-Route Corridors.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8)};
        const dataRes9 = {json.dumps(data_res9)};
        const dataRes10 = {json.dumps(data_res10)};
        const dataSubroutes100 = {json.dumps(data_subroutes_100)};
        const dataStartEndPoints = {json.dumps(start_end_points)};

        let currentScale = 1.0;
        let minDistanceFilter = 0.0;

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                
                if (info.object.rank) {{
                    tooltip.innerHTML = `
                        <div style="color:#ffd700; font-weight:700; font-size:1rem;">🔥 Popular Long Sub-Route #${{info.object.rank}}</div>
                        <div>Distance Length: <strong>${{info.object.distance}} km</strong></div>
                        <div>Trips Volume: <strong>${{info.object.support.toLocaleString()}} trips</strong></div>
                        <div>Avg Speed: <strong>${{info.object.speed}} km/h</strong></div>
                        <div>Avg Duration: <strong>${{(info.object.duration / 60.0).toFixed(1)}} min</strong></div>
                        <div style="font-size:0.75rem; color:#94a3b8;">H3 Sequence: ${{info.object.seq_len}} cells</div>
                    `;
                }} else {{
                    tooltip.innerHTML = `
                        <div style="color:#00f2fe; font-weight:700;">H3 Cell ID: ${{info.object.hex}}</div>
                        <div>Visits: <strong>${{info.object.count.toLocaleString()}}</strong></div>
                        <div>Norm Height: <strong>${{info.object.norm}} / 1.00</strong></div>
                        <div>Current Base Z: <strong>${{(info.object.base_z * currentScale).toFixed(1)}}m</strong></div>
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

        function getFilteredSubroutes() {{
            if (minDistanceFilter <= 0) return dataSubroutes100;
            return dataSubroutes100.filter(sr => sr.distance >= minDistanceFilter);
        }}

        function getLayers() {{
            const layers = [];

            // Layer 1: Res 8 Base Layer (Z = 0)
            if (document.getElementById('check-res8').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-polygon-res8',
                    data: dataRes8,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon,
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [0, 242, 254, 120],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 2: Res 9 Middle Layer (Base Z = parent_z * currentScale)
            if (document.getElementById('check-res9').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-polygon-res9',
                    data: dataRes9,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 120],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 3: Res 10 Peak Layer (Base Z = parents_z * currentScale)
            if (document.getElementById('check-res10').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-polygon-res10',
                    data: dataRes10,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 160],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 4: 100 Popular Long Sub-Routes 3D Floating Path Layer
            if (document.getElementById('check-subroutes').checked) {{
                const filteredPaths = getFilteredSubroutes();
                layers.push(new deck.PathLayer({{
                    id: 'layer-path-subroutes',
                    data: filteredPaths,
                    pickable: true,
                    widthScale: 1,
                    widthMinPixels: 6,
                    getPath: d => d.path.map(pt => [pt[0], pt[1], pt[2] * (currentScale > 0.5 ? 1.0 : 0.2)]),
                    getColor: d => d.color,
                    getWidth: d => d.rank <= 5 ? 16 : d.rank <= 25 ? 10 : 6,
                    onHover: updateTooltip
                }}));

                // Layer 5: Start & End 3D Sphere Markers
                layers.push(new deck.PointCloudLayer({{
                    id: 'layer-pointcloud-startend',
                    data: dataStartEndPoints,
                    pickable: true,
                    pointRadiusUnits: 'pixels',
                    getRadius: d => d.radius,
                    getPosition: d => [d.position[0], d.position[1], d.position[2] * (currentScale > 0.5 ? 1.0 : 0.2)],
                    getColor: d => d.color,
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
                zoom: 12.8,
                pitch: 55,
                bearing: 20
            }},
            controller: true,
            layers: getLayers()
        }});

        function updateLayers() {{
            deckgl.setProps({{ layers: getLayers() }});
        }}

        function applyPreset(mode) {{
            document.getElementById('preset-all').classList.remove('active');
            document.getElementById('preset-subroutes').classList.remove('active');

            if (mode === 'subroutes') {{
                document.getElementById('preset-subroutes').classList.add('active');
                document.getElementById('check-res8').checked = false;
                document.getElementById('check-res9').checked = false;
                document.getElementById('check-res10').checked = false;
                document.getElementById('check-subroutes').checked = true;
            }} else {{
                document.getElementById('preset-all').classList.add('active');
                document.getElementById('check-res8').checked = true;
                document.getElementById('check-res9').checked = true;
                document.getElementById('check-res10').checked = true;
                document.getElementById('check-subroutes').checked = true;
            }}
            updateLayers();
        }}

        function setDistFilter(minKm, labelText, btnElem) {{
            minDistanceFilter = minKm;
            document.getElementById('active-filter-label').innerText = labelText;
            document.querySelectorAll('.dist-btn').forEach(btn => btn.classList.remove('active'));
            btnElem.classList.add('active');
            updateLayers();
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

    with open(OUTPUT_3D_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Pyramid + 100 Popular Long Sub-Routes Map to {OUTPUT_3D_MAP}")

if __name__ == "__main__":
    generate_3d_map()
