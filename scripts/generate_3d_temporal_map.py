"""
Porto Taxi Trajectory Project – 3D Temporal Dynamic Mountain Ridge Engine
===========================================================================
Generates `output/h3_3d_temporal_map.html` with:
- 🌅 Morning Rush (07:00 - 10:00) 3D Corridors
- 🌇 Evening Rush (16:00 - 19:00) 3D Corridors
- 🌙 Nightlife Dynamics (23:00 - 04:00) 3D Corridors
Features real-time Time Window Selector Buttons, 3D Stepped Hexagon Pyramids,
and 1.0x to 5.0x Height Slider.
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

INPUT_TEMPORAL_JSON = "output/temporal_subroutes.json"
INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_TEMPORAL_MAP = "output/h3_3d_temporal_map.html"


def get_cell_polygon_3d(cell, base_z):
    try:
        boundary = h3.cell_to_boundary(cell)
        return [[round(pt[1], 6), round(pt[0], 6), round(base_z, 2)] for pt in boundary]
    except Exception:
        return None


def generate_3d_temporal_map():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Temporal Dynamic Ridge Engine      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    if not os.path.exists(INPUT_TEMPORAL_JSON):
        print(f"❌ Error: {INPUT_TEMPORAL_JSON} not found.")
        return
        
    with open(INPUT_TEMPORAL_JSON, "r", encoding="utf-8") as f:
        temporal_subroutes = json.load(f)
        
    print("\n1. Loading H3-encoded dataset for base density...")
    table = pq.read_table(
        INPUT_H3_PARQUET,
        columns=["h3_res8", "h3_res9", "h3_res10"]
    )
    df = table.to_pandas()
    
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
            
    UNIT_METERS = 180.0
    
    # Res 8
    data_res8 = []
    res8_height_map = {}
    max_res8 = float(res8_counter.most_common(1)[0][1]) if res8_counter else 1.0
    for cell, count in res8_counter.most_common(200):
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
                "color": [0, 242, 254, int(140 + norm_val * 90)]
            })
            
    # Res 9
    data_res9 = []
    res9_height_map = {}
    max_res9 = float(res9_counter.most_common(1)[0][1]) if res9_counter else 1.0
    for cell, count in res9_counter.most_common(350):
        norm_val = round(count / max_res9, 4)
        h_meters = float(round(norm_val * UNIT_METERS, 2))
        res9_height_map[cell] = h_meters
        parent_res8 = h3.cell_to_parent(cell, 8)
        base_z = res8_height_map.get(parent_res8, 0.0)
        poly3d = get_cell_polygon_3d(cell, base_z=base_z)
        if poly3d:
            data_res9.append({
                "hex": cell,
                "count": count,
                "norm": norm_val,
                "polygon": poly3d,
                "height": h_meters,
                "base_z": base_z,
                "color": [127, 0, 255, int(160 + norm_val * 80)]
            })

    # Res 10
    data_res10 = []
    res10_height_map = {}
    max_res10 = float(res10_counter.most_common(1)[0][1]) if res10_counter else 1.0
    for cell, count in res10_counter.most_common(500):
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
                "color": [255, 215, 0, int(180 + norm_val * 65)]
            })
            
    # Process Temporal Sub-Routes
    temporal_paths = {"morning": [], "evening": [], "night": []}
    colors_window = {
        "morning": [0, 242, 254],   # Cyan for Morning
        "evening": [255, 145, 0],   # Orange for Evening
        "night": [255, 8, 68]       # Crimson for Night
    }
    
    for w in ["morning", "evening", "night"]:
        sub_list = temporal_subroutes.get(w, [])
        for idx, sr in enumerate(sub_list):
            coords = sr.get("cell_coordinates", [])
            if len(coords) < 2:
                continue
                
            path_3d = []
            for pt in coords:
                cell_id = pt["cell"]
                parent_res8 = h3.cell_to_parent(cell_id, 8)
                z_offset = res8_height_map.get(parent_res8, 0.0) + res9_height_map.get(cell_id, 40.0)
                path_3d.append([round(pt["lng"], 6), round(pt["lat"], 6), round(z_offset + 35.0, 2)])
                
            temporal_paths[w].append({
                "rank": idx + 1,
                "window": w,
                "support": sr["trip_support"],
                "speed": sr["avg_speed_kmh"],
                "duration": sr["avg_duration_sec"],
                "path": path_3d,
                "color": colors_window[w]
            })
            
    print(f"\n2. Processed 3D Temporal Paths: Morning ({len(temporal_paths['morning'])}), Evening ({len(temporal_paths['evening'])}), Night ({len(temporal_paths['night'])}).")
    
    print(f"\n3. Building 3D Temporal Dynamic Web App (`{OUTPUT_TEMPORAL_MAP}`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D Temporal Dynamic Mining Dashboard</title>
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
            width: 370px;
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

        .window-selector {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
            margin-bottom: 1.2rem;
            background: rgba(0,0,0,0.3);
            padding: 4px;
            border-radius: 10px;
        }}

        .win-btn {{
            padding: 10px 0;
            border: none;
            border-radius: 8px;
            background: transparent;
            color: #94a3b8;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }}

        .win-btn.active.morning {{
            background: linear-gradient(135deg, #00f2fe, #38bdf8);
            color: #0b0f19;
            box-shadow: 0 2px 12px rgba(0, 242, 254, 0.4);
        }}

        .win-btn.active.evening {{
            background: linear-gradient(135deg, #ff9100, #fbbf24);
            color: #0b0f19;
            box-shadow: 0 2px 12px rgba(255, 145, 0, 0.4);
        }}

        .win-btn.active.night {{
            background: linear-gradient(135deg, #ff0844, #e040fb);
            color: #fff;
            box-shadow: 0 2px 12px rgba(255, 8, 68, 0.4);
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
        <div class="panel-title">3D Temporal Dynamic Mining</div>
        <div class="panel-sub">Select Time Window to Morph 3D Traffic Corridors Across Porto</div>

        <div style="font-size:0.8rem; font-weight:600; color:#cbd5e1; margin-bottom:6px;">SELECT TIME WINDOW:</div>
        <div class="window-selector">
            <button class="win-btn active morning" id="btn-morning" onclick="setWindow('morning')">
                <span>🌅 Morning</span>
                <span style="font-size:0.7rem; opacity:0.8;">07:00–10:00</span>
            </button>
            <button class="win-btn evening" id="btn-evening" onclick="setWindow('evening')">
                <span>🌇 Evening</span>
                <span style="font-size:0.7rem; opacity:0.8;">16:00–19:00</span>
            </button>
            <button class="win-btn night" id="btn-night" onclick="setWindow('night')">
                <span>🌙 Night</span>
                <span style="font-size:0.7rem; opacity:0.8;">23:00–04:00</span>
            </button>
        </div>

        <div class="layer-toggle">
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
                <span>3D Height Scale (1x to 5x)</span>
                <span id="scale-val">1.0x</span>
            </div>
            <input type="range" id="height-scale" min="1.0" max="5.0" step="0.1" value="1.0" oninput="updateHeightScale(this.value)">
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Controls:</strong><br>
            • <strong>Click Time Window Buttons:</strong> Watch 3D corridors morph!<br>
            • <strong>Ctrl + Drag / Right Click:</strong> Tilt Pitch & Rotate Camera.<br>
            • <strong>Hover:</strong> Inspect Time Window Support & Speeds.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8)};
        const dataRes9 = {json.dumps(data_res9)};
        const dataRes10 = {json.dumps(data_res10)};
        const temporalPaths = {json.dumps(temporal_paths)};

        let currentWindow = 'morning';
        let currentScale = 1.0;

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                
                if (info.object.window) {{
                    const wName = info.object.window.toUpperCase();
                    tooltip.innerHTML = `
                        <div style="color:#00f2fe; font-weight:700; font-size:1rem;">⏰ ${{wName}} CORRIDOR #${{info.object.rank}}</div>
                        <div>Trips Support: <strong>${{info.object.support.toLocaleString()}}</strong></div>
                        <div>Avg Speed: <strong>${{info.object.speed}} km/h</strong></div>
                        <div>Avg Duration: <strong>${{(info.object.duration / 60.0).toFixed(1)}} min</strong></div>
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

        function getLayers() {{
            const layers = [];

            // Res 8 Base Layer
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

            // Res 9 Middle Layer
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

            // Res 10 Peak Layer
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

            // Active Temporal Window 3D Path Layer
            const activePaths = temporalPaths[currentWindow] || [];
            layers.push(new deck.PathLayer({{
                id: 'layer-path-temporal-' + currentWindow,
                data: activePaths,
                pickable: true,
                widthScale: 1,
                widthMinPixels: 5,
                getPath: d => d.path.map(pt => [pt[0], pt[1], pt[2] * currentScale]),
                getColor: d => d.color,
                getWidth: d => d.rank <= 3 ? 14 : d.rank <= 6 ? 9 : 6,
                onHover: updateTooltip
            }}));

            return layers;
        }}

        const deckgl = new deck.DeckGL({{
            container: 'container',
            mapStyle: darkTileStyle,
            initialViewState: {{
                longitude: -8.6291,
                latitude: 41.1579,
                zoom: 13.0,
                pitch: 58,
                bearing: 25
            }},
            controller: true,
            layers: getLayers()
        }});

        function updateLayers() {{
            deckgl.setProps({{ layers: getLayers() }});
        }}

        function setWindow(w) {{
            currentWindow = w;
            document.querySelectorAll('.win-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + w).classList.add('active');
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

    with open(OUTPUT_TEMPORAL_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Temporal Dynamic Map to {OUTPUT_TEMPORAL_MAP}")

if __name__ == "__main__":
    generate_3d_temporal_map()
