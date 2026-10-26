"""Calibrate the credential channel and patching rates against the Shai-Hulud waves.

Time unit: 1 tick = 1 hour. Targets come from docs/incident-notes.md (section 7):

  wave  publish cap  detection lag  plateau (90% of compromised versions)
  SH1   20           ~24 h          ~37 h
  SH2   100          ~0 h           ~13.4 h

and, for both waves, most compromised packages were produced by stolen-token republishing
(SH2: ~570 of ~800 compromised packages have no dependents), which we target as a
maintainer-channel share of 0.75. Outbreaks start at a uniformly random package; plateau
and channel share are measured on major outbreaks (>= `major_min` packages), since the
observed waves are by definition outbreaks that took off.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import METRICS_DIR, ExperimentConfig, SIRParams
from src.experiments import ExperimentContext, seed_for, status_quo_model
from src.metrics_logger import RunMetrics, runs_frame
from src.sir_engine import MCJob, run_batch

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WaveTarget:
    name: str
    publish_cap: int
    detection_tick: int
    plateau_t90: float
    maint_share: float = 0.75


WAVES = (WaveTarget("SH1", 20, 24, 37.0), WaveTarget("SH2", 100, 0, 13.4))


def loss(t90: float, maint_share: float, target: WaveTarget) -> float:
    """Squared log-error on plateau time + squared (scaled) error on channel share."""
    if not (t90 > 0 and np.isfinite(maint_share)):
        return math.inf
    return math.log(t90 / target.plateau_t90) ** 2 + ((maint_share - target.maint_share) / 0.25) ** 2


def calibrate(ctx: ExperimentContext, cfg: ExperimentConfig, betas, beta_ms, gammas,
              n_runs: int = 40, major_min: int = 20, waves=WAVES) -> pd.DataFrame:
    model = status_quo_model(ctx, cfg)
    nodes = list(model.nodes)
    origin = lambda rng: [nodes[int(rng.integers(len(nodes)))]]  # noqa: E731
    base = replace(cfg.rq1_params, t_max=24 * 14)  # two weeks of hourly ticks
    jobs = []
    for wave, beta, bm, gamma in itertools.product(waves, betas, beta_ms, gammas):
        p = replace(base, beta=beta, beta_maintainer=bm, gamma=gamma,
                    maintainer_publish_cap=wave.publish_cap, recovery_start=wave.detection_tick)
        jobs.append(MCJob(p, origin, n_runs, seed_for(cfg, "calib", beta, bm, gamma),
                          tag={"wave": wave.name, "beta": beta, "beta_maintainer": bm, "gamma": gamma}))
    log.info("calibration: %d configurations x %d runs", len(jobs), n_runs)
    results = run_batch(model, jobs, RunMetrics(model), cfg.n_jobs)

    rows = []
    targets = {w.name: w for w in waves}
    for job, res in zip(jobs, results):
        df, _ = runs_frame(res, job.tag)
        major = df[df["ever_infected"] >= major_min]
        t90 = float(major["t90_final"].median()) if len(major) else math.nan
        share = float(major["maint_share"].mean()) if len(major) else math.nan
        rows.append({**job.tag, "p_major": len(major) / len(df), "n_major": len(major),
                     "t90_median": t90, "maint_share_mean": share,
                     "size_median": float(major["ever_infected"].median()) if len(major) else math.nan,
                     "maint_compromised_median": float(major["n_maint_compromised"].median()) if len(major) else math.nan,
                     "loss": loss(t90, share, targets[job.tag["wave"]]) if len(major) >= 5 else math.inf})
    return pd.DataFrame(rows).sort_values(["wave", "loss"]).reset_index(drop=True)


def best_per_wave(grid: pd.DataFrame) -> dict:
    out = {}
    for wave, g in grid.groupby("wave"):
        top = g.nsmallest(1, "loss").iloc[0]
        out[wave] = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v)
                     for k, v in top.items()}
    return out


def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Calibrate beta, beta_maintainer and gamma to Shai-Hulud.")
    p.add_argument("graph", type=Path)
    p.add_argument("--runs", type=int, default=40)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--betas", type=float, nargs="+", default=[0.005, 0.01, 0.02, 0.05, 0.1])
    p.add_argument("--beta-ms", type=float, nargs="+", default=[0.02, 0.05, 0.1, 0.2, 0.5, 1.0])
    p.add_argument("--gammas", type=float, nargs="+", default=[0.05, 0.1, 0.2, 0.4])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = ExperimentConfig(n_jobs=args.jobs)
    ctx = ExperimentContext.from_graph(args.graph)
    grid = calibrate(ctx, cfg, args.betas, args.beta_ms, args.gammas, args.runs)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    grid.to_csv(METRICS_DIR / f"{ctx.tag}_calibration_grid.csv", index=False)
    best = best_per_wave(grid)
    meta = {"targets": [asdict(w) for w in WAVES], "best": best, "tick": "1 hour",
            "grid": {"betas": args.betas, "beta_ms": args.beta_ms, "gammas": args.gammas, "runs": args.runs}}
    (METRICS_DIR / f"{ctx.tag}_calibration.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for wave, b in best.items():
        log.info("%s best: beta=%g beta_m=%g gamma=%g -> t90=%.1f h, maint_share=%.2f, p_major=%.2f, loss=%.3f",
                 wave, b["beta"], b["beta_maintainer"], b["gamma"], b["t90_median"], b["maint_share_mean"],
                 b["p_major"], b["loss"])


if __name__ == "__main__":
    _cli()
