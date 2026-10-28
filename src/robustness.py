"""Robustness suite for the paper: null models, synthetic ensembles, sample sizes, sensitivity.

null         degree-preserving rewirings of a contagion graph (Maslov & Sneppen 2002):
             in/out degrees and the multiset of edge attributes are kept, structure is not
seeds        an ensemble of synthetic graphs (different generator seeds)
sizes        npm snapshots of different crawl sizes (e.g. 5k / 10k / 20k)
sensitivity  RQ1 and RQ3 over a (beta, gamma) grid on one graph

Every experiment writes the usual `<tag>_rq<k>_*.csv` tables, so the paper scripts can
pool them by tag prefix.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

import networkx as nx
import numpy as np

from src.config import METRICS_DIR, PROCESSED_DIR, ExperimentConfig, SIRParams, SyntheticConfig
from src.data_ingestion import generate_synthetic_records, load_records
from src.experiments import ExperimentContext, rq_done, run_experiments
from src.graph_builder import build_from_records, load_graph, save_graph

log = logging.getLogger(__name__)


# =========================================================================== null model
def rewire_degree_preserving(g: nx.DiGraph, swaps_per_edge: float = 10.0, seed: int = 0) -> nx.DiGraph:
    """Directed double-edge swaps (u1->v1, u2->v2) -> (u1->v2, u2->v1).

    Preserves every node's in- and out-degree and each edge keeps its attribute dict (so
    the SemVer mix is unchanged); self-loops and parallel edges are never created. Runs
    `swaps_per_edge * |E|` successful swaps (attempts are capped at 10x that).
    """
    rng = np.random.default_rng(seed)
    edges = list(g.edges(data=True))
    m = len(edges)
    if m < 2:
        return g.copy()
    src = [u for u, _, _ in edges]
    dst = [v for _, v, _ in edges]
    present = set(zip(src, dst))
    target = int(swaps_per_edge * m)
    done = attempts = 0
    while done < target and attempts < 10 * target:
        attempts += 1
        i, j = rng.integers(m, size=2)
        u1, v1, u2, v2 = src[i], dst[i], src[j], dst[j]
        if i == j or u1 == v2 or u2 == v1 or v1 == v2 or (u1, v2) in present or (u2, v1) in present:
            continue
        present -= {(u1, v1), (u2, v2)}
        present |= {(u1, v2), (u2, v1)}
        dst[i], dst[j] = v2, v1
        done += 1
    if done < target:
        log.warning("rewiring: only %d of %d swaps succeeded", done, target)

    h = nx.DiGraph()
    h.add_nodes_from(g.nodes(data=True))
    h.add_edges_from((u, v, dict(d)) for u, v, (_, _, d) in zip(src, dst, edges))
    return h


# =========================================================================== suite parts
def _run(g: nx.DiGraph, tag: str, cfg: ExperimentConfig, rqs, metrics_dir: Path, save_dir: Path | None) -> None:
    if cfg.skip_existing and all(rq_done(tag, k, metrics_dir, cfg) for k in rqs):
        log.info("%s: all RQs already done, skipping", tag)
        return
    if save_dir is not None:
        save_graph(g, save_dir / tag, graphml=False)
    ctx = ExperimentContext.from_graph(g, tag, metrics_dir=metrics_dir, use_cache=False)
    run_experiments(ctx, rqs, cfg, metrics_dir)


def run_null_models(graph_path: Path, n_models: int, cfg: ExperimentConfig, rqs=(1, 3),
                    metrics_dir: Path = METRICS_DIR, tag: str | None = None) -> list[str]:
    g = load_graph(graph_path)
    base = tag or graph_path.stem
    tags = []
    for k in range(n_models):
        t = f"{base}_null{k}"
        log.info("null model %d/%d (%s)", k + 1, n_models, t)
        _run(rewire_degree_preserving(g, seed=cfg.seed + k), t, cfg, rqs, metrics_dir, PROCESSED_DIR)
        tags.append(t)
    return tags


def run_synthetic_ensemble(seeds, n_nodes: int, cfg: ExperimentConfig, rqs=(1, 2, 3),
                           metrics_dir: Path = METRICS_DIR) -> list[str]:
    tags = []
    for s in seeds:
        t = f"synthetic_n{n_nodes}_s{s}_contagion"
        log.info("synthetic seed %d (%s)", s, t)
        _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=n_nodes, seed=s)))
        _run(g, t, replace(cfg, seed=s), rqs, metrics_dir, PROCESSED_DIR)
        tags.append(t)
    return tags


def run_sample_sizes(snapshots: list[Path], cfg: ExperimentConfig, rqs=(1, 2, 3),
                     metrics_dir: Path = METRICS_DIR) -> list[str]:
    tags = []
    for snap in snapshots:
        t = f"{snap.stem}_contagion"
        log.info("sample size: %s", t)
        _, g = build_from_records(load_records(snap))
        _run(g, t, cfg, rqs, metrics_dir, PROCESSED_DIR)
        tags.append(t)
    return tags


def run_sensitivity(graph_path: Path, betas, gammas, cfg: ExperimentConfig, rqs=(1, 3),
                    metrics_dir: Path = METRICS_DIR, tag: str | None = None,
                    base: SIRParams | None = None) -> list[str]:
    """RQ1/RQ3 with (beta, gamma) varied around `base` (default: cfg.rq3_params)."""
    base = base or cfg.rq3_params
    ctx = ExperimentContext.from_graph(graph_path, tag, metrics_dir=metrics_dir)
    root = ctx.tag
    tags = []
    for beta in betas:
        for gamma in gammas:
            t = f"{root}_sens_b{beta:g}_g{gamma:g}"
            log.info("sensitivity beta=%g gamma=%g", beta, gamma)
            p = replace(base, beta=beta, gamma=gamma)
            c = replace(cfg, rq1_scenarios=((f"beta={beta:g},gamma={gamma:g}", p),), rq3_params=p)
            ctx.tag = t  # write tables under the sensitivity tag, reuse the topology
            run_experiments(ctx, rqs, c, metrics_dir)
            tags.append(t)
    ctx.tag = root
    return tags


# =========================================================================== cli
def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Robustness experiments for the paper.")
    sub = p.add_subparsers(dest="part", required=True)
    for name in ("null", "seeds", "sizes", "sensitivity"):
        s = sub.add_parser(name)
        s.add_argument("--runs", type=int, default=ExperimentConfig.n_runs)
        s.add_argument("--rq2-runs", type=int, default=ExperimentConfig.rq2_n_runs)
        s.add_argument("--jobs", type=int, default=1)
        s.add_argument("--maintainer", type=float, nargs="*", default=[])
        s.add_argument("--rq", type=int, nargs="+")
        if name in ("null", "sensitivity"):
            s.add_argument("graph", type=Path)
        if name == "null":
            s.add_argument("--models", type=int, default=5)
        if name == "seeds":
            s.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
            s.add_argument("--nodes", type=int, default=2000)
        if name == "sizes":
            s.add_argument("snapshots", type=Path, nargs="+")
        if name == "sensitivity":
            s.add_argument("--betas", type=float, nargs="+", default=[0.05, 0.15, 0.3])
            s.add_argument("--gammas", type=float, nargs="+", default=[0.02, 0.05, 0.1])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bm = (0.0, *args.maintainer)
    cfg = ExperimentConfig(n_runs=args.runs, rq2_n_runs=args.rq2_runs, n_jobs=args.jobs,
                           rq1_beta_maintainer=bm, rq2_beta_maintainer=bm)
    if args.part == "null":
        run_null_models(args.graph, args.models, cfg, tuple(args.rq or (1, 3)))
    elif args.part == "seeds":
        run_synthetic_ensemble(args.seeds, args.nodes, cfg, tuple(args.rq or (1, 2, 3)))
    elif args.part == "sizes":
        run_sample_sizes(args.snapshots, cfg, tuple(args.rq or (1, 2, 3)))
    else:
        run_sensitivity(args.graph, args.betas, args.gammas, cfg, tuple(args.rq or (1, 3)))


if __name__ == "__main__":
    _cli()
