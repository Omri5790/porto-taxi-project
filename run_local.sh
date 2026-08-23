#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Porto Taxi Project – Local Run Script
# ═══════════════════════════════════════════════════════════════
# This script sets up the environment and runs the data preparation
# pipeline locally on a sampled subset of the data.
#
# Usage:
#   ./run_local.sh           # Run on 1% sample (fast, for development)
#   ./run_local.sh --full    # Run on full dataset (slow, ~15 minutes)
# ═══════════════════════════════════════════════════════════════

set -e

# Set Java for PySpark
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"

# Suppress Spark warnings & set JVM memory limits
export PYSPARK_PYTHON=python3
export PYSPARK_DRIVER_PYTHON=python3
export PYSPARK_SUBMIT_ARGS="--driver-memory 8g --executor-memory 8g pyspark-shell"

# Project root
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "╔══════════════════════════════════════════════════╗"
echo "║  Porto Taxi Project – Local Runner               ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check if data exists
if [ ! -f "data/train.csv" ]; then
    echo "❌ Error: data/train.csv not found!"
    echo "   Please download and extract the dataset first:"
    echo "   1. Download from UCI repository"
    echo "   2. Extract train.csv.zip into data/train.csv"
    exit 1
fi

echo "✓ Data file found: data/train.csv"
echo "  Size: $(du -h data/train.csv | cut -f1)"
echo ""

# Run Stage 1
echo "Running Stage 1: Data Preparation..."
python3 scripts/stage1_data_preparation.py --mode local "$@"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Done! Results saved in output/"
echo "═══════════════════════════════════════════════════"
