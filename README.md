# Porto Taxi Trajectory Analysis Project
## Cloud Computing – Final Project

### Project Structure
```
porto-taxi-project/
├── config.py                        # Configuration constants
├── run_local.sh                     # Script to run locally
├── data/
│   └── train.csv                    # Raw dataset (~1.7GB)
├── output/
│   ├── cleaned_trips.parquet/       # Cleaned data (Parquet format)
│   └── cleaning_report.json         # Cleaning statistics
├── scripts/
│   └── stage1_data_preparation.py   # Stage 1: Data loading, cleaning, features
├── utils/
│   ├── __init__.py
│   └── geo.py                       # Haversine, polyline parsing, bbox checks
└── notebooks/
    └── (Jupyter notebooks for visualization)
```

### Quick Start (Local Development)

1. **Extract dataset:**
   ```bash
   cd data
   unzip taxi_dataset.zip
   unzip train.csv.zip
   cd ..
   ```

2. **Run Stage 1 (1% sample):**
   ```bash
   chmod +x run_local.sh
   ./run_local.sh
   ```

3. **Run Stage 1 (full dataset):**
   ```bash
   ./run_local.sh --full
   ```

### Requirements
- Python 3.9+
- Java 17 (OpenJDK)
- PySpark
- pandas, numpy
