# Porto Taxi Trajectory Analysis

Mining popular long sub-routes from 1.71M taxi trajectories in Porto, using
PySpark on Google Cloud Dataproc.

Final project for **Cloud Computing for Big Data**. The dataset is the
[Porto Taxi Service Trajectory challenge](https://archive.ics.uci.edu/dataset/339/taxi+service+trajectory+prediction+challenge+ecml+pkdd+2015)
(442 taxis, one year, one GPS fix every 15 seconds).

---

## The four questions

| Question | Where it is answered |
|:---|:---|
| What are the most popular routes in the city? | Stage 3 — [`scripts/stage3/`](scripts/stage3) |
| Which areas are activity hotspots? | Stage 2 — H3 density maps at resolutions 8/9/10 |
| How can unusual routes be identified? | [`scripts/stage3/anomalies.py`](scripts/stage3/anomalies.py) |
| How do we do this efficiently with approximate algorithms on Spark? | [`scripts/stage3/sketches.py`](scripts/stage3/sketches.py), [`gate.py`](scripts/stage3/gate.py) |

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Exercise the whole of Stage 3 without downloading the 1.7 GB dataset:
./run_local.sh --synthetic
```

`--synthetic` plants a known road network with known corridors — including one
that trips traverse via two alternative middles — runs the real pipeline over
it, and audits the output. It is the fastest way to see what the code does.

With the real dataset in `data/train.csv`:

```bash
./run_local.sh              # stages 1 -> 2 -> 3, full dataset
./run_local.sh --sample     # stage 1 on a 1% sample
./run_local.sh --stage3     # stage 3 only, from the H3 parquet
```

On the cluster — one cluster, all three stages, results to `gs://`:

```bash
bash tools/fetch_dataset.sh              # dataset -> GCS (skip if already there)
bash scripts/run_pipeline_dataproc.sh    # 1 master + 5 workers, stages 1->2->3
```

See [`QUICKSTART.md`](QUICKSTART.md) for the full sequence including what to do
with the results afterwards.

---

## Stage 1 — cleaning and feature extraction

`scripts/stage1_data_preparation.py`

Ten quality rules, each with its justification and each **counted separately**,
are documented in [`docs/stage1_data_cleaning_report.md`](docs/stage1_data_cleaning_report.md).
Every rule increments its own Spark accumulator, so `cleaning_report.json`
answers "how many trips did each rule remove?" rather than only reporting a
total.

Two details worth knowing:

* **The bounding box is checked on every point**, not just the endpoints. A
  mid-trip satellite glitch into the Atlantic passes an endpoint-only check and
  then corrupts that trip's distance and its whole H3 sequence.
* **Duration comes from the original sample count**, `(n_raw - 1) * 15`.
  Deduplication removes stationary points but not the time they represent —
  deriving duration from the deduplicated count erases the seconds a taxi spent
  at a red light and inflates its mean speed (measured: 23% on a trip with one
  short stall).

Extracted per trip: raw and deduplicated point counts, duration, Haversine
distance, start and end coordinates, mean speed, and calendar features.

## What the data does not contain

Each row of the dataset is one **fare** — the trajectory starts when the meter
starts and ends when it stops. What the taxi did between fares is not recorded.

Measured on 167,928 consecutive trip pairs by the same taxi (ignoring gaps over
three hours, which are shift breaks): the distance between where one fare ended
and the next began has a median of **1.72 km**, and exceeds 1 km **67.3%** of the
time. Only 5.9% of pairs are continuous within 100 m. The median idle time
between fares is 48 minutes.

So the corridors this project finds are **demand corridors, not traffic
corridors**. A road that taxis drive constantly while empty — heading back to
the airport rank, cruising for a hail — is invisible here. That is a property of
the dataset, and it is worth saying out loud rather than letting a reader assume
the trajectories cover a taxi's whole day.

It also bounds what "popular" can mean: support counts paid journeys along a
stretch, out of 440 taxis, not vehicles on a road.

### The long trips are mostly not journeys

A follow-on question — why would a driver go in circles, when every row is a
paid fare? — turned into a finding. `tools/measure_trip_geometry.py` compares
each trip's walked path against the straight line from its start to its end:

| trips of | count | median tortuosity | end where they began | journeys |
|:---|---:|---:|---:|---:|
| ≥ 1 km | 1,562,225 | 1.45 | 3% | **90.8%** |
| ≥ 10 km | 189,009 | 1.63 | 4% | **78.5%** |
| ≥ 20 km | 17,437 | 3.23 | 11% | **39.9%** |
| ≥ 40 km | 1,459 | 19.71 | 22% | **0.3%** |

The longer a "trip" is, the less it looks like a journey. Of the 1,459 trips of
40 km or more, **four** walk a path within 2.5× their straight-line displacement.
The rest wander and come back — 22% end within 500 m of where they started,
after tens of kilometres, over a median of 1.6 hours. Those are not fares; they
are meters that were never stopped, with a whole afternoon of driving recorded
as one journey.

This is a gap in **Stage 1**, not Stage 3: the cleaning rules cap distance at
100 km and duration at 24 hours, and a wandering 40 km trip passes both. A
tortuosity rule would remove them. The published corridors are unaffected —
they already refuse shapes like that — but the `length_ceiling` reported
alongside them is optimistic by exactly this margin, and the honest ceiling at
40 km is four trips rather than 460.

## Stage 2 — spatial encoding

`scripts/stage2_spatial_encoding.py`

Each trajectory becomes a sequence of **Uber H3** cells with consecutive
duplicates collapsed. Resolutions 8, 9 and 10 are all encoded so the
cell-size trade-off can be shown rather than asserted; Stage 3 works at
**resolution 9** (~174 m edge, ~0.1 km²) — fine enough to tell adjacent
streets apart, coarse enough that trips down the same road share cells.

| | **H3** | S2 | Geohash | HEALPix |
|:---|:---:|:---:|:---:|:---:|
| cell shape | hexagon | quad | rectangle | triangle |
| equidistant neighbours | yes (6) | no | no | no |
| hierarchical | 16 levels | yes | yes | yes |
| maintained Python binding | `h3-py` | partial | yes | partial |

Hexagons matter here specifically because every neighbour is the same distance
away: on a square grid a diagonal step is 1.41x a straight one, which biases
corridor mining toward axis-aligned roads.

## Stage 3 — popular long sub-routes

See [`docs/stage3_algorithms.md`](docs/stage3_algorithms.md) for the full
write-up, and the module docstrings for the details.

### What counts as a corridor

A corridor is an **ordered list of segments**, each segment a contiguous run of
H3 cells:

```
[ c0 c1 c2 c3 ]  ...hole...  [ c9 c10 c11 ]
```

A trip **supports** it when it contains every segment contiguously, in order,
spending at most `max_gap` cells inside each hole. The hole is the brief's
Haifa->Ashdod case: trips split between two alternatives for a stretch and
rejoin, so the popular object spans the gap.

Two invariants are enforced everywhere a corridor grows:

* **simple path** — a cell may never appear twice;
* **tortuosity <= 2.5** — path length over straight-line distance.

Without them, chaining frequent fragments produces "66 km routes" whose
endpoints are 4 km apart — sequences that are long and frequent and are still
not routes.

### Three methods

| | idea | approximate structure | character |
|:---|:---|:---|:---|
| **A** `method_a_lsh.py` | MinHash + LSH clustering of fixed-length windows | MinHash (32 hashes), LSH 8x4 bands, adaptive distinct counter -> HyperLogLog | merges *similar* traversals, not just identical ones |
| **B** `method_b_suffix.py` | prefix-bucketed generalised suffix array + LCP array | Bloom filter of frequent k-grams as an anti-monotone prefix gate | exact counts, longest exactly-repeated stretches |
| **C** `method_c_growth.py` | level-wise growth from frequent seeds | Count-Min pre-filter, Bloom gate on extension candidates | support re-measured every round; the only method that produces holes |

All three feed one **verification pass** that re-measures every candidate
against 100% of the trips. Whatever a method estimated while mining is a hint;
the support, distance, duration and speed that reach disk come from that pass.

### Where the approximations pay

`gate.py` builds a Count-Min Sketch of k-gram frequencies with `treeAggregate` —
partial sketches merge up a tree, so what crosses the network is a bounded
number of megabytes of counters rather than tens of millions of n-grams. The
sketch never underestimates, so anything it rules out is provably infrequent;
the survivors are then counted exactly. The frequent set goes into a Bloom
filter small enough to broadcast, and anti-monotonicity turns that filter into a
pruning gate for suffixes (Method B) and extension candidates (Method C).

Every structure is used only where its error runs in the safe direction. The
measured cost of each one lands in `output/stage3_benchmark.json` and on the
comparison deck.

### Choosing X

Support is anti-monotone in the threshold X, so the pipeline mines **once** at
the lowest threshold of interest and derives every higher one by filtering
measured supports. One cluster run answers the whole sweep — which is also how
the budget is kept. The sweep lands in `support_sweep` in both output files.

### On the longer configurations

A trip can only traverse a corridor of length L if the trip is itself at least L
long, so the trip-length distribution puts a ceiling on the popularity of any
long corridor that no algorithm can beat. Porto's bounding box is roughly
25 x 22 km and the median trip is under 4 km. `length_ceiling` in the results
file reports that bound for each configuration, so a short list at >= 20 km or
>= 40 km is a measured property of the data rather than a silent failure.

---

## Outputs

Written by `scripts/stage3/run_stage3.py` to `--output_dir` (a local path or a
`gs://` prefix — results from a cluster run land in the bucket and survive the
cluster being deleted):

| file | contents |
|:---|:---|
| `stage3_subroutes.json` | corridors, the six distance configurations, the X sweep, the length ceiling |
| `stage3_benchmark.json` | per-method scorecard, sketch statistics, runtimes |
| `stage3_anomalous_routes.json` | most unusual trips, novelty histogram, taxi-diversity cells |
| `stage3_run_provenance.json` | job id, cluster spec, driver-log URI for the cloud run |

Derived artefacts:

```bash
python tools/validate_results.py output/stage3_subroutes.json     # independent audit
python tools/build_stage3_notebook.py                             # Colab Enterprise demo
node   tools/build_methods_deck.js                                # methods comparison deck
```

The notebook and the deck are **generated from the results files**, so neither
can drift away from the run it describes. Regenerate both after every cluster
run.

---

## Verification

```bash
pytest tests/ -q                                # sketch guarantees, corridor geometry
python tools/validate_results.py <results.json> # re-derives every published claim
```

`validate_results.py` does not trust the pipeline: it re-reads the published
JSON and recomputes every length and tortuosity from the H3 cells themselves,
checks that no corridor visits a cell twice, that support never exceeds the trip
count, and that no column is a constant masquerading as a measurement.

---

## Layout

```
scripts/
  stage1_data_preparation.py        cleaning + features
  stage2_spatial_encoding.py        H3 encoding, res 8/9/10
  stage3/
    sketches.py                     CountMinSketch, BloomFilter, HyperLogLog, DistinctCounter
    corridors.py                    corridor model, geometry guards, support verification
    gate.py                         CMS pre-filter + Bloom broadcast
    method_a_lsh.py                 MinHash/LSH clustering
    method_b_suffix.py              distributed suffix array + LCP
    method_c_growth.py              verified level-wise growth
    anomalies.py                    unusual-route detection
    run_stage3.py                   orchestrator
    io_utils.py                     local / GCS output
  stage3_temporal_mining.py         morning / evening / night corridors
  stage5_ridge_elevation_routes.py  density-ridge route discovery (extra)
  generate_*.py                     maps and dashboards
  run_pipeline_dataproc.sh          all three stages on one cluster
tools/
  fetch_dataset.sh                  download the dataset into GCS
  make_synthetic_h3.py              ground-truth test data
  validate_results.py               independent audit
  build_subroute_maps.py            interactive corridor map generator
  build_stage3_notebook.py          Colab Enterprise notebook generator
  build_methods_deck.js             comparison deck generator
utils/
  results.py                        reads Stage 3 results for the 3D map builders
tests/                              unit tests
docs/                               stage reports
output/
  synthetic_run/                    ground-truth validation run — NOT Porto data
```

`output/` holds the Stage 1 and Stage 2 artefacts and, once the cluster run has
happened, the Stage 3 results. It deliberately contains **no** Stage 3 result
file yet: the only Stage 3 numbers currently in the repo live under
[`output/synthetic_run/`](output/synthetic_run), and that folder's README says
plainly that they come from generated test data with planted corridors, not
from Porto. Nothing in the repo should be presented as a Porto Stage 3 result
until `run_pipeline_dataproc.sh` has produced one.
