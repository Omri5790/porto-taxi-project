"""
Porto Taxi Trajectory Project – 3D Deck.gl H3 Spatial Elevation Map Generator
=============================================================================
This script loads `output/h3_encoded_trips.parquet`, computes visit frequencies
for H3 Resolution 8, Resolution 9, and Resolution 10, and generates a standalone,
GPU-accelerated 3D Interactive Deck.gl H3 Elevation Map (`output/h3_3d_map.html`).
Features:
- Extruded 3D Hexagonal Columns (Height = Taxi Trip Frequency).
- Glowing H3 Heatmap Topography.
- Full 3D Camera Controls (Pitch, Tilt, Rotation, Zoom).
- Resolution Switcher (Res 8 Neighborhoods, Res 9 Streets, Res 10 Intersections).
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


def generate_3d_map():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – 3D Deck.gl H3 Elevation Visualizer     ║")
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
            
    data_res8 = [{"hex": cell, "count": count} for cell, count in res8_counter.most_common(200)]
    data_res9 = [{"hex": cell, "count": count} for cell, count in res9_counter.most_common(400)]
    data_res10 = [{"hex": cell, "count": count} for cell, count in res10_counter.most_common(600)]
    
    print(f"  ✓ Processed Res 8 ({len(res8_counter):,} cells), Res 9 ({len(res9_counter):,} cells), Res 10 ({len(res10_counter):,} cells).")
    
    print("\n3. Building Standalone 3D Deck.gl H3 Elevation Web App (`output/h3_3d_map.html`)...")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Trajectory – 3D H3 Spatial Elevation Map</title>
    <!-- Deck.gl & MapLibre GL -->
    <script src="https://unpkg.com/deck.gl@latest/dist.min.js"></script>
    <script src="https://unpkg.com/maplibre-gl@3.0.0/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.0.0/dist/maplibre-gl.css" rel="stylesheet" />
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: #0b0f19;
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
            background: rgba(18, 26, 43, 0.85);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 1.5rem;
            width: 320px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }}
        
        .panel-title {{
            font-size: 1.25rem;
            font-weight: 700;
            background: linear-gradient(135deg, #00f2fe, #7f00ff);
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

        .btn-group {{
            display: flex;
            gap: 6px;
            margin-bottom: 1rem;
            background: rgba(0,0,0,0.3);
            padding: 4px;
            border-radius: 10px;
        }}

        .res-btn {{
            flex: 1;
            padding: 8px 0;
            border: none;
            border-radius: 6px;
            background: transparent;
            color: #94a3b8;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .res-btn.active {{
            background: linear-gradient(135deg, #00f2fe, #4facfe);
            color: #0b0f19;
            box-shadow: 0 2px 10px rgba(0, 242, 254, 0.3);
        }}

        .instruction-box {{
            background: rgba(0, 242, 254, 0.08);
            border-left: 3px solid #00f2fe;
            padding: 0.75rem;
            border-radius: 0 8px 8px 0;
            font-size: 0.8rem;
            color: #cbd5e1;
            line-height: 1.4;
        }}

        .tooltip-custom {{
            position: absolute;
            z-index: 100;
            pointer-events: none;
            background: rgba(11, 15, 25, 0.9);
            border: 1px solid #00f2fe;
            border-radius: 8px;
            padding: 10px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #fff;
            box-shadow: 0 10px 20px rgba(0,0,0,0.6);
            display: none;
        }}
    </style>
</head>
<body>
    <div id="container"></div>

    <div class="control-panel">
        <div class="panel-title">Porto 3D H3 Elevation Topography</div>
        <div class="panel-sub">1.62M Taxi Trips Encoded into Extruded 3D Hexagonal Columns</div>

        <div style="font-size:0.8rem; font-weight:600; color:#cbd5e1; margin-bottom:6px;">SELECT H3 RESOLUTION:</div>
        <div class="btn-group">
            <button class="res-btn active" id="btn-res8" onclick="setResolution(8)">Res 8 (~0.73km²)</button>
            <button class="res-btn" id="btn-res9" onclick="setResolution(9)">Res 9 (~0.10km²)</button>
            <button class="res-btn" id="btn-res10" onclick="setResolution(10)">Res 10 (~66m)</button>
        </div>

        <div class="instruction-box">
            <strong>🖱️ 3D Controls:</strong><br>
            • <strong>Ctrl + Drag / Right Click:</strong> Tilt Pitch & Rotate 3D Camera.<br>
            • <strong>Scroll:</strong> Zoom in/out.<br>
            • <strong>Hover:</strong> Inspect H3 Cell ID & Visit Counts.
        </div>
    </div>

    <div id="tooltip" class="tooltip-custom"></div>

    <script>
        const dataRes8 = {json.dumps(data_res8)};
        const dataRes9 = {json.dumps(data_res9)};
        const dataRes10 = {json.dumps(data_res10)};

        let currentRes = 8;
        let deckgl;

        const maxCountRes8 = dataRes8[0] ? dataRes8[0].count : 1;
        const maxCountRes9 = dataRes9[0] ? dataRes9[0].count : 1;
        const maxCountRes10 = dataRes10[0] ? dataRes10[0].count : 1;

        function getColor(count, maxCount) {{
            const ratio = Math.min(1.0, count / maxCount);
            if (ratio < 0.25) return [0, 242, 254, 200];    // Cyan
            if (ratio < 0.60) return [127, 0, 255, 220];   // Electric Violet
            if (ratio < 0.85) return [255, 8, 68, 230];    // Crimson Red
            return [255, 215, 0, 255];                     // Glowing Gold
        }}

        function getLayer(res) {{
            let dataset, maxCount, scale;
            if (res === 8) {{ dataset = dataRes8; maxCount = maxCountRes8; scale = 0.08; }}
            else if (res === 9) {{ dataset = dataRes9; maxCount = maxCountRes9; scale = 0.15; }}
            else {{ dataset = dataRes10; maxCount = maxCountRes10; scale = 0.40; }}

            return new deck.H3HexagonLayer({{
                id: 'h3-3d-layer-' + res,
                data: dataset,
                pickable: true,
                wireframe: true,
                filled: true,
                extruded: true,
                elevationScale: scale,
                getHexagon: d => d.hex,
                getElevation: d => d.count,
                getFillColor: d => getColor(d.count, maxCount),
                getLineColor: [255, 255, 255, 80],
                lineWidthMinPixels: 1,
                onHover: updateTooltip
            }});
        }}

        function updateTooltip(info) {{
            const tooltip = document.getElementById('tooltip');
            if (info.object) {{
                tooltip.style.left = (info.x + 15) + 'px';
                tooltip.style.top = (info.y + 15) + 'px';
                tooltip.style.display = 'block';
                tooltip.innerHTML = `
                    <div style="color:#00f2fe; font-weight:700;">H3 Cell ID: ${{info.object.hex}}</div>
                    <div>Visits: <strong>${{info.object.count.toLocaleString()}}</strong></div>
                    <div style="font-size:0.75rem; color:#94a3b8;">Resolution: ${{currentRes}}</div>
                `;
            }} else {{
                tooltip.style.display = 'none';
            }}
        }}

        function setResolution(res) {{
            currentRes = res;
            document.querySelectorAll('.res-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-res' + res).classList.add('active');

            deckgl.setProps({{
                layers: [getLayer(res)]
            }});
        }}

        // Initialize Deck.gl
        deckgl = new deck.DeckGL({{
            container: 'container',
            mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/json',
            initialViewState: {{
                longitude: -8.6291,
                latitude: 41.1579,
                zoom: 12.5,
                pitch: 52,
                bearing: 25
            }},
            controller: true,
            layers: [getLayer(8)]
        }});
    </script>
</body>
</html>
"""

    with open(OUTPUT_3D_MAP, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved 3D Deck.gl Map to {OUTPUT_3D_MAP}")

if __name__ == "__main__":
    generate_3d_map()
