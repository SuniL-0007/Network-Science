# Problem Statement and Team Contributions

**Project:** Super-spreaders, firebreaks and stolen tokens: SIR modelling of self-propagating worms in
the npm dependency network

**Team:** Member 1, `[Name, Roll No.]` · Member 2, `[Name, Roll No.]`

---

## 1. Problem statement

npm, the package registry for JavaScript, forms a huge directed network. Each package depends on other
packages, and most dependencies use loose version ranges (`^`, `~`), so a new release, including a
malicious one, is installed automatically.

In 2025, two self-propagating worms hit npm: **Shai-Hulud** (Sept 2025, ~200 packages) and
**Shai-Hulud 2.0** (Nov 2025, ~800 packages). Each worm used the same loop:

1. A developer installs a compromised package, and its install script runs.
2. The script steals the developer's npm publish token.
3. The worm uses the token to republish that maintainer's other packages with the malicious script.
4. Anyone who installs those packages repeats the loop.

The worm therefore spreads over **two coupled networks**: the dependency graph and the maintainer
("who can publish what") graph. This makes it a network-science problem: an epidemic on a real,
heavy-tailed, almost loop-free network.

**Goal.** Model these worms as an **SIR epidemic** on a real npm dependency graph, calibrate the model to
the real outbreaks, and use it to answer three research questions:

| | Research question | Network-science concept |
|---|---|---|
| **RQ1** | Does it matter whether the worm starts at a hub, a bridge, a mid-tier or a leaf package? | Super-spreaders, centrality |
| **RQ2** | Do lockfiles, disabled install scripts or trusted publishing raise the epidemic threshold? | Epidemic threshold, phase transition |
| **RQ3** | With a fixed budget, should we patch infected packages or immunize central ones in advance? | Targeted vs random immunization |

---

## 2. Division of work

We split the project along the pipeline:

- **Member 1** built the **data and network side**: from the npm registry to a clean graph and its
  structural analysis.
- **Member 2** built the **epidemic side**: from that graph to simulations, experiments and results.

Both of us worked on the parts listed under "Joint work".

### Member 1: Data collection and network analysis

| Area | What was implemented | Files |
|---|---|---|
| **npm registry crawler** | Breadth-first crawl of `registry.npmjs.org` from 4,686 high-impact seed packages; follows production, optional and peer dependencies; HTTP caching, retries and parallel fetching; dependent counts from deps.dev | `src/data_ingestion.py` |
| **Package metadata extraction** | Version-range classifier (exact / tilde / caret / wildcard / non-registry), install-script detection, provenance attestations, maintainer lists | `src/data_ingestion.py` |
| **Synthetic benchmark network** | 2,000-node scale-free graph generator, oriented newer → older to remove the artificial hub cycle and make it loop-free like real npm | `src/data_ingestion.py` |
| **Graph construction** | Dependency graph built and reversed into the contagion graph (infection flows from a package to its dependents); 5k / 10k / full-closure graphs | `src/graph_builder.py` |
| **Spam-ring cleaning** | Found a 36-package reward-farming spam ring (a 25-package clique that pushed λmax to 24); wrote an automatic filter for dense mutual-dependency rings that keeps real monorepos | `src/graph_builder.py` |
| **Topology analysis** | Degree, PageRank, betweenness, harmonic centrality, k-core, clustering, blast radius (transitive dependents), DAG/cycle structure, assortativity, power-law vs lognormal fits, spectral radius | `src/topology_analyzer.py` |
| **Origin groups** | Hub / bridge / mid-tier / leaf groups for RQ1; super-spreader and firebreak candidate lists | `src/topology_analyzer.py` |
| **Validation against real victims** | Checked whether real Shai-Hulud victims share maintainers (95–98% vs 49–69% for random package sets), confirming the stolen-token channel | `src/validation.py` |
| **Figures and paper numbers** | Publication figures (degree distribution, epidemic curves, super-spreader violins, phase-transition heatmaps, immunization curves) and automatic generation of every number used in the paper | `src/visualizer.py`, `src/paper_numbers.py` |
| **Literature review** | 63 verified references on network epidemics, immunization and software supply chains | `docs/literature.md`, `docs/references.bib` |
| **Tests** | Crawler, graph builder and topology tests | `tests/test_data_ingestion.py`, `tests/test_graph_builder.py`, `tests/test_topology.py` |

### Member 2: Epidemic modelling and experiments

| Area | What was implemented | Files |
|---|---|---|
| **SIR simulation engine** | Fast vectorised SIR simulator on the contagion graph (100 runs in ~1 s); records each package's infection time, source, channel and generation; cross-checked against NDlib | `src/sir_engine.py` |
| **Two-channel contagion model** | Dependency channel weighted by version range and install scripts; stolen-token channel that republishes up to 20 / 100 of a maintainer's packages; provenance and script-blocking defences | `src/sir_engine.py`, `src/config.py` |
| **Intervention policies** | Reactive patching (hub-first, random) that starts at detection; proactive immunization (degree, betweenness "firebreak", acquaintance) with matched budgets | `src/sir_engine.py` |
| **Incident data and calibration** | Collected the real timelines of both waves; fitted β, β_m and γ so the model reproduces the observed plateaus (41.5 h vs 37 h observed; 14.0 h vs 13.4 h) | `docs/incident-notes.md`, `src/calibration.py` |
| **Experiment runners** | RQ1 (origin groups), RQ2 (β × γ sweeps per defence regime, empirical vs spectral thresholds, critical token-leak rate), RQ3 (strategy × budget × detection delay) | `src/experiments.py` |
| **Metrics and statistics** | Outbreak size R∞, time to 80%, peak, cascade depth, channel shares; bootstrap 95% CIs, paired seeds, probability of a major outbreak | `src/metrics_logger.py` |
| **Robustness suite** | 6 synthetic seeds, 3 sample sizes, 5 degree-preserving rewirings (null models), 9-point β × γ sensitivity sweep | `src/robustness.py`, `src/paper_suite.py` |
| **End-to-end pipeline** | One-command CLI (synthetic / crawl / snapshot modes, figures-only re-render) | `main.py` |
| **Tests** | Simulation, experiment, robustness and pipeline tests | `tests/test_simulation.py`, `tests/test_experiments.py`, `tests/test_robustness.py`, `tests/test_pipeline.py` |

### Joint work

- Reviewing the original spec and writing up 20 improvements (`docs/spec-improvements.md`)
- Interpreting results and drawing defender takeaways
- Project report (`docs/PROJECT_REPORT.md`) and paper draft (`paper/`)
- Presentation and presenter script (`docs/PRESENTER_SCRIPT.md`)

---

## 3. Key results (summary)

- **RQ1.** With dependencies alone, only hubs cause outbreaks, and they stay small (3–5% of the core).
  With stolen tokens, even a leaf package reaches 20–55%.
- **RQ2.** Lockfiles raise the epidemic threshold about 12× and blocking install scripts about 6×, but
  only while tokens can't be stolen.
- **RQ3.** Reactive patching prevents only 13% of the outbreak after a 24-hour detection delay;
  immunizing hubs in advance prevents about 42% at the same cost.
- **Takeaway.** Break the credential channel first (short-lived tokens, trusted publishing), then
  harden dependencies, then protect central packages in advance.
