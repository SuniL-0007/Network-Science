"""Data ingestion: npm registry crawler, deps.dev enrichment, and synthetic scale-free generator.

Both data modes emit the same `PackageRecord` list, so `graph_builder` has one input format.

Edge semantics in a record: `PackageRecord(name=u).deps` contains `v` iff u depends on v
(dependency direction u -> v). Contagion reversal happens later, in graph_builder.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import networkx as nx
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    DEFAULT_SEEDS,
    LIFECYCLE_HOOKS,
    RAW_DIR,
    SEMVER_TYPES,
    CrawlConfig,
    SyntheticConfig,
)

log = logging.getLogger(__name__)


# =========================================================================== records
@dataclass
class Dependency:
    target: str  # real package name (npm: aliases already resolved)
    raw_spec: str  # e.g. "^1.2.0", "npm:strip-ansi@^6", "github:user/repo"
    dep_type: str  # prod | dev | peer | optional
    semver_type: str  # one of config.SEMVER_TYPES


@dataclass
class PackageRecord:
    name: str
    version: str
    deps: list[Dependency] = field(default_factory=list)
    lifecycle_hooks: list[str] = field(default_factory=list)
    has_install_script: bool = False
    has_provenance: bool = False
    maintainers: list[str] = field(default_factory=list)
    dependent_count: int | None = None  # ecosystem-wide, from deps.dev (corrects crawl bias)
    depth: int | None = None  # BFS depth from the seed set (None for synthetic)
    source: str = "npm"

    @classmethod
    def from_dict(cls, d: dict) -> PackageRecord:
        d = dict(d)
        d["deps"] = [Dependency(**x) for x in d.get("deps", [])]
        return cls(**d)


# =========================================================================== semver
_NON_REGISTRY_PREFIXES = (
    "git+", "git:", "git@", "github:", "gitlab:", "bitbucket:", "gist:",
    "http:", "https:", "file:", "link:", "workspace:", "portal:", "patch:",
)
_GITHUB_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+(#.*)?$")
_DIST_TAG = re.compile(r"^[a-z][\w.-]*$", re.IGNORECASE)
_PARTIAL = re.compile(r"^v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(-[\w.-]+)?(\+[\w.-]+)?$")


def _loosest(types: Iterable[str]) -> str:
    return max(types, key=SEMVER_TYPES.index)


def _partial(version: str) -> list[int | None] | None:
    """'1.2.x' -> [1, 2, None]; missing or wildcard components become None."""
    m = _PARTIAL.match(version.strip())
    if not m:
        return None
    parts = [m.group(i) for i in (1, 2, 3)]
    return [int(p) if p is not None and p.isdigit() else None for p in parts]


def _classify_xrange(parts: list[int | None]) -> str:
    major, minor, patch = parts
    if major is None:
        return "wildcard"
    if minor is None:
        return "caret"  # "1" / "1.x" == >=1.0.0 <2.0.0
    if patch is None:
        return "tilde"  # "1.2" / "1.2.x" == >=1.2.0 <1.3.0
    return "exact"


def _classify_caret(parts: list[int | None]) -> str:
    # npm caret: allow changes that don't modify the left-most non-zero component.
    major, minor, patch = parts
    if major is None:
        return "wildcard"
    if major > 0 or minor is None:
        return "caret"  # ^1.2.3 / ^0 / ^0.x
    if minor > 0 or patch is None:
        return "tilde"  # ^0.2.3 == >=0.2.3 <0.3.0 ; ^0.0 == <0.1.0
    return "exact"  # ^0.0.3 == >=0.0.3 <0.0.4


def _classify_comparators(tokens: list[str]) -> str:
    lowers = [t for t in tokens if t.startswith(">")]
    uppers = [t for t in tokens if t.startswith("<")]
    if lowers and not uppers:
        return "wildcard"  # open upper bound, e.g. ">=1.0.0"
    if lowers and uppers:
        lo = _partial(lowers[0].lstrip(">="))
        hi = _partial(uppers[0].lstrip("<="))
        if lo and hi and lo[0] is not None and lo[0] == hi[0] and lo[1] is not None and hi[1] is not None:
            exclusive = not uppers[0].startswith("<=")
            same_minor = hi[1] == lo[1]
            # "<1.3.0" (exclusive, next minor at .0) still only admits 1.2.x patches
            next_minor_floor = exclusive and hi[1] == lo[1] + 1 and not hi[2]
            if same_minor or next_minor_floor:
                return "tilde"
        return "caret"
    return "caret"  # "<2.0.0" floats over the latest 1.x line


def classify_semver(spec: str) -> str:
    """Classify an npm dependency spec by how permissive it is to automatic updates.

    Returns one of `config.SEMVER_TYPES`. Follows node-semver semantics for caret on 0.x,
    x-ranges, hyphen ranges, `||` unions (loosest branch wins), and dist-tags.
    """
    s = spec.strip()
    if "||" in s:
        return _loosest(classify_semver(p) for p in s.split("||"))
    if s.startswith("npm:"):
        return classify_semver(split_alias(s)[1])
    if s in ("", "*", "x", "X", "latest"):
        return "wildcard"
    if s.lower().startswith(_NON_REGISTRY_PREFIXES) or _GITHUB_SHORTHAND.match(s):
        return "non_registry"

    if " - " in s:  # hyphen range "1.2.3 - 2.3.4"
        lo, hi = (x.strip() for x in s.split(" - ", 1))
        return _classify_comparators([">=" + lo, "<=" + hi])

    tokens = s.split()
    if len(tokens) > 1 or s[0] in "<>":
        return _classify_comparators([t for t in tokens if t])

    if s.startswith("^"):
        parts = _partial(s[1:])
        return _classify_caret(parts) if parts else "caret"
    if s.startswith("~"):
        parts = _partial(s.lstrip("~>"))
        if parts is None:
            return "tilde"
        return "caret" if parts[1] is None and parts[0] is not None else (
            "wildcard" if parts[0] is None else "tilde"
        )

    parts = _partial(s.lstrip("="))
    if parts is not None:
        return _classify_xrange(parts)
    if _DIST_TAG.match(s):
        return "wildcard"  # dist-tag such as "next" or "beta" follows new publishes
    log.debug("Unrecognised semver spec %r; treating as caret", spec)
    return "caret"


def split_alias(spec: str) -> tuple[str, str]:
    """'npm:@scope/pkg@^1.0.0' -> ('@scope/pkg', '^1.0.0'); 'npm:pkg' -> ('pkg', '*')."""
    body = spec[len("npm:"):]
    at = body.rfind("@")
    if at > 0:
        return body[:at], body[at + 1:] or "*"
    return body, "*"


def parse_dependency(name: str, spec: str, dep_type: str) -> Dependency:
    spec = spec if isinstance(spec, str) else str(spec)
    target = split_alias(spec.strip())[0] if spec.strip().startswith("npm:") else name
    return Dependency(target=target, raw_spec=spec, dep_type=dep_type,
                      semver_type=classify_semver(spec))


# =========================================================================== manifests
_DEP_FIELDS = (
    ("optionalDependencies", "optional"),  # first: npm also mirrors these into dependencies
    ("dependencies", "prod"),
    ("peerDependencies", "peer"),
    ("devDependencies", "dev"),
)


def _maintainer_names(raw) -> list[str]:
    names = []
    for m in raw or []:
        if isinstance(m, dict) and m.get("name"):
            names.append(m["name"])
        elif isinstance(m, str):
            names.append(m.split("<")[0].strip())
    return sorted(set(n for n in names if n))


def record_from_manifest(manifest: dict, depth: int | None = None) -> PackageRecord:
    """Build a PackageRecord from a registry version manifest (`/<name>/latest`)."""
    deps: list[Dependency] = []
    seen: set[tuple[str, str]] = set()
    for fld, dep_type in _DEP_FIELDS:
        table = manifest.get(fld) or {}
        if not isinstance(table, dict):
            continue
        for dep_name, spec in table.items():
            # An optional dep also listed under dependencies is recorded once, as optional.
            key = (dep_name, "installed" if dep_type in ("prod", "optional") else dep_type)
            if key in seen:
                continue
            seen.add(key)
            deps.append(parse_dependency(dep_name, spec, dep_type))

    scripts = manifest.get("scripts") or {}
    hooks = [h for h in LIFECYCLE_HOOKS if isinstance(scripts, dict) and scripts.get(h)]
    dist = manifest.get("dist") or {}
    return PackageRecord(
        name=manifest["name"],
        version=str(manifest.get("version", "")),
        deps=deps,
        lifecycle_hooks=hooks,
        has_install_script=bool(hooks or manifest.get("hasInstallScript") or manifest.get("gypfile")),
        has_provenance=bool(dist.get("attestations")),
        maintainers=_maintainer_names(manifest.get("maintainers")),
        depth=depth,
        source="npm",
    )


# =========================================================================== http clients
class _CachedJsonClient:
    """GET JSON with retries, a thread-local session, and an on-disk cache (incl. 404s)."""

    _MISSING = {"__missing__": True}

    def __init__(self, cfg: CrawlConfig, namespace: str):
        self.cfg = cfg
        self.cache_dir = Path(cfg.cache_dir) / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            retry = Retry(
                total=self.cfg.max_retries,
                backoff_factor=self.cfg.backoff_factor,
                status_forcelist=(429, 500, 502, 503, 504),
                respect_retry_after_header=True,
                allowed_methods=("GET",),
            )
            s.mount("https://", HTTPAdapter(max_retries=retry))
            s.headers["User-Agent"] = self.cfg.user_agent
            self._local.session = s
        return s

    def get_json(self, url: str, cache_key: str) -> dict | None:
        path = self.cache_dir / (quote(cache_key, safe="") + ".json")
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return None if data == self._MISSING else data
        resp = self._session().get(url, timeout=self.cfg.timeout_s)
        if resp.status_code == 404:
            data = None
        else:
            resp.raise_for_status()
            data = resp.json()
        path.write_text(json.dumps(data if data is not None else self._MISSING), encoding="utf-8")
        return data


class NpmRegistryClient(_CachedJsonClient):
    def __init__(self, cfg: CrawlConfig = CrawlConfig()):
        super().__init__(cfg, "registry")

    def fetch_manifest(self, name: str) -> dict | None:
        """Latest-version manifest (package.json + dist + maintainers), or None if absent."""
        url = f"{self.cfg.registry_url}/{quote(name, safe='@')}/latest"
        return self.get_json(url, name)


class DepsDevClient(_CachedJsonClient):
    def __init__(self, cfg: CrawlConfig = CrawlConfig()):
        super().__init__(cfg, "depsdev")

    def dependent_count(self, name: str, version: str) -> int | None:
        """Ecosystem-wide number of packages depending on name@version (deps.dev v3alpha)."""
        url = (f"{self.cfg.depsdev_url}/v3alpha/systems/npm/packages/{quote(name, safe='')}"
               f"/versions/{quote(version, safe='')}:dependents")
        data = self.get_json(url, f"{name}@{version}")
        return int(data["dependentCount"]) if data and "dependentCount" in data else None


# =========================================================================== crawler
def crawl_npm(
    seeds: Iterable[str] = DEFAULT_SEEDS,
    cfg: CrawlConfig = CrawlConfig(),
    fetch: Callable[[str], dict | None] | None = None,
    dependents: Callable[[str, str], int | None] | None = None,
) -> list[PackageRecord]:
    """Breadth-first crawl of the dependency closure of `seeds`, bounded by depth and size.

    `fetch` / `dependents` default to the live registry and deps.dev clients and can be
    replaced by fakes in tests. deps.dev enrichment runs only when `dependents` is given
    (or call `enrich_dependent_counts` later). Dependencies that fall outside
    the limits remain in each record's `deps`; graph_builder decides how to treat them.
    """
    fetch = fetch or NpmRegistryClient(cfg).fetch_manifest
    follow = set(cfg.follow_dep_types)
    records: dict[str, PackageRecord] = {}
    frontier = list(dict.fromkeys(seeds))
    seen = set(frontier)
    depth = 0

    def safe_fetch(name: str) -> dict | None:
        try:
            return fetch(name)
        except Exception as exc:  # network failure after retries: skip, don't cache
            log.warning("Failed to fetch %s: %s", name, exc)
            return None

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        while frontier and depth <= cfg.max_depth and len(records) < cfg.max_nodes:
            next_frontier: list[str] = []
            while frontier and len(records) < cfg.max_nodes:
                chunk, frontier = frontier[: cfg.max_nodes - len(records)], frontier[cfg.max_nodes - len(records):]
                for name, manifest in zip(chunk, pool.map(safe_fetch, chunk)):
                    if manifest is None or "name" not in manifest:
                        continue
                    rec = record_from_manifest(manifest, depth)
                    rec.name = name  # key by the requested name for consistent edges
                    records[name] = rec
                    for d in rec.deps:
                        if d.dep_type in follow and d.semver_type != "non_registry" and d.target not in seen:
                            seen.add(d.target)
                            next_frontier.append(d.target)
            log.info("depth %d done: %d packages, %d queued", depth, len(records), len(next_frontier))
            frontier, depth = next_frontier, depth + 1

    out = list(records.values())
    if dependents:
        enrich_dependent_counts(out, dependents, cfg.max_workers)
    return out


def enrich_dependent_counts(
    records: list[PackageRecord],
    dependents: Callable[[str, str], int | None] | None = None,
    max_workers: int = 8,
) -> None:
    """Fill `dependent_count` in place from deps.dev (failures leave it as None)."""
    dependents = dependents or DepsDevClient().dependent_count

    def one(rec: PackageRecord) -> int | None:
        try:
            return dependents(rec.name, rec.version)
        except Exception as exc:
            log.warning("deps.dev lookup failed for %s@%s: %s", rec.name, rec.version, exc)
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for rec, count in zip(records, pool.map(one, records)):
            rec.dependent_count = count


def load_seeds(path: str | Path, top_n: int | None = None) -> list[str]:
    """Read seeds from a .txt (one name per line, '#' comments) or a Libraries.io-style CSV.

    For CSVs, rows are filtered to Platform == NPM when that column exists and sorted by
    'Dependents Count' / 'Dependent Projects Count' when present.
    """
    path = Path(path)
    if path.suffix.lower() != ".csv":
        names = [ln.split("#")[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()]
        names = [n for n in names if n]
        return names[:top_n] if top_n else names

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "Platform" in rows[0]:
        rows = [r for r in rows if r["Platform"].strip().lower() == "npm"]
    for col in ("Dependents Count", "Dependent Projects Count"):
        if rows and col in rows[0]:
            rows.sort(key=lambda r: int(r[col] or 0), reverse=True)
            break
    name_col = "Name" if rows and "Name" in rows[0] else "name"
    names = list(dict.fromkeys(r[name_col].strip() for r in rows if r.get(name_col)))
    return names[:top_n] if top_n else names


# =========================================================================== synthetic
_HOOK_WEIGHTS = {"postinstall": 0.7, "install": 0.2, "preinstall": 0.1}


def _synthetic_spec(semver_type: str, rng: np.random.Generator) -> str:
    # Major >= 1 so caret/tilde keep their usual meaning (caret on 0.x behaves like tilde).
    major, minor, patch = int(rng.integers(1, 10)), int(rng.integers(0, 20)), int(rng.integers(0, 30))
    v = f"{major}.{minor}.{patch}"
    return {"exact": v, "tilde": "~" + v, "caret": "^" + v, "wildcard": "*"}[semver_type]


def generate_synthetic_records(cfg: SyntheticConfig = SyntheticConfig()) -> list[PackageRecord]:
    """Directed scale-free benchmark ecosystem with npm-like attribute proportions.

    `nx.scale_free_graph` attaches new edges *to* nodes chosen by in-degree, so for an edge
    u -> v we read "u depends on v": in-degree (number of dependents) is heavy-tailed. The
    multigraph is collapsed to a simple DiGraph without self-loops and, with `cfg.acyclic`,
    every edge is oriented newer -> older, which makes the graph a DAG.
    """
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_nodes
    mg = nx.scale_free_graph(
        n, alpha=cfg.alpha, beta=cfg.beta, gamma=cfg.gamma,
        delta_in=cfg.delta_in, delta_out=cfg.delta_out, seed=cfg.seed,
    )
    g = nx.DiGraph(mg)
    g.remove_edges_from(list(nx.selfloop_edges(g)))
    if cfg.acyclic:  # node index == creation order, so u > v means u is newer than v
        flipped = nx.DiGraph()
        flipped.add_nodes_from(range(n))
        flipped.add_edges_from((max(u, v), min(u, v)) for u, v in g.edges)
        g = flipped
    names = [f"pkg-{i:05d}" for i in range(n)]

    in_deg = np.array([g.in_degree(i) for i in range(n)], dtype=float)
    n_top = max(1, int(round(cfg.top_fraction * n)))
    top = set(np.argsort(-in_deg, kind="stable")[:n_top].tolist())

    sv_types = list(cfg.semver_mix)
    sv_p = np.array([cfg.semver_mix[t] for t in sv_types], dtype=float)
    sv_p /= sv_p.sum()
    hook_names, hook_p = list(_HOOK_WEIGHTS), np.array(list(_HOOK_WEIGHTS.values()))

    # Maintainers: Zipf-like portfolio sizes over ranks, assigned independently of popularity.
    n_maint = max(1, int(round(n / cfg.packages_per_maintainer)))
    m_w = np.arange(1, n_maint + 1, dtype=float) ** -cfg.maintainer_zipf_s
    m_w /= m_w.sum()
    m_ids = rng.permutation(n_maint)

    dev_w = (in_deg + 1.0) / (in_deg + 1.0).sum()

    records = []
    for i in range(n):
        prod_targets = sorted(g.successors(i))
        types = rng.choice(sv_types, size=len(prod_targets), p=sv_p) if prod_targets else []
        deps = []
        for v, t in zip(prod_targets, types):
            spec = _synthetic_spec(str(t), rng)
            deps.append(Dependency(names[v], spec, "prod", classify_semver(spec)))

        k_dev = int(rng.poisson(cfg.mean_dev_deps))
        if k_dev:
            cand = rng.choice(n, size=2 * k_dev, p=dev_w)
            excluded = set(prod_targets) | {i}
            dev_targets = [c for c in dict.fromkeys(cand.tolist()) if c not in excluded][:k_dev]
            for v in dev_targets:
                spec = _synthetic_spec(str(rng.choice(sv_types, p=sv_p)), rng)
                deps.append(Dependency(names[v], spec, "dev", classify_semver(spec)))

        hooks = [str(rng.choice(hook_names, p=hook_p))] if rng.random() < cfg.p_lifecycle_hook else []
        p_prov = cfg.p_provenance_top if i in top else cfg.p_provenance_base
        maint = {int(m_ids[rng.choice(n_maint, p=m_w)])}
        if rng.random() < cfg.p_second_maintainer:
            maint.add(int(m_ids[rng.choice(n_maint, p=m_w)]))

        records.append(PackageRecord(
            name=names[i],
            version="1.0.0",
            deps=deps,
            lifecycle_hooks=hooks,
            has_install_script=bool(hooks),
            has_provenance=bool(rng.random() < p_prov),
            maintainers=sorted(f"maint-{m:05d}" for m in maint),
            dependent_count=int(in_deg[i]),
            depth=None,
            source="synthetic",
        ))
    return records


# =========================================================================== io
def save_records(records: list[PackageRecord], path: str | Path, meta: dict | None = None) -> Path:
    """Write records as JSONL plus a sidecar `<stem>.meta.json` describing the snapshot."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(asdict(r), separators=(",", ":")) + "\n")
    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_records": len(records),
        "n_edges": sum(len(r.deps) for r in records),
        **(meta or {}),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return path


