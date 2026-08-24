#!/usr/bin/env bash
# ==============================================================================
# Porto Taxi Trajectory Project – Stage 4: GCP DataProc 5-Node Cluster Deployment
# ==============================================================================
set -e

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "project-bf990986-f458-4b39-926")
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
REGION="europe-west1"
BUCKET_NAME="gs://porto-taxi-project-bf990986"
CLUSTER_NAME="porto-cluster-5nodes"
LOCAL_H3_PARQUET="output/h3_encoded_trips.parquet"
SCRIPT_FILE="scripts/stage3_popular_long_subroutes.py"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Porto Taxi Project – Stage 4: GCP DataProc Cloud Deployment  ║"
echo "║  GCP Project: $PROJECT_ID | Region: $REGION              ║"
echo "╚══════════════════════════════════════════════════════════════╝"

echo ""
echo "STEP 1: Binding 'Dataproc Worker' IAM Role to Compute Service Account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/dataproc.worker" \
    --quiet >/dev/null 2>&1 || true
echo "  ✓ Granted 'roles/dataproc.worker' to $SA_EMAIL"

echo ""
echo "STEP 2: Checking / Creating GCS Bucket ($BUCKET_NAME)..."
if ! gcloud storage buckets describe "$BUCKET_NAME" >/dev/null 2>&1; then
    gcloud storage buckets create "$BUCKET_NAME" --location="$REGION"
    echo "  ✓ Created GCS Bucket: $BUCKET_NAME"
else
    echo "  ✓ GCS Bucket active: $BUCKET_NAME"
fi

echo ""
echo "STEP 3: Uploading Data & PySpark Scripts to GCS..."
gcloud storage cp -r "$LOCAL_H3_PARQUET" "$BUCKET_NAME/data/" >/dev/null 2>&1 || true
gcloud storage cp "$SCRIPT_FILE" "$BUCKET_NAME/scripts/" >/dev/null 2>&1 || true
echo "  ✓ Uploaded dataset & scripts to GCS successfully."

echo ""
echo "STEP 4: Creating 5-Node GCP DataProc Cluster with H3 PySpark package ($CLUSTER_NAME)..."
# Delete stale cluster if exists
gcloud dataproc clusters delete "$CLUSTER_NAME" --region="$REGION" --quiet >/dev/null 2>&1 || true

# 1 Master + 4 Workers = 5 Nodes total with --properties dataproc:pip.packages=h3==4.2.2
gcloud dataproc clusters create "$CLUSTER_NAME" \
    --region="$REGION" \
    --num-workers=4 \
    --master-machine-type=n1-standard-4 \
    --worker-machine-type=n1-standard-4 \
    --master-boot-disk-size=50GB \
    --worker-boot-disk-size=50GB \
    --image-version=2.1-debian11 \
    --properties=dataproc:pip.packages=h3==4.2.2 \
    --quiet

echo "  ✓ 5-Node DataProc Cluster provisioned with H3 library active!"

echo ""
echo "STEP 5: Submitting PySpark Job to 5-Node GCP Cluster..."
START_CLOUD_TIME=$(date +%s)

gcloud dataproc jobs submit pyspark "$BUCKET_NAME/scripts/stage3_popular_long_subroutes.py" \
    --cluster="$CLUSTER_NAME" \
    --region="$REGION" \
    -- --input_path="$BUCKET_NAME/data/h3_encoded_trips.parquet"

END_CLOUD_TIME=$(date +%s)
CLOUD_RUNTIME=$((END_CLOUD_TIME - START_CLOUD_TIME))

echo ""
echo "======================================================================"
echo "  ✅ GCP DataProc 5-Node Execution Completed in ${CLOUD_RUNTIME} seconds!"
echo "======================================================================"

echo ""
echo "STEP 6: Cleaning up and deleting DataProc Cluster to save budget..."
gcloud dataproc clusters delete "$CLUSTER_NAME" --region="$REGION" --quiet
echo "  ✓ Cluster $CLUSTER_NAME deleted successfully. Budget protected!"

echo ""
echo "======================================================================"
echo "  📊 STAGE 4 BENCHMARK SUMMARY:"
echo "  • Local Single Machine (Mac 8-Cores): ~1582 seconds"
echo "  • GCP Cloud DataProc Cluster (5-Nodes): ${CLOUD_RUNTIME} seconds"
echo "======================================================================"
