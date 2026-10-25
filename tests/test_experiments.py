"""Milestone 4 tests: run metrics, statistics, regimes, and end-to-end RQ1-RQ3 runners."""

import math

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from src.config import ExperimentConfig, SIRParams, SyntheticConfig
from src.data_ingestion import generate_synthetic_records
from src.experiments import (
    ExperimentContext,
    Regime,
    apply_regime,
    run_experiments,
    run_rq1,
    run_rq2,
    run_rq3,
)
from src.graph_builder import build_from_records
from src.metrics_logger import (
    RunMetrics,
    bootstrap_ci,
    curve_summary,
    estimate_threshold,
    paired_reduction,
    summarize_runs,
)
from src.sir_engine import ContagionModel, MCJob, run_batch, run_monte_carlo, simulate


def chain(n=5):
    g = nx.DiGraph()
    nx.add_path(g, range(n), edge_beta_modifier=1.0)
    g.add_node("island")
    for u in g:
        g.nodes[u].update(has_lifecycle_hook=False, has_provenance=False, maintainers=[])
    return g


# --------------------------------------------------------------------------- run metrics
def test_run_metrics_on_deterministic_chain():
    m = ContagionModel.from_graph(chain(5))
    res = simulate(m, SIRParams(beta=1.0, gamma=1.0), [0], rng=0)
    out = RunMetrics(m, keep_curves=True)(res)
    assert out["n_reachable"] == 5 and out["ever_infected"] == 5
    assert out["r_inf"] == pytest.approx(5 / 6) and out["r_inf_reachable"] == 1.0
    assert out["t80"] == 3  # cumulative infections 1,2,3,4 >= 0.8 * 5 at t=3
    assert out["i_max"] == 1 and out["t_peak"] == 0
    assert out["depth_max"] == 4 and out["depth_mean"] == pytest.approx(2.5)
    assert out["hop1_share"] == pytest.approx(0.25) and out["hop3plus_share"] == pytest.approx(0.5)
    assert out["maint_share"] == 0.0
    assert out["_curves"].shape == (3, res.duration + 1)


def test_run_metrics_t80_nan_when_blocked():
    m = ContagionModel.from_graph(chain(5))
    res = simulate(m, SIRParams(beta=1.0, gamma=1.0), [0], rng=0, immunized=[2])
    out = RunMetrics(m)(res)
    assert math.isnan(out["t80"]) and out["ever_infected"] == 2 and out["n_reachable"] == 5


def test_reachable_union_of_seeds():
    m = ContagionModel.from_graph(chain(5))
    rm = RunMetrics(m)
    assert rm.reachable(m.idx([3])) == 2
    assert rm.reachable(m.idx([3, "island"])) == 3


# --------------------------------------------------------------------------- statistics
def test_bootstrap_ci_and_paired_reduction():
    rng = np.random.default_rng(0)
    x = rng.normal(10, 2, 400)
    lo, hi = bootstrap_ci(x)
    assert lo < x.mean() < hi and hi - lo < 1.0
    assert bootstrap_ci([3, 3, 3]) == (3.0, 3.0)
    assert all(math.isnan(v) for v in bootstrap_ci([math.nan]))

    base = rng.uniform(0.4, 0.6, 200)
    red = paired_reduction(base, base * 0.5)
    assert red["reduction"] == pytest.approx(0.5)
    assert red["ci_lo"] == pytest.approx(0.5) and red["ci_hi"] == pytest.approx(0.5)
    assert math.isnan(paired_reduction(np.zeros(3), np.zeros(3))["reduction"])


def test_summarize_runs():
    df = pd.DataFrame({"g": ["a"] * 4 + ["b"] * 4,
                       "r_inf": [0.0, 0.0, 0.5, 0.7, 0.01, 0.02, 0.01, 0.0],
                       "t80": [np.nan, np.nan, 5, 7, np.nan, np.nan, np.nan, np.nan]})
    s = summarize_runs(df, ["g"], metrics=("r_inf", "t80")).set_index("g")
    assert s.at["a", "p_major"] == 0.5 and s.at["a", "r_inf_given_major"] == pytest.approx(0.6)
    assert s.at["a", "t80_mean"] == 6 and s.at["a", "frac_reached_t80"] == 0.5
    assert s.at["b", "p_major"] == 0 and math.isnan(s.at["b", "t80_mean"])


