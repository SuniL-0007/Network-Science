"""Central configuration: paths, seeds, SemVer weights, and data-generation constants.

All settings are frozen dataclasses so an experiment can log the exact config it ran with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = RAW_DIR / "cache"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = PROJECT_ROOT / "results"
METRICS_DIR = RESULTS_DIR / "metrics"
FIGURES_DIR = RESULTS_DIR / "figures"

GLOBAL_SEED = 42

# --------------------------------------------------------------------------- semver
# Ordered from least to most permissive; used to pick the loosest branch of `a || b`.
SEMVER_TYPES = ("non_registry", "exact", "tilde", "caret", "wildcard")

# How easily an automatic malicious patch-bump crosses an edge (spec §3.2).
SEMVER_BETA_MODIFIER = {
    "non_registry": 0.0,  # git/file/url deps never receive registry publishes
    "exact": 0.05,
    "tilde": 0.85,
    "caret": 1.0,
    "wildcard": 1.0,
}

# Dependency types npm installs for a consumer of the package.
INSTALLED_DEP_TYPES = ("prod", "optional", "peer")
ALL_DEP_TYPES = ("prod", "optional", "peer", "dev")

LIFECYCLE_HOOKS = ("preinstall", "install", "postinstall")


# --------------------------------------------------------------------------- synthetic
@dataclass(frozen=True)
class SyntheticConfig:
    """Parameters for the scale-free benchmark generator."""

    n_nodes: int = 2000
    seed: int = GLOBAL_SEED
    # nx.scale_free_graph params. A large delta_out flattens out-degree preference, giving
    # npm's narrow out-degree / heavy-tailed in-degree shape.
    alpha: float = 0.41
    beta: float = 0.54
    gamma: float = 0.05
    delta_in: float = 0.2
    delta_out: float = 10.0
    # Orient every edge newer -> older (packages depend on already-published ones). The raw
    # generator creates a large dependency cycle among hubs that real npm does not have.
    acyclic: bool = True
    # "Status quo npm" SemVer mix (spec RQ2 regime 1: ~80% caret/tilde, ~20% exact).
    semver_mix: dict[str, float] = field(
        default_factory=lambda: {"caret": 0.70, "tilde": 0.10, "exact": 0.17, "wildcard": 0.03}
    )
    # Roughly 2-3% of npm packages declare install-time scripts.
    p_lifecycle_hook: float = 0.025
    # Provenance adoption is low overall and concentrated among popular packages.
    p_provenance_base: float = 0.03
    p_provenance_top: float = 0.30
    top_fraction: float = 0.05
    # devDependencies per package ~ Poisson(mean), targets chosen preferentially.
    mean_dev_deps: float = 2.0
    # Maintainers: about one per this many packages, ownership is Zipf-like.
    packages_per_maintainer: float = 3.0
    maintainer_zipf_s: float = 0.8  # rank exponent; top maintainer owns ~7% at n=2000
    p_second_maintainer: float = 0.25


# --------------------------------------------------------------------------- topology
HOOK_BETA_MULTIPLIER = 1.25  # w_hook(v) for packages with install-time lifecycle scripts


@dataclass(frozen=True)
class TopologyConfig:
    """Centrality approximation thresholds and node-classification rules (spec §4)."""

    seed: int = GLOBAL_SEED
    # Above this many nodes, betweenness / harmonic use `sample_k` sampled sources.
    exact_max_nodes: int = 3000
    sample_k: int = 500
    pagerank_alpha: float = 0.85
    hub_fraction: float = 0.01  # super-spreaders: top 1% by contagion out-degree
    firebreak_fraction: float = 0.01  # firebreak candidates: top 1% betweenness ...
    firebreak_core_quantile: float = 0.75  # ... fed by a dependency in the upper k-core ...
    firebreak_reach_quantile: float = 0.75  # ... and with a large downstream tree
    periphery_fraction: float = 0.20  # bottom 20% of nodes with non-zero out-degree
    n_per_group: int = 10  # origins per group in RQ1
    powerlaw_min_tail: int = 50  # skip fitting when fewer non-zero degrees than this


# --------------------------------------------------------------------------- sir
@dataclass(frozen=True)
class SIRParams:
    """Parameters of one SIR configuration (spec §5).

    beta_vu = min(1, beta * w_semver(v,u) * w_hook(v) * w_prov(u)). The defaults reproduce
    the spec formula exactly: provenance has no effect and the maintainer channel is off.
    """

    beta: float = 0.15
    gamma: float = 0.05
    t_max: int = 300
    hook_multiplier: float = HOOK_BETA_MULTIPLIER  # w_hook(v) for packages with install scripts
    # w_prov(u): susceptibility of provenance/trusted-publishing packages. Values < 1 model
    # stolen tokens failing to publish (RQ2 "hardened" regime).
    provenance_factor: float = 1.0
    # Credential channel: each tick, an infected package leaks each maintainer's token with
    # this probability; the worm then republishes every package of that maintainer.
    beta_maintainer: float = 0.0


# --------------------------------------------------------------------------- crawler
DEFAULT_SEEDS = (
    "express", "react", "lodash", "chalk", "commander", "debug", "axios", "webpack",
    "typescript", "eslint", "jest", "vue", "next", "moment", "yargs", "uuid", "semver",
    "glob", "minimist", "body-parser", "request", "async", "fs-extra", "rxjs", "tslib",
    "@babel/core", "@types/node", "prettier", "dotenv", "ws", "mkdirp", "rimraf",
    "inquirer", "cross-spawn", "postcss", "esbuild", "vite", "mocha", "core-js", "bluebird",
)


@dataclass(frozen=True)
class CrawlConfig:
    """Limits and politeness settings for the npm registry crawler."""

    max_nodes: int = 10_000
    max_depth: int = 6
    # Which dependency types to *follow* while crawling. All types are still *recorded*.
    follow_dep_types: tuple[str, ...] = ("prod", "optional", "peer")
    registry_url: str = "https://registry.npmjs.org"
    depsdev_url: str = "https://api.deps.dev"
    max_workers: int = 8
    timeout_s: float = 20.0
    max_retries: int = 4
    backoff_factor: float = 0.5
    cache_dir: Path = CACHE_DIR
    user_agent: str = "npm-sir-contagion research crawler (academic)"
