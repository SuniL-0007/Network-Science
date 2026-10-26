"""Per-run epidemic metrics, Monte Carlo aggregation, and CSV logging (spec §7).

Per run (`RunMetrics`, used as a Monte Carlo reducer inside workers):
  r_inf            final outbreak size: ever-infected / N (improvement 17a)
  r_inf_reachable  ever-infected / |dependency-reachable set of patient zero|
  t80              first tick with ever-infected >= 80% of the reachable set (NaN if never)
  t90_final        first tick with ever-infected >= 90% of the run's own final size (plateau)
  i_max, t_peak    peak simultaneous infections and its tick
  depth_max/mean   infection-tree depth (generation) from patient zero
  hop1_share       share of non-seed infections at depth 1; hop3plus_share at depth >= 3
  maint_share      share of non-seed infections via the maintainer-credential channel

Aggregates use bootstrap 95% CIs (outbreak sizes are bimodal, so normal CIs mislead) and
report the probability of a major outbreak separately from size given a major outbreak.
"""

from __future__ import annotations

import json
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import breadth_first_order

from src.config import METRICS_DIR
from src.sir_engine import MAINTAINER, SEED, ContagionModel, SimulationResult

RUN_METRICS = (
    "r_inf", "r_inf_reachable", "t80", "t90_final", "i_max", "i_max_frac", "t_peak", "duration",
    "depth_max", "depth_mean", "hop1_share", "hop3plus_share", "maint_share", "n_patched",
)


# =========================================================================== per run
@dataclass
class RunMetrics:
    """Callable reducer: SimulationResult -> dict of scalar metrics (+ optional curves)."""

    model: ContagionModel
    t80_frac: float = 0.80
    keep_curves: bool = False
    _adj: sp.csr_array | None = field(default=None, repr=False)
    _reach: dict = field(default_factory=dict, repr=False)

    def reachable(self, patient_zero: np.ndarray) -> int:
        """|patient zero ∪ nodes reachable from it| in G_contagion (cached per seed set)."""
        key = tuple(sorted(int(x) for x in patient_zero))
        if key not in self._reach:
            if self._adj is None:
                m = self.model
                self._adj = sp.csr_array((np.ones(len(m.indices)), m.indices, m.indptr), shape=(m.n, m.n))
            seen = np.zeros(self.model.n, dtype=bool)
            for s in key:
                if not seen[s]:
                    seen[breadth_first_order(self._adj, s, directed=True, return_predecessors=False)] = True
            self._reach[key] = int(seen.sum())
        return self._reach[key]

    def __call__(self, res: SimulationResult) -> dict:
        n = self.model.n
        infected = res.infection_time >= 0
        ever = int(infected.sum())
        n_reach = self.reachable(res.patient_zero)
        cum = np.bincount(res.infection_time[infected], minlength=res.duration + 1).cumsum()
        hit80 = np.flatnonzero(cum >= self.t80_frac * n_reach)
        t90 = int(np.flatnonzero(cum >= 0.9 * ever)[0])
        kids = res.channel > SEED
        n_kids = int(kids.sum())
        gens = res.generation[kids]

        out = {
            "n_nodes": n,
            "n_reachable": n_reach,
            "ever_infected": ever,
            "r_inf": ever / n,
            "r_inf_reachable": ever / n_reach,
            "t80": float(hit80[0]) if len(hit80) else math.nan,
            "t90_final": t90,
            "i_max": int(res.I.max()),
            "i_max_frac": float(res.I.max()) / n,
            "t_peak": int(np.argmax(res.I)),
            "duration": res.duration,
            "depth_max": int(res.generation.max()),
            "depth_mean": float(gens.mean()) if n_kids else 0.0,
            "hop1_share": float((gens == 1).mean()) if n_kids else math.nan,
            "hop3plus_share": float((gens >= 3).mean()) if n_kids else math.nan,
            "maint_share": float((res.channel[kids] == MAINTAINER).mean()) if n_kids else math.nan,
            "n_patched": int(res.n_patched.sum()),
            "n_maint_compromised": res.n_maint_compromised,
        }
        if self.keep_curves:
            out["_curves"] = np.stack([res.S, res.I, res.R]).astype(np.int32)
        return out


def runs_frame(results: Sequence[dict], tag: dict | None = None) -> tuple[pd.DataFrame, list]:
    """Rows of RunMetrics dicts -> DataFrame (+ list of curves split off)."""
    curves = [r.get("_curves") for r in results]
    rows = [{**(tag or {}), "run": i, **{k: v for k, v in r.items() if k != "_curves"}}
            for i, r in enumerate(results)]
    return pd.DataFrame(rows), curves


# =========================================================================== statistics
def bootstrap_ci(x, n_boot: int = 1000, level: float = 0.95, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the (nan-ignoring) mean."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return math.nan, math.nan
    if len(x) == 1 or np.all(x == x[0]):
        return float(x[0]), float(x[0])
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))


