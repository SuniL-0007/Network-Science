# Spec Improvements (addendum to `ns-project-outline.md`)

Changes to the original spec, roughly in order of impact. Items marked **[M1]** are
already reflected in the Milestone 1 code; the rest are planned for later milestones.

## A. Modelling realism

1. **Add a maintainer / credential-theft contagion channel.** Shai-Hulud-style worms do
   not spread only through dependency edges. They steal npm tokens on developer/CI machines
   and **republish every package that maintainer controls**. Model a second layer: the
   package–maintainer bipartite graph (projected to package–package "co-maintained" edges).
   Infection can then hop between unrelated packages that share a maintainer. The
   crawler records `maintainers` for each package. **[M1]**
2. **Separate dependency types.** `dependencies` are installed by consumers (install-time
   channel). `devDependencies` are *not* installed transitively, but they *do* run on the
   maintainer's machine/CI, which is where tokens get stolen (credential channel).
   `peerDependencies` / `optionalDependencies` sit in between. Every edge carries a
   `dep_type`. **[M1]**
3. **Use npm's real SemVer semantics.** `^0.2.3` only allows patch updates (it behaves like
   tilde) and `^0.0.3` is effectively exact. `1.2.x` behaves like tilde and `1.x` like
   caret. `>=1.0.0` and dist-tags (`latest`, `next`) behave like wildcard. `||` unions take
   the most permissive branch. `npm:` aliases resolve to the real target, and git/file/url
   specs are `non_registry`, meaning no registry-borne contagion. **[M1]**
4. **Use real provenance and install-script data.** `has_provenance` comes from
   `dist.attestations` in the registry manifest instead of random assignment. Install
   hooks come from `scripts.{preinstall,install,postinstall}` plus npm's `hasInstallScript`
   flag (which also covers implicit `node-gyp` builds). **[M1]**
5. **Exposure ≠ infection.** Every transitive dependent that installs during the attack
   window is *exposed*. *Infection* (the package republishing malicious code) needs the
   worm to execute and to hold publish credentials. Report both "exposed reach" (a cheap
   graph computation) and "worm infection" (the SIR process).

## B. Data & sampling

6. **Crawl bias.** A downward BFS from seed packages samples the *dependency core* and
   misses most dependents, so in-degree inside the crawled graph underestimates real
   popularity. Mitigations: seed from a high-impact list (top-N by dependents/downloads),
   and store the true ecosystem-wide `dependent_count` from deps.dev
   (`v3alpha …:dependents`) as a node attribute. Hub selection can then use real
   popularity. **[M1]**
7. **Polite, reproducible crawling.** Use an on-disk response cache, retry with backoff,
   bounded concurrency, and JSONL snapshots with a crawl manifest (seeds, limits, date).
   **[M1]**
8. **One record format for both modes.** Synthetic and empirical loaders both emit
   `PackageRecord`s, so `graph_builder` has a single input path. **[M1]**
9. **`nx.scale_free_graph` caveats.** It returns a `MultiDiGraph` with self-loops and
   parallel edges, and with default parameters its out-degree is *also* heavy-tailed.
   Collapse it to a simple `DiGraph` and raise `delta_out` to get npm's narrow out-degree.
   The raw generator also creates a large dependency cycle among hubs (91 nodes at
   N=2000), which inflates λ_max. Real npm is nearly a DAG, with only a few tiny cycles.
   Orient edges newer → older by default (`acyclic=True`). **[M1, M2]**
10. **Graph serialization.** NetworkX 3 removed `write_gpickle`. Use `pickle` directly
    (fast) plus GraphML (portable).

## C. Experimental design & statistics

11. **Fair budgets in RQ3.** Reactive patching (B nodes/tick) and proactive immunization
    (K nodes at t=0) are only comparable at matched total budget. Compare at equal
    `K = B × expected response ticks`, or plot both against total nodes treated.
12. **Scale budgets with N.** B=50/tick on a 2,000-node graph treats 2.5% of the ecosystem
    every tick. Express B and K as fractions of N.
13. **Theoretical threshold check.** For directed SIR, compare the simulated phase
    transition with the spectral prediction `τ_c ≈ 1/λ_max(W)` of the weighted contagion
    adjacency matrix (SemVer/hook weights included). Showing where they agree or diverge
    is a strong paper result.
14. **Null models.** Re-run RQ1/RQ3 on degree-preserving rewired graphs to show the
    effects come from npm's specific topology, not only from its degree sequence.
15. **Statistics.** Use `numpy.random.SeedSequence` to spawn an independent stream per
    run. Report bootstrap 95% CIs (outbreak sizes are bimodal, so normal CIs are wrong).
    Report the *probability of a major outbreak* separately from the *size given a major
    outbreak*. Use paired comparisons (same seeds) across strategies.
16. **Additional baselines.** Add acquaintance immunization (needs no global knowledge)
    and PageRank-targeted immunization alongside degree and betweenness.
17. **Parallelism.** Monte Carlo runs are embarrassingly parallel (`ProcessPoolExecutor`),
    so M=100 across a full parameter grid stays practical.

17a. **Outbreak size = ever infected, not |R(T)|.** Under interventions, R also contains
    patched/vaccinated and pre-immunized nodes that were never compromised, so the spec's
    `R∞ = |R(T_max)|/N` would overstate damage exactly when defences work. The engine
    records `infection_time` per node, and R∞ uses `ever_infected / N`. **[M3]**
17b. **Calibrate `beta_maintainer` before it drives conclusions.** In a first test at
    0.05/tick, the credential channel saturates the graph from *any* origin. The RQ1
    hub-vs-leaf contrast disappears (leaf origin: mean R∞ 0.001 → 0.56). Sweep it in RQ2,
    and anchor it to observed Shai-Hulud spread (~500 packages in days).

17c. **Sweep the response delay in RQ3.** With a 1-tick detection lag, hub-targeted
    patching removes a hub patient zero at once (96% of the outbreak prevented at B=2/tick),
    which amounts to instant unpublishing. On the synthetic graph at B=5/tick, hub patching
    falls to 65% / 34% / 9% at delays of 5 / 10 / 20 ticks. Proactive immunization at the
    same total budget holds at 77–82%. The strategy ranking depends on the detection lag.
    **[M4]**
17d. **The spectral threshold is set by local cliques in real npm.** The high-impact 10k
    graph has λ_max(W)=4.9 (τ_c≈0.20). It comes from small, tightly connected monorepo
    groups: the largest SCC is 22 packages (@eggjs, linked via peer deps), and λ is unchanged
    without peer edges. Report τ_c theory next to the empirical threshold, but don't read it
    as an ecosystem-wide threshold. **[M4]**

## D. Engineering

18. **NDlib is optional.** It installs on Python 3.14, but it is lightly maintained and
    about 30× slower per run. Keep it as the cross-validation baseline and make the custom
    engine the primary one. **[M3]**
19. **Typed config.** Use frozen dataclasses instead of loose constants, so every
    experiment logs its exact configuration next to its results.
20. **Tests per module**, plus offline crawler tests that use an injected fake fetcher
    (no network in CI).
