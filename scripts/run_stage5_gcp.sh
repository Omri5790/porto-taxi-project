#!/usr/bin/env bash
# ==============================================================================
# Porto Taxi Trajectory Project – Stage 5: Ridge Elevation Topography (DataProc)
# ==============================================================================
set -e

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "project-bf990986-f458-4b39-926")
REGION="europe-west1"
BUCKET_NAME="gs://porto-taxi-project-bf990986"
CLUSTER_NAME="porto-cluster-ridge-5nodes"
LOCAL_CSV="data/train.csv"
SCRIPT_FILE="scripts/stage5_ridge_elevation_routes.py"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Porto Taxi Project – Stage 5: Cloud Ridge Elevation (GCP)   ║"
echo "║  GCP Project: $PROJECT_ID | Region: $REGION              ║"
echo "╚══════════════════════════════════════════════════════════════╝"

echo ""
echo "STEP 1: Uploading Raw GPS Data (train.csv) to GCS..."
if ! gcloud storage ls "$BUCKET_NAME/data/train.csv" >/dev/null 2>&1; then
    echo "  Uploading $LOCAL_CSV (This may take a few minutes for 1.8GB)..."
    gcloud storage cp "$LOCAL_CSV" "$BUCKET_NAME/data/"
    echo "  ✓ Uploaded train.csv to GCS."
else
    echo "  ✓ train.csv already exists in GCS."
fi

gcloud storage cp "$SCRIPT_FILE" "$BUCKET_NAME/scripts/" >/dev/null 2>&1 || true
echo "  ✓ Uploaded Stage 5 script to GCS."

echo ""
echo "STEP 2: Creating 5-Node GCP DataProc Cluster with H3..."
gcloud dataproc clusters delete "$CLUSTER_NAME" --region="$REGION" --quiet >/dev/null 2>&1 || true

gcloud dataproc clusters create "$CLUSTER_NAME" \
    --region="$REGION" \
    --zone="${REGION}-b" \
    --num-workers=4 \
    --master-machine-type=n1-standard-4 \
    --worker-machine-type=n1-standard-4 \
    --master-boot-disk-size=50GB \
    --worker-boot-disk-size=50GB \
    --image-version=2.1-debian11 \
    --properties=dataproc:pip.packages=h3==4.4.2 \
    --quiet

echo "  ✓ 5-Node DataProc Cluster provisioned!"

echo ""
echo "STEP 3: Submitting PySpark Job to GCP DataProc..."
START_CLOUD_TIME=$(date +%s)

gcloud dataproc jobs submit pyspark "$BUCKET_NAME/scripts/stage5_ridge_elevation_routes.py" \
    --cluster="$CLUSTER_NAME" \
    --region="$REGION" \
    -- --input_path="$BUCKET_NAME/data/train.csv"

END_CLOUD_TIME=$(date +%s)
CLOUD_RUNTIME=$((END_CLOUD_TIME - START_CLOUD_TIME))

echo ""
echo "======================================================================"
echo "  ✅ GCP DataProc Execution Completed in ${CLOUD_RUNTIME} seconds!"
echo "======================================================================"

echo ""
echo "STEP 4: Cleaning up DataProc Cluster to save budget..."
gcloud dataproc clusters delete "$CLUSTER_NAME" --region="$REGION" --quiet
echo "  ✓ Cluster $CLUSTER_NAME deleted successfully."
