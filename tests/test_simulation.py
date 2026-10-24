"""Milestone 3 tests: SIR state transitions, edge weighting, interventions, Monte Carlo, NDlib."""

import networkx as nx
import numpy as np
import pytest

from src.config import SIRParams, SyntheticConfig
from src.data_ingestion import generate_synthetic_records
from src.graph_builder import build_from_records
from src.sir_engine import (
    DEPENDENCY,
    MAINTAINER,
    NEVER,
    SEED,
    ContagionModel,
    PatchPolicy,
    make_policy,
    run_monte_carlo,
    run_ndlib_sir,
    simulate,
)


def contagion(edges, modifier=1.0, hooks=(), provenance=(), maintainers=None, nodes=()):
    g = nx.DiGraph()
    g.add_nodes_from(nodes)
    for e in edges:
        u, v, *m = e
        g.add_edge(u, v, edge_beta_modifier=m[0] if m else modifier)
    for n in g:
        g.nodes[n].update(has_lifecycle_hook=n in hooks, has_provenance=n in provenance,
                          maintainers=(maintainers or {}).get(n, []))
    return g


CHAIN = contagion([("a", "b"), ("b", "c"), ("c", "d")])


def ever(model, res):
    return {model.nodes[i] for i in np.flatnonzero(res.infection_time >= 0)}


# --------------------------------------------------------------------------- transitions
def test_deterministic_chain_s_to_i_to_r():
    m = ContagionModel.from_graph(CHAIN)
    res = simulate(m, SIRParams(beta=1.0, gamma=1.0), ["a"], rng=0)
    assert res.S.tolist() == [3, 2, 1, 0, 0]
    assert res.I.tolist() == [1, 1, 1, 1, 0]
    assert res.R.tolist() == [0, 1, 2, 3, 4]
    assert res.infection_time.tolist() == [0, 1, 2, 3]
    assert res.recovery_time.tolist() == [1, 2, 3, 4]
    assert res.generation.tolist() == [0, 1, 2, 3]
    assert res.infector.tolist() == [-1, 0, 1, 2]
    assert res.channel.tolist() == [SEED, DEPENDENCY, DEPENDENCY, DEPENDENCY]
    assert res.pathways() == [(0, 1, 1, DEPENDENCY), (1, 2, 2, DEPENDENCY), (2, 3, 3, DEPENDENCY)]


def test_contagion_follows_edge_direction():
    m = ContagionModel.from_graph(CHAIN)
    # d is a leaf dependent: compromising it must not reach its dependencies
    res = simulate(m, SIRParams(beta=1.0, gamma=1.0), ["d"], rng=0)
    assert ever(m, res) == {"d"}
    res = simulate(m, SIRParams(beta=1.0, gamma=1.0), ["b"], rng=0)
    assert ever(m, res) == {"b", "c", "d"}


def test_no_transmission_when_beta_zero():
    m = ContagionModel.from_graph(CHAIN)
    res = simulate(m, SIRParams(beta=0.0, gamma=0.3), ["a"], rng=1)
    assert res.ever_infected == 1 and res.I[-1] == 0 and res.R[-1] == 1


def test_stops_at_t_max_without_recovery():
    m = ContagionModel.from_graph(CHAIN)
    res = simulate(m, SIRParams(beta=1.0, gamma=0.0, t_max=10), ["a"], rng=0)
    assert res.duration == 10 and res.I[-1] == 4


def test_invariants_on_random_runs():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=600, seed=2)))
    m = ContagionModel.from_graph(g)
    hub = max(g, key=g.out_degree)
    for seed in range(5):
        res = simulate(m, SIRParams(beta=0.4, gamma=0.1, beta_maintainer=0.05), [hub], rng=seed)
        assert ((res.S + res.I + res.R) == m.n).all()
        assert (np.diff(res.S) <= 0).all() and (np.diff(res.R) >= 0).all()
        inf = res.infection_time >= 0
        recovered = res.recovery_time >= 0
        # every recovered infected node was infected strictly earlier (S -> I -> R)
        both = inf & recovered
        assert (res.infection_time[both] < res.recovery_time[both]).all()
        assert ((res.infection_time >= 0) == (res.channel != NEVER)).all()
        # each infection's infector was infected earlier and is one generation shallower
        kids = np.flatnonzero(res.channel > SEED)
        par = res.infector[kids]
        assert (res.infection_time[par] < res.infection_time[kids]).all()
        assert (res.generation[kids] == res.generation[par] + 1).all()
        dep = kids[res.channel[kids] == DEPENDENCY]
        assert all(g.has_edge(m.nodes[res.infector[u]], m.nodes[u]) for u in dep)


