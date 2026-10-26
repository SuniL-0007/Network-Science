# Literature Review

**Paper (working title):** *Super-spreaders, Firebreaks and Stolen Tokens: SIR Modelling of Self-Propagating Worms in the npm Dependency Network*

**Compiled:** 2026-10-26. BibTeX keys refer to `docs/references.bib`.

**How entries were verified.** Every entry below was checked on 2026-10-26 by doing one of the following:
- resolving its DOI through `doi.org` with Crossref content negotiation, which also produced the BibTeX metadata;
- fetching the publisher, arXiv or USENIX page;
- fetching the vendor or advisory page itself.

Quantitative facts are given with their location in the source. "Abstract" means the fact was read from the abstract, which was retrieved through OpenAlex or Semantic Scholar or from the landing page. Facts for vendor reports come from the fetched page. Read the full text of the academic papers before quoting them in the paper.

**Counts:** 63 verified entries (all in BibTeX) and 1 unverified (not in BibTeX). About a third of the verified entries are incident and vendor sources, because the paper's empirical setting is a run of incidents in 2025-26.

---

## 1. Empirical studies of package dependency networks

**Kikas, R., Gousios, G., Dumas, M., & Pfahl, D. (2017).** Structure and Evolution of Package Dependency Networks. *Proc. 14th IEEE/ACM MSR*, 102-112. `kikas2017structure`
- Verified: https://doi.org/10.1109/MSR.2017.55
- Relevance: an early comparative network study of npm (JavaScript), RubyGems and Cargo. It frames dependency edges as channels of "transitive bug propagation", which is the premise our SIR model builds on (reversed edges). **Supports** our edge orientation and our motivation.
- Facts (abstract): the number of transitive dependencies for JavaScript "has grown 60% over the last year". Vulnerability to the removal of the most popular package is increasing, while most other packages have a decreasing impact.

**Decan, A., Mens, T., & Grosjean, P. (2019).** An Empirical Comparison of Dependency Network Evolution in Seven Software Packaging Ecosystems. *Empirical Software Engineering*, 24(1), 381-416. `decan2019empirical`
- Verified: https://doi.org/10.1007/s10664-017-9589-y (published online 2018)
- Relevance: the reference cross-ecosystem study (Cargo, CPAN, CRAN, npm, NuGet, Packagist, RubyGems). It shows that reverse dependencies are concentrated in a few packages. This is the "super-spreader" structure behind our RQ1 hubs. **Supports** the heterogeneity assumption and gives the context for our degree-tail analysis.
- Facts (abstract): "only a small proportion of packages accounts for most of the reverse dependencies". There is "a high proportion of 'fragile' packages due to a high and increasing number of transitive dependencies".

**Abdalkareem, R., Nourry, O., Wehaibi, S., Mujahid, S., & Shihab, E. (2017).** Why Do Developers Use Trivial Packages? An Empirical Case Study on npm. *Proc. ESEC/FSE 2017*, 385-395. `abdalkareem2017trivial`
- Verified: https://doi.org/10.1145/3106237.3106267
- Relevance: explains why npm has so many tiny, heavily depended-on leaves and micro-hubs. It is motivated by left-pad. It also explains the high fan-in to small packages that our hub and leaf origins exploit. **Context** for RQ1.
- Facts (abstract): it is motivated by "a recent incident where a trivial package led to the breakdown of some of the most popular web applications".

**npm, Inc. (2016, 23 March).** kik, left-pad, and npm. *The npm Blog*. `npm2016leftpad`
- Verified: https://blog.npmjs.org/post/141577284765/kik-left-pad-and-npm
- Relevance: the canonical demonstration that removing one tiny package cascades through the dependency graph. It is a non-malicious "outbreak" from a leaf-like package. **Supports** the cascade framing.
- Facts: the author unpublished `kik` "and 272 others, including left-pad". The disruption lasted about 2.5 hours. npm then made unpublishing harder when it would break dependents.

---

## 2. npm security and supply-chain attacks

### Academic

**Zimmermann, M., Staicu, C.-A., Tenny, C., & Pradel, M. (2019).** Small World with High Risks: A Study of Security Threats in the npm Ecosystem. *Proc. 28th USENIX Security Symposium*, 995-1010. `zimmermann2019smallworld`
- Verified: https://www.usenix.org/conference/usenixsecurity19/presentation/zimmerman (full text also at https://arxiv.org/abs/1902.09217)
- Relevance: **the closest prior work and the main benchmark for our results.** It quantifies static reachability through both packages and *maintainer accounts*, which corresponds to our two contagion channels. It does not model dynamics, detection or recovery. **Supports** the credential-channel premise. It also **challenges** our numbers, because static reach is much larger than our dynamic outbreak sizes (see "Claims to support").
- Facts: installing an average package implicitly trusts "79 third-party packages and 39 maintainers" (Introduction; about 80 and 40 in Sections 4.1.1 and 4.2.2). "20 maintainers can reach more than half of the ecosystem" (Section 4.2.3). "Up to 40% of all packages rely on code known to be vulnerable" (Section 4.3).

**Ohm, M., Plate, H., Sykosch, A., & Meier, M. (2020).** Backstabber's Knife Collection: A Review of Open Source Software Supply Chain Attacks. *DIMVA 2020*, LNCS, Springer, 23-43. `ohm2020backstabber`
- Verified: https://doi.org/10.1007/978-3-030-52683-2_2 (arXiv: https://arxiv.org/abs/2005.09535)
- Relevance: a taxonomy and dataset of real malicious packages, including install-hook triggers and account takeover as injection vectors. **Provides context** for our infection mechanism, in which the payload runs at install time.
- Facts (abstract): a dataset of "174 malicious software packages" from npm, PyPI and RubyGems, November 2015 to November 2019.

