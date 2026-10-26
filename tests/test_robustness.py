"""Robustness tests: the degree-preserving null model and the suite runners."""

from collections import Counter

import networkx as nx

from src.config import ExperimentConfig, SyntheticConfig
from src.data_ingestion import generate_synthetic_records
from src.graph_builder import build_from_records
from src.robustness import rewire_degree_preserving, run_synthetic_ensemble


def _graph(n=400, seed=5):
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=n, seed=seed)))
    return g


def test_rewiring_preserves_degrees_and_attributes():
    g = _graph()
    h = rewire_degree_preserving(g, swaps_per_edge=5, seed=1)
    assert dict(g.in_degree()) == dict(h.in_degree())
    assert dict(g.out_degree()) == dict(h.out_degree())
    assert nx.number_of_selfloops(h) == 0
    assert Counter(d["semver_type"] for *_, d in g.edges(data=True)) == \
        Counter(d["semver_type"] for *_, d in h.edges(data=True))
    assert h.nodes["pkg-00000"] == g.nodes["pkg-00000"]
    # structure actually changes
    overlap = len(set(g.edges) & set(h.edges)) / g.number_of_edges()
    assert overlap < 0.5


def test_rewiring_is_deterministic():
    g = _graph(200)
    assert set(rewire_degree_preserving(g, seed=3).edges) == set(rewire_degree_preserving(g, seed=3).edges)
    assert set(rewire_degree_preserving(g, seed=3).edges) != set(rewire_degree_preserving(g, seed=4).edges)


def test_synthetic_ensemble_runs(tmp_path, monkeypatch):
    import src.robustness as rb
    monkeypatch.setattr(rb, "PROCESSED_DIR", tmp_path / "processed")
    cfg = ExperimentConfig(n_runs=2, rq2_n_runs=2, n_boot=50, rq2_betas=(0.3,), rq2_gammas=(0.1,),
                           rq3_budget_fracs=(0.01,), rq3_response_delays=(1,))
    tags = run_synthetic_ensemble([1, 2], 200, cfg, rqs=(1, 3), metrics_dir=tmp_path)
    assert tags == ["synthetic_n200_s1_contagion", "synthetic_n200_s2_contagion"]
    for t in tags:
        assert (tmp_path / f"{t}_rq1_summary.csv").exists()
        assert (tmp_path / f"{t}_rq3_summary.csv").exists()
