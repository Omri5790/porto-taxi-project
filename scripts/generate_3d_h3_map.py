"""
Porto Taxi Trajectory Project – 3D Deck.gl Stacked H3 Hexagon Elevation Engine
==============================================================================
This script generates a 3D Stacked Hexagon Pyramid Map (`output/h3_3d_map.html`).
- Base Layer (Bottom): Res 8 Hexagons (~0.73 km²) – Wide Cyan Base.
- Middle Layer (Stacked): Res 9 Hexagons (~0.10 km²) – Medium Violet Core.
- Top Layer (Peak): Res 10 Hexagons (~66m edge) – Glowing Gold Pinnacle.
Columns extrude vertically proportionally to trip frequency.
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

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_3D_MAP = "output/h3_3d_map.html"


def generate_3d_stacked_map():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Stacked H3 Hexagon Pyramid Engine   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    if not os.path.exists(INPUT_H3_PARQUET):
        print(f"❌ Error: {INPUT_H3_PARQUET} not found.")
        return
        
    print(f"\n1. Loading H3-encoded dataset from {INPUT_H3_PARQUET}...")
    table = pq.read_table(
        INPUT_H3_PARQUET,
        columns=["h3_res8", "h3_res9", "h3_res10"]
    )
    df = table.to_pandas()
    total_trips = len(df)
    print(f"  ✓ Loaded {total_trips:,} trips.")
    
    print("\n2. Computing Frequency Topography for Res 8, Res 9, and Res 10...")
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
            
    data_res8 = [{"hex": cell, "count": count} for cell, count in res8_counter.most_common(250)]
    data_res9 = [{"hex": cell, "count": count} for cell, count in res9_counter.most_common(400)]
    data_res10 = [{"hex": cell, "count": count} for cell, count in res10_counter.most_common(600)]
    
    print(f"  ✓ Processed Res 8 ({len(data_res8):,} active cells), Res 9 ({len(data_res9):,} cells), Res 10 ({len(data_res10):,} cells).")
    
    print("\n3. Building 3D Deck.gl Stacked Hexagon Pyramid Map (`output/h3_3d_map.html`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D Stacked H3 Hexagon Pyramid</title>
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
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 1.5rem;
            width: 340px;
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
            border: 1px solid rgba(255,255,255,0.06);
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
            background: rgba(11, 15, 25, 0.92);
            border: 1px solid #00f2fe;
            border-radius: 8px;
            padding: 10px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #fff;
            box-shadow: 0 10px 25px rgba(0,0,0,0.7);
            display: none;
        }}
    </style>
</head>
<body>
    <div id="container"></div>

    <div class="control-panel">
        <div class="panel-title">3D Stacked H3 Hexagon Pyramid</div>
        <div class="panel-sub">Porto Taxi Density Topography • Extruded 3D Multi-Layer Hexagonal Columns</div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res8"></div>
                Res 8 (Base Layer ~0.73km²)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res8" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res9"></div>
                Res 9 (Middle Layer ~0.10km²)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res9" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="layer-toggle">
            <div class="layer-label">
                <div class="color-dot dot-res10"></div>
                Res 10 (Peak Layer ~66m)
            </div>
            <label class="switch">
                <input type="checkbox" id="check-res10" checked onchange="updateLayers()">
                <span class="slider"></span>
            </label>
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Camera Controls:</strong><br>
            • <strong>Ctrl + Drag / Right Click:</strong> Tilt Pitch & Rotate Camera.<br>
            • <strong>Scroll:</strong> Zoom in/out.<br>
            • <strong>Hover Hexagon:</strong> Inspect H3 Cell ID & Visit Counts.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8)};
        const dataRes9 = {json.dumps(data_res9)};
        const dataRes10 = {json.dumps(data_res10)};

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                tooltip.innerHTML = `
                    <div style="color:#00f2fe; font-weight:700;">H3 Cell ID: ${{info.object.hex}}</div>
                    <div>Visits: <strong>${{info.object.count.toLocaleString()}}</strong></div>
                `;
            }} else {{
                tooltip.style.display = 'none';
            }}
        }}

        function getLayers() {{
            const layers = [];

            // Layer 1: Res 8 Base Layer (Cyan - Wide Footprint)
            if (document.getElementById('check-res8').checked) {{
                layers.push(new deck.H3HexagonLayer({{
                    id: 'layer-h3-res8',
                    data: dataRes8,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    coverage: 0.92,
                    elevationScale: 0.12,
                    getHexagon: d => d.hex,
                    getElevation: d => d.count,
                    getFillColor: [0, 242, 254, 160],
                    getLineColor: [0, 242, 254, 80],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 2: Res 9 Middle Layer (Electric Violet - Inset Footprint Stacked Above)
            if (document.getElementById('check-res9').checked) {{
                layers.push(new deck.H3HexagonLayer({{
                    id: 'layer-h3-res9',
                    data: dataRes9,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    coverage: 0.82,
                    elevationScale: 0.25,
                    getHexagon: d => d.hex,
                    getElevation: d => d.count,
                    getFillColor: [127, 0, 255, 210],
                    getLineColor: [255, 255, 255, 100],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            // Layer 3: Res 10 Top Layer (Glowing Gold Pinnacle)
            if (document.getElementById('check-res10').checked) {{
                layers.push(new deck.H3HexagonLayer({{
                    id: 'layer-h3-res10',
                    data: dataRes10,
                    pickable: true,
                    wireframe: true,
                    filled: true,
                    extruded: true,
                    coverage: 0.68,
                    elevationScale: 0.50,
                    getHexagon: d => d.hex,
                    getElevation: d => d.count,
                    getFillColor: [255, 215, 0, 240],
                    getLineColor: [255, 255, 255, 120],
                    lineWidthMinPixels: 1,
                    onHover: updateTooltip
                }}));
            }}

            return layers;
        }}

        const deckgl = new deck.DeckGL({{
            container: 'container',
            mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/json',
            initialViewState: {{
                longitude: -8.6291,
                latitude: 41.1579,
                zoom: 12.8,
                pitch: 58,
                bearing: 30
            }},
            controller: true,
            layers: getLayers()
        }});

        function updateLayers() {{
            deckgl.setProps({{ layers: getLayers() }});
        }}
    </script>
</body>
</html>
"""

    with open(OUTPUT_3D_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Deck.gl Stacked Map to {OUTPUT_3D_MAP}")

if __name__ == "__main__":
    generate_3d_stacked_map()
