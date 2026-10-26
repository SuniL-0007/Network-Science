# npm-sir-contagion

SIR epidemic modelling of self-propagating worms (Shai-Hulud style) across the npm
dependency network. The full spec is in [`ns-project-outline.md`](ns-project-outline.md),
and the agreed changes to it are in [`docs/spec-improvements.md`](docs/spec-improvements.md).

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
```

## Data (Milestone 1)

```bash
# Synthetic scale-free benchmark ecosystem -> data/raw/synthetic_n2000_s42.jsonl
python -m src.data_ingestion synthetic --nodes 2000 --seed 42

# Live npm crawl (registry.npmjs.org), optional deps.dev ecosystem-wide dependent counts
python -m src.data_ingestion crawl --max-nodes 10000 --max-depth 6 --dependents
python -m src.data_ingestion crawl --seeds my_seeds.txt --top-n 200   # .txt or Libraries.io .csv
```

Each snapshot is a JSONL file of `PackageRecord`s with a `.meta.json` sidecar. Every record
holds the package's dependency edges (u → v means u depends on v), with dependency type,
raw spec, and SemVer class. It also holds lifecycle hooks, provenance (from
`dist.attestations`), maintainers, and dependent count. HTTP responses are cached under
`data/raw/cache/`, so re-running a crawl is cheap.

## Graph & topology (Milestone 2)

```bash
# G_dep (u -> v: u depends on v) reversed into G_contagion (v -> u) -> data/processed/*_contagion.{pkl,graphml}
python -m src.graph_builder data/raw/synthetic_n2000_s42.jsonl            # add --include-dev for dev edges
python -m src.topology_analyzer data/processed/synthetic_n2000_s42_contagion.pkl
```

The analyzer writes three files to `results/metrics/`:

- `*_node_metrics.csv`: per package, out/in-degree, transitive dependents (blast radius),
  PageRank, betweenness, harmonic centrality, k-core and clustering.
- `*_topology_summary.json`: DAG/SCC structure, directed assortativity, power-law fits
  with lognormal/exponential likelihood-ratio tests, and spectral radius λ_max of the
  SemVer/hook-weighted contagion matrix.
- `*_node_groups.json`: super-spreaders, firebreak candidates, periphery, and the disjoint
  RQ1 origin groups (hub / bridge / mid-tier / leaf).

## SIR engines (Milestone 3)

```python
from src.config import SIRParams
from src.graph_builder import load_graph
from src.sir_engine import ContagionModel, make_policy, run_monte_carlo, run_ndlib_sir

g = load_graph("data/processed/synthetic_n2000_s42_contagion.pkl")
model = ContagionModel.from_graph(g)                      # compile once (CSR arrays)
params = SIRParams(beta=0.15, gamma=0.05)                 # + provenance_factor, beta_maintainer
runs = run_monte_carlo(model, params, ["pkg-00001"], n_runs=100, seed=0,
                       policy=make_policy(model, "hub", budget=10), n_jobs=4)
baseline = run_ndlib_sir(g, params, ["pkg-00001"], seed=0)  # homogeneous NDlib reference
```

Each `SimulationResult` holds S/I/R curves plus per-node infection/recovery time,
infector, channel (dependency vs. maintainer credentials) and infection-tree generation.

## Experiments & metrics (Milestone 4)

```bash
# Real npm: seeds = npm-high-impact top-dependent list (data/raw/seeds_high_impact_dependents.txt)
python -m src.data_ingestion crawl --seeds data/raw/seeds_high_impact_dependents.txt --max-nodes 10000 --dependents --out data/raw/npm_hi_n10k.jsonl

# RQ1-RQ3 Monte Carlo; --maintainer adds credential-channel variants to RQ1/RQ2
python -m src.experiments data/processed/synthetic_n2000_s42_contagion.pkl --runs 100 --rq2-runs 50 --jobs 6 --maintainer 0.01 0.05
```

Outputs go to `results/metrics/<tag>_rq<k>_*.csv` (+ `_meta.json` with the full config):

| RQ | Tables |
|---|---|
| 1 | `runs` (one row per run), `summary` (per origin group), `per_origin`, `curves` (S/I/R mean, CI, 2.5–97.5% envelope per tick) |
| 2 | `runs`, `summary` (regime × β × γ), `thresholds` (empirical β_c, τ_c vs. spectral τ_c), `regimes` (achieved pin/provenance shares) |
| 3 | `runs`, `summary` (strategy × response delay × budget), `reductions` (paired ΔR∞ with bootstrap CI), `info` |

Per-run metrics: R∞ (ever infected / N), R∞ over the reachable set, T₈₀, I_max, t_peak, cascade
depth, hop-1 / hop-3+ shares, maintainer-channel share, nodes patched. Summaries report
bootstrap 95% CIs and the probability of a major outbreak (R∞ ≥ 5%). Configurations that share
a seed are paired (same origin draw and random stream per run).

## Figures & CLI (Milestone 5)

```bash
python main.py --mode synthetic --nodes 2000 --runs 50 --jobs 6          # generate -> ... -> figures
python main.py --mode snapshot --snapshot data/raw/npm_hi_n10k.jsonl --maintainer 0.01 0.05 --jobs 6
python main.py --mode crawl --seeds data/raw/seeds_high_impact_dependents.txt --max-nodes 10000 --dependents
python main.py --figures-only --tag npm_hi_n10k_contagion                # re-render from existing CSVs
python main.py --mode synthetic --nodes 300 --runs 3 --quick              # smoke run (small grids)
```

Figures are written to `results/figures/<tag>/` as 300 DPI PNG plus vector PDF (embedded TrueType):

| Figure | Content |
|---|---|
| `fig1_degree_distribution` | log-log CCDF of dependents/dependencies with fitted α from x_min |
| `fig2_sir_epidemic_curves` | S/I/R share (log) per origin group: mean, 95% CI, 2.5–97.5% of runs |
| `fig3_superspreader_comparison` | R∞ and T₈₀ violins + boxes per origin group, per credential-channel setting |
| `fig4_semver_phase_transition` | R∞ heatmaps over β×γ per regime, with empirical β_c markers |
| `fig5_firebreak_immunization` | R∞ vs. budget per strategy (95% CI), one panel per response delay |

## Tests

```bash
.venv/Scripts/python -m pytest              # all tests, including one live-registry smoke test
.venv/Scripts/python -m pytest -m "not network"   # offline only
```

## Status

- [x] M1: Setup & data ingestion
- [x] M2: Graph builder (contagion reversal) & topology analysis
- [x] M3: SIR engines
- [x] M4: Experiments & metrics
- [x] M5: Visualization & CLI