**Taylor, M., Vaidya, R., Davidson, D., De Carli, L., & Rastogi, V. (2020).** Defending Against Package Typosquatting. *NSS 2020*, LNCS, Springer, 112-131. `taylor2020typosquatting`
- Verified: https://doi.org/10.1007/978-3-030-65745-1_7
- Relevance: covers typosquatting, an initial-access vector that is distinct from the worm's propagation. Useful for scoping: our model starts at a patient zero and does not model how the first package is compromised.

**Ladisa, P., Plate, H., Martinez, M., & Barais, O. (2023).** SoK: Taxonomy of Attacks on Open-Source Software Supply Chains. *IEEE S&P 2023*, 1509-1526. `ladisa2023sok`
- Verified: https://doi.org/10.1109/SP46215.2023.10179304
- Relevance: the standard taxonomy for placing our threat model: maintainer-account compromise plus malicious install scripts. It maps vectors to safeguards, which matches our RQ2 regimes.
- Facts (abstract): "107 unique vectors, linked to 94 real-world incidents, and mapped to 33 mitigating safeguards".

**Zahan, N., Zimmermann, T., Godefroid, P., Murphy, B., Maddila, C., & Williams, L. (2022).** What Are Weak Links in the npm Supply Chain? *Proc. ICSE-SEIP 2022*, 331-340. `zahan2022weaklinks`
- Verified: https://doi.org/10.1145/3510457.3513044 (arXiv: https://arxiv.org/abs/2112.10165)
- Relevance: shows that maintainer accounts are a takeover surface independent of code. **Supports** treating maintainer identity as a contagion channel, and install scripts as a risk signal.
- Facts (abstract): 1.63 million packages analysed. 2,818 maintainer emails on expired domains could let attackers "hijack 8,494 packages".

**Wyss, E., Wittman, A., Davidson, D., & De Carli, L. (2022).** Wolf at the Door: Preventing Install-Time Attacks in npm with Latch. *Proc. ASIA CCS 2022*, 1139-1153. `wyss2022latch`
- Verified: https://doi.org/10.1145/3488932.3523262
- Relevance: academic grounding for the "scripts disabled" regime in RQ2. Install scripts are the execution vector that turns dependency exposure into infection.
- Facts (abstract): "A particularly dangerous form of attack comes from malicious code embedded into package install scripts."

### Incidents before 2025

**npm, Inc. (2018, 27 November).** Details about the event-stream incident. *The npm Blog*. `npm2018eventstream`
- Verified: https://blog.npmjs.org/post/180565383195/details-about-the-event-stream-incident
- Relevance: the archetypal *dependency-channel* attack. A malicious transitive dependency (`flatmap-stream`) was added after a social-engineered maintainer handover. It is not self-propagating, which makes it a useful contrast with worms.
- Facts: malicious `flatmap-stream@0.1.1` was added to `event-stream@3.3.6` on 9 September 2018. npm was notified on 26 November 2018. The payload targeted the Copay Bitcoin wallet.

**GitHub Advisory Database (2021, 22 October).** Embedded malware in ua-parser-js (GHSA-pjwm-rvh2-c87w, CVE-2021-4229). `github2021uaparser`
- Verified: https://github.com/advisories/GHSA-pjwm-rvh2-c87w (CISA also issued an alert on 22 October 2021: https://www.cisa.gov/news-events/alerts/2021/10/22/malware-discovered-popular-npm-package-ua-parser-js)
- Relevance: a popular hub package published with malware. This is a hub patient zero (RQ1) without self-propagation.
- Facts: versions 0.7.29, 0.8.0 and 1.0.0 were malicious. Hosts with them installed should be treated as "fully compromised". Neither the advisory nor the CISA page states the account-hijack mechanism, so do not cite them for it.

### Incidents in 2025-2026 (primary or vendor sources)

**Eriksen, C. / Aikido Security (2025, 8 September).** npm debug and chalk packages compromised. `aikido2025chalkdebug`
- Verified: https://www.aikido.dev/blog/npm-debug-and-chalk-packages-compromised
- Relevance: a maintainer-account takeover hitting top hubs, a week before Shai-Hulud. It shows that one stolen credential reaches many hubs at once, which is the credential channel without the worm. The payload ran at runtime in browsers, not at install time.
- Facts: "18 popular npm packages" including debug and chalk, with "more than 2 billion downloads per week". Access came from phishing via the domain `npmjs.help`, registered three days before the attack. The payload was a crypto-wallet interceptor.

**Bar, M., & McCarthy, R. / Wiz (2025, 27 August; updated 29 August).** s1ngularity: supply chain attack leaks secrets on GitHub. `wiz2025singularity`
- Verified: https://www.wiz.io/blog/s1ngularity-supply-chain-attack
- Relevance: the precursor to Shai-Hulud, with a postinstall credential stealer. Its root cause was a CI workflow injection (`pull_request_target`). **Complicates** the trusted-publishing regime, because compromising the CI pipeline gets around token-based controls.
- Facts: 19 malicious versions of `nx` and `@nx/*` packages were published on 26 August 2025. Over 1,000 valid GitHub tokens leaked. In phase two, more than 400 users and organisations were affected and more than 5,500 private repositories were made public.