# --------------------------------------------------------------------------- edge weights
def transmission_rate(g, params, n=4000):
    m = ContagionModel.from_graph(g)
    hits = sum(simulate(m, params, ["a"], rng=s).ever_infected == 2 for s in range(n))
    return hits / n


@pytest.mark.parametrize("modifier, hooks, beta, expected", [
    (0.05, (), 1.0, 0.05),  # exact pin
    (0.85, (), 1.0, 0.85),  # tilde
    (1.0, ("a",), 0.4, 0.5),  # lifecycle hook on the infected source: 0.4 * 1.25
    (1.0, ("b",), 0.4, 0.4),  # hook on the target does not matter
    (1.0, ("a",), 0.9, 1.0),  # capped at 1
])
def test_edge_beta_weighting(modifier, hooks, beta, expected):
    g = contagion([("a", "b")], modifier=modifier, hooks=hooks)
    # gamma = 1: exactly one transmission attempt
    assert transmission_rate(g, SIRParams(beta=beta, gamma=1.0)) == pytest.approx(expected, abs=0.025)


def test_provenance_factor():
    g = contagion([("a", "b")], provenance=("b",))
    assert transmission_rate(g, SIRParams(beta=1.0, gamma=1.0), 200) == 1.0
    assert transmission_rate(g, SIRParams(beta=1.0, gamma=1.0, provenance_factor=0.0), 200) == 0.0


def test_with_overrides_changes_weights():
    m = ContagionModel.from_graph(contagion([("a", "b")]))
    pinned = m.with_overrides(w_semver=np.array([0.0]))
    assert simulate(pinned, SIRParams(beta=1.0, gamma=1.0), ["a"], rng=0).ever_infected == 1
    assert m.w_semver.tolist() == [1.0]


# --------------------------------------------------------------------------- maintainers
def test_maintainer_channel():
    g = contagion([], nodes=["a", "x", "y", "z"],
                  maintainers={"a": ["eve"], "x": ["eve"], "y": ["eve", "bob"], "z": ["bob"]})
    m = ContagionModel.from_graph(g)
    off = simulate(m, SIRParams(beta=1.0, gamma=1.0), ["a"], rng=0)
    assert off.ever_infected == 1
    on = simulate(m, SIRParams(beta=1.0, gamma=1.0, beta_maintainer=1.0), ["a"], rng=0)
    # eve leaks at t=0 -> x, y published at t=1; y leaks bob -> z at t=2
    assert on.infection_time.tolist() == [0, 1, 1, 2]
    assert on.channel.tolist() == [SEED, MAINTAINER, MAINTAINER, MAINTAINER]
    assert on.infector[m.index["z"]] == m.index["y"]


# --------------------------------------------------------------------------- interventions
def test_preimmunized_firebreak_blocks_path():
    m = ContagionModel.from_graph(CHAIN)
    p = SIRParams(beta=1.0, gamma=1.0)
    res = simulate(m, p, ["a"], rng=0, immunized=["b"])
    assert ever(m, res) == {"a"} and res.R[0] == 1
    # patient zero cannot be pre-immunized
    res = simulate(m, p, ["a"], rng=0, immunized=["a", "c"])
    assert ever(m, res) == {"a", "b"} and res.immunized.tolist() == [2]


def test_hub_policy_patches_highest_degree_infected():
    star = contagion([("hub", "mid")] + [("mid", f"l{i}") for i in range(5)] + [("hub", "x")])
    m = ContagionModel.from_graph(star)
    pol = make_policy(m, "hub", budget=1)
    res = simulate(m, SIRParams(beta=1.0, gamma=0.0, t_max=5), ["hub"], rng=0, policy=pol)
    # t=1: mid and x infected; mid (out-degree 5) outranks hub (2) and x (0), so it is patched
    assert res.recovery_time[m.index["mid"]] == 1
    assert ever(m, res) == {"hub", "mid", "x"}
    assert (res.n_patched <= 1).all()


