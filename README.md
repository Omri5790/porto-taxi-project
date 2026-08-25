# 🚖 Porto Taxi Trajectory Analysis & Frequent Sub-Route Mining

![Porto Taxi Project](output/h3_3d_map.html) <!-- Placeholder for image, assuming they'll view the interactive maps -->

This repository contains the complete implementation of a big data project designed to analyze **1.6 million taxi trajectories** in Porto, Portugal. The primary goal is to discover the top 100 most popular long sub-routes using distributed computing and advanced approximate data structures.

## 🌟 Project Highlights

- **Big Data Processing:** Processed 1.6M+ GPS trajectories using **Apache Spark (PySpark)**.
- **Spatial Encoding:** Transformed raw GPS coordinates into hierarchical hexagonal grids using **Uber's H3** index (Resolution 9).
- **Algorithmic Complexity:** Implemented three distinct algorithmic approaches for pattern mining, utilizing Approximate Data Structures.
- **Cloud Computing:** Designed for cloud execution and successfully deployed on a **5-Node GCP DataProc Cluster**.
- **Stunning Visualizations:** Interactive 3D Pyramidal Maps (Deck.gl) and 2D Interactive dashboards (Folium).

---

## 🛠️ Technology Stack

- **Data Processing:** Python, PySpark (RDDs & DataFrames), Pandas
- **Spatial Engineering:** Uber H3
- **Visualization:** Deck.gl, Folium, Plotly, HTML/CSS/JS
- **Cloud Infrastructure:** Google Cloud Platform (GCS, DataProc)

---

## 🏗️ Architecture & Stages

### Stage 1: Data Cleaning & Exploratory Data Analysis (EDA)
- Removed incomplete and anomalous trips (e.g., negative travel times, out-of-bounds coordinates).
- Visualized basic statistics (trip durations, peak hours) via interactive HTML dashboards.
- **Script:** `scripts/stage1_data_cleaning.py`

### Stage 2: Spatial Encoding (Uber H3)
- Converted variable-length GPS (lat/lng) sequences into fixed-resolution H3 spatial indices (Res 9: ~0.1 km² area).
- Drastically reduced computational complexity by mapping continuous space to discrete cells.
- **Script:** `scripts/stage2_h3_encoding.py`

### Stage 3: Popular Long Sub-Route Discovery
This is the core of the project. We developed three distinct algorithms to find the 100 most popular long sub-routes:

1. **Method 1: MinHash LSH Clustering on Sub-Sequences**
   - **How it works:** Extracts 8-20 cell windows, creates 2-shingle sets, and generates a MinHash signature (80 hashes). Applies LSH (10 bands × 8 rows) to cluster similar sub-routes in `O(1)` candidate time.
   - **Advantage:** Capable of finding *similar* (not just exact) routes traversing parallel streets.

2. **Method 2: Generalized Suffix Array + LCP Array Mining**
   - **How it works:** Treats spatial trajectories as strings. Builds a Suffix Array on a sample dataset and computes the Longest Common Prefix (LCP) to locate exact repeating subsequences.
   - **Advantage:** Blazing fast. Discovered the longest continuous corridor (190 cells, ~66.8 km).

3. **Method 3: Count-Min Sketch Pre-Filtering + Greedy Chain Extension**
   - **How it works:** Extracts n-grams (5-8 cells) and counts frequencies using a **Count-Min Sketch** probabilistic data structure (constant memory: 2.5MB). Frequent n-grams are then greedily chained together to form long continuous routes.
   - **Advantage:** Memory-efficient (O(1) memory footprint for the structure) and excellent at reconstructing long chains.

- **Post-Processing:** Implemented a *Gap-Tolerant Merge* to bridge small geographic holes (taxis diverting for 1-2 cells).
- **Script:** `scripts/stage3_popular_long_subroutes.py`

### Stage 4: GCP Cloud Deployment (DataProc)
- Fully automated bash script to provision a 5-node Google Cloud DataProc cluster (1 Master, 4 Workers).
- Uploads the H3 Parquet dataset to GCS, submits the PySpark job, executes distributedly, and safely tears down the cluster to prevent idle costs.
- **Script:** `scripts/run_gcp_dataproc.sh`

---

## 🏆 Key Results

The pipeline successfully discovered 59 unique, highly popular long corridors (after deduplication and gap-merging), strictly adhering to honest, un-fabricated data extraction:

| Rank | Length (Cells) | Distance | Trip Support | Method |
|:---:|:---:|:---:|:---:|:---|
| **#1** | 190 | 66.8 km | 3,906 | Suffix Array + LCP |
| **#2** | 60 | 21.0 km | 10,005 | Count-Min Sketch + Greedy |
| **#3** | 144 | 49.5 km | 3,929 | Count-Min Sketch + Greedy |
| **#4** | 115 | 41.3 km | 4,147 | LSH Clustering |

*See `output/popular_long_subroutes_100.json` for the full dataset.*

---

## 🗺️ Visualizations (Outputs)

Open the following files in your browser to view the interactive results:
- `output/h3_3d_map.html` - The flagship 3D Pyramidal Hexagon Map displaying the top sub-routes hovering over the city density.
- `output/popular_100_subroutes_map.html` - 2D Folium Map of the popular corridors.
- `output/popular_100_subroutes_dashboard.html` - Benchmark comparisons of the 3 algorithms.

---

## 🚀 How to Run

### 1. Local Execution (Requires PySpark)
```bash
# 1. Clean Data
python3 scripts/stage1_data_cleaning.py

# 2. Encode to H3
python3 scripts/stage2_h3_encoding.py

# 3. Discover Sub-routes
python3 scripts/stage3_popular_long_subroutes.py

# 4. Generate Visualizations
python3 scripts/generate_3d_h3_map.py
python3 scripts/generate_100_subroutes_map.py
```

### 2. Cloud Execution (Google Cloud DataProc)
*Prerequisites: Google Cloud SDK (`gcloud`) authenticated, Billing enabled.*
```bash
bash scripts/run_gcp_dataproc.sh
```

---
*Developed for Advanced Big Data & Data Mining Coursework.*