**Kurmi, A. / StepSecurity (2025, 15 September).** Shai-Hulud: Self-Replicating Worm Compromises 500+ NPM Packages. `stepsecurity2025shaihulud`
- Verified: https://www.stepsecurity.io/blog/ctrl-tinycolor-and-40-npm-packages-compromised
- Relevance: the primary technical description of the first worm's credential-channel propagation. **Important for model calibration:** propagation was *capped per maintainer*.
- Facts: it reads the npm token from `~/.npmrc` or environment variables and validates it via `/whoami`. It then "force-publishes patches" to "up to 20 packages owned by the maintainer". It was likely triggered by a hijacked postinstall script and uses TruffleHog for secret scanning. The headline count is 500+, while the body says "@ctrl/tinycolor and more than 40 other packages" (an early snapshot).

**Pandya, K., van der Zee, P., Brown, O., & Socket Research Team (2025, 16 September).** Updated and Ongoing Supply Chain Attack Targets CrowdStrike npm Packages. `socket2025shaihulud`
- Verified: https://socket.dev/blog/ongoing-supply-chain-attack-targets-crowdstrike-npm-packages
- Relevance: gives counts and a key qualitative point for our model: the worm "cannot self-propagate without those credentials". **Supports** making the credential channel conditional on a stolen token, not automatic.
- Facts: IoC list of "Total packages: 526". The largest burst (16 September, 01:14 UTC) hit nearly 100 packages. About 700 "Shai-Hulud Migration" repositories appeared.

**CISA (2025, 23 September).** Widespread Supply Chain Compromise Impacting npm Ecosystem. `cisa2025npm`
- Verified: https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem
- Relevance: the authoritative government advisory on Shai-Hulud. Its recommendation to pin dependencies maps directly to our "strict lockfile" regime.
- Facts: "over 500 packages". The worm authenticated to npm as the compromised developer, injected code into other packages and published them. It recommends pinning to "known safe releases produced prior to Sept. 16, 2025", rotating credentials and phishing-resistant MFA.

**Unit 42, Palo Alto Networks (2025; updated 25-26 November and 3 December 2025).** "Shai-Hulud" Worm Compromises npm Ecosystem in Supply Chain Attack. `unit42025shaihulud`
- Verified: https://unit42.paloaltonetworks.com/npm-supply-chain-attack/
- Relevance: covers both waves. It contrasts postinstall (wave 1) with preinstall (wave 2), which matters for our "scripts disabled" regime because both are lifecycle scripts.
- Facts: wave 1 used the stolen npm token to "find other packages the developer maintains" and republish them. Initial access was possibly a phishing campaign impersonating npm. Wave 2 produced "over 25,000 malicious repositories across about 350 unique users", ran in preinstall, and had a destructive home-directory wipe fallback.

**Ramati, H., Bar, M., Benmocha, G., & Tikochinski, G. / Wiz (2025, 24 November).** Shai-Hulud 2.0 Supply Chain Attack: 25K+ Repos Exposing Secrets. `wiz2025shaihulud2`
- Verified: https://www.wiz.io/blog/shai-hulud-2-0-ongoing-supply-chain-attack
- Relevance: gives the timeline needed to set realistic detection delays in RQ3. Uploads ran from 21 to 23 November, public disclosure was on 24 November, and GitHub cleanup began around 26 November.
- Facts: about 700 compromised npm packages in the key takeaways, "nearly 800" in the body. 25,000+ repositories, growing by about 1,000 every 30 minutes. "This variant executes only during the preinstall phase." About 15 malicious versions remained on 27 November.

**Tafani-Dereeper, C., & Obregoso, S. / Datadog Security Labs (2025, 25 November; updated 4 December).** The Shai-Hulud 2.0 npm worm: analysis, and what you need to know. `datadog2025shaihulud2`
- Verified: https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/
- Relevance: the most precise count for wave 2. It also confirms the per-token cap, which is **important for calibrating our credential channel**.
- Facts: "796 unique npm packages" and 1,092 versions, with over 20 million weekly downloads. The worm backdoors "up to 100" of a victim's packages, bumping the patch version each time. If it finds no token it "attempts to delete the user's home directory".

**Unit 42, Palo Alto Networks (2026, updated 15 July).** The npm Threat Landscape: Attack Surface and Mitigations. `unit422026npmlandscape`
- Verified: https://unit42.paloaltonetworks.com/monitoring-npm-supply-chain-attacks/
- Relevance: shows that Shai-Hulud-style worms continued into 2026 (the "Mini Shai-Hulud" waves). Several waves started from compromised CI pipelines, which **complicates** the trusted-publishing regime. A single account compromise produced hundreds of packages in an hour, which **supports** the strength of the credential channel.
- Facts: on 11 May 2026, "84 malicious package artifacts" were published across 42 `@tanstack` packages in 6 minutes, reaching 373 versions across 169 packages by end of day, starting from TanStack's GitHub Actions pipeline. On 19 May 2026, one compromised maintainer account (`@antv`) produced about 639 malicious versions across 323 packages in about an hour. The worm source was leaked on 12 May 2026. This is a single vendor source; corroborate it before relying on the 2026 figures.

---

## 3. Defences

**Preston-Werner, T. (2013).** Semantic Versioning 2.0.0. `prestonwerner2013semver`
- Verified: https://semver.org/spec/v2.0.0.html
- Relevance: the normative basis for our SemVer-permissiveness edge weights (exact < tilde < caret < wildcard).

**Decan, A., & Mens, T. (2021).** What Do Package Dependencies Tell Us About Semantic Versioning? *IEEE TSE*, 47(6), 1226-1240. `decan2021semver`
- Verified: https://doi.org/10.1109/TSE.2019.2918315
- Relevance: empirical constraint-type usage and semver compliance across Cargo, npm, Packagist and RubyGems. It provides the **empirical justification** for weighting edges by constraint permissiveness, describing constraints that "range from very permissive to very restrictive" (abstract).