def test_random_policy_budget_delay_and_vaccination():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=400, seed=4)))
    m = ContagionModel.from_graph(g)
    hub = max(g, key=g.out_degree)
    pol = PatchPolicy(budget=3, start_tick=4)
    res = simulate(m, SIRParams(beta=0.5, gamma=0.05), [hub], rng=0, policy=pol)
    assert (res.n_patched[:4] == 0).all() and (res.n_patched <= 3).all() and res.n_patched.sum() > 0

    vax = make_policy(m, "hub", budget=5, target="susceptible", start_tick=1)
    res = simulate(m, SIRParams(beta=0.0, gamma=0.0, t_max=3), [hub], rng=0, policy=vax)
    vaccinated = np.flatnonzero((res.recovery_time > 0) & (res.infection_time < 0))
    assert len(vaccinated) == 15
    top = set(np.argsort(-m.out_degree, kind="stable")[:16].tolist()) - {m.index[hub]}
    assert set(vaccinated.tolist()) <= top


def test_policy_reduces_outbreak():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=1000, seed=6)))
    m = ContagionModel.from_graph(g)
    hub = max(g, key=g.out_degree)
    p = SIRParams(beta=0.5, gamma=0.05)
    base = np.mean(run_monte_carlo(m, p, [hub], 40, seed=1, reducer=_size))
    patched = np.mean(run_monte_carlo(m, p, [hub], 40, seed=1, reducer=_size,
                                      policy=make_policy(m, "hub", budget=10)))
    assert patched < base


# --------------------------------------------------------------------------- monte carlo
def _size(res):
    return res.ever_infected


def test_monte_carlo_reproducible_and_parallel_identical():
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=500, seed=9)))
    m = ContagionModel.from_graph(g)
    hub = max(g, key=g.out_degree)
    p = SIRParams(beta=0.3, gamma=0.1)
    a = run_monte_carlo(m, p, [hub], 12, seed=5, reducer=_size)
    b = run_monte_carlo(m, p, [hub], 12, seed=5, reducer=_size)
    c = run_monte_carlo(m, p, [hub], 12, seed=5, reducer=_size, n_jobs=2)
    assert a == b == c
    assert len(set(a)) > 1  # runs are independent, not copies
    assert run_monte_carlo(m, p, [hub], 12, seed=6, reducer=_size) != a


def test_monte_carlo_random_patient_zero():
    m = ContagionModel.from_graph(CHAIN)
    res = run_monte_carlo(m, SIRParams(beta=0.0, gamma=1.0), lambda rng: [rng.choice(list("abcd"))], 30)
    assert len({int(r.patient_zero[0]) for r in res}) > 1


# --------------------------------------------------------------------------- ndlib
def test_custom_engine_matches_ndlib_on_homogeneous_graph():
    pytest.importorskip("ndlib")
    _, g = build_from_records(generate_synthetic_records(SyntheticConfig(n_nodes=400, seed=12)))
    nx.set_edge_attributes(g, 1.0, "edge_beta_modifier")
    nx.set_node_attributes(g, False, "has_lifecycle_hook")
    hub = max(g, key=g.out_degree)
    p = SIRParams(beta=0.3, gamma=0.2)
    m = ContagionModel.from_graph(g)

    ours = np.array(run_monte_carlo(m, p, [hub], 300, seed=0, reducer=_size))
    nd = np.array([run_ndlib_sir(g, p, [hub], seed=s).ever_infected for s in range(300)])
    se = np.sqrt(ours.var() / len(ours) + nd.var() / len(nd))
    assert abs(ours.mean() - nd.mean()) < 4 * se

    res = run_ndlib_sir(g, p, [hub], seed=1)
    assert ((res.S + res.I + res.R) == g.number_of_nodes()).all() and res.I[-1] == 0
    assert res.ever_infected == res.R[-1]
