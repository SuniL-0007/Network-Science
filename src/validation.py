"""Empirical validation against the real Shai-Hulud compromised-package lists.

Uses registry *metadata only* (latest-version manifests, never tarballs) for the packages in
data/raw/incidents/compromised_packages.csv and asks:

1. Clustering: do compromised packages of a wave share maintainers with each other far
   more often than they are linked by dependencies?  (credential vs. dependency channel)
2. Position: where do compromised packages that appear in our npm graphs sit in terms of
   contagion out-degree and blast radius (were the worms' victims hubs)?
3. Null: the same statistics for random package sets of equal size drawn from our crawl.

Caveat: manifests are fetched today, so maintainers/dependencies may differ slightly from
those at the time of the incident.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import METRICS_DIR, RAW_DIR, CrawlConfig
from src.data_ingestion import NpmRegistryClient, load_records, record_from_manifest

log = logging.getLogger(__name__)

INCIDENT_CSV = RAW_DIR / "incidents" / "compromised_packages.csv"


def load_incident_packages(path: Path = INCIDENT_CSV) -> dict[str, set[str]]:
    """incident -> set of compromised package names."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {inc: set(g["package"].str.strip()) - {""} for inc, g in df.groupby("incident")}


def fetch_records(names, cfg: CrawlConfig = CrawlConfig(), workers: int = 8) -> dict:
    client = NpmRegistryClient(cfg)

    def one(name):
        try:
            m = client.fetch_manifest(name)
            return name, (record_from_manifest(m) if m and "name" in m else None)
        except Exception as exc:  # unpublished/blocked packages are expected
            log.debug("no manifest for %s: %s", name, exc)
            return name, None

    with ThreadPoolExecutor(workers) as pool:
        return {n: r for n, r in pool.map(one, sorted(names)) if r is not None}


def clustering_stats(records: dict) -> dict:
    """Shares of packages with a co-maintained / dependency-linked partner inside the set."""
    names = set(records)
    by_maint = defaultdict(set)
    for n, r in records.items():
        for m in r.maintainers:
            by_maint[m].add(n)
    co_maint = {n for pkgs in by_maint.values() if len(pkgs) > 1 for n in pkgs}
    dep_linked = set()
    for n, r in records.items():
        targets = {d.target for d in r.deps} & names
        targets.discard(n)
        if targets:
            dep_linked.add(n)
            dep_linked |= targets
    sizes = np.array(sorted((len(p) for p in by_maint.values()), reverse=True))
    return {
        "n_packages": len(names),
        "n_maintainers": len(by_maint),
        "share_co_maintained": len(co_maint) / len(names) if names else np.nan,
        "share_dependency_linked": len(dep_linked) / len(names) if names else np.nan,
        "share_installed_dependency_linked": (
            len({n for n, r in records.items()
                 if {d.target for d in r.deps if d.dep_type != "dev"} & (names - {n})}) / len(names)
            if names else np.nan),
        "largest_maintainer_cluster": int(sizes[0]) if len(sizes) else 0,
        "median_maintainer_cluster": float(np.median(sizes)) if len(sizes) else np.nan,
    }


def null_clustering(population: list, k: int, draws: int = 200, seed: int = 0) -> dict:
    """Mean clustering stats over random size-k subsets of a record population."""
    rng = np.random.default_rng(seed)
    stats = [clustering_stats({r.name: r for r in rng.choice(population, size=min(k, len(population)),
                                                                replace=False)})
             for _ in range(draws)]
    df = pd.DataFrame(stats)
    return {f"null_{c}": float(df[c].mean()) for c in
            ("share_co_maintained", "share_dependency_linked", "share_installed_dependency_linked")}


def graph_positions(names: set, node_metrics: pd.DataFrame) -> dict:
    """Percentile ranks of compromised packages present in a topology node-metrics table."""
    present = [n for n in names if n in node_metrics.index]
    out = {"n_in_graph": len(present)}
    for col in ("out_degree", "transitive_dependents", "pagerank", "betweenness"):
        pct = node_metrics[col].rank(pct=True)
        out[f"median_pct_{col}"] = float(pct.loc[present].median()) if present else np.nan
    return out


def run_validation(population_snapshot: Path, metrics_tags: list[str], metrics_dir: Path = METRICS_DIR,
                   draws: int = 200) -> pd.DataFrame:
    incidents = load_incident_packages()
    all_names = set().union(*incidents.values())
    log.info("fetching metadata for %d compromised packages", len(all_names))
    records = fetch_records(all_names)
    population = load_records(population_snapshot)
    tables = {t: pd.read_csv(metrics_dir / f"{t}_node_metrics.csv", index_col="name", dtype={"name": str},
                             keep_default_na=False, na_values=[""]) for t in metrics_tags}
    rows = []
    for inc, names in sorted(incidents.items()):
        recs = {n: records[n] for n in names if n in records}
        row = {"incident": inc, "n_listed": len(names), "n_metadata": len(recs), **clustering_stats(recs)}
        row.update(null_clustering(population, len(recs), draws))
        for t, nm in tables.items():
            row.update({f"{t}:{k}": v for k, v in graph_positions(names, nm).items()})
        rows.append(row)
        log.info("%s: %d/%d with metadata, co-maintained %.2f vs null %.2f, dep-linked %.2f vs null %.2f",
                 inc, len(recs), len(names), row["share_co_maintained"], row["null_share_co_maintained"],
                 row["share_dependency_linked"], row["null_share_dependency_linked"])
    return pd.DataFrame(rows)


def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Validate the model's channels against Shai-Hulud data.")
    p.add_argument("--population", type=Path, default=RAW_DIR / "npm_hi_n14660.jsonl")
    p.add_argument("--tags", nargs="+", default=["npm_hi_n10k_contagion", "npm_hi_n14660_contagion"])
    p.add_argument("--draws", type=int, default=200)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = run_validation(args.population, args.tags, draws=args.draws)
    out = METRICS_DIR / "validation_incidents.csv"
    df.to_csv(out, index=False)
    log.info("wrote %s", out)
    print(json.dumps(df.set_index("incident").round(3).to_dict(orient="index"), indent=1))


if __name__ == "__main__":
    _cli()