**Pinckney, D., Cassano, F., Guha, A., & Bell, J. (2023).** A Large Scale Analysis of Semantic Versioning in NPM. *Proc. MSR 2023*, 485-497. `pinckney2023semver`
- Verified: https://doi.org/10.1109/MSR59073.2023.00073 (arXiv: https://arxiv.org/abs/2304.00394)
- Relevance: **complicates our lockfile result.** Permissive ranges are also how *security fixes* reach dependents quickly, so strict pinning raises the worm threshold but slows remediation. Mention this trade-off when presenting RQ2.
- Facts (abstract): built from "every version of every package on NPM" with a time-travelling resolver. When semver is used correctly, security patches flow downstream rapidly "in the majority of cases (90.09%)".

**DeHamer, B., & Harrison, P. / GitHub (2023, 19 April).** Introducing npm package provenance. `github2023provenance`
- Verified: https://github.blog/security/supply-chain-security/introducing-npm-package-provenance/
- Relevance: the mechanism behind our "provenance" regime. It links a package to its source repository and build, follows SLSA provenance and is signed via Sigstore.
- Facts: it requires `--provenance` from GitHub Actions, uses Fulcio short-lived certificates and Rekor transparency logging, and can be checked with `npm audit signatures` (npm 9.5.0 or later).

**Newman, Z., Meyers, J. S., & Torres-Arias, S. (2022).** Sigstore: Software Signing for Everybody. *Proc. ACM CCS 2022*, 2353-2367. `newman2022sigstore`
- Verified: https://doi.org/10.1145/3548606.3560596
- Relevance: the peer-reviewed reference for the signing infrastructure behind npm provenance and trusted publishing.

**GitHub (2025, 31 July).** npm trusted publishing with OIDC is generally available. *GitHub Changelog*. `github2025trustedpublishing`
- Verified: https://github.blog/changelog/2025-07-31-npm-trusted-publishing-with-oidc-is-generally-available/
- Relevance: defines our "trusted publishing" regime. Publishing uses short-lived OIDC credentials instead of stealable long-lived tokens, which cuts the credential channel.
- Facts: "short-lived, workflow-specific credentials" with provenance by default. It requires npm CLI 11.5.1 or later and supports GitHub Actions and GitLab CI/CD at launch.

**SLSA Community (2023).** SLSA Specification v1.0. `slsa2023spec`
- Verified: https://slsa.dev/spec/v1.0/ (the page notes that v1.2 is now current)
- Relevance: the framework that the provenance attestations follow. Cite it when describing the provenance regime.

**npm, Inc.** npm config: `ignore-scripts`. *npm Docs (CLI v11)*. `npmdocs2026ignorescripts`
- Verified: https://docs.npmjs.com/cli/v11/using-npm/config#ignore-scripts
- Relevance: the opt-in switch behind the "scripts disabled" regime. Its default being `false` is why the baseline regime allows install-time execution.
- Facts: "If true, npm does not run scripts specified in package.json files." Default: `false`.

**pnpm contributors (2025, 7 January).** pnpm v10.0.0 release notes. `pnpm2025v10`
- Verified: https://github.com/pnpm/pnpm/releases/tag/v10.0.0
- Relevance: a real-world move to scripts-off by default, which grounds the "scripts disabled" regime as deployable, not hypothetical.
- Facts: dependency lifecycle scripts are "not executed during installation by default". Packages can be allowlisted via `pnpm.onlyBuiltDependencies`.

**LavaMoat contributors.** `@lavamoat/allow-scripts`. `lavamoat2026allowscripts`
- Verified: https://github.com/LavaMoat/LavaMoat/tree/main/packages/allow-scripts
- Relevance: an allowlist alternative to disabling all scripts. It supports modelling a *partial* scripts-disabled regime (a fraction of nodes immune to install-time execution).
- Facts: "A tool for running only the dependency lifecycle hooks specified in an allowlist."

**René-Corail, X. / GitHub (2025, 22 September).** Our plan for a more secure npm supply chain. `github2025npmplan`
- Verified: https://github.blog/security/supply-chain-security/our-plan-for-a-more-secure-npm-supply-chain/
- Relevance: the registry operator's response to Shai-Hulud, aimed directly at the credential channel. It motivates the policy relevance of our RQ2 credential-channel results.
- Facts: more than 500 compromised packages were removed. Planned changes: local publishing with "required two-factor authentication", granular tokens with "a limited lifetime of seven days", trusted publishing, deprecation of classic tokens and TOTP, and token publishing disallowed by default.

**GitHub (2025, 9 December).** npm classic tokens revoked, session-based auth and CLI token management now available. *GitHub Changelog*. `github2025classictokens`
- Verified: https://github.blog/changelog/2025-12-09-npm-classic-tokens-revoked-session-based-auth-and-cli-token-management-now-available/
- Relevance: evidence that the token policy was actually implemented after Shai-Hulud 2.0. Long-lived tokens, the worm's fuel, were removed.
- Facts: all classic tokens were revoked. `npm login` now issues two-hour sessions with 2FA enforced for publishing, and 2FA is on by default for new packages. A 5 November 2025 changelog (seen in search results, not fetched) set 90-day caps on write-enabled granular tokens.

---

## 4. Network epidemiology

**Kermack, W. O., & McKendrick, A. G. (1927).** A Contribution to the Mathematical Theory of Epidemics. *Proc. R. Soc. Lond. A*, 115(772), 700-721. `kermack1927contribution`
- Verified: https://doi.org/10.1098/rspa.1927.0118
- Relevance: the origin of the SIR compartmental model.

