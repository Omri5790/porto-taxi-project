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
LOCAL_H3_PARQUET = "output/h3_encoded_trips.parquet"
LOCAL_STAGE3_DIR = "output"
LOCAL_STATS_JSON = "output/cleaning_report.json"

# ──────────────────────────────────────────────
# Paths (GCS – for DataProc runs)
# ──────────────────────────────────────────────
GCS_BUCKET = "gs://porto-taxi-project-bf990986"  # must match scripts/run_pipeline_dataproc.sh
GCS_RAW_CSV = f"{GCS_BUCKET}/raw/train.csv"
GCS_CLEANED_PARQUET = f"{GCS_BUCKET}/cleaned/cleaned_trips.parquet"
GCS_H3_PARQUET = f"{GCS_BUCKET}/data/h3_encoded_trips.parquet"

# ──────────────────────────────────────────────
# Porto Geographic Bounding Box
# ──────────────────────────────────────────────
# The greater Porto metropolitan area.  This is the *study area* -- where the
# corridors we care about live, and the extent the maps are drawn over.
# Source: OpenStreetMap bounding box for Porto, Portugal + buffer
PORTO_BBOX = {
    "min_lng": -8.7500,
    "max_lng": -8.4500,
    "min_lat": 41.0500,
    "max_lat": 41.2500,
}

# Points outside PORTO_BBOX are NOT automatically GPS errors, and treating them
# that way threw away exactly the trips this project needs.
#
# Measured on 400,000 raw rows: 4,482 trips have a point outside PORTO_BBOX.
# Only 0.4% of them have a single point outside -- the isolated-spike pattern a
# satellite glitch produces.  42% have more than *half* their points outside,
# the median excursion past the boundary is 6.7 km, and 78.6% stay within 20 km
# of it.  Those are journeys to neighbouring towns, not errors.
#
# And they are overwhelmingly the long ones: median 16.05 km against 3.91 km for
# the trips that were kept, with 89.8% over 10 km and 24.8% over 20 km.  The old
# rule was removing a quarter of the trips long enough to contain a 20 km
# corridor, while looking for corridors of 20 and 40 km.
#
# So validity is judged against a wider region box, and the study area is left
# to do the job it is actually for.  A genuine satellite error still fails:
# an isolated spike creates a step of hundreds of km/h, which MAX_JUMP_KM
# catches, and a sustained excursion beyond this box is not a taxi fare.
REGION_BBOX = {
    "min_lng": -9.7500,
    "max_lng": -7.4500,
    "min_lat": 40.0500,
    "max_lat": 42.2500,
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

# Minimum plausible journey.  A "trip" of a few dozen metres is a meter that
# was started and stopped, not a journey, and it pollutes every distribution.
MIN_TRIP_KM = 0.2

# Maximum plausible journey.  Greater Porto is roughly 25 x 22 km; a trip of
# hundreds of kilometres inside that box is a meter left running while the taxi
# circles.  Such trips pass every other rule and then dominate the tail, which
# is how a 99th percentile ends up equal to the maximum.
MAX_TRIP_KM = 100.0

# ──────────────────────────────────────────────
# Sampling (for local development)
# ──────────────────────────────────────────────
# Fraction of data to use when developing locally (1.0 = full dataset)
LOCAL_SAMPLE_FRACTION = 0.01  # 1% ≈ 17K trips – enough for development

# ──────────────────────────────────────────────
# Earth radius for Haversine computation
# ──────────────────────────────────────────────
EARTH_RADIUS_KM = 6371.0
