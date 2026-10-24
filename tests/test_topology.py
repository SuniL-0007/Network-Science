"""Milestone 2 tests: topology metrics orientation, reach, spectra, power law, classification."""

import networkx as nx
import numpy as np
import pytest

from src.config import SyntheticConfig, TopologyConfig
from src.data_ingestion import generate_synthetic_records
from src.graph_builder import build_from_records
from src.topology_analyzer import (
    analyze,
    classify_nodes,
    export_profile,
    fit_power_law,
    node_metrics,
    spectral_radius,
    transitive_reach,
)


def contagion(edges, hooks=(), modifier=1.0):
    g = nx.DiGraph()
    g.add_edges_from(edges, edge_beta_modifier=modifier, semver_type="caret")
    for n in g:
        g.nodes[n]["has_lifecycle_hook"] = n in hooks
    return g


def test_transitive_reach_matches_descendants():
    g = nx.gnp_random_graph(150, 0.02, seed=1, directed=True)  # contains cycles
    reach = transitive_reach(g)
    assert all(reach[n] == len(nx.descendants(g, n)) for n in g)


def test_spectral_radius():
    dag = contagion([("a", "b"), ("b", "c"), ("a", "c")])
    assert spectral_radius(dag) == 0.0
    cyc = contagion([("a", "b"), ("b", "a"), ("b", "c")], modifier=0.5)
    assert spectral_radius(cyc, weighted=False) == pytest.approx(1.0)
    assert spectral_radius(cyc) == pytest.approx(0.5)
    hooked = contagion([("a", "b"), ("b", "a")], hooks={"a"}, modifier=1.0)
    assert spectral_radius(hooked) == pytest.approx(np.sqrt(1.25))


def test_centrality_orientation():
    # contagion star: hub is a dependency of 20 packages; chain hub -> mid -> leaf
    g = contagion([("hub", f"d{i}") for i in range(20)] + [("hub", "mid"), ("mid", "leaf")])
    df = node_metrics(g, TopologyConfig())
    assert df["out_degree"].idxmax() == "hub"
    assert df["pagerank"].idxmax() == "hub"  # rank accumulates on depended-upon packages
    assert df["harmonic"].idxmax() == "hub"  # hub reaches the ecosystem in fewest hops
    assert df["betweenness"].idxmax() == "mid"
    assert df.at["hub", "transitive_dependents"] == 22


def test_sampled_centralities_match_exact_ranking():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=800, seed=5)))
    exact = node_metrics(g, TopologyConfig())
    approx = node_metrics(g, TopologyConfig(exact_max_nodes=100, sample_k=400))
    for col in ("harmonic", "betweenness"):
        top_exact = set(exact[col].nlargest(10).index)
        top_approx = set(approx[col].nlargest(10).index)
        assert len(top_exact & top_approx) >= 6, col


def test_power_law_recovers_exponent():
    rng = np.random.default_rng(0)
    x = rng.zipf(2.5, size=5000)
    fit = fit_power_law(x)
    assert fit["alpha"] == pytest.approx(2.5, abs=0.15)
    assert np.isnan(fit_power_law([1, 2, 3])["alpha"])


@pytest.fixture(scope="module")
def synthetic_profile():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=2000, seed=11)))
    cfg = TopologyConfig()
    profile = analyze(g, cfg)
    return g, profile, classify_nodes(g, profile.nodes, cfg)


def test_summary_on_synthetic(synthetic_profile):
    g, profile, _ = synthetic_profile
    s = profile.summary
    assert s["n_nodes"] == 2000 and s["n_edges"] == g.number_of_edges()
    assert 1.5 < s["powerlaw_out_degree"]["alpha"] < 4.0
    assert s["lambda_max_weighted"] <= s["lambda_max_unweighted"] * 1.25 + 1e-9
    assert s["max_core"] >= 2
    assert set(s["semver_mix"]) <= {"exact", "tilde", "caret", "wildcard"}


def test_classification(synthetic_profile):
    g, profile, groups = synthetic_profile
    df = profile.nodes
    cfg = TopologyConfig()

    assert len(groups["super_spreaders"]) == 20  # top 1% of 2000
    assert df.loc[groups["super_spreaders"], "out_degree"].min() >= df["out_degree"].quantile(0.98)

    origins = [groups[k] for k in ("origin_hub", "origin_bridge", "origin_mid", "origin_leaf")]
    assert all(len(o) == cfg.n_per_group for o in origins)
    flat = [u for o in origins for u in o]
    assert len(flat) == len(set(flat)), "origin groups must be disjoint"

    hub_mean = df.loc[groups["origin_hub"], "transitive_dependents"].mean()
    leaf_mean = df.loc[groups["origin_leaf"], "transitive_dependents"].mean()
    assert hub_mean > 10 * max(leaf_mean, 1)
    assert (df.loc[groups["periphery"], "out_degree"] > 0).all()
    assert len(groups["periphery"]) == int(np.ceil(0.2 * (df["out_degree"] > 0).sum()))
    for u in groups["firebreak_candidates"]:
        assert df.at[u, "betweenness_rank"] <= int(np.ceil(0.01 * len(df)))

    again = classify_nodes(g, df, cfg)
    assert again == groups  # deterministic under fixed seed


def test_export(tmp_path, synthetic_profile):
    _, profile, groups = synthetic_profile
    paths = export_profile(profile, groups, "t", out_dir=tmp_path)
    assert all(p.exists() for p in paths.values())