**Pastor-Satorras, R., & Vespignani, A. (2001).** Epidemic Spreading in Scale-Free Networks. *PRL*, 86(14), 3200-3203. `pastorsatorras2001epidemic`
- Verified: https://doi.org/10.1103/PhysRevLett.86.3200
- Relevance: the classic vanishing-threshold result for scale-free networks. **Contrasts** with our finding that npm degree tails are lognormal and that thresholds are finite and measurable.

**Pastor-Satorras, R., Castellano, C., Van Mieghem, P., & Vespignani, A. (2015).** Epidemic Processes in Complex Networks. *Rev. Mod. Phys.*, 87(3), 925-979. `pastorsatorras2015review`
- Verified: https://doi.org/10.1103/RevModPhys.87.925
- Relevance: the standard review. Use it for SIR vs SIS threshold definitions, the quenched mean-field (spectral) threshold and its known limitations.

**Newman, M. E. J. (2002).** Spread of Epidemic Disease on Networks. *PRE*, 66(1), 016128. `newman2002spread`
- Verified: https://doi.org/10.1103/PhysRevE.66.016128
- Relevance: maps SIR onto bond percolation, so final outbreak size equals cluster size at transmissibility T. This is the theoretical lens for interpreting our bimodal outbreak-size distributions and the empirical threshold.

**Wang, Y., Chakrabarti, D., Wang, C., & Faloutsos, C. (2003).** Epidemic Spreading in Real Networks: An Eigenvalue Viewpoint. *Proc. SRDS 2003*, 25-34. `wang2003eigenvalue`
- Verified: https://doi.org/10.1109/RELDIS.2003.1238052
- Relevance: the source of the 1/lambda_max threshold for arbitrary graphs that we compare against in RQ2.
- Facts (abstract): "the epidemic threshold for a network is closely related to the largest eigenvalue of its adjacency matrix".

**Chakrabarti, D., Wang, Y., Wang, C., Leskovec, J., & Faloutsos, C. (2008).** Epidemic Thresholds in Real Networks. *ACM TISSEC*, 10(4), 1-26. `chakrabarti2008thresholds`
- Verified: https://doi.org/10.1145/1284680.1284681
- Relevance: the journal version, proving that the threshold "is exactly the inverse of the largest eigenvalue" (abstract) *for their SIS-type NLDS model*. Note the model mismatch: we use SIR on a directed graph. Present 1/lambda_max as a reference point, not an exact prediction.

**Li, C., Wang, H., & Van Mieghem, P. (2013).** Epidemic Threshold in Directed Networks. *PRE*, 88(6), 062802. `li2013directed`
- Verified: https://doi.org/10.1103/PhysRevE.88.062802
- Relevance: the key directed-network result. For SIS in directed networks, 1/lambda_1 is a *lower bound*, and the spectral radius decreases as directionality increases. **Supports and explains** our finding that lambda_max is set by small cycles (monorepo cliques). A dependency graph that is close to a DAG has a near-nilpotent adjacency matrix, so lambda_max comes only from the few cycles (a mathematical consequence, not stated in the paper).
- Facts (abstract): "the spectral radius lambda_1 decreases with the directionality xi". In directed networks "the epidemic threshold is larger".

**Boguñá, M., & Serrano, M. Á. (2005).** Generalized Percolation in Random Directed Networks. *PRE*, 72(1), 016106. `boguna2005directed`
- Verified: https://doi.org/10.1103/PhysRevE.72.016106
- Relevance: percolation thresholds and giant out-component sizes in directed networks with correlations and bidirectional edges. It is the directed analogue of Newman (2002), and the theory behind "how far can a worm reach downstream".

**Kephart, J. O., & White, S. R. (1991).** Directed-Graph Epidemiological Models of Computer Viruses. *Proc. IEEE Symp. Security and Privacy*, 343-359. `kephart1991directed`
- Verified: https://doi.org/10.1109/RISP.1991.130801
- Relevance: **an important precedent for novelty.** Epidemic models of software spreading along *directed program-sharing graphs* date back to 1991. Our contribution is the instantiation on a real package-dependency graph with a second credential channel and modern defences.
- Facts (abstract): "an imperfect defense against computer viruses can still be highly effective ... provided that the infection rate does not exceed a well-defined critical epidemic threshold".

**Zou, C. C., Gong, W., & Towsley, D. (2002).** Code Red Worm Propagation Modeling and Analysis. *Proc. ACM CCS 2002*, 138-147. `zou2002codered`
- Verified: https://doi.org/10.1145/586110.586130
- Relevance: the canonical compartmental model of an Internet worm fitted to a real outbreak, including human countermeasures (patching/removal), which is our reactive-patching analogue. It contrasts with ours in having random scanning rather than graph-constrained spread.

---

## 5. Immunization

**Pastor-Satorras, R., & Vespignani, A. (2002).** Immunization of Complex Networks. *PRE*, 65(3), 036104. `pastorsatorras2002immunization`
- Verified: https://doi.org/10.1103/PhysRevE.65.036104
- Relevance: random immunization fails on scale-free networks, while targeted (hub) immunization works. This is the baseline expectation for RQ3's hub vs random comparison.
- Facts (abstract): scale-free networks "do not acquire global immunity ... even in the presence of unrealistically high densities of randomly immunized individuals".

**Cohen, R., Havlin, S., & ben-Avraham, D. (2003).** Efficient Immunization Strategies for Computer Networks and Populations. *PRL*, 91(24), 247901. `cohen2003acquaintance`
- Verified: https://doi.org/10.1103/PhysRevLett.91.247901
- Relevance: acquaintance immunization, the local-knowledge strategy used in RQ3 at matched budget. It is relevant because ecosystem defenders often lack a global graph view.

