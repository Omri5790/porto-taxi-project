"""
Porto Taxi Project – Configuration Constants
=============================================
All configurable parameters for the project are centralized here.
"""

# ──────────────────────────────────────────────
# Paths (local development)
# ──────────────────────────────────────────────
LOCAL_DATA_DIR = "data"
LOCAL_RAW_CSV = f"{LOCAL_DATA_DIR}/train.csv"
LOCAL_CLEANED_PARQUET = "output/cleaned_trips.parquet"
LOCAL_STATS_JSON = "output/cleaning_report.json"

# ──────────────────────────────────────────────
# Paths (GCS – for DataProc runs)
# ──────────────────────────────────────────────
GCS_BUCKET = "gs://porto-taxi-project"  # Update with your actual bucket name
GCS_RAW_CSV = f"{GCS_BUCKET}/raw/train.csv"
GCS_CLEANED_PARQUET = f"{GCS_BUCKET}/cleaned/cleaned_trips.parquet"

# ──────────────────────────────────────────────
# Porto Geographic Bounding Box
# ──────────────────────────────────────────────
# The greater Porto metropolitan area. Points outside this box are GPS errors.
# Source: OpenStreetMap bounding box for Porto, Portugal + buffer
PORTO_BBOX = {
    "min_lng": -8.7500,
    "max_lng": -8.4500,
    "min_lat": 41.0500,
    "max_lat": 41.2500,
}

# ──────────────────────────────────────────────
# Data Cleaning Thresholds
# ──────────────────────────────────────────────
# Minimum number of GPS points for a valid trip (2 points = 15 seconds minimum)
MIN_POINTS = 2

# Maximum trip duration in seconds (24 hours – trips longer than this are anomalies)
MAX_DURATION_SEC = 24 * 3600  # 86400 seconds

# Maximum plausible speed between consecutive GPS points (km/h)
# Porto speed limit is ~120 km/h on highways, we allow 200 for GPS jitter
MAX_SPEED_KMH = 200.0

# Maximum distance for a single 15-second GPS jump (km)
# At 200 km/h, you travel ~0.83 km in 15 seconds
MAX_JUMP_KM = MAX_SPEED_KMH * (15 / 3600)  # ~0.833 km

# ──────────────────────────────────────────────
# Sampling (for local development)
# ──────────────────────────────────────────────
# Fraction of data to use when developing locally (1.0 = full dataset)
LOCAL_SAMPLE_FRACTION = 0.01  # 1% ≈ 17K trips – enough for development

# ──────────────────────────────────────────────
# Earth radius for Haversine computation
# ──────────────────────────────────────────────
EARTH_RADIUS_KM = 6371.0