def summarize_runs(
    df: pd.DataFrame,
    by: Sequence[str],
    metrics: Sequence[str] = RUN_METRICS,
    major_frac: float = 0.05,
    n_boot: int = 1000,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per group: n_runs, p_major, r_inf_given_major, and mean/median/CI per metric."""
    rows = []
    for key, grp in df.groupby(list(by), sort=False, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        major = grp["r_inf"] >= major_frac
        row["n_runs"] = len(grp)
        row["p_major"] = float(major.mean())
        row["r_inf_given_major"] = float(grp.loc[major, "r_inf"].mean()) if major.any() else math.nan
        if "t80" in grp:
            row["frac_reached_t80"] = float(grp["t80"].notna().mean())
        for m in metrics:
            if m not in grp:
                continue
            x = grp[m].to_numpy(dtype=float)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                row[f"{m}_mean"] = float(np.nanmean(x)) if np.isfinite(x).any() else math.nan
                row[f"{m}_median"] = float(np.nanmedian(x)) if np.isfinite(x).any() else math.nan
            row[f"{m}_ci_lo"], row[f"{m}_ci_hi"] = bootstrap_ci(x, n_boot, seed=seed)
        rows.append(row)
    return pd.DataFrame(rows)


def paired_reduction(baseline, treated, n_boot: int = 1000, seed: int = 0) -> dict:
    """Relative reduction (mean_b - mean_t) / mean_b with a paired bootstrap CI.

    Run i of both arrays must share an origin and random stream (same MCJob seed). This is
    the spec's firebreak cascade reduction ΔR∞ when applied to r_inf.
    """
    b, t = np.asarray(baseline, float), np.asarray(treated, float)
    if b.shape != t.shape:
        raise ValueError("paired arrays must have equal length")
    if b.mean() == 0:
        return {"reduction": math.nan, "ci_lo": math.nan, "ci_hi": math.nan}
    idx = np.random.default_rng(seed).integers(0, len(b), size=(n_boot, len(b)))
    bb, tt = b[idx].mean(axis=1), t[idx].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        boots = (bb - tt) / bb
    boots = boots[np.isfinite(boots)]
    return {
        "reduction": float((b.mean() - t.mean()) / b.mean()),
        "ci_lo": float(np.quantile(boots, 0.025)),
        "ci_hi": float(np.quantile(boots, 0.975)),
    }


def curve_summary(curves: Sequence[np.ndarray], length: int) -> pd.DataFrame:
    """Per tick, for S/I/R: mean, 95% CI of the mean, and 2.5-97.5% run envelope.

    Each curve is a (3, T_i + 1) array; runs that ended early hold their final value.
    """
    stack = np.stack([
        c[:, :length] if c.shape[1] >= length
        else np.concatenate([c, np.repeat(c[:, -1:], length - c.shape[1], axis=1)], axis=1)
        for c in curves
    ]).astype(float)  # (runs, 3, length)
    mean = stack.mean(axis=0)
    se = stack.std(axis=0, ddof=1) / np.sqrt(len(stack)) if len(stack) > 1 else np.zeros_like(mean)
    lo, hi = np.quantile(stack, [0.025, 0.975], axis=0)
    rows = {"tick": np.arange(length)}
    for k, comp in enumerate("SIR"):
        rows[f"{comp}_mean"] = mean[k]
        rows[f"{comp}_ci_lo"] = mean[k] - 1.96 * se[k]
        rows[f"{comp}_ci_hi"] = mean[k] + 1.96 * se[k]
        rows[f"{comp}_p025"] = lo[k]
        rows[f"{comp}_p975"] = hi[k]
    return pd.DataFrame(rows)


def estimate_threshold(
    summary: pd.DataFrame,
    by: Sequence[str] = ("regime", "gamma"),
    metric: str = "r_inf_mean",
    level: float = 0.05,
) -> pd.DataFrame:
    """Empirical epidemic threshold per group: smallest beta where `metric` crosses `level`.

    Linear interpolation between grid points; tau_c = beta_c / gamma. NaN when the metric
    never crosses (always below: no epidemic; already above at the smallest beta: < grid).
    """
    rows = []
    for key, grp in summary.groupby(list(by), sort=False):
        key = key if isinstance(key, tuple) else (key,)
        g = grp.sort_values("beta")
        b, y = g["beta"].to_numpy(float), g[metric].to_numpy(float)
        above = np.flatnonzero(y >= level)
        if len(above) == 0 or above[0] == 0:
            beta_c = math.nan if len(above) == 0 else float(b[0])
            censored = "never" if len(above) == 0 else "below_grid"
        else:
            i = above[0]
            beta_c = float(b[i - 1] + (level - y[i - 1]) * (b[i] - b[i - 1]) / (y[i] - y[i - 1]))
            censored = ""
        row = dict(zip(by, key))
        gamma = row.get("gamma", math.nan)
        row.update(beta_c=beta_c, tau_c=beta_c / gamma if gamma else math.nan, censored=censored)
        rows.append(row)
    return pd.DataFrame(rows)


# =========================================================================== io
def write_tables(tables: dict[str, pd.DataFrame], prefix: str, out_dir: Path = METRICS_DIR,
                 meta: dict | None = None) -> dict[str, Path]:
    """Write each table to `<prefix>_<name>.csv` and optional `<prefix>_meta.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in tables.items():
        paths[name] = out_dir / f"{prefix}_{name}.csv"
        df.to_csv(paths[name], index=False)
    if meta is not None:
        paths["meta"] = out_dir / f"{prefix}_meta.json"
        paths["meta"].write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return paths