def test_curve_summary_pads_short_runs():
    a = np.array([[2, 1, 1], [1, 1, 0], [0, 1, 2]])
    b = np.array([[2, 2], [1, 0], [0, 1]])
    cs = curve_summary([a, b], 4)
    assert len(cs) == 4
    assert cs["S_mean"].tolist() == [2.0, 1.5, 1.5, 1.5]
    assert cs["R_mean"].tolist() == [0.0, 1.0, 1.5, 1.5]


def test_estimate_threshold():
    s = pd.DataFrame({"regime": "x", "gamma": 0.1, "beta": [0.01, 0.02, 0.04, 0.08],
                      "r_inf_mean": [0.0, 0.01, 0.09, 0.5]})
    t = estimate_threshold(s, by=("regime", "gamma"), level=0.05).iloc[0]
    assert t["beta_c"] == pytest.approx(0.03) and t["tau_c"] == pytest.approx(0.3)
    never = estimate_threshold(s.assign(r_inf_mean=0.0), by=("regime", "gamma")).iloc[0]
    assert math.isnan(never["beta_c"]) and never["censored"] == "never"


# --------------------------------------------------------------------------- batching
def test_run_batch_matches_run_monte_carlo():
    m = ContagionModel.from_graph(chain(6))
    p = SIRParams(beta=0.6, gamma=0.3)
    rm = RunMetrics(m)
    single = run_monte_carlo(m, p, [0], 20, seed=3, reducer=rm)
    batched = run_batch(m, [MCJob(p, [1], 5, seed=9), MCJob(p, [0], 20, seed=3)], rm)
    assert batched[1] == single and len(batched[0]) == 5


# --------------------------------------------------------------------------- regimes
@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=500, seed=21)))
    return ExperimentContext.from_graph(g, "t500", metrics_dir=tmp_path_factory.mktemp("m"))


def test_apply_regime(ctx):
    base = SIRParams()
    m0 = ctx.model
    exact0 = np.isclose(m0.w_semver, 0.05)
    pinned, over = apply_regime(m0, Regime("p", pin_fraction=0.8), base, seed=1)
    assert np.isclose(pinned.w_semver, 0.05).mean() == pytest.approx(0.8, abs=0.04)
    assert np.isclose(pinned.w_semver[exact0], 0.05).all()  # pinned edges stay pinned
    assert over == {"hook_multiplier": pytest.approx(1.25), "provenance_factor": 1.0}
    assert np.array_equal(m0.w_semver[exact0], np.full(exact0.sum(), 0.05))  # original untouched

    _, over = apply_regime(m0, Regime("s", hook_reduction=0.7), base)
    assert over["hook_multiplier"] == pytest.approx(1.075)
    hard, over = apply_regime(m0, Regime("h", provenance_top=0.05, provenance_factor=0.1), base)
    top = np.argsort(-m0.out_degree, kind="stable")[:25]
    assert hard.provenance[top].all() and over["provenance_factor"] == 0.1


def test_context_cache_roundtrip(ctx, tmp_path):
    g = ctx.graph
    first = ExperimentContext.from_graph(g, "c", metrics_dir=tmp_path)
    cached = ExperimentContext.from_graph(g, "c", metrics_dir=tmp_path)
    assert cached.groups == first.groups
    assert np.allclose(cached.nodes.loc[first.nodes.index, "betweenness"], first.nodes["betweenness"])


def test_context_cache_keeps_na_like_package_names(tmp_path):
    g = nx.DiGraph()
    nx.add_path(g, ["null", "nan", "NA", "true", "1"], edge_beta_modifier=1.0)
    for u in g:
        g.nodes[u].update(has_lifecycle_hook=False, has_provenance=False, maintainers=[], dependent_count=None)
    ExperimentContext.from_graph(g, "na", metrics_dir=tmp_path)
    cached = ExperimentContext.from_graph(g, "na", metrics_dir=tmp_path)
    assert set(cached.nodes.index) == {"null", "nan", "NA", "true", "1"}
    assert cached.nodes["dependent_count"].isna().all() and cached.nodes["out_degree"].dtype.kind == "i"


