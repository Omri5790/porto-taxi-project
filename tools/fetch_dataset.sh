#!/usr/bin/env bash
# ==============================================================================
#  Fetch the Porto Taxi dataset and put train.csv in GCS.
# ==============================================================================
#  The UCI archive is a zip inside a zip: the outer file (~509 MB) contains
#  train.csv.zip (~509 MB), which contains train.csv (~1.9 GB).  This script
#  unpacks each layer and deletes it immediately, so peak disk stays near 2.4 GB
#  rather than 2.9 GB -- which matters in Cloud Shell, where $HOME is 5 GB.
#
#  Best run in Google Cloud Shell: it already has gcloud authenticated and the
#  upload to GCS goes over Google's internal network instead of your home
#  connection.
#
#      bash tools/fetch_dataset.sh
#
#  If you already have train.csv locally, skip this and just run:
#      gcloud storage cp train.csv gs://YOUR-BUCKET/raw/train.csv
# ==============================================================================
set -euo pipefail

BUCKET="${BUCKET:-gs://porto-taxi-project-bf990986}"
DEST="$BUCKET/raw/train.csv"
WORK="${WORK:-$HOME/porto-dataset}"
URL="https://archive.ics.uci.edu/static/public/339/taxi+service+trajectory+prediction+challenge+ecml+pkdd+2015.zip"

echo "=============================================================="
echo "  Porto Taxi dataset -> GCS"
echo "  work dir : $WORK"
echo "  target   : $DEST"
echo "=============================================================="

# ── 0. do we already have it? ─────────────────────────────────────────────────
if gcloud storage ls "$DEST" >/dev/null 2>&1; then
  SIZE=$(gcloud storage ls -l "$DEST" | head -1 | awk '{print $1}')
  echo "Already in the bucket ($SIZE bytes). Nothing to do."
  echo "Delete it first if you want to re-upload."
  exit 0
fi

mkdir -p "$WORK"
cd "$WORK"

AVAIL_KB=$(df -Pk . | tail -1 | awk '{print $4}')
if (( AVAIL_KB < 3000000 )); then
  echo "WARNING: only $((AVAIL_KB/1024)) MB free here; ~3 GB is comfortable." >&2
  echo "         Set WORK=/some/roomier/path and re-run if this fails." >&2
fi

# ── 1. outer archive ──────────────────────────────────────────────────────────
if [[ ! -f train.csv && ! -f train.csv.zip ]]; then
  echo ""
  echo "STEP 1/4  downloading (~509 MB)..."
  curl -L --fail --progress-bar -o uci.zip "$URL"
  echo "STEP 2/4  unpacking outer archive..."
  unzip -o -q uci.zip
  rm -f uci.zip                      # free 509 MB before the next layer
fi

# ── 2. inner archive ──────────────────────────────────────────────────────────
if [[ ! -f train.csv ]]; then
  echo "STEP 3/4  unpacking train.csv.zip (~1.9 GB when open)..."
  unzip -o -q train.csv.zip
  rm -f train.csv.zip
fi

if [[ ! -f train.csv ]]; then
  echo "train.csv did not appear. Contents of $WORK:" >&2
  ls -lah >&2
  exit 1
fi

# ── 3. sanity check before uploading 1.9 GB ───────────────────────────────────
HEADER=$(head -1 train.csv)
if [[ "$HEADER" != *"POLYLINE"* ]]; then
  echo "This does not look like the trajectory file. Header was:" >&2
  echo "  $HEADER" >&2
  exit 1
fi
echo "  header OK: $(echo "$HEADER" | cut -c1-70)..."
echo "  size: $(du -h train.csv | cut -f1)"

# ── 4. upload ─────────────────────────────────────────────────────────────────
echo ""
echo "STEP 4/4  uploading to $DEST ..."
gcloud storage cp train.csv "$DEST"

echo ""
echo "=============================================================="
echo "  Done. train.csv is at $DEST"
echo ""
echo "  Next:  bash scripts/run_pipeline_dataproc.sh"
echo "=============================================================="
echo ""
echo "  (You can delete $WORK now to reclaim ~1.9 GB.)"
