#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Porto Taxi Project — local runner
# ═══════════════════════════════════════════════════════════════════
#  Runs the pipeline on this machine, for development and for
#  reproducing the cloud results at small scale.
#
#    ./run_local.sh --sample     Stage 1 on a 1% sample (fast)
#    ./run_local.sh              Stage 1 on the full dataset (~15 min)
#    ./run_local.sh --stage3     Stage 3 only, on the H3 parquet
#    ./run_local.sh --synthetic  end-to-end smoke test, no dataset needed
#
#  The previous version of this script documented a --full flag the
#  Python never accepted, and defaulted to the opposite of what it said.
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# JAVA_HOME is only set if the caller has not chosen one.  Hard-coding a
# Homebrew path here meant the script only ran on one laptop.
if [[ -z "${JAVA_HOME:-}" ]]; then
  if command -v java >/dev/null 2>&1; then
    :
  else
    echo "Java 11 or 17 is required for PySpark but no 'java' was found." >&2
    echo "  macOS : brew install openjdk@17" >&2
    echo "  Debian: sudo apt install openjdk-17-jdk" >&2
    exit 1
  fi
fi
export PYSPARK_PYTHON="${PYSPARK_PYTHON:-$(command -v python3)}"
export PYSPARK_DRIVER_PYTHON="$PYSPARK_PYTHON"
# Spark hash-partitions Python objects; without a fixed seed the partitioning
# differs between driver and executors on some setups.
export PYTHONHASHSEED=0

MODE="${1:-}"

case "$MODE" in
  --synthetic)
    echo "Generating synthetic H3 trips (no dataset required)..."
    python3 tools/make_synthetic_h3.py --trips 20000 --out output/synthetic_h3.parquet
    echo
    echo "Running Stage 3 on the synthetic data..."
    python3 -m scripts.stage3.run_stage3 \
        --input_path output/synthetic_h3.parquet \
        --output_dir output/synthetic_run \
        --support_pct 0.3
    echo
    python3 tools/validate_results.py output/synthetic_run/stage3_subroutes.json
    exit $?
    ;;

  --stage3)
    if [[ ! -d "output/h3_encoded_trips.parquet" ]]; then
      echo "output/h3_encoded_trips.parquet not found — run stages 1 and 2 first." >&2
      exit 1
    fi
    python3 -m scripts.stage3.run_stage3 \
        --input_path output/h3_encoded_trips.parquet \
        --output_dir output \
        --support_pct "${SUPPORT_PCT:-0.05}"
    echo
    python3 tools/validate_results.py output/stage3_subroutes.json
    exit $?
    ;;
esac

if [[ ! -f "data/train.csv" ]]; then
  cat >&2 <<'MSG'
data/train.csv not found.

Download the Porto Taxi Trajectory dataset and extract train.csv into data/:
  https://archive.ics.uci.edu/dataset/339/taxi+service+trajectory+prediction+challenge+ecml+pkdd+2015

Or run ./run_local.sh --synthetic to exercise the pipeline without it.
MSG
  exit 1
fi

echo "Data: data/train.csv ($(du -h data/train.csv | cut -f1))"
echo
echo "Stage 1 — cleaning and feature extraction..."
python3 scripts/stage1_data_preparation.py --mode local "$@"

echo
echo "Stage 2 — H3 spatial encoding..."
python3 scripts/stage2_spatial_encoding.py --mode local "$@"

echo
echo "Stage 3 — popular long sub-route discovery..."
python3 -m scripts.stage3.run_stage3 \
    --input_path output/h3_encoded_trips.parquet \
    --output_dir output \
    --support_pct "${SUPPORT_PCT:-0.05}"

echo
python3 tools/validate_results.py output/stage3_subroutes.json
echo
echo "Done. Results in output/"