**Holme, P., Kim, B. J., Yoon, C. N., & Han, S. K. (2002).** Attack Vulnerability of Complex Networks. *PRE*, 65(5), 056109. `holme2002attack`
- Verified: https://doi.org/10.1103/PhysRevE.65.056109
- Relevance: compares degree and betweenness removal, both static and recalculated. It is methodological support for the betweenness firebreak and a prompt to report *recalculated* betweenness.
- Facts (abstract): "removals by the recalculated degrees and betweenness centralities are often more harmful than the attack strategies based on the initial network".

**Schneider, C. M., Mihaljev, T., Havlin, S., & Herrmann, H. J. (2011).** Suppressing Epidemics with a Limited Amount of Immunization Units. *PRE*, 84(6), 061911. `schneider2011limited`
- Verified: https://doi.org/10.1103/PhysRevE.84.061911
- Relevance: limited-budget immunization. It treats highest-betweenness immunization as "the best known strategy" and then **beats it**. This is support for betweenness as a strong baseline, and a caution that it is not optimal.
- Facts (abstract): infection probability is reduced "by up to 55%" for small budgets.

**Chen, Y., Paul, G., Havlin, S., Liljeros, F., & Stanley, H. E. (2008).** Finding a Better Immunization Strategy. *PRL*, 101(5), 058701. `chen2008immunization`
- Verified: https://doi.org/10.1103/PhysRevLett.101.058701
- Relevance: a graph-partitioning (firebreak-like) strategy that cuts the network into small components. It is conceptually the closest physics precedent to our "firebreak" framing.
- Facts (abstract): it requires "5% to 50% fewer immunization doses compared to the targeted strategy".

**Freeman, L. C. (1977).** A Set of Measures of Centrality Based on Betweenness. *Sociometry*, 40(1), 35-41. `freeman1977betweenness`
- Verified: https://doi.org/10.2307/3033543
- Relevance: the definition of betweenness centrality used to choose firebreak nodes.

---

## 6. Methods

**Clauset, A., Shalizi, C. R., & Newman, M. E. J. (2009).** Power-Law Distributions in Empirical Data. *SIAM Review*, 51(4), 661-703. `clauset2009powerlaw`
- Verified: https://doi.org/10.1137/070710111
- Relevance: the maximum-likelihood fitting, KS-based x_min selection and likelihood-ratio comparison behind our power-law vs lognormal result.

**Alstott, J., Bullmore, E., & Plenz, D. (2014).** powerlaw: A Python Package for Analysis of Heavy-Tailed Distributions. *PLoS ONE*, 9(1), e85777. `alstott2014powerlaw`
- Verified: https://doi.org/10.1371/journal.pone.0085777
- Relevance: the implementation we use (`powerlaw.Fit` in `src/topology_analyzer.py`).

**Broido, A. D., & Clauset, A. (2019).** Scale-Free Networks Are Rare. *Nature Communications*, 10, 1017. `broido2019rare`
- Verified: https://doi.org/10.1038/s41467-019-08746-5
- Relevance: **supports** our lognormal-over-power-law finding as the typical empirical outcome. It tempers any "scale-free npm" claim.
- Facts (abstract): across nearly 1,000 networks, "for most networks, log-normal distributions fit the data as well or better than power laws".

**Rossetti, G., Milli, L., Rinzivillo, S., Sîrbu, A., Pedreschi, D., & Giannotti, F. (2018).** NDlib: A Python Library to Model and Analyze Diffusion Processes over Complex Networks. *Int. J. Data Sci. Anal.*, 5(1), 61-79. `rossetti2018ndlib`
- Verified: https://doi.org/10.1007/s41060-017-0086-6
- Relevance: the homogeneous SIR baseline (`run_ndlib_sir` in `src/sir_engine.py`).

**Maslov, S., & Sneppen, K. (2002).** Specificity and Stability in Topology of Protein Networks. *Science*, 296(5569), 910-913. `maslov2002specificity`
- Verified: https://doi.org/10.1126/science.1065103
- Relevance: the degree-preserving rewiring null model, used to test whether outbreak sizes and thresholds depend on structure beyond the degree sequence (for example monorepo cliques).

**Foster, J. G., Foster, D. V., Grassberger, P., & Paczuski, M. (2010).** Edge Direction and the Structure of Networks. *PNAS*, 107(24), 10815-10820. `foster2010direction`
- Verified: https://doi.org/10.1073/pnas.0912671107
- Relevance: the four directed assortativity coefficients (out-in, in-out, and so on) for characterising the dependency graph.

**Efron, B. (1979).** Bootstrap Methods: Another Look at the Jackknife. *Annals of Statistics*, 7(1), 1-26. `efron1979bootstrap`
- Verified: https://doi.org/10.1214/aos/1176344552
- Relevance: the percentile bootstrap CIs used in `src/metrics_logger.py`. These are needed because outbreak sizes are bimodal.

**Barabási, A.-L., & Albert, R. (1999).** Emergence of Scaling in Random Networks. *Science*, 286(5439), 509-512. `barabasi1999scaling`
- Verified: https://doi.org/10.1126/science.286.5439.509
- Relevance: the preferential-attachment origin of the synthetic benchmark family. The directed generator itself is Bollobás et al. (2003); see Unverified.

---

## 7. Propagation models applied to software ecosystems

**Decan, A., Mens, T., & Constantinou, E. (2018).** On the Impact of Security Vulnerabilities in the npm Package Dependency Network. *Proc. MSR 2018*, 181-191. `decan2018vulnerabilities`
- Verified: https://doi.org/10.1145/3196398.3196401
- Relevance: vulnerability propagation to dependents "in presence of dependency constraints". It is a direct precedent for constraint-aware exposure, as in our SemVer-weighted edges. The analysis is static: who is exposed, with no dynamics.
- Facts (abstract): nearly 400 security reports over 6 years in an npm network of more than 610k packages.

