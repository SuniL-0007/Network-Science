"""Milestone 2 tests: dependency/contagion graph construction and edge reversal."""

import networkx as nx
import pytest

from src.config import ALL_DEP_TYPES, SEMVER_BETA_MODIFIER, SyntheticConfig
from src.data_ingestion import Dependency, PackageRecord, generate_synthetic_records
from src.graph_builder import (
    State,
    build_contagion_graph,
    build_dependency_graph,
    build_from_records,
    load_graph,
    maintainer_index,
    save_graph,
)


def rec(name, deps=(), **kw):
    return PackageRecord(name=name, version="1.0.0", deps=[Dependency(*d) for d in deps], **kw)


# app depends on express (caret) and lodash (exact); express depends on lodash (tilde).
RECORDS = [
    rec("app", [("express", "^4.0.0", "prod", "caret"), ("lodash", "4.17.21", "prod", "exact"),
                ("jest", "^29.0.0", "dev", "caret"), ("ghost", "^1.0.0", "prod", "caret"),
                ("mylib", "github:me/mylib", "prod", "non_registry"), ("app", "*", "prod", "wildcard")],
        maintainers=["alice"]),
    rec("express", [("lodash", "~4.17.0", "prod", "tilde"), ("lodash", "^4.0.0", "dev", "wildcard")],
        has_install_script=True, maintainers=["alice", "bob"]),
    rec("lodash", has_provenance=True, maintainers=["bob"], dependent_count=999),
    rec("jest", maintainers=["carol"]),
    rec("mylib"),
]


@pytest.fixture
def graphs():
    return build_from_records(RECORDS)


def test_dependency_edges_point_to_dependencies(graphs):
    g_dep, _ = graphs
    assert set(g_dep.edges) == {("app", "express"), ("app", "lodash"), ("express", "lodash")}


def test_contagion_graph_is_exact_reversal(graphs):
    g_dep, g_con = graphs
    # compromise of a dependency exposes its dependents: lodash -> express -> app
    assert set(g_con.edges) == {(v, u) for u, v in g_dep.edges}
    assert set(g_con.successors("lodash")) == {"express", "app"}
    assert set(g_con.predecessors("app")) == {"express", "lodash"}
    assert nx.descendants(g_con, "lodash") == {"express", "app"}
    assert nx.descendants(g_con, "app") == set()
    for u, v, data in g_dep.edges(data=True):
        assert g_con.edges[v, u] == data
    # reversal must not alias the original graph
    g_con.edges["lodash", "app"]["edge_beta_modifier"] = -1
    assert g_dep.edges["app", "lodash"]["edge_beta_modifier"] == SEMVER_BETA_MODIFIER["exact"]


def test_edge_attributes(graphs):
    _, g_con = graphs
    e = g_con.edges["express", "app"]
    assert e == {"semver_type": "caret", "dep_type": "prod", "raw_spec": "^4.0.0",
                 "edge_beta_modifier": 1.0}
    assert g_con.edges["lodash", "app"]["edge_beta_modifier"] == 0.05
    # prod (installed) link wins over a looser dev link between the same pair
    assert g_con.edges["lodash", "express"]["semver_type"] == "tilde"
    assert g_con.edges["lodash", "express"]["edge_beta_modifier"] == 0.85


def test_node_attributes(graphs):
    _, g_con = graphs
    assert set(g_con.nodes) == {"app", "express", "lodash", "jest", "mylib"}
    assert all(d["state"] == State.S for _, d in g_con.nodes(data=True))
    assert g_con.nodes["express"]["has_lifecycle_hook"] is True
    assert g_con.nodes["lodash"]["has_provenance"] is True
    assert g_con.nodes["lodash"]["dependent_count"] == 999
    assert g_con.nodes["app"]["name"] == "app"


def test_filters_dev_external_nonregistry_selfloops(graphs):
    g_dep, _ = graphs
    assert not g_dep.has_edge("app", "jest")  # dev not installed by consumers
    assert "ghost" not in g_dep  # outside snapshot
    assert not g_dep.has_edge("app", "mylib")  # git dep: no registry contagion
    assert nx.number_of_selfloops(g_dep) == 0

    with_dev = build_dependency_graph(RECORDS, dep_types=ALL_DEP_TYPES)
    assert with_dev.edges["app", "jest"]["dep_type"] == "dev"
    with_git = build_dependency_graph(RECORDS, drop_non_registry=False)
    assert with_git.edges["app", "mylib"]["edge_beta_modifier"] == 0.0


def test_maintainer_index(graphs):
    _, g_con = graphs
    idx = maintainer_index(g_con)
    assert sorted(idx["alice"]) == ["app", "express"]
    assert sorted(idx["bob"]) == ["express", "lodash"]


@pytest.mark.parametrize("fmt", ["pkl", "graphml"])
def test_save_load_roundtrip(tmp_path, graphs, fmt):
    _, g_con = graphs
    save_graph(g_con, tmp_path / "g")
    back = load_graph(tmp_path / f"g.{fmt}")
    assert set(back.edges) == set(g_con.edges)
    assert back.nodes["express"]["maintainers"] == ["alice", "bob"]
    assert back.nodes["express"]["has_lifecycle_hook"] is True
    assert back.edges["lodash", "app"]["edge_beta_modifier"] == pytest.approx(0.05)


def test_synthetic_contagion_hubs_have_high_out_degree():
    records = generate_synthetic_records(SyntheticConfig(n_nodes=1000, seed=3))
    g_dep, g_con = build_from_records(records)
    assert g_con.number_of_edges() == g_dep.number_of_edges()
    hub = max(g_con.nodes, key=g_con.out_degree)
    # the most-depended-upon package spreads to the most direct dependents
    assert g_con.out_degree(hub) == g_dep.in_degree(hub) == max(d for _, d in g_dep.in_degree())
    assert build_contagion_graph(g_con).edges == g_dep.edges


def test_spam_rings_are_dropped_but_sparse_cycles_kept():
    from src.graph_builder import spam_ring_nodes
    ring = [f"fruit{i}" for i in range(12)]
    records = [rec(u, [(v, "^1.0.0", "prod", "caret") for v in ring if v != u], maintainers=["spammer"])
               for u in ring]
    records.append(rec("fruit-extra", maintainers=["spammer"]))
    mono = [f"@mono/p{i}" for i in range(12)]  # sparse legitimate cycle: a ring of 12
    records += [rec(u, [(mono[(i + 1) % 12], "^1.0.0", "prod", "caret")], maintainers=["dev"])
                for i, u in enumerate(mono)]
    records.append(rec("app", [("fruit0", "^1.0.0", "prod", "caret"), ("@mono/p0", "^1.0.0", "prod", "caret")]))

    g_dep = build_dependency_graph(records)
    assert spam_ring_nodes(g_dep) == set(ring) | {"fruit-extra"}
    g_dep, g_con = build_from_records(records)
    assert not any(u.startswith("fruit") for u in g_con)
    assert set(mono) <= set(g_con) and "app" in g_con
    kept = build_from_records(records, drop_spam=False)[1]
    assert "fruit0" in kept
