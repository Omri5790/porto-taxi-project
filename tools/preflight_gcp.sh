#!/usr/bin/env bash
# ==============================================================================
#  Check everything the cluster run needs, before spending a cent on a cluster.
#
#  Answers four questions:
#     1. Is gcloud pointed at the right project, with the right APIs on?
#     2. What is already in the bucket -- do we still need to upload anything?
#     3. How much CPU quota is actually free in this region?
#     4. Is there an old cluster still running and billing?
#
#  Prints a recommended command at the end.  Read-only: creates nothing.
#
#      bash tools/preflight_gcp.sh
# ==============================================================================
set -uo pipefail

REGION="${REGION:-europe-west1}"
BUCKET="${BUCKET:-gs://porto-taxi-project-bf990986}"

hr() { printf '%s\n' "--------------------------------------------------------------"; }

echo "=============================================================="
echo "  GCP preflight"
echo "=============================================================="

# ── 1. project and auth ───────────────────────────────────────────────────────
PROJECT="$(gcloud config get-value project 2>/dev/null)"
ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
echo "project : ${PROJECT:-<none set>}"
echo "account : ${ACCOUNT:-<not logged in>}"
echo "region  : $REGION"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
  echo ""
  echo "STOP: no project set.   gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

hr
echo "APIs:"
for api in dataproc.googleapis.com compute.googleapis.com storage.googleapis.com; do
  if gcloud services list --enabled --filter="config.name=$api" --format="value(config.name)" 2>/dev/null | grep -q .; then
    echo "  on   $api"
  else
    echo "  OFF  $api      <- gcloud services enable $api"
  fi
done

# ── 2. what is already in the bucket ──────────────────────────────────────────
hr
echo "Bucket $BUCKET:"
if ! gcloud storage ls "$BUCKET" >/dev/null 2>&1; then
  echo "  NOT REACHABLE -- wrong name, or no permission, or it does not exist."
  echo "  create it with:  gcloud storage buckets create $BUCKET --location=$REGION"
  HAVE_RAW=0; HAVE_H3=0
else
  if gcloud storage ls "$BUCKET/raw/train.csv" >/dev/null 2>&1; then
    SZ=$(gcloud storage ls -l "$BUCKET/raw/train.csv" 2>/dev/null | awk 'NR==1{print $1}')
    echo "  raw/train.csv                 present (${SZ:-?} bytes)"
    HAVE_RAW=1
  else
    echo "  raw/train.csv                 MISSING"
    HAVE_RAW=0
  fi
  if gcloud storage ls "$BUCKET/data/h3_encoded_trips.parquet/_SUCCESS" >/dev/null 2>&1; then
    echo "  data/h3_encoded_trips.parquet  present (stage 2 output already uploaded)"
    HAVE_H3=1
  else
    echo "  data/h3_encoded_trips.parquet  MISSING"
    HAVE_H3=0
  fi
fi

# ── 3. quota ──────────────────────────────────────────────────────────────────
hr
echo "CPU quota in $REGION:"
gcloud compute regions describe "$REGION" \
  --format="table[no-heading](quotas.filter(\"metric:CPUS\").extract(metric,usage,limit))" 2>/dev/null \
  | tr -d "[]'" | awk -F', *' '{printf "  %s: %s used of %s\n", $1, $2, $3}'
echo ""
echo "  6 nodes x n1-standard-4 needs 24 vCPU."
echo "  6 nodes x e2-standard-2 needs 12 vCPU  <- use this if the number above is tight."

# ── 4. clusters still up ──────────────────────────────────────────────────────
hr
echo "Clusters currently in $REGION:"
LIVE="$(gcloud dataproc clusters list --region="$REGION" \
        --format='value(clusterName,status.state,config.workerConfig.numInstances)' 2>/dev/null)"
if [[ -z "$LIVE" ]]; then
  echo "  none  (good -- nothing is billing)"
else
  echo "$LIVE" | sed 's/^/  /'
  echo ""
  echo "  A cluster left RUNNING bills by the minute and eats the quota above."
  echo "  Delete one with:  gcloud dataproc clusters delete NAME --region=$REGION --quiet"
fi

# ── recommendation ────────────────────────────────────────────────────────────
hr
echo "Recommended next command:"
echo ""
if [[ "${HAVE_H3:-0}" == "1" ]]; then
  echo "  MACHINE=e2-standard-2 STAGES=3 bash scripts/run_pipeline_dataproc.sh"
  echo ""
  echo "  Stage 2 output is already in the bucket, so only stage 3 needs to run."
elif [[ "${HAVE_RAW:-0}" == "1" ]]; then
  echo "  MACHINE=e2-standard-2 bash scripts/run_pipeline_dataproc.sh"
  echo ""
  echo "  The raw CSV is in the bucket; all three stages run on the cluster."
else
  echo "  Nothing is in the bucket yet.  Upload ONE of these first:"
  echo ""
  echo "    # the raw CSV -- all three stages then run in the cloud"
  echo "    gcloud storage cp data/train.csv $BUCKET/raw/train.csv"
  echo ""
  echo "    # or, if stages 1-2 already ran locally, just their output (~1.3 GB)"
  echo "    gcloud storage cp -r output/h3_encoded_trips.parquet \\"
  echo "        $BUCKET/data/h3_encoded_trips.parquet"
fi
echo ""
echo "=============================================================="