# --------------------------------------------------------------------------- end to end
SMALL = ExperimentConfig(n_runs=8, rq2_n_runs=6, n_boot=200, rq2_betas=(0.05, 0.3, 1.0),
                         rq2_gammas=(0.05, 0.4), rq3_budget_fracs=(0.004, 0.02), rq3_response_delays=(1, 6),
                         rq1_beta_maintainer=(0.0, 0.05))


def test_rq1(ctx):
    out = run_rq1(ctx, SMALL)
    runs, s = out["runs"], out["summary"].set_index(["beta_maintainer", "group"])
    assert len(runs) == 2 * 4 * 10 * 8
    assert s.loc[(0.0, "hub"), "r_inf_mean"] > s.loc[(0.0, "leaf"), "r_inf_mean"]
    assert s.loc[(0.05, "leaf"), "r_inf_mean"] >= s.loc[(0.0, "leaf"), "r_inf_mean"]
    assert set(out["curves"]["group"]) == {"hub", "bridge", "mid", "leaf"}
    assert len(out["per_origin"]) == 2 * 40


def test_rq2(ctx):
    out = run_rq2(ctx, SMALL)
    s = out["summary"]
    assert len(s) == 4 * 3 * 2
    assert set(out["regimes"]["name"]) == {"status_quo", "strict_lockfile", "scripts_disabled", "hardened"}
    piv = s.groupby("regime")["r_inf_mean"].mean()
    assert piv["strict_lockfile"] < piv["status_quo"]
    assert piv["hardened"] <= piv["strict_lockfile"] + 0.02
    assert {"beta_c", "tau_c", "censored", "tau_c_theory"} <= set(out["thresholds"].columns)


def test_rq3(ctx):
    out = run_rq3(ctx, SMALL)
    runs, s = out["runs"], out["summary"]
    assert set(s["strategy"]) == {"none", "random_patch", "hub_patch", "firebreak_immunize",
                                  "hub_immunize", "acquaintance_immunize"}
    # matched budget: K equals mean nodes treated by hub patching at the same B
    for (b, d), grp in runs[runs["strategy"] == "hub_patch"].groupby(["budget", "delay"]):
        fb = runs[(runs["strategy"] == "firebreak_immunize") & (runs["budget"] == b) & (runs["delay"] == d)]
        assert fb["k_immunized"].iloc[0] == max(1, round(grp["n_patched"].mean()))
    # paired runs: every strategy sees the same patient zero sequence
    first = runs[runs["run"] == 0]
    assert first["n_reachable"].nunique() == 1
    red = out["reductions"].set_index(["strategy", "delay", "budget"])
    assert (red["delta_r_inf"] <= 1.0).all()
    big = max(runs["budget"])
    assert red.loc[("hub_patch", 1, big), "delta_r_inf"] > 0
    # later detection can only help reactive patching less (paired runs)
    assert red.loc[("hub_patch", 6, big), "delta_r_inf"] <= red.loc[("hub_patch", 1, big), "delta_r_inf"] + 1e-9


def test_run_experiments_writes_files(ctx, tmp_path):
    cfg = ExperimentConfig(n_runs=2, rq2_n_runs=2, n_boot=50, rq2_betas=(0.3,), rq2_gammas=(0.1,),
                           rq3_budget_fracs=(0.01,), rq3_response_delays=(1,))
    run_experiments(ctx, (1, 2, 3), cfg, out_dir=tmp_path)
    names = {p.name for p in tmp_path.iterdir()}
    for k, tables in {1: ("runs", "summary", "per_origin", "curves", "meta"),
                      2: ("runs", "summary", "thresholds", "regimes", "meta"),
                      3: ("runs", "summary", "reductions", "info", "meta")}.items():
        for t in tables:
            ext = "json" if t == "meta" else "csv"
            assert f"t500_rq{k}_{t}.{ext}" in names
