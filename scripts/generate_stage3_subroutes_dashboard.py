"""
Porto Taxi Trajectory Project – Stage 3 Sub-Route Visualizer & Dashboard Generator
===================================================================================
Loads `output/top_20_subroutes.json` and generates:
1. `output/top_20_subroutes_map.html`: Interactive Folium Map showing the Top 20 Corridors
   with glowing polylines, start/end markers, and rich tooltips.
2. `output/stage3_subroutes_dashboard.html`: Interactive Analytics Dashboard with Chart.js.
"""

import os
import sys
import json
import pandas as pd
import folium

INPUT_SUBROUTES_JSON = "output/top_20_subroutes.json"
OUTPUT_SUBROUTES_MAP = "output/top_20_subroutes_map.html"
OUTPUT_SUBROUTES_DASHBOARD = "output/stage3_subroutes_dashboard.html"


def generate_visualizations():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Porto Taxi Project – Stage 3: Top 20 Sub-Routes Visualizer  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    if not os.path.exists(INPUT_SUBROUTES_JSON):
        print(f"❌ Error: {INPUT_SUBROUTES_JSON} not found.")
        return
        
    with open(INPUT_SUBROUTES_JSON, "r", encoding="utf-8") as f:
        subroutes = json.load(f)
        
    print(f"\n1. Loaded {len(subroutes)} mined sub-routes from {INPUT_SUBROUTES_JSON}.")
    
    # 2. Build Folium Map for Top 20 Sub-Routes
    print(f"\n2. Building Interactive Folium Map (`{OUTPUT_SUBROUTES_MAP}`)...")
    m = folium.Map(
        location=[41.1579, -8.6291], # Porto center
        zoom_start=13,
        tiles="CartoDB dark_matter"
    )
    
    colors = [
        "#00f2fe", "#4facfe", "#00e676", "#7f00ff", "#ff0844",
        "#ff9100", "#ffd700", "#e040fb", "#00e5ff", "#a78bfa",
        "#34d399", "#f43f5e", "#fbbf24", "#38bdf8", "#c084fc",
        "#4ade80", "#fb7185", "#fbbf24", "#818cf8", "#2dd4bf"
    ]
    
    for idx, sr in enumerate(subroutes):
        coords_list = sr.get("cell_coordinates", [])
        if len(coords_list) < 2:
            continue
            
        latlngs = [[pt["lat"], pt["lng"]] for pt in coords_list]
        rank = idx + 1
        color = colors[idx % len(colors)]
        support = sr["trip_support"]
        speed = sr["avg_speed_kmh"]
        dur = sr["avg_duration_sec"]
        res = sr["res_level"]
        
        # Polyline
        folium.PolyLine(
            locations=latlngs,
            color=color,
            weight=5 if rank <= 5 else 3,
            opacity=0.9,
            tooltip=f"<b>Rank #{rank} Sub-Route</b><br>Trips: {support:,}<br>Avg Speed: {speed} km/h<br>Resolution: {res}",
            popup=f"""
            <div style="font-family: sans-serif; font-size: 13px;">
                <b style="color: {color}; font-size: 15px;">Rank #{rank} Active Sub-Route</b><br>
                <b>Trip Support:</b> {support:,} trips<br>
                <b>Avg Speed:</b> {speed} km/h<br>
                <b>Avg Duration:</b> {dur:.1f} sec ({dur/60:.1f} min)<br>
                <b>H3 Sequence:</b> {sr['h3_sequence']}<br>
                <b>Resolution:</b> {res}
            </div>
            """
        ).add_to(m)
        
        # Start marker
        folium.CircleMarker(
            location=latlngs[0],
            radius=6 if rank <= 5 else 4,
            color=color,
            fill=True,
            fill_color="#fff",
            fill_opacity=1.0,
            tooltip=f"Start Rank #{rank}"
        ).add_to(m)
        
        # End marker
        folium.CircleMarker(
            location=latlngs[-1],
            radius=6 if rank <= 5 else 4,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=1.0,
            tooltip=f"End Rank #{rank}"
        ).add_to(m)
        
    m.save(OUTPUT_SUBROUTES_MAP)
    print(f"  ✓ Saved Folium Map to {OUTPUT_SUBROUTES_MAP}")
    
    # 3. Generate Interactive HTML Dashboard
    print(f"\n3. Generating Stage 3 Dashboard (`{OUTPUT_SUBROUTES_DASHBOARD}`)...")
    
    ranks = [f"Rank #{i+1}" for i in range(len(subroutes))]
    supports = [sr["trip_support"] for sr in subroutes]
    speeds = [sr["avg_speed_kmh"] for sr in subroutes]
    durations = [round(sr["avg_duration_sec"] / 60.0, 1) for sr in subroutes]
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Porto Taxi Project – Stage 3: Top 20 Sub-Routes Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #0b0f19;
            --card-bg: rgba(18, 26, 43, 0.78);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-cyan: #00f2fe;
            --accent-purple: #7f00ff;
            --accent-pink: #ff0844;
            --accent-green: #00e676;
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
            background: rgba(0, 230, 118, 0.15);
            border: 1px solid rgba(0, 230, 118, 0.4);
            color: #6ee7b7;
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
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            color: #fff;
            padding: 0.5rem 1.2rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        iframe {{
            width: 100%;
            height: 500px;
            border: none;
            border-radius: 12px;
        }}

        .table-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            color: var(--text-sub);
            text-transform: uppercase;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        tr:hover {{ background: rgba(255,255,255,0.02); }}

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
        .chart-container {{ position: relative; height: 280px; width: 100%; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>Stage 3: Top 20 Sub-Routes Dashboard</h1>
            <p>1.62M Porto Taxi Trajectories • PySpark N-Gram Sub-Route Mining</p>
        </div>
        <div class="badge">STAGE 3 COMPLETED</div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Top Sub-Route Volume</div>
            <div class="kpi-value">{supports[0]:,}</div>
            <div class="kpi-subtext">Rank #1 Active Corridor</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Sub-Routes Mined</div>
            <div class="kpi-value">20</div>
            <div class="kpi-subtext">Support Threshold ≥ 300 Trips</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Max Speed Corridor</div>
            <div class="kpi-value">{max(speeds)} km/h</div>
            <div class="kpi-subtext">Expressway Sub-Route</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Avg Corridor Speed</div>
            <div class="kpi-value">{sum(speeds)/len(speeds):.1f} km/h</div>
            <div class="kpi-subtext">Across Top 20 Corridors</div>
        </div>
    </div>

    <!-- Map Section -->
    <div class="map-section">
        <div class="map-title">
            <span>🗺️ Top 20 Frequent Sub-Routes Interactive Map (Porto)</span>
            <a href="top_20_subroutes_map.html" target="_blank" class="map-btn">Open Full Screen Map ↗</a>
        </div>
        <iframe src="top_20_subroutes_map.html"></iframe>
    </div>

    <!-- Table Section -->
    <div class="table-section">
        <h3 style="margin-bottom: 1rem; color: var(--accent-cyan);">Top 20 Frequent Sub-Routes Leaderboard</h3>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Resolution</th>
                    <th>Trip Support</th>
                    <th>Avg Speed</th>
                    <th>Avg Duration</th>
                    <th>Start H3 Cell</th>
                    <th>End H3 Cell</th>
                </tr>
            </thead>
            <tbody>
"""
    for idx, sr in enumerate(subroutes):
        html_content += f"""
                <tr>
                    <td><strong style="color: {colors[idx % len(colors)]}">#{idx+1}</strong></td>
                    <td><span class="badge" style="font-size:0.75rem; padding:2px 8px;">{sr['res_level']}</span></td>
                    <td><strong>{sr['trip_support']:,}</strong> trips</td>
                    <td>{sr['avg_speed_kmh']} km/h</td>
                    <td>{sr['avg_duration_sec']:.1f}s ({sr['avg_duration_sec']/60:.1f}m)</td>
                    <td style="font-family:monospace; color:#94a3b8;">{sr['start_h3']}</td>
                    <td style="font-family:monospace; color:#94a3b8;">{sr['end_h3']}</td>
                </tr>
        """

    html_content += f"""
            </tbody>
        </table>
    </div>

    <!-- Charts Section -->
    <div class="charts-grid">
        <div class="chart-card col-6">
            <div class="chart-title">Trip Support Volume (Top 20 Sub-Routes)</div>
            <div class="chart-container">
                <canvas id="supportChart"></canvas>
            </div>
        </div>

        <div class="chart-card col-6">
            <div class="chart-title">Average Speed per Sub-Route (km/h)</div>
            <div class="chart-container">
                <canvas id="speedChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Outfit', sans-serif";

        new Chart(document.getElementById('supportChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(ranks)},
                datasets: [{{
                    label: 'Trips',
                    data: {json.dumps(supports)},
                    backgroundColor: 'rgba(0, 242, 254, 0.75)',
                    borderRadius: 6
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        new Chart(document.getElementById('speedChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(ranks)},
                datasets: [{{
                    label: 'Speed (km/h)',
                    data: {json.dumps(speeds)},
                    borderColor: '#ff0844',
                    fill: true,
                    backgroundColor: 'rgba(255, 8, 68, 0.1)',
                    tension: 0.3
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""

    with open(OUTPUT_SUBROUTES_DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"  ✓ Saved Stage 3 Dashboard to {OUTPUT_SUBROUTES_DASHBOARD}")
    print("\n✅ All Stage 3 Visualizations generated successfully!")

if __name__ == "__main__":
    generate_visualizations()
