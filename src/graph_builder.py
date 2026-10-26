"""Build dependency and contagion graphs from `PackageRecord`s.

G_dep:        u -> v  iff package u depends on package v.
G_contagion:  v -> u  (G_dep reversed): a compromise of v exposes its dependent u.

Every edge carries `semver_type`, `dep_type`, `raw_spec` and `edge_beta_modifier`.
Every node carries `name`, `version`, `state` (S=0), `has_lifecycle_hook`, `has_provenance`,
`maintainers`, `dependent_count` and `depth`.
"""

from __future__ import annotations

import argparse
import logging
import pickle
from collections import defaultdict
from collections.abc import Iterable
from enum import IntEnum
from pathlib import Path

import networkx as nx

from src.config import INSTALLED_DEP_TYPES, PROCESSED_DIR, SEMVER_BETA_MODIFIER, SEMVER_TYPES
from src.data_ingestion import PackageRecord, load_records

log = logging.getLogger(__name__)


class State(IntEnum):
    S = 0
    I = 1  # noqa: E741 - epidemiological convention
    R = 2


def _edge_rank(dep_type: str, semver_type: str) -> tuple[int, int]:
    # When a pair is linked twice (e.g. prod + dev), keep the installed, loosest link.
    return (dep_type in INSTALLED_DEP_TYPES, SEMVER_TYPES.index(semver_type))


def build_dependency_graph(
    records: Iterable[PackageRecord],
    dep_types: Iterable[str] = INSTALLED_DEP_TYPES,
    drop_non_registry: bool = True,
) -> nx.DiGraph:
    """Dependency graph G_dep over the packages present in `records`.

    Edges to packages without a record (outside the crawl limits) are dropped so every node
    has complete attributes. `non_registry` deps (git/file/url) are dropped by default since
    registry publishes never reach them. Self-dependencies are ignored.
    """
    records = list(records)
    dep_types = set(dep_types)
    g = nx.DiGraph()
    for r in records:
        g.add_node(
            r.name,
            name=r.name,
            version=r.version,
            state=int(State.S),
            has_lifecycle_hook=r.has_install_script,
            has_provenance=r.has_provenance,
            maintainers=list(r.maintainers),
            dependent_count=r.dependent_count,
            depth=r.depth,
        )

    dropped_external = 0
    for r in records:
        for d in r.deps:
            if d.dep_type not in dep_types or d.target == r.name:
                continue
            if drop_non_registry and d.semver_type == "non_registry":
                continue
            if d.target not in g:
                dropped_external += 1
                continue
            if g.has_edge(r.name, d.target):
                old = g.edges[r.name, d.target]
                if _edge_rank(d.dep_type, d.semver_type) <= _edge_rank(old["dep_type"], old["semver_type"]):
                    continue
            g.add_edge(
                r.name, d.target,
                semver_type=d.semver_type,
                dep_type=d.dep_type,
                raw_spec=d.raw_spec,
                edge_beta_modifier=SEMVER_BETA_MODIFIER[d.semver_type],
            )
    if dropped_external:
        log.info("Dropped %d edges to packages outside the snapshot", dropped_external)
    return g


def build_contagion_graph(g_dep: nx.DiGraph) -> nx.DiGraph:
    """G_contagion = reverse(G_dep): edges point from dependency v to dependent u."""
    return g_dep.reverse(copy=True)


def maintainer_index(g: nx.DiGraph) -> dict[str, list[str]]:
    """maintainer -> packages they can publish (the credential-theft contagion channel)."""
    idx: dict[str, list[str]] = defaultdict(list)
    for node, maint in g.nodes(data="maintainers"):
        for m in maint or []:
            idx[m].append(node)
    return dict(idx)


def spam_ring_nodes(g: nx.DiGraph, min_size: int = 10, min_density: float = 0.5,
                    owner_share: float = 0.5) -> set:
    """Packages of artificial mutual-dependency rings (e.g. reward-farming spam).

    A ring is an SCC of at least `min_size` packages with edge density >= `min_density`;
    legitimate monorepo cycles are far sparser. Also returns the other packages of any
    maintainer who owns at least `owner_share` of a ring.
    """
    flagged: set = set()
    for scc in nx.strongly_connected_components(g):
        n = len(scc)
        if n < min_size or g.subgraph(scc).number_of_edges() / (n * (n - 1)) < min_density:
            continue
        flagged |= scc
        owners = maintainer_index(g.subgraph(scc))
        spammers = {m for m, pkgs in owners.items() if len(pkgs) >= owner_share * n}
        flagged |= {u for u, ms in g.nodes(data="maintainers") if spammers & set(ms or [])}
    return flagged


def build_from_records(
    records: Iterable[PackageRecord], dep_types: Iterable[str] = INSTALLED_DEP_TYPES,
    drop_spam: bool = True,
) -> tuple[nx.DiGraph, nx.DiGraph]:
    g_dep = build_dependency_graph(records, dep_types)
    if drop_spam:
        spam = spam_ring_nodes(g_dep)
        if spam:
            log.info("Dropped %d packages in spam rings: %s", len(spam), sorted(spam)[:5])
            g_dep.remove_nodes_from(spam)
    return g_dep, build_contagion_graph(g_dep)


# =========================================================================== io
def _graphml_safe(g: nx.DiGraph) -> nx.DiGraph:
    """GraphML has no list/None types: join lists with ';' and drop None attributes."""
    h = g.copy()
    for _, data in list(h.nodes(data=True)) + [(None, d) for *_, d in h.edges(data=True)]:
        for k, v in list(data.items()):
            if v is None:
                del data[k]
            elif isinstance(v, (list, tuple)):
                data[k] = ";".join(map(str, v))
    return h


def save_graph(g: nx.DiGraph, stem: str | Path, graphml: bool = True) -> Path:
    """Write `<stem>.pkl` (lossless, fast) and optionally `<stem>.graphml` (portable)."""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    pkl = stem.with_suffix(".pkl")
    with pkl.open("wb") as fh:
        pickle.dump(g, fh, protocol=pickle.HIGHEST_PROTOCOL)
    if graphml:
        nx.write_graphml(_graphml_safe(g), stem.with_suffix(".graphml"))
    return pkl


def load_graph(path: str | Path) -> nx.DiGraph:
    """Load a graph saved by `save_graph` (.pkl, or .graphml with lists restored)."""
    path = Path(path)
    if path.suffix == ".pkl":
        with path.open("rb") as fh:
            return pickle.load(fh)
    g = nx.read_graphml(path)
    for _, data in g.nodes(data=True):
        data["maintainers"] = [m for m in str(data.get("maintainers", "")).split(";") if m]
        data.setdefault("dependent_count", None)
        data.setdefault("depth", None)
    return g


# =========================================================================== cli
def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build the contagion graph from a JSONL snapshot.")
    p.add_argument("snapshot", type=Path, help="data/raw/*.jsonl produced by data_ingestion")
    p.add_argument("--include-dev", action="store_true",
                   help="also add devDependency edges (credential channel, not install-time)")
    p.add_argument("--out", type=Path, help="output stem (default: data/processed/<snapshot>)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dep_types = INSTALLED_DEP_TYPES + (("dev",) if args.include_dev else ())
    _, g_con = build_from_records(load_records(args.snapshot), dep_types)
    stem = args.out or PROCESSED_DIR / f"{args.snapshot.stem}_contagion"
    pkl = save_graph(g_con, stem)
    log.info("Contagion graph: %d nodes, %d edges -> %s", g_con.number_of_nodes(),
             g_con.number_of_edges(), pkl)


if __name__ == "__main__":
    _cli()
