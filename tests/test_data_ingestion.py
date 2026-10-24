"""Milestone 1 tests: SemVer classification, manifest parsing, crawler, synthetic generator."""

import numpy as np
import pytest

from src.config import CrawlConfig, SyntheticConfig
from src.data_ingestion import (
    NpmRegistryClient,
    classify_semver,
    crawl_npm,
    generate_synthetic_records,
    load_records,
    load_seeds,
    record_from_manifest,
    save_records,
)


# --------------------------------------------------------------------------- semver
@pytest.mark.parametrize("spec, expected", [
    ("1.2.3", "exact"), ("=1.2.3", "exact"), ("v1.2.3", "exact"), ("1.2.3-beta.1", "exact"),
    ("~1.2.3", "tilde"), ("~1.2", "tilde"), ("1.2.x", "tilde"), ("1.2", "tilde"),
    ("^1.2.3", "caret"), ("1.x", "caret"), ("1", "caret"), ("~1", "caret"),
    # node-semver caret on 0.x: ^0.2.3 only floats patches, ^0.0.3 is pinned
    ("^0.2.3", "tilde"), ("^0.0.3", "exact"), ("^0.x", "caret"),
    ("*", "wildcard"), ("", "wildcard"), ("x", "wildcard"), ("latest", "wildcard"),
    ("next", "wildcard"), (">=1.0.0", "wildcard"),
    (">=1.2.0 <2.0.0", "caret"), (">=1.2.0 <1.3.0", "tilde"), ("1.2.3 - 2.0.0", "caret"),
    ("1.2.3 || ^2.0.0", "caret"), ("1.2.3 || *", "wildcard"), ("1.2.3 || 1.2.4", "exact"),
    ("npm:strip-ansi@^6.0.1", "caret"), ("npm:@scope/pkg@1.0.0", "exact"),
    ("github:user/repo", "non_registry"), ("user/repo#v1", "non_registry"),
    ("git+https://github.com/a/b.git", "non_registry"), ("file:../local", "non_registry"),
    ("https://example.com/x.tgz", "non_registry"), ("workspace:*", "non_registry"),
])
def test_classify_semver(spec, expected):
    assert classify_semver(spec) == expected


# --------------------------------------------------------------------------- manifest
MANIFEST = {
    "name": "@acme/widget",
    "version": "2.1.0",
    "dependencies": {"chalk": "^5.0.0", "fsevents": "~2.3.2", "lodash-alias": "npm:lodash@4.17.21"},
    "optionalDependencies": {"fsevents": "~2.3.2"},
    "peerDependencies": {"react": ">=17"},
    "devDependencies": {"jest": "^29.0.0", "local-tool": "file:../tool"},
    "scripts": {"postinstall": "node install.js", "test": "jest"},
    "maintainers": [{"name": "alice", "email": "a@x"}, "bob <b@x>"],
    "dist": {"attestations": {"url": "https://registry.npmjs.org/-/npm/v1/attestations/x"}},
}


def test_record_from_manifest():
    rec = record_from_manifest(MANIFEST, depth=1)
    by_target = {(d.target, d.dep_type): d for d in rec.deps}

    assert rec.name == "@acme/widget" and rec.version == "2.1.0" and rec.depth == 1
    assert rec.lifecycle_hooks == ["postinstall"] and rec.has_install_script
    assert rec.has_provenance
    assert rec.maintainers == ["alice", "bob"]
    # optional dep mirrored in `dependencies` is recorded once, as optional
    assert ("fsevents", "optional") in by_target and ("fsevents", "prod") not in by_target
    # npm: alias resolves to the real package
    assert by_target[("lodash", "prod")].semver_type == "exact"
    assert by_target[("react", "peer")].semver_type == "wildcard"
    assert by_target[("local-tool", "dev")].semver_type == "non_registry"
    assert len(rec.deps) == 6


def test_manifest_without_optional_fields():
    rec = record_from_manifest({"name": "bare", "version": "1.0.0", "hasInstallScript": True})
    assert rec.deps == [] and rec.has_install_script and not rec.has_provenance
    assert rec.lifecycle_hooks == [] and rec.maintainers == []


# --------------------------------------------------------------------------- crawler
FAKE_REGISTRY = {
    "a": {"name": "a", "version": "1.0.0", "dependencies": {"b": "^1.0.0", "c": "1.0.0"},
          "devDependencies": {"devonly": "^1.0.0"}},
    "b": {"name": "b", "version": "1.0.0", "dependencies": {"d": "~1.0.0", "gitdep": "github:x/y"}},
    "c": {"name": "c", "version": "1.0.0", "dependencies": {"d": "^1.0.0", "missing": "^1.0.0"}},
    "d": {"name": "d", "version": "1.0.0", "dependencies": {"a": "^1.0.0"}},  # cycle back to a
    "devonly": {"name": "devonly", "version": "1.0.0"},
}


def fake_fetch(name):
    return FAKE_REGISTRY.get(name)


def test_crawl_follows_installed_deps_only():
    recs = crawl_npm(["a"], CrawlConfig(max_workers=2), fetch=fake_fetch)
    names = {r.name for r in recs}
    # devDependencies are recorded but not followed; git deps and 404s are skipped
    assert names == {"a", "b", "c", "d"}
    depth = {r.name: r.depth for r in recs}
    assert depth == {"a": 0, "b": 1, "c": 1, "d": 2}
    a = next(r for r in recs if r.name == "a")
    assert any(d.target == "devonly" and d.dep_type == "dev" for d in a.deps)


