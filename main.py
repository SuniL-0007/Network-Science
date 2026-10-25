"""End-to-end pipeline: data -> contagion graph -> topology -> RQ1-RQ3 experiments -> figures.

Examples:
    python main.py --mode synthetic --nodes 2000 --runs 50
    python main.py --mode crawl --seeds data/raw/seeds_high_impact_dependents.txt --max-nodes 10000 --jobs 6
    python main.py --mode snapshot --snapshot data/raw/npm_hi_n10k.jsonl --maintainer 0.01 0.05 --jobs 6
    python main.py --figures-only --tag npm_hi_n10k_contagion
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from src.config import (
    DATA_DIR,
    DEFAULT_SEEDS,
    INSTALLED_DEP_TYPES,
    RESULTS_DIR,
    CrawlConfig,
    ExperimentConfig,
    SyntheticConfig,
)
from src.data_ingestion import (
    DepsDevClient,
    crawl_npm,
    generate_synthetic_records,
    load_records,
    load_seeds,
    save_records,
)
from src.experiments import ExperimentContext, run_experiments
from src.graph_builder import build_from_records, save_graph
from src.visualizer import make_all_figures

log = logging.getLogger("npm-sir-contagion")

# Small grids for smoke tests and quick looks (--quick).
QUICK = dict(rq2_betas=(0.05, 0.2, 1.0), rq2_gammas=(0.05, 0.2), rq3_budget_fracs=(0.005, 0.025),
             rq3_response_delays=(1, 10), n_boot=200)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SIR worm-propagation pipeline over the npm dependency network.")
    p.add_argument("--mode", choices=["synthetic", "crawl", "snapshot"], default="synthetic",
                   help="data source: generate, crawl the live registry, or reuse a JSONL snapshot")
    p.add_argument("--nodes", type=int, default=SyntheticConfig.n_nodes, help="synthetic: number of packages")
    p.add_argument("--seed", type=int, default=SyntheticConfig.seed, help="generator + experiment seed")
    p.add_argument("--snapshot", type=Path, help="snapshot mode: data/raw/*.jsonl")
    p.add_argument("--seeds", type=Path, help="crawl mode: seed list (.txt or Libraries.io .csv)")
    p.add_argument("--top-n", type=int, help="crawl mode: use the first N seeds")
    p.add_argument("--max-nodes", type=int, default=CrawlConfig.max_nodes)
    p.add_argument("--max-depth", type=int, default=CrawlConfig.max_depth)
    p.add_argument("--dependents", action="store_true", help="crawl mode: deps.dev dependent counts")
    p.add_argument("--include-dev", action="store_true", help="add devDependency edges to the graph")
    p.add_argument("--runs", type=int, default=ExperimentConfig.n_runs, help="Monte Carlo runs (RQ1 per origin, RQ3)")
    p.add_argument("--rq2-runs", type=int, default=ExperimentConfig.rq2_n_runs)
    p.add_argument("--rq", type=int, nargs="+", default=[1, 2, 3], choices=[1, 2, 3])
    p.add_argument("--maintainer", type=float, nargs="*", default=[],
                   help="extra beta_maintainer values (credential channel) for RQ1/RQ2")
    p.add_argument("--jobs", type=int, default=1, help="worker processes for Monte Carlo runs")
    p.add_argument("--quick", action="store_true", help="small RQ2/RQ3 grids for a fast smoke run")
    p.add_argument("--skip-experiments", action="store_true", help="stop after the topology profile")
    p.add_argument("--figures-only", action="store_true", help="only re-render figures for --tag")
    p.add_argument("--tag", help="output prefix (default: derived from the snapshot name)")
    p.add_argument("--force", action="store_true", help="recompute the topology profile even if cached")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    return p.parse_args(argv)


def _snapshot(args: argparse.Namespace, raw_dir: Path) -> Path:
    if args.mode == "snapshot":
        if not args.snapshot:
            raise SystemExit("--mode snapshot needs --snapshot PATH")
        return args.snapshot
    if args.mode == "synthetic":
        cfg = SyntheticConfig(n_nodes=args.nodes, seed=args.seed)
        path = raw_dir / f"synthetic_n{cfg.n_nodes}_s{cfg.seed}.jsonl"
        return save_records(generate_synthetic_records(cfg), path, {"mode": "synthetic", "config": asdict(cfg)})
    seeds = load_seeds(args.seeds, args.top_n) if args.seeds else list(DEFAULT_SEEDS)[: args.top_n]
    cfg = CrawlConfig(max_nodes=args.max_nodes, max_depth=args.max_depth, cache_dir=raw_dir / "cache")
    records = crawl_npm(seeds, cfg, dependents=DepsDevClient(cfg).dependent_count if args.dependents else None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = raw_dir / f"npm_{stamp}_n{len(records)}.jsonl"
    return save_records(records, path, {"mode": "crawl", "seeds": seeds, "config": asdict(cfg)})


def run_pipeline(args: argparse.Namespace) -> dict:
    """Run the selected stages; returns the key output locations."""
    metrics_dir, figures_dir = args.results_dir / "metrics", args.results_dir / "figures"
    if args.figures_only:
        if not args.tag:
            raise SystemExit("--figures-only needs --tag")
        return {"tag": args.tag, "figures": make_all_figures(args.tag, metrics_dir, figures_dir)}

    t0 = time.perf_counter()
    snapshot = _snapshot(args, args.data_dir / "raw")
    log.info("[1/5] snapshot: %s", snapshot)

    dep_types = INSTALLED_DEP_TYPES + (("dev",) if args.include_dev else ())
    _, g = build_from_records(load_records(snapshot), dep_types)
    tag = args.tag or f"{snapshot.stem}_contagion"
    graph_path = save_graph(g, args.data_dir / "processed" / tag)
    log.info("[2/5] contagion graph: %d nodes, %d edges -> %s", g.number_of_nodes(), g.number_of_edges(), graph_path)

    ctx = ExperimentContext.from_graph(g, tag, metrics_dir=metrics_dir, use_cache=not args.force)
    s = ctx.topology
    log.info("[3/5] topology: DAG=%s, max blast radius=%s, lambda_max(W)=%.3f",
             s.get("is_dag"), s.get("max_transitive_dependents"), s.get("lambda_max_weighted", float("nan")))

    if not args.skip_experiments:
        bm = (0.0, *args.maintainer)
        cfg = ExperimentConfig(n_runs=args.runs, rq2_n_runs=args.rq2_runs, n_jobs=args.jobs, seed=args.seed,
                               rq1_beta_maintainer=bm, rq2_beta_maintainer=bm)
        if args.quick:
            cfg = replace(cfg, **QUICK)
        run_experiments(ctx, args.rq, cfg, metrics_dir)
        log.info("[4/5] experiments RQ%s done", ",".join(map(str, args.rq)))
    else:
        log.info("[4/5] experiments skipped")

    figures = make_all_figures(tag, metrics_dir, figures_dir)
    log.info("[5/5] %d figure files -> %s (%.0fs total)", len(figures), figures_dir / tag, time.perf_counter() - t0)
    return {"tag": tag, "snapshot": snapshot, "graph": graph_path, "figures": figures}


def main(argv: list[str] | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    return run_pipeline(parse_args(argv))


if __name__ == "__main__":  # required on Windows: worker processes re-import this module
    main()
