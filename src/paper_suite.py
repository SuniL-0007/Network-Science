"""Frozen settings and the one-command run that produces every number in the paper.

Time unit: 1 tick = 1 hour. Calibrated scenarios come from src/calibration.py on the
high-impact 10k graph (results/metrics/npm_hi_n10k_contagion_calibration.json):

  SH1_calibrated  beta=0.02  beta_m=0.02  gamma=0.10  cap=20   patching from t=24 h
  SH2_calibrated  beta=0.20  beta_m=0.10  gamma=0.05  cap=100  patching from t=0

Parts (each writes <tag>_rq<k>_*.csv to results/metrics/):
  main         npm 10k + synthetic seed 42: RQ1-RQ3
  seeds        synthetic ensemble, seeds 1-5: RQ1-RQ3
  sizes        npm 5k and full closure (14,624 after spam cleaning): RQ1-RQ3
  null         5 degree-preserving rewirings of npm 10k: RQ1, RQ3
  sensitivity  RQ1, RQ3 around SH1 on npm 10k: beta x gamma (50 runs per configuration)

Usage:  python -m src.paper_suite all --jobs 7
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, replace
from pathlib import Path

from src.config import METRICS_DIR, PROCESSED_DIR, RAW_DIR, ExperimentConfig, SIRParams
from src.data_ingestion import load_records
from src.experiments import ExperimentContext, run_experiments
from src.graph_builder import build_from_records, save_graph
from src.robustness import run_null_models, run_sample_sizes, run_sensitivity, run_synthetic_ensemble

log = logging.getLogger(__name__)

T_MAX = 24 * 14  # two weeks of hourly ticks
SH1 = SIRParams(hook_mode="injected", beta=0.02, gamma=0.10, beta_maintainer=0.02,
                maintainer_publish_cap=20, recovery_start=24, t_max=T_MAX)
SH2 = SIRParams(hook_mode="injected", beta=0.20, gamma=0.05, beta_maintainer=0.10,
                maintainer_publish_cap=100, recovery_start=0, t_max=T_MAX)
SPEC = SIRParams(hook_mode="injected", maintainer_publish_cap=20)  # spec beta=0.15, gamma=0.05
SCENARIOS = (
    ("spec_reference", SPEC),
    ("dependency_only", replace(SH1, beta_maintainer=0.0)),
    ("SH1_calibrated", SH1),
    ("SH2_calibrated", SH2),
)

NPM_10K = RAW_DIR / "npm_hi_n10k.jsonl"
NPM_5K = RAW_DIR / "npm_hi_n5k.jsonl"
NPM_FULL = RAW_DIR / "npm_hi_n14660.jsonl"


def paper_config(n_jobs: int = 1, **overrides) -> ExperimentConfig:
    cfg = ExperimentConfig(
        n_runs=100,
        rq2_n_runs=50,
        n_jobs=n_jobs,
        rq1_scenarios=SCENARIOS,
        rq1_params=SPEC,  # RQ2 base: stationary patching for threshold estimation
        rq2_beta_maintainer=(0.0, SH1.beta_maintainer, SH2.beta_maintainer),
        rq3_params=SH1,
        rq3_response_delays=(1, 6, 12, 24, 48),
    )
    return replace(cfg, **overrides)


def _graph_path(snapshot: Path) -> Path:
    """Build (with spam cleaning) and save the contagion graph for a snapshot."""
    _, g = build_from_records(load_records(snapshot))
    return save_graph(g, PROCESSED_DIR / f"{snapshot.stem}_contagion", graphml=False)


def part_main(cfg: ExperimentConfig) -> None:
    for path in (_graph_path(NPM_10K), PROCESSED_DIR / "synthetic_n2000_s42_contagion.pkl"):
        ctx = ExperimentContext.from_graph(path, use_cache=False)
        run_experiments(ctx, (1, 2, 3), cfg)


# Robustness parts do not need RQ1 curves (fig2 uses the main runs); dropping them saves memory.
def part_seeds(cfg: ExperimentConfig) -> None:
    run_synthetic_ensemble([1, 2, 3, 4, 5], 2000, replace(cfg, keep_curves=False))


def part_sizes(cfg: ExperimentConfig) -> None:
    run_sample_sizes([NPM_5K, NPM_FULL], replace(cfg, keep_curves=False))


def part_null(cfg: ExperimentConfig) -> None:
    run_null_models(_graph_path(NPM_10K), 5, replace(cfg, keep_curves=False), rqs=(1, 3))


SENSITIVITY_RUNS = 50  # half the main run count: enough to rank strategies, halves the compute


def part_sensitivity(cfg: ExperimentConfig) -> None:
    run_sensitivity(_graph_path(NPM_10K), [0.01, 0.02, 0.05], [0.05, 0.1, 0.2],
                    replace(cfg, keep_curves=False, n_runs=SENSITIVITY_RUNS), base=SH1)


def part_credential(cfg: ExperimentConfig) -> None:
    """RQ2b on the main npm graph: critical beta_m per regime (credential channel)."""
    ctx = ExperimentContext.from_graph(PROCESSED_DIR / "npm_hi_n10k_contagion.pkl")
    run_experiments(ctx, ("2b",), cfg)


PARTS = {"main": part_main, "credential": part_credential, "seeds": part_seeds, "sizes": part_sizes, "null": part_null,
         "sensitivity": part_sensitivity}


def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Run the frozen paper experiment suite.")
    p.add_argument("parts", nargs="+", choices=[*PARTS, "all"])
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--runs", type=int, help="override Monte Carlo runs (smoke tests)")
    p.add_argument("--resume", action="store_true", help="skip RQs whose tables already exist")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)

    over = {"n_runs": args.runs, "rq2_n_runs": args.runs} if args.runs else {}
    if args.resume:
        over["skip_existing"] = True
    cfg = paper_config(args.jobs, **over)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (METRICS_DIR / "paper_config.json").write_text(json.dumps(asdict(cfg), indent=2, default=str), encoding="utf-8")
    parts = list(PARTS) if "all" in args.parts else args.parts
    for name in parts:
        t0 = time.perf_counter()
        log.info("=== paper part: %s ===", name)
        PARTS[name](cfg)
        log.info("=== %s done in %.1f min ===", name, (time.perf_counter() - t0) / 60)


if __name__ == "__main__":
    _cli()
