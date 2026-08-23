import nbformat as nbf

nb = nbf.v4.new_notebook()

cells = [
    nbf.v4.new_markdown_cell("""# 📊 Porto Taxi Trajectory Project – Exploratory Data Analysis (EDA)
### Stage 1: Cleaned Dataset Exploratory Data Analysis & Spatial Dynamics
---
This notebook presents an in-depth analytical EDA on the cleaned Porto Taxi dataset (**1,622,765 trips**, **442 taxis**).
It analyzes temporal patterns, trip distance distributions, fleet velocities, and spatial origin-destination dynamics.
"""),
    
    nbf.v4.new_code_cell("""import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import matplotlib.pyplot as plt
import seaborn as sns

# Configure plot styles
plt.style.use('dark_background')
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#334155'
plt.rcParams['axes.linewidth'] = 1.2

print("✓ Libraries imported successfully.")
"""),

    nbf.v4.new_code_cell("""# Load Cleaned Parquet Dataset
PARQUET_PATH = "../output/cleaned_trips.parquet"

columns = [
    "TRIP_ID", "CALL_TYPE", "TAXI_ID", "TIMESTAMP",
    "num_points", "duration_sec", "distance_km",
    "avg_speed_kmh", "hour_of_day", "day_of_week", "ORIGIN_STAND"
]

df = pd.read_parquet(PARQUET_PATH, columns=columns)
print(f"✓ Loaded {len(df):,} clean trips across {df['TAXI_ID'].nunique()} unique taxis.")
df.head()
"""),

    nbf.v4.new_markdown_cell("""## 1. Summary Statistics & Percentile Analysis"""),
    
    nbf.v4.new_code_cell("""# Distance & Duration Statistics
dist_stats = df["distance_km"].describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
dur_stats = (df["duration_sec"] / 60.0).describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99])

stats_summary = pd.DataFrame({
    "Distance (km)": dist_stats,
    "Duration (min)": dur_stats,
    "Speed (km/h)": df["avg_speed_kmh"].describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
})

display(stats_summary.round(2))
"""),

    nbf.v4.new_markdown_cell("""## 2. Temporal Dynamics: Demand by Hour of Day & Day of Week"""),

    nbf.v4.new_code_cell("""fig, axes = plt.subplots(1, 2, figsize=(16, 5))

# Hourly Demand
hourly_counts = df["hour_of_day"].value_counts().sort_index()
axes[0].bar(hourly_counts.index, hourly_counts.values, color='#00f2fe', alpha=0.85, edgecolor='#00f2fe')
axes[0].set_title("Hourly Taxi Demand (Trips per Hour)", fontsize=13, fontweight='bold', pad=12)
axes[0].set_xlabel("Hour of Day (00:00 - 23:00)")
axes[0].set_ylabel("Total Completed Trips")
axes[0].grid(axis='y', linestyle='--', alpha=0.2)

# Speed curve by hour
hourly_speed = df.groupby("hour_of_day")["avg_speed_kmh"].mean()
axes[1].plot(hourly_speed.index, hourly_speed.values, color='#00e676', linewidth=2.5, marker='o', markersize=5)
axes[1].set_title("Average Speed vs. Hour of Day", fontsize=13, fontweight='bold', pad=12)
axes[1].set_xlabel("Hour of Day")
axes[1].set_ylabel("Avg Speed (km/h)")
axes[1].grid(linestyle='--', alpha=0.2)

plt.tight_layout()
plt.show()
"""),

    nbf.v4.new_markdown_cell("""## 3. Trip Origin Types (Dispatch vs Taxi Stand vs Hail)"""),

    nbf.v4.new_code_cell("""call_type_map = {'A': 'Central Dispatch (A)', 'B': 'Taxi Stand (B)', 'C': 'Street Hail / Other (C)'}
df['call_type_desc'] = df['CALL_TYPE'].map(call_type_map)

plt.figure(figsize=(8, 5))
counts = df['call_type_desc'].value_counts()
colors = ['#00f2fe', '#7f00ff', '#ff0844']

plt.pie(counts.values, labels=counts.index, autopct='%1.1f%%', colors=colors, startangle=140, 
        textprops={'color': 'w', 'fontsize': 11, 'weight': 'bold'}, explode=(0.03, 0.03, 0.03))
plt.title("Trip Origin Distribution", fontsize=14, fontweight='bold', pad=15)
plt.show()
"""),

    nbf.v4.new_markdown_cell("""## 4. Top 10 Popular Taxi Stands in Porto"""),

    nbf.v4.new_code_cell("""top_stands = df[df['ORIGIN_STAND'].notna() & (df['ORIGIN_STAND'] != '')]['ORIGIN_STAND'].value_counts().head(10)

plt.figure(figsize=(10, 5))
sns.barplot(x=top_stands.values, y=[f"Stand #{int(float(s))}" for s in top_stands.index], palette="flare")
plt.title("Top 10 Pick-up Taxi Stands in Porto", fontsize=14, fontweight='bold', pad=12)
plt.xlabel("Total Pick-up Volume")
plt.ylabel("Taxi Stand ID")
plt.grid(axis='x', linestyle='--', alpha=0.2)
plt.show()
""")
]

nb.cells = cells

with open("/Users/omriliberty/.gemini/antigravity/scratch/porto-taxi-project/notebooks/stage1_eda.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print("✓ Created notebook: notebooks/stage1_eda.ipynb")