def load_records(path: str | Path) -> list[PackageRecord]:
    with Path(path).open(encoding="utf-8") as fh:
        return [PackageRecord.from_dict(json.loads(line)) for line in fh if line.strip()]


# =========================================================================== cli
def _cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Fetch or generate npm dependency snapshots.")
    sub = p.add_subparsers(dest="mode", required=True)

    s = sub.add_parser("synthetic", help="generate a scale-free benchmark ecosystem")
    s.add_argument("--nodes", type=int, default=SyntheticConfig.n_nodes)
    s.add_argument("--seed", type=int, default=SyntheticConfig.seed)
    s.add_argument("--out", type=Path)

    c = sub.add_parser("crawl", help="crawl the live npm registry")
    c.add_argument("--seeds", type=Path, help=".txt or Libraries.io .csv (default: built-in list)")
    c.add_argument("--top-n", type=int, help="use only the first N seeds")
    c.add_argument("--max-nodes", type=int, default=CrawlConfig.max_nodes)
    c.add_argument("--max-depth", type=int, default=CrawlConfig.max_depth)
    c.add_argument("--workers", type=int, default=CrawlConfig.max_workers)
    c.add_argument("--dependents", action="store_true", help="enrich with deps.dev dependent counts")
    c.add_argument("--out", type=Path)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.mode == "synthetic":
        cfg = SyntheticConfig(n_nodes=args.nodes, seed=args.seed)
        records = generate_synthetic_records(cfg)
        out = args.out or RAW_DIR / f"synthetic_n{cfg.n_nodes}_s{cfg.seed}.jsonl"
        save_records(records, out, {"mode": "synthetic", "config": asdict(cfg)})
    else:
        seeds = load_seeds(args.seeds, args.top_n) if args.seeds else list(DEFAULT_SEEDS)[: args.top_n]
        cfg = CrawlConfig(max_nodes=args.max_nodes, max_depth=args.max_depth, max_workers=args.workers)
        dependents = DepsDevClient(cfg).dependent_count if args.dependents else None
        records = crawl_npm(seeds, cfg, dependents=dependents)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        out = args.out or RAW_DIR / f"npm_{stamp}_n{len(records)}.jsonl"
        save_records(records, out, {"mode": "crawl", "seeds": seeds, "config": asdict(cfg)})
    log.info("Wrote %d records to %s", len(records), out)


if __name__ == "__main__":
    _cli()
