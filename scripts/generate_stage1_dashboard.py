"""
Generate Visual Dashboard & Folium Interactive Map for Stage 1
===============================================================
Reads output/cleaned_trips.parquet and outputs an interactive HTML map
with sample taxi trajectories in Porto.
"""

import json
import os
import pandas as pd
import folium

def main():
    parquet_path = "output/cleaned_trips.parquet"
    report_path = "output/cleaning_report.json"
    map_output_path = "output/porto_trips_map.html"
    
    if not os.path.exists(parquet_path):
        print("Error: output/cleaned_trips.parquet not found.")
        return
        
    print("Loading cleaned dataset sample for visualization...")
    # Read sample using pandas
    df = pd.read_parquet(parquet_path)
    
    print(f"Loaded {len(df):,} cleaned trips.")
    
    # Create Folium Map centered around Porto (41.1579, -8.6291)
    m = folium.Map(location=[41.1579, -8.6291], zoom_start=13, tiles="CartoDB positron")
    
    # Plot top 50 trajectories with interesting colors
    sample_df = df.sample(min(50, len(df)), random_state=42)
    
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe"]
    
    for idx, row in sample_df.reset_index().iterrows():
        coords = row['coordinates']
        if coords is None or len(coords) < 2:
            continue
        
        # Convert coords to (lat, lng) format for Folium
        lat_lngs = [[float(p['lat']), float(p['lng'])] for p in coords]
        color = colors[idx % len(colors)]
        
        # Draw trajectory polyline
        folium.PolyLine(
            lat_lngs,
            color=color,
            weight=3,
            opacity=0.8,
            popup=f"Trip ID: {row['TRIP_ID']}<br>Distance: {row['distance_km']:.2f} km<br>Duration: {row['duration_sec']}s<br>Avg Speed: {row['avg_speed_kmh']:.1f} km/h"
        ).add_to(m)
        
        # Start marker (Green)
        folium.CircleMarker(
            location=lat_lngs[0],
            radius=4,
            color="green",
            fill=True,
            fill_color="green",
            popup="Start"
        ).add_to(m)
        
        # End marker (Red)
        folium.CircleMarker(
            location=lat_lngs[-1],
            radius=4,
            color="red",
            fill=True,
            fill_color="red",
            popup="End"
        ).add_to(m)
        
    m.save(map_output_path)
    print(f"✓ Interactive HTML Map generated at: {map_output_path}")

if __name__ == "__main__":
    main()