**Zerouali, A., Mens, T., Decan, A., & De Roover, C. (2022).** On the Impact of Security Vulnerabilities in the npm and RubyGems Dependency Networks. *Empirical Software Engineering*, 27(5). `zerouali2022vulnerabilities`
- Verified: https://doi.org/10.1007/s10664-022-10154-1
- Relevance: measures direct and transitive exposure, and the delay of fixes within the same major range. Useful for calibrating "recovery" through fix uptake.
- Facts (abstract): an npm vulnerability affects a median of 30 package releases (59 for RubyGems). 33% (projects) and 40% (packages) of exposed vulnerabilities have fixes available in the same major range.

**Liu, C., Chen, S., Fan, L., Chen, B., Liu, Y., & Peng, X. (2022).** Demystifying the Vulnerability Propagation and Its Evolution via Dependency Trees in the NPM Ecosystem. *Proc. ICSE 2022*, 672-684. `liu2022demystifying`
- Verified: https://doi.org/10.1145/3510003.3510142 (arXiv: https://arxiv.org/abs/2201.03981)
- Relevance: precise npm-resolution-aware propagation of *vulnerabilities* through dependency trees. It is the main "reachability" precedent. It is static and graph-theoretic, with no epidemic model.
- Facts (abstract): a knowledge graph of "over 10 million library versions and 60 million well-resolved dependency relations". Its remediation method (DTReme) outperforms `npm audit fix`.

**Mir, A. M., Keshani, M., & Proksch, S. (2023).** On the Effect of Transitivity and Granularity on Vulnerability Propagation in the Maven Ecosystem. *Proc. SANER 2023*, 201-211. `mir2023maven`
- Verified: https://doi.org/10.1109/SANER56733.2023.00028
- Relevance: shows that package-level reachability strongly overestimates *vulnerability* impact compared with call-graph reachability. This contrasts with our setting in a way that **justifies** package-level exposure: install-time malware executes regardless of whether its code is called.
- Facts (abstract): about one third of 3M Maven packages are vulnerable when all transitive dependencies are considered, but "less than 1%" have a reachable call path to vulnerable code.

**Schueller, W., & Wachs, J. (2024).** Modeling Interconnected Social and Technical Risks in Open Source Software Ecosystems. *Collective Intelligence*, 3(1). `schueller2024risks`
- Verified: https://doi.org/10.1177/26339137241231912 (arXiv: https://arxiv.org/abs/2205.04268)
- Relevance: **the closest methodological precedent to our two-channel model.** Failure propagates both along dependency links and through shared maintainers, applied to Rust. It also compares interventions under a limited budget. It differs from our paper: it models non-adversarial failure (developer departure), not an SIR worm, and has no thresholds, credential theft or detection delay. Cite it and position our work against it.
- Facts (abstract): "a library's chance of failure increases as its developers leave and as its upstream dependencies fail". Systemically important libraries "are overlooked when only considering technical dependencies".

**Robinson, M., Halder, S., Ahmed, M. E., Ikram, M., Camtepe, S., & Kim, H. (2026).** Original Sin of npm: A Study on Vulnerability Propagation in JavaScript Dependency Networks. arXiv:2604.17668 (listed as accepted at ACM AsiaCCS 2026). `robinson2026originalsin`
- Verified: https://arxiv.org/abs/2604.17668
- Relevance: very recent large-scale *vulnerability* propagation study. It is static, with no compartmental model and no worm or credential modelling (abstract). Its finding that a few vulnerabilities account for most exposure **parallels** our super-spreader finding.
- Facts (abstract): 1,077,946 npm packages and 1,515 vulnerabilities. 21.60% of packages have at least one known vulnerability in their dependency network. The top 7 vulnerabilities account for 25% of cases and the top 23 for 50%. The mean time to fix is about 4 years 11 months.

---

## Unverified / could not confirm

