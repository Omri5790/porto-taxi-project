"""
Porto Taxi Trajectory Project – 3D Cumulative Stepped Pyramid Engine
======================================================================
Generates `output/h3_3d_map.html` with TRUE 3D Cumulative Step Stacking:
- Res 8 (Base Layer): Base elevation Z = 0.
- Res 9 (Middle Layer): Base elevation Z = Res 8 Parent Height (sits on top of Res 8).
- Res 10 (Peak Layer): Base elevation Z = Res 8 Height + Res 9 Parent Height (sits on top of Res 9).
Includes working real-time Deck.gl elevationScale slider (1.0 to 5.0).
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
OUTPUT_3D_MAP = "output/h3_3d_map.html"


def get_cell_polygon_3d(cell, base_z):
    try:
        boundary = h3.cell_to_boundary(cell)
        # Convert (lat, lng) -> [lng, lat, base_z] for 3D Deck.gl GeoJSON
        return [[round(pt[1], 6), round(pt[0], 6), round(base_z, 1)] for pt in boundary]
    except Exception:
        return None


def generate_3d_map():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Cumulative Stepped Pyramid Engine   ║")
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
    
    print("\n2. Computing Cumulative Spatial Step Elevations...")
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
            
    # Unit scale in meters for 1.0 normalized value
    UNIT_METERS = 200.0
    
    # 1. Base Layer: Res 8 (Neighborhoods - Cyan Base at Z = 0)
    data_res8 = []
    res8_height_map = {}
    max_res8 = float(res8_counter.most_common(1)[0][1]) if res8_counter else 1.0
    
    for cell, count in res8_counter.most_common(200):
        norm_val = round(count / max_res8, 4)  # 0.0 to 1.0
        h_meters = float(round(norm_val * UNIT_METERS, 1))
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
            
    # 2. Middle Layer: Res 9 (Streets - Electric Violet stacked at Z = Res 8 Parent Height)
    data_res9 = []
    res9_height_map = {}
    max_res9 = float(res9_counter.most_common(1)[0][1]) if res9_counter else 1.0
    
    for cell, count in res9_counter.most_common(350):
        norm_val = round(count / max_res9, 4)  # 0.0 to 1.0
        h_meters = float(round(norm_val * UNIT_METERS, 1))
        res9_height_map[cell] = h_meters
        
        # Find parent Res 8 cell height
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
                "color": [127, 0, 255, int(180 + norm_val * 75)]
            })

    # 3. Peak Layer: Res 10 (Intersections - Glowing Gold stacked at Z = Res 8 Base + Res 9 Middle)
    data_res10 = []
    max_res10 = float(res10_counter.most_common(1)[0][1]) if res10_counter else 1.0
    
    for cell, count in res10_counter.most_common(500):
        norm_val = round(count / max_res10, 4)  # 0.0 to 1.0
        h_meters = float(round(norm_val * UNIT_METERS, 1))
        
        # Find parent Res 9 and grandparent Res 8 height
        parent_res9 = h3.cell_to_parent(cell, 9)
        grandparent_res8 = h3.cell_to_parent(cell, 8)
        
        z_res8 = res8_height_map.get(grandparent_res8, 0.0)
        z_res9 = res9_height_map.get(parent_res9, 0.0)
        base_z = float(round(z_res8 + z_res9, 1))
        
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
            
    print(f"  ✓ Processed Res 8 (Base Z=0), Res 9 (Stacked Z=Res8 Parent), Res 10 (Stacked Z=Res8+Res9 Parents).")
    
    print("\n3. Building 3D Deck.gl Cumulative Stepped App (`output/h3_3d_map.html`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D Cumulative Stepped H3 Hexagon Pyramid</title>
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
            width: 350px;
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
        <div class="panel-title">3D Cumulative Stepped Pyramid</div>
        <div class="panel-sub">True 3D Step Stacking: Res 8 Base ➔ Res 9 Middle ➔ Res 10 Pinnacle</div>

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
                <span>3D Height Extrusion Multiplier</span>
                <span id="scale-val">1.0x</span>
            </div>
            <input type="range" id="height-scale" min="1.0" max="5.0" step="0.1" value="1.0" oninput="updateHeightScale(this.value)">
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Camera Controls:</strong><br>
            • <strong>Ctrl + Drag / Right Click:</strong> Tilt Pitch & Rotate Camera.<br>
            • <strong>Scroll:</strong> Zoom in/out.<br>
            • <strong>Hover Hexagon:</strong> Inspect Cell ID, Visits & Base Height.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8)};
        const dataRes9 = {json.dumps(data_res9)};
        const dataRes10 = {json.dumps(data_res10)};

        let currentScale = 1.0;

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                tooltip.innerHTML = `
                    <div style="color:#00f2fe; font-weight:700;">H3 Cell ID: ${{info.object.hex}}</div>
                    <div>Visits: <strong>${{info.object.count.toLocaleString()}}</strong></div>
                    <div>Norm Height: <strong>${{info.object.norm}} / 1.00</strong></div>
                    <div>Base Offset Z: <strong>${{info.object.base_z}}m</strong></div>
                `;
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

            // Layer 2: Res 9 Middle Layer (Base Z = Res 8 Parent Height)
            if (document.getElementById('check-res9').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-polygon-res9',
                    data: dataRes9,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon,
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 120],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 3: Res 10 Peak Layer (Base Z = Res 8 + Res 9 Parents Height)
            if (document.getElementById('check-res10').checked) {{
                layers.push(new deck.PolygonLayer({{
                    id: 'layer-polygon-res10',
                    data: dataRes10,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    elevationScale: currentScale,
                    getPolygon: d => d.polygon,
                    getElevation: d => d.height,
                    getFillColor: d => d.color,
                    getLineColor: [255, 255, 255, 160],
                    lineWidthMinPixels: 1,
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
                pitch: 58,
                bearing: 25
            }},
            controller: true,
            layers: getLayers()
        }});

        function updateLayers() {{
            deckgl.setProps({{ layers: getLayers() }});
        }}

        function updateHeightScale(val) {{
            currentScale = parseFloat(val);
            document.getElementById('scale-val').innerText = parseFloat(val).toFixed(1) + 'x';
            updateLayers();
        }}
    </script>
</body>
</html>
"""

    with open(OUTPUT_3D_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Cumulative Stepped Map to {OUTPUT_3D_MAP}")

if __name__ == "__main__":
    generate_3d_map()
