"""Structural profile of the contagion graph and node classification for experiments (spec §4).

All metrics take G_contagion (v -> u: dependency v exposes dependent u). In contagion terms:
  out_degree            = direct dependents (npm "in-degree" in the dependency graph)
  in_degree             = direct dependencies
  transitive_dependents = nodes reachable from v, i.e. the worst-case blast radius of v
  harmonic              = outward closeness: how few hops v needs to reach the ecosystem
  pagerank              = PageRank on G_dep, so rank accumulates on depended-upon packages
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import ArpackNoConvergence, eigs

from src.config import HOOK_BETA_MULTIPLIER, METRICS_DIR, TopologyConfig
from src.graph_builder import load_graph

log = logging.getLogger(__name__)


@dataclass
class TopologyProfile:
    nodes: pd.DataFrame  # one row per package, indexed by name
    summary: dict = field(default_factory=dict)  # global metrics, incl. power-law fits


# =========================================================================== reach
def transitive_reach(g: nx.DiGraph) -> dict:
    """Number of nodes reachable from each node (excluding itself), exact.

    Collapses SCCs, then propagates reachable sets as Python-int bitsets in reverse
    topological order. Memory is O(N^2 / 8) bytes in the worst case (~12 MB at N=10k).
    """
    index = {node: i for i, node in enumerate(g)}
    cond = nx.condensation(g)
    reach: dict[int, int] = {}
    for c in reversed(list(nx.topological_sort(cond))):
        bits = 0
        for m in cond.nodes[c]["members"]:
            bits |= 1 << index[m]
        for child in cond.successors(c):
            bits |= reach[child]
        reach[c] = bits
    return {m: reach[c].bit_count() - 1 for c in cond for m in cond.nodes[c]["members"]}


# =========================================================================== spectra
def contagion_matrix(g: nx.DiGraph, weighted: bool = True) -> tuple[sp.csr_array, list]:
    """W[v, u] = w_semver(v, u) * w_hook(v), the per-edge multiplier on beta_base."""
    nodes = list(g)
    if not weighted:
        return nx.to_scipy_sparse_array(g, nodelist=nodes, weight=None, format="csr", dtype=float), nodes
    a = nx.to_scipy_sparse_array(g, nodelist=nodes, weight="edge_beta_modifier", format="csr", dtype=float)
    hook = np.array([HOOK_BETA_MULTIPLIER if g.nodes[n].get("has_lifecycle_hook") else 1.0 for n in nodes])
    return sp.csr_array(sp.diags_array(hook) @ a), nodes


def spectral_radius(g: nx.DiGraph, weighted: bool = True) -> float:
    """lambda_max of the (weighted) contagion matrix.

    The matrix is block-triangular over SCCs, so lambda_max is the maximum over non-trivial
    SCCs. A DAG therefore has lambda_max = 0: no self-sustaining epidemic threshold exists
    and outbreak size is bounded by transitive reach.
    """
    w, nodes = contagion_matrix(g, weighted)
    pos = {n: i for i, n in enumerate(nodes)}
    best = 0.0
    for scc in nx.strongly_connected_components(g):
        if len(scc) < 2:
            continue
        idx = np.array([pos[n] for n in scc])
        sub = w[idx][:, idx]
        if len(scc) <= 500:
            rho = float(np.max(np.abs(np.linalg.eigvals(sub.toarray()))))
        else:
            try:
                rho = float(np.abs(eigs(sub, k=1, which="LM", return_eigenvectors=False)[0]))
            except ArpackNoConvergence as exc:
                rho = float(np.max(np.abs(exc.eigenvalues))) if len(exc.eigenvalues) else math.nan
        best = max(best, rho)
    return best


# =========================================================================== degrees
def fit_power_law(degrees, min_tail: int = 50) -> dict:
    """Clauset-Shalizi-Newman discrete power-law fit, with likelihood-ratio comparisons.

    A positive `llr_vs_*` favours the power law; the matching `p_vs_*` is its significance.
    """
    import powerlaw  # local import: heavy, and only needed here

    x = np.asarray([d for d in degrees if d > 0])
    if len(x) < min_tail:
        return {"alpha": math.nan, "xmin": math.nan, "n": int(len(x)), "note": "too few non-zero degrees"}
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        fit = powerlaw.Fit(x, discrete=True, verbose=False)
        llr_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        llr_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
    pl = fit.power_law
    return {
        "alpha": float(pl.alpha),
        "sigma": float(pl.standard_err),
        "xmin": float(pl.xmin),
        "ks_D": float(pl.D),
        "n": int(len(x)),
        "n_tail": int((x >= pl.xmin).sum()),
        "llr_vs_lognormal": float(llr_ln),
        "p_vs_lognormal": float(p_ln),
        "llr_vs_exponential": float(llr_exp),
        "p_vs_exponential": float(p_exp),
    }


# =========================================================================== metrics
def _safe(fn, *args, **kwargs) -> float:
    try:
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            return float(fn(*args, **kwargs))
    except (ZeroDivisionError, ValueError, nx.NetworkXError):
        return math.nan


def node_metrics(g: nx.DiGraph, cfg: TopologyConfig = TopologyConfig()) -> pd.DataFrame:
    n = g.number_of_nodes()
    g_dep = g.reverse(copy=False)
    und = nx.Graph(g)
    sample = n > cfg.exact_max_nodes
    k = min(cfg.sample_k, n) if sample else None

    log.info("Centralities on %d nodes (%s)", n, f"sampled k={k}" if sample else "exact")
    betweenness = nx.betweenness_centrality(g, k=k, seed=cfg.seed, normalized=True)
    pagerank = nx.pagerank(g_dep, alpha=cfg.pagerank_alpha)
    if sample:
        rng = np.random.default_rng(cfg.seed)
        sources = rng.choice(np.array(list(g), dtype=object), size=k, replace=False).tolist()
        harmonic = {u: h / k for u, h in nx.harmonic_centrality(g_dep, sources=sources).items()}
    else:
        harmonic = {u: h / max(n - 1, 1) for u, h in nx.harmonic_centrality(g_dep).items()}

    df = pd.DataFrame(index=pd.Index(list(g), name="name"))
    df["out_degree"] = pd.Series(dict(g.out_degree()))
    df["in_degree"] = pd.Series(dict(g.in_degree()))
    df["transitive_dependents"] = pd.Series(transitive_reach(g))
    df["pagerank"] = pd.Series(pagerank)
    df["betweenness"] = pd.Series(betweenness)
    df["harmonic"] = pd.Series(harmonic)
    df["core_number"] = pd.Series(nx.core_number(und))
    df["clustering"] = pd.Series(nx.clustering(und))
    for attr in ("has_lifecycle_hook", "has_provenance"):
        df[attr] = pd.Series({u: bool(d.get(attr)) for u, d in g.nodes(data=True)})
    df["dependent_count"] = pd.Series({u: d.get("dependent_count") for u, d in g.nodes(data=True)})
    df["n_maintainers"] = pd.Series({u: len(d.get("maintainers") or []) for u, d in g.nodes(data=True)})
    df["betweenness_rank"] = df["betweenness"].rank(ascending=False, method="first").astype(int)
    return df


def global_metrics(g: nx.DiGraph, df: pd.DataFrame, cfg: TopologyConfig = TopologyConfig()) -> dict:
    und = nx.Graph(g)
    wccs = list(nx.weakly_connected_components(g))
    sccs = [c for c in nx.strongly_connected_components(g) if len(c) > 1]
    semver = pd.Series([t for *_, t in g.edges(data="semver_type")], dtype=object)
    lam_w = spectral_radius(g, weighted=True)
    out = {
        "n_nodes": g.number_of_nodes(),
        "n_edges": g.number_of_edges(),
        "density": nx.density(g),
        "is_dag": nx.is_directed_acyclic_graph(g),
        "n_wcc": len(wccs),
        "largest_wcc_frac": max(map(len, wccs)) / g.number_of_nodes() if wccs else 0.0,
        "n_nontrivial_scc": len(sccs),
        "largest_scc_size": max(map(len, sccs), default=1),
        "reciprocity": _safe(nx.reciprocity, g) if g.number_of_edges() else 0.0,
        "avg_clustering": float(df["clustering"].mean()),
        "transitivity": nx.transitivity(und),
        "max_core": int(df["core_number"].max()),
        "mean_transitive_dependents": float(df["transitive_dependents"].mean()),
        "max_transitive_dependents": int(df["transitive_dependents"].max()),
        "lambda_max_unweighted": spectral_radius(g, weighted=False),
        "lambda_max_weighted": lam_w,
        # Mean-field threshold: self-sustaining spread needs beta/gamma > 1/lambda_max(W).
        "tau_c_theory": 1.0 / lam_w if lam_w > 0 else math.inf,
        "frac_lifecycle_hook": float(df["has_lifecycle_hook"].mean()),
        "frac_provenance": float(df["has_provenance"].mean()),
        "semver_mix": (semver.value_counts(normalize=True).round(4).to_dict() if len(semver) else {}),
    }
    # Directed assortativity (Foster et al. 2010): x = source degree type, y = target's.
    for x in ("in", "out"):
        for y in ("in", "out"):
            out[f"assortativity_{x}_{y}"] = _safe(nx.degree_assortativity_coefficient, g, x=x, y=y)
    out["powerlaw_out_degree"] = fit_power_law(df["out_degree"], cfg.powerlaw_min_tail)
    out["powerlaw_in_degree"] = fit_power_law(df["in_degree"], cfg.powerlaw_min_tail)
    return out


def analyze(g: nx.DiGraph, cfg: TopologyConfig = TopologyConfig()) -> TopologyProfile:
    df = node_metrics(g, cfg)
    return TopologyProfile(nodes=df, summary=global_metrics(g, df, cfg))


# =========================================================================== classification
def _top(df: pd.DataFrame, cols: list[str], n: int, exclude: set) -> list[str]:
    ranked = df.drop(index=list(exclude & set(df.index))).sort_values(cols, ascending=False, kind="stable")
    return ranked.index[:n].tolist()


def classify_nodes(g: nx.DiGraph, df: pd.DataFrame, cfg: TopologyConfig = TopologyConfig()) -> dict:
    """Node groups for the experiments.

    Population-level classes (spec §4.4): `super_spreaders`, `firebreak_candidates`,
    `periphery`. RQ1 origin groups (`origin_*`, `n_per_group` each) are mutually disjoint,
    so Hub / Bridge / Mid-tier / Leaf comparisons don't share nodes.
    """
    rng = np.random.default_rng(cfg.seed)
    n = len(df)
    spreading = df[df["out_degree"] > 0]

    n_hub = max(1, math.ceil(cfg.hub_fraction * n))
    super_spreaders = _top(df, ["out_degree", "pagerank"], n_hub, set())

    # Firebreaks: high betweenness, fed by a dependency in the upper k-core, large downstream tree.
    core_cut = df["core_number"].quantile(cfg.firebreak_core_quantile)
    reach_cut = spreading["transitive_dependents"].quantile(cfg.firebreak_reach_quantile) if len(spreading) else 0
    n_fb = max(1, math.ceil(cfg.firebreak_fraction * n))
    top_btw = df[df["betweenness"] > 0].nlargest(n_fb, "betweenness")
    firebreaks = [
        u for u in top_btw.index
        if df.at[u, "transitive_dependents"] >= reach_cut
        and any(df.at[p, "core_number"] >= core_cut for p in g.predecessors(u))
    ]
    if len(firebreaks) < len(top_btw):
        log.info("Firebreak filter kept %d of %d top-betweenness nodes", len(firebreaks), len(top_btw))

    n_peri = max(1, math.ceil(cfg.periphery_fraction * len(spreading)))
    periphery = spreading.sort_values(["out_degree", "transitive_dependents"], kind="stable").index[:n_peri].tolist()

    k = cfg.n_per_group
    taken: set = set()
    origin_hub = _top(df, ["out_degree", "pagerank"], k, taken)
    taken |= set(origin_hub)
    origin_bridge = _top(df[df["betweenness"] > 0], ["betweenness"], k, taken)
    taken |= set(origin_bridge)

    # Mid-tier: nodes at the median k-core of spreading nodes, widening the band if needed.
    pool = spreading.drop(index=list(taken & set(spreading.index)))
    median_core = pool["core_number"].median() if len(pool) else 0
    band, mid_pool = 0, pool.iloc[:0]
    while len(mid_pool) < k and band <= int(pool["core_number"].max() if len(pool) else 0):
        mid_pool = pool[(pool["core_number"] - median_core).abs() <= band]
        band += 1
    origin_mid = sorted(rng.choice(mid_pool.index.to_numpy(), size=min(k, len(mid_pool)), replace=False).tolist())
    taken |= set(origin_mid)

    leaf_pool = [u for u in periphery if u not in taken]
    origin_leaf = sorted(rng.choice(np.array(leaf_pool, dtype=object), size=min(k, len(leaf_pool)), replace=False).tolist())

    return {
        "super_spreaders": super_spreaders,
        "firebreak_candidates": firebreaks,
        "periphery": periphery,
        "origin_hub": origin_hub,
        "origin_bridge": origin_bridge,
        "origin_mid": origin_mid,
        "origin_leaf": origin_leaf,
    }


# =========================================================================== export
def export_profile(profile: TopologyProfile, groups: dict, tag: str, out_dir: Path = METRICS_DIR,
                   cfg: TopologyConfig = TopologyConfig()) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "nodes": out_dir / f"{tag}_node_metrics.csv",
        "summary": out_dir / f"{tag}_topology_summary.json",
        "groups": out_dir / f"{tag}_node_groups.json",
    }
    profile.nodes.sort_values("pagerank", ascending=False).to_csv(paths["nodes"])
    summary = {**profile.summary, "config": asdict(cfg)}
    paths["summary"].write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    paths["groups"].write_text(json.dumps(groups, indent=2), encoding="utf-8")
    return paths


def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Topological profile of a contagion graph.")
    p.add_argument("graph", type=Path, help="data/processed/*_contagion.pkl (or .graphml)")
    p.add_argument("--tag", help="output file prefix (default: graph file stem)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = TopologyConfig()
    g = load_graph(args.graph)
    profile = analyze(g, cfg)
    groups = classify_nodes(g, profile.nodes, cfg)
    paths = export_profile(profile, groups, args.tag or args.graph.stem, cfg=cfg)
    s = profile.summary
    log.info("N=%d E=%d DAG=%s lambda_max(W)=%.3f alpha_out=%.2f core_max=%d",
             s["n_nodes"], s["n_edges"], s["is_dag"], s["lambda_max_weighted"],
             s["powerlaw_out_degree"].get("alpha", math.nan), s["max_core"])
    for name, path in paths.items():
        log.info("wrote %s: %s", name, path)


if __name__ == "__main__":
    _cli()