- **Bollobás, B., Borgs, C., Chayes, J., & Riordan, O. (2003). Directed scale-free graphs. *Proc. 14th ACM-SIAM SODA*, 132-139.** This is the generator behind `nx.scale_free_graph`, which our synthetic benchmark uses (`src/data_ingestion.py`). The citation as given appears in the official NetworkX documentation (https://networkx.org/documentation/stable/reference/generated/networkx.generators.directed.scale_free_graph.html). The primary sources could not be reached: the ACM DL returned HTTP 403, DBLP was behind a bot wall, and the guessed DOI `10.5555/644108.644133` did not resolve at doi.org. **Not in the BibTeX.** Confirm via the ACM DL or SIAM proceedings in a browser and then add it. It almost certainly exists, but under these verification rules it is not confirmed.

Also searched for but **not found** (this does not mean they do not exist):
- An SIR, SIS or percolation model of malware or worm spread on npm, PyPI or Maven dependency graphs.
- A paper modelling a token or credential contagion channel for package-registry worms.

Searches covered general web results plus results restricted to arxiv.org, dl.acm.org, ieeexplore.ieee.org, usenix.org and ndss-symposium.org, in October 2026. Recent arXiv papers that mention Shai-Hulud (arXiv 2608.08131, 2607.24888, 2607.01711) appeared in search snippets as qualitative incident discussions. They were not opened and are not cited.

---

## Novelty assessment

Epidemic models of software spreading along directed sharing graphs are old (Kephart & White 1991). The spectral threshold, percolation and immunization theory we use is standard (Wang et al. 2003; Newman 2002; Li et al. 2013; Pastor-Satorras & Vespignani 2002; Cohen et al. 2003). npm's dependency structure and its security exposure are also well documented (Kikas et al. 2017; Decan et al. 2019; Zimmermann et al. 2019). However, the software-engineering work on propagation in package ecosystems is *static reachability* of vulnerabilities (Decan et al. 2018; Liu et al. 2022; Zerouali et al. 2022; Mir et al. 2023; Robinson et al. 2026). The nearest dynamic model, Schueller & Wachs (2024), covers non-adversarial failure in Rust. **We found no prior work that models self-propagating npm worms as an SIR process.** In particular, nothing we found:
- couples a SemVer-weighted dependency channel with a stolen-token maintainer channel;
- estimates empirical epidemic thresholds under deployable ecosystem regimes (lockfiles, scripts off, trusted publishing);
- compares reactive patching with proactive betweenness and acquaintance immunization under realistic detection delays calibrated to the 2025 Shai-Hulud timelines.

The novelty claim should be phrased as "first epidemic-dynamics model of npm worms with a credential channel", not as "first epidemic model of software" or "first two-channel ecosystem risk model". Recheck arXiv just before submission, because post-Shai-Hulud work is appearing quickly.

---

## Claims to support

| Our finding | Backed by | Challenged or complicated by |
|---|---|---|
| Dependency edges are contagion channels; reverse them for exposure | Kikas 2017; Decan 2019; Decan 2018; Liu 2022; Kephart & White 1991 | Mir 2023: package-level reachability overestimates *vulnerability* impact. Rebut this by noting that install-time payloads run regardless of call reachability (Wyss 2022; StepSecurity 2025; Wiz 2025). |
| SemVer permissiveness weights transmission | semver.org; Decan & Mens 2021; Decan 2018 (constraint-aware exposure) | Pinckney 2023: the same permissiveness speeds *security fixes* (90.09%), so the net effect is a trade-off |
| Dependency-only spread is bounded (hubs reach about 6% of the 10k graph) | Socket 2025: the worm "cannot self-propagate without those credentials". Li 2013: directionality raises the threshold. | Zimmermann 2019: static reach of single packages can be ecosystem-wide. Explain the gap as dynamic (beta < 1, recovery) vs static reach, plus the scope of the 10k crawl. |
| The credential channel lets leaf origins reach 20-50% | Zimmermann 2019 (20 maintainers reach more than half of npm); Zahan 2022; StepSecurity 2025; Datadog 2025; Unit 42 2026 (about 639 versions across 323 packages from one account in an hour); Schueller & Wachs 2024 (shared-maintainer coupling) | **Real worms capped republishing**: up to 20 packages per maintainer (StepSecurity 2025, wave 1) and up to 100 (Datadog 2025, wave 2). Our "all of a maintainer's packages" assumption is an upper bound. Real totals were about 500 (wave 1; CISA 2025, Socket 2025) and 796 (wave 2; Datadog 2025) packages out of a registry of millions, so 20-50% must be stated as a share *of the 10k high-impact graph* only. |
| Strict lockfiles raise the threshold about 9x | CISA 2025 recommends pinning; Pinckney 2023 (ranges drive update flow) | Pinckney 2023 and Zerouali 2022: pinning delays fixes. Also, a lockfile does not stop the credential channel or a fresh install of a compromised top-level package. |
| Scripts-disabled regime is effective and deployable | Wyss 2022; pnpm v10 (2025); npm `ignore-scripts`; LavaMoat; Unit 42 2025 and Wiz 2025 (both waves used lifecycle scripts) | Aikido 2025: the chalk/debug payload ran at *runtime*, not install time. Scripts-off does not stop such payloads, only worm propagation through install hooks. |
| Trusted publishing / provenance cuts the credential channel | GitHub 2025 trusted publishing; GitHub 2025 plan; GitHub Dec 2025 token revocation; DeHamer 2023; Newman 2022; SLSA | Wiz 2025 s1ngularity (CI workflow injection) and Unit 42 2026 (Mini Shai-Hulud from TanStack's GitHub Actions pipeline): a compromised CI can still publish. Model this as partial, not complete, protection. |
| Empirical thresholds vs spectral 1/lambda_max; lambda_max is set by small monorepo cliques | Wang 2003; Chakrabarti 2008; Li 2013 (directed: 1/lambda_1 is a lower bound and lambda_1 falls with directionality); Pastor-Satorras 2015 review | Chakrabarti's exact result is for SIS-type dynamics on (effectively) undirected graphs. For SIR on a near-DAG, the spectral threshold is a loose bound dominated by cycles, so frame it as a bound, not a prediction. |
| Degree tails fit lognormal better than power law | Broido & Clauset 2019; Clauset 2009; Alstott 2014 | Pastor-Satorras & Vespignani 2001 assume scale-free tails with a vanishing threshold. Our finite thresholds are consistent with non-power-law tails. |
| Hub immunization beats random | Pastor-Satorras & Vespignani 2002; Cohen 2003 | none found |
| Proactive betweenness firebreak beats reactive patching under realistic detection delays | Holme 2002; Chen 2008 (partitioning strategies); Wiz 2025 timeline (days from upload to cleanup) motivates realistic delays; Zou 2002 (countermeasure timing in worm models) | Schneider 2011: an optimised strategy beats highest-betweenness immunization (up to 55% lower infection). Chen 2008: graph partitioning beats targeted strategies. Holme 2002: *recalculated* betweenness is stronger than static. Betweenness is a strong heuristic but not optimal; report which variant we use. |
| Acquaintance immunization is a practical low-information alternative | Cohen 2003 | none found; note that it was derived for undirected networks |
