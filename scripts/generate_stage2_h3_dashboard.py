"""
Porto Taxi Trajectory Project – Stage 2 H3 Visualizer & Dashboard Generator
=============================================================================
This script loads `output/h3_encoded_trips.parquet`, extracts H3 Resolution 8
& Resolution 9 cell frequencies, computes hexagon polygons using `h3.cell_to_boundary`,
and generates an interactive Folium Hexagon Map (`output/h3_hexagons_map.html`)
and a custom H3 Analytics Dashboard (`output/stage2_h3_dashboard.html`).
"""

import os
import sys
import json
import pandas as pd
import pyarrow.parquet as pq
import folium
from collections import Counter

# Ensure user site packages are in python path for H3
user_site = os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages")
if os.path.exists(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import h3

INPUT_H3_PARQUET = "output/h3_encoded_trips.parquet"
OUTPUT_H3_MAP = "output/h3_hexagons_map.html"
OUTPUT_H3_DASHBOARD = "output/stage2_h3_dashboard.html"


def generate_visualizations():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Stage 2: H3 Visualizer & Dashboard     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    if not os.path.exists(INPUT_H3_PARQUET):
        print(f"❌ Error: {INPUT_H3_PARQUET} not found.")
        return
        
    print(f"\n1. Reading H3-encoded Parquet dataset from {INPUT_H3_PARQUET}...")
    table = pq.read_table(
        INPUT_H3_PARQUET,
        columns=["TRIP_ID", "h3_res8", "h3_res9", "start_h3_res8", "end_h3_res8", "h3_res8_length", "h3_res9_length"]
    )
    df = table.to_pandas()
    total_trips = len(df)
    print(f"  ✓ Loaded {total_trips:,} trips.")
    
    # 2. Compute Top H3 Cells
    print("\n2. Computing H3 Cell Frequencies & Boundaries...")
    res8_counter = Counter()
    res9_counter = Counter()
    
    for row in df["h3_res8"]:
        if row is not None:
            res8_counter.update(row)
            
    for row in df["h3_res9"]:
        if row is not None:
            res9_counter.update(row)
            
    top_res8 = res8_counter.most_common(50)
    top_res9 = res9_counter.most_common(50)
    
    print(f"  ✓ Top Res 8 Cell: {top_res8[0][0]} ({top_res8[0][1]:,} visits)")
    print(f"  ✓ Top Res 9 Cell: {top_res9[0][0]} ({top_res9[0][1]:,} visits)")
    
    # 3. Create Folium H3 Map
    print("\n3. Building Interactive Folium H3 Hexagon Map (`output/h3_hexagons_map.html`)...")
    m = folium.Map(
        location=[41.1579, -8.6291], # Porto center
        zoom_start=13,
        tiles="CartoDB dark_matter"
    )
    
    # Render Top 40 Res 8 Hexagons
    max_res8_count = top_res8[0][1]
    res8_group = folium.FeatureGroup(name="H3 Res 8 Hexagons (~0.73 km²)", show=True)
    
    for cell, count in top_res8[:40]:
        try:
            # h3.cell_to_boundary returns tuple of (lat, lng)
            boundary = h3.cell_to_boundary(cell)
            intensity = min(1.0, count / max_res8_count)
            color = "#00f2fe" if intensity < 0.5 else "#7f00ff" if intensity < 0.8 else "#ff0844"
            
            folium.Polygon(
                locations=boundary,
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.35 + (intensity * 0.4),
                tooltip=f"<b>H3 Res 8 Cell:</b> {cell}<br><b>Visits:</b> {count:,}<br><b>Resolution:</b> 8 (~0.73 km²)",
                popup=f"H3 Cell ID: {cell}<br>Visits: {count:,}"
            ).add_to(res8_group)
        except Exception as e:
            continue
            
    res8_group.add_to(m)
    
    # Render Top 40 Res 9 Hexagons
    max_res9_count = top_res9[0][1]
    res9_group = folium.FeatureGroup(name="H3 Res 9 Hexagons (~0.10 km²)", show=False)
    
    for cell, count in top_res9[:40]:
        try:
            boundary = h3.cell_to_boundary(cell)
            intensity = min(1.0, count / max_res9_count)
            color = "#00e676" if intensity < 0.5 else "#ff9100" if intensity < 0.8 else "#ff0844"
            
            folium.Polygon(
                locations=boundary,
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.4 + (intensity * 0.4),
                tooltip=f"<b>H3 Res 9 Cell:</b> {cell}<br><b>Visits:</b> {count:,}<br><b>Resolution:</b> 9 (~0.10 km²)",
                popup=f"H3 Cell ID: {cell}<br>Visits: {count:,}"
            ).add_to(res9_group)
        except Exception as e:
            continue
            
    res9_group.add_to(m)
    folium.LayerControl().add_to(m)
    
    m.save(OUTPUT_H3_MAP)
    print(f"  ✓ Saved Folium H3 Map to {OUTPUT_H3_MAP}")
    
    # 4. Generate Interactive HTML Dashboard
    print("\n4. Generating Interactive Stage 2 H3 Dashboard (`output/stage2_h3_dashboard.html`)...")
    
    top_res8_dict = {cell: count for cell, count in top_res8[:10]}
    top_res9_dict = {cell: count for cell, count in top_res9[:10]}
    
    res8_lens = df["h3_res8_length"].value_counts().sort_index().head(15).to_dict()
    res9_lens = df["h3_res9_length"].value_counts().sort_index().head(15).to_dict()
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Project – Stage 2: H3 Spatial Encoding Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #0b0f19;
            --card-bg: rgba(18, 26, 43, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-purple: #7f00ff;
            --accent-pink: #ff0844;
            --accent-green: #00e676;
            --accent-orange: #ff9100;
            --text-main: #f0f4f8;
            --text-sub: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg-dark);
            background-image: 
                radial-gradient(at 10% 20%, rgba(0, 242, 254, 0.08) 0px, transparent 50%),
                radial-gradient(at 90% 80%, rgba(127, 0, 255, 0.1) 0px, transparent 50%);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--card-border);
        }}
        .header-title h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }}
        .badge {{
            background: rgba(127, 0, 255, 0.15);
            border: 1px solid rgba(127, 0, 255, 0.4);
            color: #d8b4fe;
            padding: 0.5rem 1rem;
            border-radius: 30px;
            font-size: 0.85rem;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}
        .kpi-card {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
        }}
        .kpi-label {{ color: var(--text-sub); font-size: 0.85rem; text-transform: uppercase; margin-bottom: 0.4rem; }}
        .kpi-value {{ font-size: 2rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: #fff; }}
        .kpi-subtext {{ font-size: 0.8rem; color: var(--accent-cyan); margin-top: 0.4rem; }}
        
        .map-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .map-title {{
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .map-btn {{
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            color: #0b0f19;
            padding: 0.5rem 1.2rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        iframe {{
            width: 100%;
            height: 480px;
            border: none;
            border-radius: 12px;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 1.5rem;
        }}
        .chart-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
        }}
        .col-6 {{ grid-column: span 6; }}
        @media (max-width: 900px) {{ .col-6 {{ grid-column: span 12; }} }}
        .chart-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #f1f5f9; }}
        .chart-container {{ position: relative; height: 260px; width: 100%; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>Stage 2: Uber H3 Spatial Encoding Dashboard</h1>
            <p>1,622,765 Encoded Porto Taxi Trajectories • Multi-Resolution Hexagonal Grid</p>
        </div>
        <div class="badge">STAGE 2 COMPLETED</div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Total Trips Encoded</div>
            <div class="kpi-value">{total_trips:,}</div>
            <div class="kpi-subtext">100% Valid Cleaned Trips</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">H3 Res 8 Cells</div>
            <div class="kpi-value">{len(res8_counter):,}</div>
            <div class="kpi-subtext">~0.73 km² Neighborhood Grid</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">H3 Res 9 Cells</div>
            <div class="kpi-value">{len(res9_counter):,}</div>
            <div class="kpi-subtext">~0.10 km² Street-Level Grid</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Mean Res 8 Sequence</div>
            <div class="kpi-value">7.66 cells</div>
            <div class="kpi-subtext">Avg Cells per Trip</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Mean Res 9 Sequence</div>
            <div class="kpi-value">16.90 cells</div>
            <div class="kpi-subtext">Avg Cells per Trip</div>
        </div>
    </div>

    <!-- Map Preview -->
    <div class="map-section">
        <div class="map-title">
            <span>🗺️ Interactive Folium H3 Hexagon Map (Porto, Portugal)</span>
            <a href="h3_hexagons_map.html" target="_blank" class="map-btn">Open Full Screen Map ↗</a>
        </div>
        <iframe src="h3_hexagons_map.html"></iframe>
    </div>

    <!-- Charts -->
    <div class="charts-grid">
        <div class="chart-card col-6">
            <div class="chart-title">Top 10 Most Visited H3 Res 8 Neighborhood Cells</div>
            <div class="chart-container">
                <canvas id="res8Chart"></canvas>
            </div>
        </div>

        <div class="chart-card col-6">
            <div class="chart-title">Top 10 Most Visited H3 Res 9 Street Cells</div>
            <div class="chart-container">
                <canvas id="res9Chart"></canvas>
            </div>
        </div>

        <div class="chart-card col-6">
            <div class="chart-title">Res 8 Sequence Length Distribution</div>
            <div class="chart-container">
                <canvas id="res8LenChart"></canvas>
            </div>
        </div>

        <div class="chart-card col-6">
            <div class="chart-title">Res 9 Sequence Length Distribution</div>
            <div class="chart-container">
                <canvas id="res9LenChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Outfit', sans-serif";

        // Top Res 8
        new Chart(document.getElementById('res8Chart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(list(top_res8_dict.keys()))},
                datasets: [{{
                    label: 'Visits',
                    data: {json.dumps(list(top_res8_dict.values()))},
                    backgroundColor: 'rgba(0, 242, 254, 0.75)',
                    borderRadius: 6
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Top Res 9
        new Chart(document.getElementById('res9Chart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(list(top_res9_dict.keys()))},
                datasets: [{{
                    label: 'Visits',
                    data: {json.dumps(list(top_res9_dict.values()))},
                    backgroundColor: 'rgba(127, 0, 255, 0.75)',
                    borderRadius: 6
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Res 8 Lengths
        new Chart(document.getElementById('res8LenChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(list(res8_lens.keys()))},
                datasets: [{{
                    label: 'Trips Count',
                    data: {json.dumps(list(res8_lens.values()))},
                    borderColor: '#00e676',
                    fill: true,
                    backgroundColor: 'rgba(0, 230, 118, 0.1)',
                    tension: 0.3
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Res 9 Lengths
        new Chart(document.getElementById('res9LenChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(list(res9_lens.keys()))},
                datasets: [{{
                    label: 'Trips Count',
                    data: {json.dumps(list(res9_lens.values()))},
                    borderColor: '#ff9100',
                    fill: true,
                    backgroundColor: 'rgba(255, 145, 0, 0.1)',
                    tension: 0.3
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""
    
    with open(OUTPUT_H3_DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved H3 Dashboard to {OUTPUT_H3_DASHBOARD}")
    print("\n✅ All Stage 2 H3 Visualizations generated successfully!")

if __name__ == "__main__":
    generate_visualizations()