def test_crawl_respects_limits():
    assert len(crawl_npm(["a"], CrawlConfig(max_nodes=2, max_workers=1), fetch=fake_fetch)) == 2
    shallow = crawl_npm(["a"], CrawlConfig(max_depth=1, max_workers=1), fetch=fake_fetch)
    assert {r.name for r in shallow} == {"a", "b", "c"}


def test_crawl_survives_fetch_errors_and_enriches():
    def flaky(name):
        if name == "c":
            raise ConnectionError("boom")
        return fake_fetch(name)

    recs = crawl_npm(["a"], CrawlConfig(max_workers=2), fetch=flaky,
                     dependents=lambda n, v: len(n) * 10)
    assert {r.name for r in recs} == {"a", "b", "d"}
    assert all(r.dependent_count == len(r.name) * 10 for r in recs)


def test_registry_client_caches(tmp_path, monkeypatch):
    client = NpmRegistryClient(CrawlConfig(cache_dir=tmp_path))
    calls = []

    class Resp:
        def __init__(self, code, body=None):
            self.status_code, self._body = code, body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    class Session:
        def get(self, url, timeout):
            calls.append(url)
            return Resp(404) if "nope" in url else Resp(200, {"name": "@s/p", "version": "1.0.0"})

    monkeypatch.setattr(client, "_session", lambda: Session())
    for _ in range(2):
        assert client.fetch_manifest("@s/p")["version"] == "1.0.0"
        assert client.fetch_manifest("nope") is None
    assert calls == ["https://registry.npmjs.org/@s%2Fp/latest", "https://registry.npmjs.org/nope/latest"]


def test_load_seeds(tmp_path):
    txt = tmp_path / "seeds.txt"
    txt.write_text("express\n# comment\n\nlodash  # inline\n", encoding="utf-8")
    assert load_seeds(txt) == ["express", "lodash"]

    csv_path = tmp_path / "libs.csv"
    csv_path.write_text(
        "Platform,Name,Dependents Count\nNPM,small,5\nPypi,requests,999\nNPM,big,100\n",
        encoding="utf-8",
    )
    assert load_seeds(csv_path) == ["big", "small"]
    assert load_seeds(csv_path, top_n=1) == ["big"]


# --------------------------------------------------------------------------- synthetic
@pytest.fixture(scope="module")
def synth():
    return generate_synthetic_records(SyntheticConfig(n_nodes=3000, seed=7))


def test_synthetic_is_deterministic(synth):
    again = generate_synthetic_records(SyntheticConfig(n_nodes=3000, seed=7))
    assert synth == again
    assert generate_synthetic_records(SyntheticConfig(n_nodes=3000, seed=8)) != synth


def test_synthetic_structure(synth):
    names = {r.name for r in synth}
    assert len(synth) == 3000
    for r in synth:
        targets = [(d.target, d.dep_type) for d in r.deps]
        assert r.name not in {t for t, _ in targets}, "self-dependency"
        assert len(targets) == len(set(targets)), "duplicate edge"
        assert all(t in names for t, _ in targets)

    prod = [d for r in synth for d in r.deps if d.dep_type == "prod"]
    in_deg = np.zeros(3000)
    for d in prod:
        in_deg[int(d.target.split("-")[1])] += 1
    out_deg = np.array([sum(d.dep_type == "prod" for d in r.deps) for r in synth])
    # heavy-tailed in-degree (popular hubs) vs narrow out-degree, as in npm
    assert in_deg.max() > 5 * out_deg.max()
    assert in_deg.max() > 20 * in_deg.mean()


def test_synthetic_acyclic_by_default(synth):
    import networkx as nx
    g = nx.DiGraph((r.name, d.target) for r in synth for d in r.deps if d.dep_type == "prod")
    assert nx.is_directed_acyclic_graph(g)
    cyclic = generate_synthetic_records(SyntheticConfig(n_nodes=3000, seed=7, acyclic=False))
    g2 = nx.DiGraph((r.name, d.target) for r in cyclic for d in r.deps if d.dep_type == "prod")
    assert not nx.is_directed_acyclic_graph(g2)


def test_synthetic_attribute_proportions(synth):
    prod = [d for r in synth for d in r.deps if d.dep_type == "prod"]
    share = {t: np.mean([d.semver_type == t for d in prod]) for t in ("caret", "tilde", "exact", "wildcard")}
    assert share["caret"] == pytest.approx(0.70, abs=0.03)
    assert share["exact"] == pytest.approx(0.17, abs=0.03)
    assert share["caret"] + share["tilde"] == pytest.approx(0.80, abs=0.03)

    hooks = np.mean([r.has_install_script for r in synth])
    assert hooks == pytest.approx(0.025, abs=0.012)
    assert all(r.maintainers for r in synth)
    # provenance is concentrated among the top-5% most-depended-upon packages
    ranked = sorted(synth, key=lambda r: -r.dependent_count)
    top, rest = ranked[:150], ranked[150:]
    assert np.mean([r.has_provenance for r in top]) > 3 * np.mean([r.has_provenance for r in rest])


def test_records_roundtrip(tmp_path, synth):
    path = save_records(synth[:50], tmp_path / "snap.jsonl", {"mode": "test"})
    assert load_records(path) == synth[:50]
    assert (tmp_path / "snap.meta.json").exists()


# --------------------------------------------------------------------------- live (opt-in)
@pytest.mark.network
def test_live_registry_smoke(tmp_path):
    cfg = CrawlConfig(cache_dir=tmp_path, max_nodes=5, max_depth=1, max_workers=2)
    recs = crawl_npm(["express"], cfg)
    assert recs and recs[0].name == "express" and recs[0].maintainers
