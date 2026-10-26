"""Experiment runners for the three research questions (spec §6).

RQ1  origin topology: outbreaks seeded at each node of the hub / bridge / mid / leaf groups.
RQ2  ecosystem regimes (status quo, strict lockfile, scripts disabled, hardened) across a
     (beta, gamma) grid, with empirical epidemic thresholds per regime.
RQ3  interventions against a hub outbreak at budgets B (fraction of N per tick): random and
     hub-targeted patching, plus proactive immunization (betweenness firebreaks, hubs,
     acquaintance) at a matched total budget K = mean nodes treated by hub patching.

Configurations that share a seed are paired: run i has the same origin and random stream
across strategies/regimes, so differences are not sampling noise.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import zlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from src.config import (
    METRICS_DIR,
    SEMVER_BETA_MODIFIER,
    ExperimentConfig,
    SIRParams,
    TopologyConfig,
)
from src.graph_builder import load_graph
from src.metrics_logger import (
    RunMetrics,
    curve_summary,
    estimate_threshold,
    paired_reduction,
    runs_frame,
    summarize_runs,
    write_tables,
)
from src.sir_engine import ContagionModel, MCJob, make_policy, run_batch
from src.topology_analyzer import analyze, classify_nodes, export_profile

log = logging.getLogger(__name__)

ORIGIN_GROUPS = ("origin_hub", "origin_bridge", "origin_mid", "origin_leaf")


def seed_for(cfg: ExperimentConfig, *key) -> int:
    """Stable per-configuration seed (identical keys -> paired runs)."""
    return (cfg.seed * 1_000_003 + zlib.crc32("|".join(map(str, key)).encode())) % 2**63


# =========================================================================== context
@dataclass
class ExperimentContext:
    tag: str
    graph: nx.DiGraph
    model: ContagionModel
    nodes: pd.DataFrame  # topology node metrics, indexed by package name
    groups: dict
    topology: dict  # topology summary

    @classmethod
    def from_graph(cls, graph: nx.DiGraph | str | Path, tag: str | None = None,
                   topo_cfg: TopologyConfig = TopologyConfig(), metrics_dir: Path = METRICS_DIR,
                   use_cache: bool = True) -> ExperimentContext:
        """Compile the model and load (or compute and export) the topology profile."""
        if not isinstance(graph, nx.DiGraph):
            tag = tag or Path(graph).stem
            graph = load_graph(graph)
        tag = tag or "graph"
        paths = {k: metrics_dir / f"{tag}_{k}" for k in
                 ("node_metrics.csv", "node_groups.json", "topology_summary.json")}
        if use_cache and all(p.exists() for p in paths.values()):
            # npm has packages named "null", "nan", "true"...: only empty cells are missing values
            nodes = pd.read_csv(paths["node_metrics.csv"], index_col="name", dtype={"name": str},
                                keep_default_na=False, na_values=[""])
            groups = json.loads(paths["node_groups.json"].read_text(encoding="utf-8"))
            topology = json.loads(paths["topology_summary.json"].read_text(encoding="utf-8"))
            if set(nodes.index) != set(map(str, graph.nodes)):
                raise ValueError(f"cached topology for {tag!r} does not match the graph; use use_cache=False")
        else:
            profile = analyze(graph, topo_cfg)
            groups = classify_nodes(graph, profile.nodes, topo_cfg)
            export_profile(profile, groups, tag, metrics_dir, topo_cfg)
            nodes, topology = profile.nodes, profile.summary
        return cls(tag, graph, ContagionModel.from_graph(graph), nodes, groups, topology)

    def draw_from(self, group: str):
        """Patient-zero sampler: one node drawn uniformly from `group` per run."""
        pool = list(self.groups[group])
        if not pool:
            raise ValueError(f"node group {group!r} is empty")
        return lambda rng: [pool[int(rng.integers(len(pool)))]]


def _reducer(ctx: ExperimentContext, cfg: ExperimentConfig, curves: bool = False) -> RunMetrics:
    return RunMetrics(ctx.model, t80_frac=cfg.t80_frac, keep_curves=curves)


def _frame(jobs: list[MCJob], results: list[list]) -> tuple[pd.DataFrame, list[list]]:
    frames, curves = [], []
    for job, res in zip(jobs, results):
        df, c = runs_frame(res, job.tag)
        frames.append(df)
        curves.append(c)
    return pd.concat(frames, ignore_index=True), curves


# =========================================================================== RQ1
def rq1_scenarios(cfg: ExperimentConfig) -> list[tuple[str, SIRParams]]:
    """Named parameter sets for RQ1: `cfg.rq1_scenarios` if given, else rq1_params x beta_m."""
    if cfg.rq1_scenarios:
        return list(cfg.rq1_scenarios)
    return [(f"beta_m={bm:g}", replace(cfg.rq1_params, beta_maintainer=bm)) for bm in cfg.rq1_beta_maintainer]


def run_rq1(ctx: ExperimentContext, cfg: ExperimentConfig = ExperimentConfig()) -> dict[str, pd.DataFrame]:
    """Super-spreader effect: `n_runs` outbreaks per origin node in each origin group."""
    jobs = []
    for scenario, params in rq1_scenarios(cfg):
        for group in ORIGIN_GROUPS:
            for origin in ctx.groups[group]:
                jobs.append(MCJob(params, [origin], cfg.n_runs, seed_for(cfg, "rq1", origin),
                                  tag={"scenario": scenario, "beta_maintainer": params.beta_maintainer,
                                       "group": group.removeprefix("origin_"), "origin": origin}))
    log.info("RQ1: %d configurations x %d runs", len(jobs), cfg.n_runs)
    results = run_batch(status_quo_model(ctx, cfg), jobs, _reducer(ctx, cfg, curves=True), cfg.n_jobs)
    runs, curves = _frame(jobs, results)

    by = ["scenario", "beta_maintainer", "group"]
    summary = summarize_runs(runs, by, major_frac=cfg.major_outbreak_frac, n_boot=cfg.n_boot)
    per_origin = summarize_runs(runs, by + ["origin"], metrics=("r_inf", "t80"),
                                major_frac=cfg.major_outbreak_frac, n_boot=cfg.n_boot)
    curve_frames = []
    length = max(p.t_max for _, p in rq1_scenarios(cfg)) + 1
    flat = [c for job_curves in curves for c in job_curves]  # aligned with runs' row index
    for (scenario, bm, group), idx in runs.groupby(by, sort=False).groups.items():
        sub = curve_summary([flat[i] for i in idx], length)
        sub.insert(0, "group", group)
        sub.insert(0, "beta_maintainer", bm)
        sub.insert(0, "scenario", scenario)
        curve_frames.append(sub)
    return {"runs": runs, "summary": summary, "per_origin": per_origin,
            "curves": pd.concat(curve_frames, ignore_index=True)}


# =========================================================================== RQ2
@dataclass(frozen=True)
class Regime:
    name: str
    pin_fraction: float | None = None  # convert loose edges to exact until this share is pinned
    hook_reduction: float = 0.0  # static hook mode: cut of the hook boost (w_hook - 1)
    scripts_blocked_frac: float = 0.0  # injected hook mode: share of packages blocking scripts
    provenance_top: float = 0.0  # extra provenance on the top fraction of hubs
    provenance_factor: float = 1.0


def default_regimes(cfg: ExperimentConfig) -> list[Regime]:
    base, off = cfg.baseline_scripts_blocked, cfg.scripts_disabled_frac
    return [
        Regime("status_quo", scripts_blocked_frac=base),
        Regime("strict_lockfile", pin_fraction=cfg.pin_fraction, scripts_blocked_frac=base),
        Regime("scripts_disabled", hook_reduction=cfg.hook_reduction, scripts_blocked_frac=off),
        Regime("hardened", pin_fraction=cfg.pin_fraction, hook_reduction=cfg.hook_reduction,
               scripts_blocked_frac=off, provenance_top=cfg.provenance_top,
               provenance_factor=cfg.provenance_factor),
    ]


def apply_regime(model: ContagionModel, regime: Regime, base: SIRParams,
                 seed: int = 0, node_seed: int = 0) -> tuple[ContagionModel, dict]:
    """Model with the regime's edge/node overrides, plus SIRParams overrides.

    Status quo keeps the observed SemVer mix. Pinning converts each loose (non-exact) edge
    to exact with the probability that brings the exact share to `pin_fraction`, so already
    pinned edges stay pinned. The conversion is one fixed draw per regime. Script-blocking
    packages are the nodes whose fixed uniform draw (from `node_seed`) falls below the
    regime's share, so a 10% blocking set is nested inside a 70% one.
    """
    rng = np.random.default_rng(seed)
    w = model.w_semver.copy()
    exact = SEMVER_BETA_MODIFIER["exact"]
    if regime.pin_fraction is not None and len(w):
        is_exact = np.isclose(w, exact)
        loose = np.flatnonzero(~is_exact & (w > 0))
        e0 = is_exact.mean()
        if e0 < regime.pin_fraction and len(loose):
            p = min(1.0, (regime.pin_fraction - e0) * len(w) / len(loose))
            w[loose[rng.random(len(loose)) < p]] = exact

    prov = model.provenance.copy()
    if regime.provenance_top > 0:
        k = max(1, math.ceil(regime.provenance_top * model.n))
        prov[np.argsort(-model.out_degree, kind="stable")[:k]] = True

    blocked = np.random.default_rng(node_seed).random(model.n) < regime.scripts_blocked_frac

    params = {
        "hook_multiplier": 1.0 + (base.hook_multiplier - 1.0) * (1.0 - regime.hook_reduction),
        "provenance_factor": regime.provenance_factor,
    }
    return model.with_overrides(w_semver=w, provenance=prov, scripts_blocked=blocked), params


def status_quo_model(ctx: ExperimentContext, cfg: ExperimentConfig) -> ContagionModel:
    """The base model with the status-quo share of script-blocking packages (RQ1, RQ3)."""
    regime = Regime("status_quo", scripts_blocked_frac=cfg.baseline_scripts_blocked)
    model, _ = apply_regime(ctx.model, regime, cfg.rq1_params, node_seed=seed_for(cfg, "scripts"))
    return model


def run_rq2(ctx: ExperimentContext, cfg: ExperimentConfig = ExperimentConfig(),
            regimes: list[Regime] | None = None) -> dict[str, pd.DataFrame]:
    """SemVer / lifecycle-script risk across a (beta, gamma) grid per regime."""
    regimes = regimes or default_regimes(cfg)
    base = cfg.rq1_params
    models, overrides, regime_rows = {}, {}, []
    for r in regimes:
        models[r.name], overrides[r.name] = apply_regime(ctx.model, r, base, seed_for(cfg, "regime", r.name),
                                                         node_seed=seed_for(cfg, "scripts"))
        m = models[r.name]
        regime_rows.append({**asdict(r), **overrides[r.name], "hook_mode": base.hook_mode,
                            "exact_share": float(np.isclose(m.w_semver, SEMVER_BETA_MODIFIER["exact"]).mean()),
                            "provenance_share": float(m.provenance.mean()),
                            "scripts_blocked_share": float(m.scripts_blocked.mean())})

    origin = ctx.draw_from("origin_hub")
    jobs = []
    for r in regimes:
        for bm in cfg.rq2_beta_maintainer:
            for beta in cfg.rq2_betas:
                for gamma in cfg.rq2_gammas:
                    params = replace(base, beta=beta, gamma=gamma, beta_maintainer=bm, **overrides[r.name])
                    jobs.append(MCJob(params, origin, cfg.rq2_n_runs, seed_for(cfg, "rq2", beta, gamma, bm),
                                      model_key=r.name,
                                      tag={"regime": r.name, "beta_maintainer": bm, "beta": beta,
                                           "gamma": gamma, "tau": beta / gamma}))
    log.info("RQ2: %d configurations x %d runs", len(jobs), cfg.rq2_n_runs)
    runs, _ = _frame(jobs, run_batch(models, jobs, _reducer(ctx, cfg), cfg.n_jobs))
    by = ["regime", "beta_maintainer", "beta", "gamma", "tau"]
    summary = summarize_runs(runs, by, metrics=("r_inf", "t80", "i_max_frac", "t_peak", "depth_max"),
                             major_frac=cfg.major_outbreak_frac, n_boot=cfg.n_boot)
    thresholds = estimate_threshold(summary, by=("regime", "beta_maintainer", "gamma"),
                                    level=cfg.major_outbreak_frac)
    thresholds["tau_c_theory"] = ctx.topology.get("tau_c_theory", math.nan)
    return {"runs": runs, "summary": summary, "thresholds": thresholds,
            "regimes": pd.DataFrame(regime_rows)}


# =========================================================================== RQ3
def _acquaintance_sampler(graph: nx.DiGraph, nodes: list, k: int):
    """Acquaintance immunization (Cohen et al. 2003): random node -> immunize a random
    neighbour (either direction). Needs no global knowledge; biased towards hubs."""
    nbrs = [list(set(graph.successors(u)) | set(graph.predecessors(u))) for u in nodes]
    has = [i for i, nb in enumerate(nbrs) if nb]

    def draw(rng):
        chosen: set = set()
        for _ in range(50 * max(k, 1)):
            if len(chosen) >= k or not has:
                break
            nb = nbrs[has[int(rng.integers(len(has)))]]
            chosen.add(nb[int(rng.integers(len(nb)))])
        return sorted(chosen)
    return draw


def run_rq3(ctx: ExperimentContext, cfg: ExperimentConfig = ExperimentConfig()) -> dict[str, pd.DataFrame]:
    """Patching vs. proactive immunization at equal total budget, against a hub outbreak.

    Phase 1 runs no-intervention and reactive policies (B nodes/tick). Phase 2 immunizes
    K nodes at t=0, with K = mean total nodes treated by hub patching at the same B and
    response delay (the delay only changes K for proactive strategies).
    """
    model, params = status_quo_model(ctx, cfg), cfg.rq3_params
    origin = ctx.draw_from("origin_hub")
    seed = seed_for(cfg, "rq3")  # shared by every strategy -> paired runs
    budgets = sorted({max(1, round(f * model.n)) for f in cfg.rq3_budget_fracs})
    reducer = _reducer(ctx, cfg)

    def job(strategy, b, d, k=0, policy=None, immunized=()):
        p = replace(params, recovery_start=d) if cfg.rq3_couple_recovery else params
        return MCJob(p, origin, cfg.n_runs, seed, immunized, policy,
                     tag={"strategy": strategy, "delay": d, "budget": b, "budget_frac": b / model.n,
                          "k_immunized": k})

    delays = cfg.rq3_response_delays
    phase1 = [job("none", 0, d) for d in delays]  # natural patching also waits for detection
    for d in delays:
        for b in budgets:
            phase1.append(job("random_patch", b, d, policy=make_policy(model, "random", b, start_tick=d)))
            phase1.append(job("hub_patch", b, d, policy=make_policy(model, "hub", b, start_tick=d)))
    log.info("RQ3 phase 1: %d configurations x %d runs", len(phase1), cfg.n_runs)
    runs1, _ = _frame(phase1, run_batch(model, phase1, reducer, cfg.n_jobs))

    by_btw = ctx.nodes["betweenness"].sort_values(ascending=False, kind="stable").index.tolist()
    by_deg = [model.nodes[i] for i in np.argsort(-model.out_degree, kind="stable")]
    phase2 = []
    for d in delays:
        for b in budgets:
            hub = runs1[(runs1["strategy"] == "hub_patch") & (runs1["budget"] == b) & (runs1["delay"] == d)]
            k = max(1, int(round(hub["n_patched"].mean())))
            phase2.append(job("firebreak_immunize", b, d, k, immunized=by_btw[:k]))
            phase2.append(job("hub_immunize", b, d, k, immunized=by_deg[:k]))
            phase2.append(job("acquaintance_immunize", b, d, k,
                              immunized=_acquaintance_sampler(ctx.graph, list(model.nodes), k)))
    log.info("RQ3 phase 2: %d configurations x %d runs", len(phase2), cfg.n_runs)
    runs2, _ = _frame(phase2, run_batch(model, phase2, reducer, cfg.n_jobs))

    runs = pd.concat([runs1, runs2], ignore_index=True)
    summary = summarize_runs(runs, ["strategy", "delay", "budget", "budget_frac", "k_immunized"],
                             metrics=("r_inf", "t80", "i_max_frac", "n_patched"),
                             major_frac=cfg.major_outbreak_frac, n_boot=cfg.n_boot)
    base = {d: g.sort_values("run")["r_inf"].to_numpy()
            for d, g in runs[runs["strategy"] == "none"].groupby("delay")}
    red_rows = []
    treated = runs[runs["strategy"] != "none"]
    for (strategy, d, b), grp in treated.groupby(["strategy", "delay", "budget"], sort=False):
        red = paired_reduction(base[d], grp.sort_values("run")["r_inf"].to_numpy(), cfg.n_boot)
        red_rows.append({"strategy": strategy, "delay": d, "budget": b, "budget_frac": b / model.n,
                         "k_immunized": int(grp["k_immunized"].iloc[0]),
                         "delta_r_inf": red["reduction"], "delta_r_inf_ci_lo": red["ci_lo"],
                         "delta_r_inf_ci_hi": red["ci_hi"]})
    fb = set(ctx.groups.get("firebreak_candidates", []))
    meta = {"firebreak_candidates": len(fb),
            "firebreak_hub_overlap": len(fb & set(ctx.groups.get("super_spreaders", [])))}
    return {"runs": runs, "summary": summary, "reductions": pd.DataFrame(red_rows),
            "info": pd.DataFrame([meta])}


# =========================================================================== orchestration
RUNNERS = {1: run_rq1, 2: run_rq2, 3: run_rq3}


def run_experiments(ctx: ExperimentContext, rqs=(1, 2, 3), cfg: ExperimentConfig = ExperimentConfig(),
                    out_dir: Path = METRICS_DIR) -> dict[int, dict[str, pd.DataFrame]]:
    """Run the selected RQs and write `<tag>_rq<k>_<table>.csv` plus a meta JSON each."""
    out = {}
    for k in rqs:
        tables = RUNNERS[k](ctx, cfg)
        meta = {"tag": ctx.tag, "rq": k, "n_nodes": ctx.model.n, "config": asdict(cfg)}
        paths = write_tables(tables, f"{ctx.tag}_rq{k}", out_dir, meta)
        log.info("RQ%d written: %s", k, ", ".join(p.name for p in paths.values()))
        out[k] = tables
    return out


def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Run RQ1-RQ3 Monte Carlo experiments on a contagion graph.")
    p.add_argument("graph", type=Path, help="data/processed/*_contagion.pkl")
    p.add_argument("--rq", type=int, nargs="+", default=[1, 2, 3], choices=[1, 2, 3])
    p.add_argument("--runs", type=int, default=ExperimentConfig.n_runs)
    p.add_argument("--rq2-runs", type=int, default=ExperimentConfig.rq2_n_runs)
    p.add_argument("--jobs", type=int, default=1, help="worker processes")
    p.add_argument("--maintainer", type=float, nargs="*", default=[],
                   help="extra beta_maintainer values for RQ1/RQ2 (credential channel)")
    p.add_argument("--seed", type=int, default=ExperimentConfig.seed)
    p.add_argument("--tag", help="output prefix (default: graph file stem)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bm = (0.0, *args.maintainer)
    cfg = ExperimentConfig(n_runs=args.runs, rq2_n_runs=args.rq2_runs, n_jobs=args.jobs, seed=args.seed,
                           rq1_beta_maintainer=bm, rq2_beta_maintainer=bm)
    ctx = ExperimentContext.from_graph(args.graph, args.tag)
    run_experiments(ctx, args.rq, cfg)


if __name__ == "__main__":
    _cli()
