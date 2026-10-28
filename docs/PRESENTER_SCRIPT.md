# Presenter's Script: npm Worms as Epidemics

A slide-by-slide speech for the 15-slide deck
([link](https://claude.ai/artifact/QJhHGwyvzFeTwCKkGPj61C)).

**Total time:** about 19 minutes of talk, plus questions. Each slide lists a target duration, what to
say, the numbers to stress, and a transition into the next slide. Lines in *italics* are stage
directions; everything else is meant to be said out loud, in your own words if you prefer.

**Pacing tips**
- Slides 1–7 set things up (about 9 minutes). Slides 8–11 are the results (about 7 minutes). Slides
  12–15 wrap up (about 3 minutes).
- If you're short on time, shorten slide 5 (network structure) and slide 7 (calibration); never cut
  slides 9–11.
- Pause after each big number. The audience needs a second to take it in.

---

## Slide 1: Title (≈ 45 s)

*Wait for the room to settle. Look at the audience, not the screen.*

> Good [morning/afternoon], everyone. My project is called "Super-spreaders, firebreaks and stolen
> tokens." It is about a new kind of malware that appeared in 2025: worms that spread on their own
> through npm, the package registry that almost every JavaScript application depends on.
>
> I'll treat that malware the way an epidemiologist treats a disease: as an SIR epidemic on a
> network. Over the next twenty minutes I want to answer three questions. Where do these outbreaks
> start? Which defences actually change the epidemic threshold? And if you're the security team with
> limited resources, should you react to infections or protect key packages in advance?
>
> One visual cue before we start: the two coloured bars here, blue and orange, are the two ways the
> worm spreads. You'll see blue for dependencies and orange for stolen credentials throughout the
> talk.

**Transition:** "Let me start with what actually happened."

---

## Slide 2: The problem (≈ 1 min 30 s)

> In September 2025, a worm called Shai-Hulud hit npm. It compromised about 200 packages, and it took
> roughly a day before anyone publicly noticed.
>
> *(Point to the second number.)* Two months later, Shai-Hulud 2.0 hit about 800 packages. This time
> automated scanners flagged it within minutes, and it still kept spreading for about 14 hours.
>
> What makes this interesting for a network-science course is *how* it spreads. *(Point to the bottom
> line.)*
> 1. Someone installs a compromised package, and npm automatically runs its install script.
> 2. That script searches the machine for the developer's npm publish token and steals it.
> 3. With the token, the worm publishes new, infected versions of that developer's own packages.
> 4. Anyone who installs those packages repeats the cycle.
>
> So this isn't one network, it's two coupled networks: the dependency graph, meaning who installs
> whom, and the maintainer graph, meaning who can publish what. That coupling turns out to be the key
> to the whole story.

**Key numbers:** ~200 packages / 24 h detection (wave 1); ~800 packages / 14 h plateau (wave 2).

**Transition:** "That gives us three concrete research questions."

---

## Slide 3: Research questions (≈ 1 min)

> Each question maps to a classic concept from this course.
>
> **RQ1 is the super-spreader question.** Does it matter where the worm starts: a hub that thousands
> of packages depend on, a bridge between communities, a mid-tier package, or an obscure leaf
> package?
>
> **RQ2 is about the epidemic threshold,** the critical transmission rate above which you get large
> outbreaks, the phase transition we studied in class. Do ecosystem-wide policies, such as pinning
> versions with lockfiles, disabling install scripts, or verified publishing, push that threshold up?
>
> **RQ3 is an immunization question.** If the security team can only handle a fixed number of packages
> per hour, should it patch infected packages as they appear, or immunize structurally important
> packages before the worm even shows up?

**Transition:** "To answer these, we first needed a real network."

---

## Slide 4: Data (≈ 1 min 15 s)

> We built the network ourselves from the live npm registry. We started from the 4,686 packages with
> the most dependents and crawled outward along their dependencies until we had 10,000 packages and
> 43,233 dependency edges.
>
> For every package we recorded:
> - the version ranges it uses for each dependency (71% are "caret" ranges, which automatically
>   accept new minor releases, including malicious ones);
> - whether it runs install scripts;
> - whether it is published with verified provenance;
> - who its maintainers are.
>
> One surprise worth mentioning. *(Point to the cleaning line.)* The full crawl contained a spam ring:
> 36 packages with fruit names like "applelemon", all from one account, 25 of which depend on every
> other one. It's a reward-farming scheme. That single clique pushed the network's spectral radius to
> 24, which would have completely distorted our threshold analysis, so we wrote an automatic filter
> for such rings.
>
> We also generated a synthetic scale-free network as a controlled baseline.

**Key numbers:** 4,686 seeds → 10,000 packages → 43,233 edges; spam farm of 36 packages.

**Transition:** "Before simulating anything, let's look at the structure."

---

## Slide 5: Network structure (≈ 1 min 15 s)

> Three things about the topology matter for everything that follows.
>
> **First, it's heavy-tailed.** *(Point to the plot.)* A handful of packages are depended on by
> hundreds of others. A power-law fit gives alpha around 2.08, but a likelihood-ratio test prefers a
> lognormal (p = 0.006). That matches Broido and Clauset's result that strictly scale-free real
> networks are rare.
>
> **Second, and most important, it's almost a DAG,** a directed acyclic graph. There are only 47 small
> cycles, the largest with 22 packages. Infection therefore mostly flows one way, downstream from
> wherever it starts.
>
> **Third, the blast radius is bounded.** The package with the most transitive dependents reaches
> 1,456 of the 10,000; the average reaches 45.
>
> Keep "almost a DAG" in mind. It explains why the dependency channel on its own can't go very far.

**Key numbers:** α = 2.08 (lognormal better, p = 0.006); 47 cycles, largest 22; max blast radius 1,456.

**Transition:** "Now, the model."

---

## Slide 6: The model (≈ 1 min 45 s)

> We use the standard SIR model: every package is Susceptible, Infected or Recovered. Infected means
> it has published a malicious version; recovered means patched, unpublished or protected. One time
> step is one hour.
>
> The novelty is that infection travels two ways.
>
> *(Point to the blue row.)* **The dependency channel:** an infected package infects each package that
> depends on it, with probability beta, scaled by how loose the dependent's version range is, and
> scaled down if the dependent blocks install scripts. An exact pin almost never picks up a malicious
> release; a caret range almost always does.
>
> *(Point to the orange row.)* **The credential channel:** an infected package leaks its maintainer's
> token with probability beta-m. The worm then republishes up to 20 or 100 of that maintainer's
> packages. Those caps aren't our invention; they're the limits the real worms used.
>
> Two details matter for realism. Patching only starts once the worm has been *detected*, because
> nobody patches a threat they don't know about. And we measure outbreak size as the share of packages
> *ever* infected, so that patched or protected packages aren't counted as damage.
>
> Statistically, every setting is run 100 times with paired random seeds, so when we compare two
> strategies they face exactly the same random outbreaks. We report bootstrap confidence intervals,
> because outbreak sizes are bimodal and normal-theory intervals would be misleading.

**Transition:** "A model is only useful if it matches reality, so we calibrated it."

---

## Slide 7: Calibration (≈ 1 min 15 s)

> From vendor reports and registry timestamps we know three things about each wave: when it was
> detected, how many packages each stolen token republished, and how long it took to stop spreading.
>
> We grid-searched the three free parameters (transmission rate, token-leak rate and patching rate)
> so that our simulated outbreaks plateau at the same time as the real ones, with about three quarters
> of infections coming from stolen tokens.
>
> *(Point to the plateau row.)* Wave 1 plateaued at 37 hours in reality; our model gives 41.5. Wave 2
> plateaued at 13.4 hours; the model gives 14.0. Both best fits lie inside our search grid, so they're
> not artifacts of where we drew its boundaries.
>
> An honest caveat: the data pin down *timing* and the *mix of channels* well, but not the absolute
> size of outbreaks. So when I show outbreak sizes in the core, read them as projections: what would
> happen if a worm with Shai-Hulud's dynamics got into the core.

**Key numbers:** plateau 37 h vs 41.5 h (wave 1); 13.4 h vs 14.0 h (wave 2); 76–77% via tokens.

**Transition:** "We also checked the model's central assumption against the real victims."

---

## Slide 8: Validation (≈ 1 min 15 s)

> If stolen tokens really drive the spread, the real victims should share maintainers with each
> other. So we took the published lists of compromised packages and fetched their registry metadata.
> We only looked at metadata; we never downloaded or ran any malicious code.
>
> *(Point to the left number.)* In wave 1, 98% of victims share a maintainer with another victim. For
> random sets of packages of the same size, that figure is only 49%.
>
> *(Point to the right number.)* In wave 2 it's 95% against 69%.
>
> Dependency links between victims are much rarer, and almost none of the victims are in the
> high-impact core we crawled. So the real worms spread through stolen tokens among small maintainers
> on the periphery. That gives our experiments their framing: we ask what happens when such a worm
> reaches the core.

**Key numbers:** 98% vs 49% (wave 1); 95% vs 69% (wave 2).

**Transition:** "So, on to the results. First: does the origin matter?"

---

## Slide 9: RQ1, origin (≈ 2 min)

> We started outbreaks from four groups of packages (hubs, bridges, mid-tier and leaves), 1,000 runs
> per group.
>
> *(Point to the blue number.)* With dependencies only, the classic super-spreader picture holds. Hub
> outbreaks reach a few percent of the core, and leaf outbreaks reach essentially zero. That's the
> near-DAG structure at work: infection can only flow downstream.
>
> *(Point to the orange numbers. Slow down here; this is the main result.)* Now add the calibrated
> credential channel. A leaf package, which on its own cannot infect anything through dependencies,
> now reaches 19.6% of the core with wave-1 parameters and 55.4% with wave-2 parameters.
>
> *(Point to the plot.)* Look at the shape of the distributions: they become bimodal. Either the
> outbreak dies before a token leaks, or it takes over a large part of the core. Origin topology now
> mostly changes the *probability* that an outbreak takes off, not how big it gets once it does.
>
> One caveat for precision: these are shares of our 10,000-package graph. On the 5,000-package sample
> and the full 14,600-package closure, the leaf figure is 22% and 8%, so it's best read as a range.

**Key numbers:** leaf origin 0% (dependencies only) → 19.6% (SH1) → 55.4% (SH2).

**Transition:** "If origin barely matters, maybe ecosystem policies can help. That's RQ2."

---

## Slide 10: RQ2, regimes (≈ 2 min)

> RQ2 is about the epidemic threshold. We compared four regimes: the status quo; strict lockfiles,
> where 80% of version ranges are pinned; scripts disabled, where 70% of packages block install
> scripts; and a fully hardened regime that combines both with verified publishing on the top hubs.
>
> *(Point to the heatmaps.)* Each heatmap shows outbreak size across transmission and patching rates.
> Without stolen tokens, hardening clearly works. *(Point to the blue numbers.)* Strict lockfiles
> raise the threshold about twelve-fold, and blocking scripts about six-fold. The hardened regime
> never produced a major outbreak at all.
>
> As a side note, the classic spectral prediction, one over lambda-max, is far off here. On a directed,
> nearly acyclic graph it's only a lower bound, and it's set by a few small monorepo cycles.
>
> *(Point to the orange numbers.)* But once tokens can be stolen, the threshold in the transmission
> rate collapses. The credential channel can sustain the epidemic on its own. So we computed the
> threshold in the *token-leak rate* instead.
> - Hardening raises that threshold about seven-fold.
> - But the calibrated wave-1 worm leaks tokens about ten times faster than the status-quo threshold,
>   and the wave-2 worm is above the threshold of every regime we tested.
> - Only hardening combined with fast patching gets a wave-1-like worm below threshold.

**Key numbers:** lockfiles 12×, scripts 6×; token threshold raised 7× by hardening; SH1 is 10× above
the status-quo token threshold.

**Transition:** "If we can't prevent outbreaks, how should we respond? That's RQ3."

---

## Slide 11: RQ3, response (≈ 2 min)

> We compared reactive and proactive strategies at exactly the same total cost. Reactive strategies
> patch up to 50 packages per hour after detection, either hubs first or at random. Proactive
> strategies protect the same total number of packages in advance, chosen by degree, by betweenness,
> or by acquaintance sampling, which needs no global knowledge.
>
> *(Walk through the table row by row, left to right.)*
> - If the worm is detected within an hour, reacting wins: patching hubs prevents essentially the
>   whole outbreak.
> - The value of reacting collapses with delay: 90% at 6 hours, 52% at 12, and only 13% at 24 hours,
>   which was the actual detection lag of wave 1.
> - *(Point to the highlighted row.)* Immunizing hubs in advance holds steady at around 40%.
>
> The crossover is between 12 and 24 hours of detection delay.
>
> One result surprised us. The original plan expected betweenness-based "firebreaks" to be the best
> proactive strategy. At realistic budgets, degree-based immunization beats them clearly. Only at the
> largest budget we tried do they converge. Optimised strategies could do better than either, so we
> don't claim optimality, just that degree beats betweenness and reaction at realistic costs.

**Key numbers:** hub patching 100% → 52% → 13% (1 h → 12 h → 24 h); hub immunization ≈ 42% at 24 h.

**Transition:** "These are strong claims, so we stress-tested them."

---

## Slide 12: Robustness (≈ 1 min 15 s)

> Four checks.
>
> **Six synthetic graphs:** hub immunization was the best response in all six, so the conclusion
> doesn't depend on our particular crawl.
>
> **Sample size:** the same pattern on the 5,000-package sample, the 10,000-package graph and the full
> 14,624-package closure. Only the leaf figure moves, between about 8% and 22% of the graph.
>
> **Null models:** we randomly rewired the network while keeping every package's degrees, five times.
> Outbreaks got *bigger*: dependency-only hub outbreaks reached about 8% instead of 2.6%. So npm's
> real layered, nearly acyclic structure actually *dampens* spread compared with a random network that
> has the same degrees.
>
> **Sensitivity:** we varied the transmission and patching rates over nine settings around the
> calibration. All nine reach the same conclusions: proactive beats reactive at 24 hours, degree beats
> betweenness at a realistic budget, and leaf-started outbreaks stay substantial.

**Key numbers:** 6 of 6 synthetic; leaf reach 8–22%; null hubs ~8% vs 2.6%; 9 of 9 sensitivity settings.

**Transition:** "So what should defenders actually do?"

---

## Slide 13: Takeaways (≈ 1 min)

*This is the dark slide; slow down and let each point land.*

> If you remember three things from this talk:
>
> **One: break the credential channel.** Stolen tokens are what turn a bounded, hub-driven process into
> one that can take over the core from almost anywhere. Short-lived, narrowly scoped tokens and
> verified publishing come first.
>
> **Two: then harden dependencies.** Lockfiles and script blocking still raise the threshold six- to
> twelve-fold, but only while tokens can't be stolen.
>
> **Three: protect hubs in advance.** With detection lags of a day, protecting the most
> depended-upon packages in advance beats chasing infections after the fact.

**Transition:** "Before I finish, let me be clear about what the model doesn't tell us."

---

## Slide 14: Limitations (≈ 50 s)

> Four limitations.
>
> **First,** our graph is the high-impact core, not all of npm, and the real worms mostly hit the
> periphery. Outbreak sizes in the core are projections, not predictions.
>
> **Second,** we assumed that 10% of packages block install scripts today and 70% in the
> scripts-disabled regime. We couldn't find any real measurements of those shares.
>
> **Third,** the metadata comes from 2026, not from the dates of the attacks.
>
> **Fourth,** our immunization strategies are simple static heuristics. The literature shows that
> optimised strategies can do better.

**Transition:** "With that, thank you."

---

## Slide 15: Questions (≈ 15 s, then Q&A)

> Thank you for listening. The code, the data and a draft of the paper are on GitHub at the address
> on the slide. I'm happy to take questions.

---

## Q&A preparation

**Why SIR and not SIS?**
Once a package is patched or unpublished, the same malicious version can't reinfect it, and the
stolen token is revoked. "Recovered" is a reasonable absorbing state. SIS would fit a worm that can
reinfect patched packages, which these worms couldn't.

**Why one hour per time step?**
It matches the timescales we calibrated to: detection after about 24 hours or within minutes, plateau
after 14–37 hours. Hourly steps resolve both waves. Changing the tick length would rescale the rates
without changing the conclusions.

**Why only the high-impact core and not all of npm?**
The full registry has millions of packages. Crawling all of it, with metadata, isn't feasible for a
course project, and most packages are never installed by anyone. The core is where an outbreak would
do the most damage. We tested 5k, 10k and the full 14,624-package closure of the seed set, and the
conclusions held.

**Isn't the credential channel just an assumption you built in?**
We validated it. Real victims share maintainers 98% and 95% of the time, against 49% and 69% for
random package sets. We calibrated its strength to the observed plateau times and channel mix, and
the token caps come from the real worms.

**Why did betweenness lose to degree?**
Our best explanation is that betweenness targets packages that cut *dependency* paths, but under the
credential channel most infections bypass those paths through stolen tokens. We haven't tested that
mechanism directly, and at the largest budget betweenness catches up.

**Why is the spectral threshold so far off?**
For SIR on a directed, nearly acyclic graph, 1/λmax is only a lower bound. Here λmax is set by a few
small, dense monorepo cycles (e.g. `@stdlib`), not by the network as a whole. We report it but rely on
empirical thresholds from simulation.

**How reliable are the outbreak sizes?**
Timing and channel mix are well constrained by calibration; absolute sizes are not. That's why we
present core sizes as projections and focus the claims on *comparisons* (origin groups, regimes,
strategies), which are robust across sizes, null models and the parameter sweep.

**Did you run any malware?**
No. Validation used only registry metadata and public indicator lists. No compromised package was
downloaded, installed or executed.

**What would you do next?**
Measure real adoption of script blocking and trusted publishing; model a worm crawling the periphery
rather than the core; test optimised immunization sets; and extend the model to other ecosystems such
as PyPI.
