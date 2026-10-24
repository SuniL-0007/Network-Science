Below is a complete, production-ready **Master Project Specification (SPEC.md)** designed specifically for an agentic coding tool (such as Claude Code, Cursor, Windsurf, or Aider).  
You can save the specification below directly as SPEC.md or CLAUDE.md in an empty repository and instruct your agent: *"Read SPEC.md and implement the project milestone by milestone."*

## **Master Project Specification: npm-sir-contagion**

### **1\. Project Context & Objective**

Build a modular Python research simulation and network analysis pipeline that models **software supply chain vulnerability propagation** (specifically self-propagating npm worms like *Shai-Hulud* / *CHAINDROP*) across the JavaScript (npm) dependency network using **SIR (Susceptible-Infected-Recovered)** epidemic diffusion models.

* **Analytical Engine:** Python (NetworkX, NDlib, Pandas, NumPy, SciPy, Matplotlib, Seaborn).  
* **Subject Matter / Data Domain:** JavaScript / npm package ecosystem (package.json metadata, SemVer dependency constraints, lifecycle scripts, and transitive dependency graphs from Google deps.dev API or Libraries.io).

### **2\. Repository Architecture**

The coding agent must scaffold and maintain the following directory structure:

npm-sir-contagion/  
├── data/  
│   ├── raw/                  \# Raw JSON/CSV snapshots from Deps.dev or Libraries.io  
│   └── processed/            \# Serialized NetworkX graphs (.gpickle / .graphml)  
├── results/  
│   ├── metrics/              \# CSV logs of simulation runs and topological metrics  
│   └── figures/              \# Publication-ready PDF/PNG plots (300 DPI)  
├── src/  
│   ├── \_\_init\_\_.py  
│   ├── config.py             \# Hyperparameters, random seeds, simulation constants  
│   ├── data\_ingestion.py     \# Deps.dev / npm registry fetcher & synthetic generator  
│   ├── graph\_builder.py      \# Directed graph construction & edge reversal logic  
│   ├── topology\_analyzer.py  \# Centrality, k-core, power-law, and Firebreak detection  
│   ├── sir\_engine.py         \# NDlib wrapper \+ custom SemVer-aware SIR contagion engine  
│   ├── experiments.py        \# Runners for RQ1, RQ2, and RQ3 Monte Carlo simulations  
│   ├── metrics\_logger.py     \# Time-to-Saturation, peak infection, cascade size calculators  
│   └── visualizer.py         \# Plotting scripts for epidemic curves and phase transitions  
├── tests/  
│   └── test\_simulation.py    \# Unit tests for edge directionality and SIR state transitions  
├── main.py                   \# CLI entry point to run full pipeline  
├── requirements.txt  
└── README.md

### **3\. Data Ingestion & Graph Construction (src/data\_ingestion.py & src/graph\_builder.py)**

#### **3.1 Dual Data Modes**

To support both fast prototyping and full empirical evaluation, implement two data loaders:

> 1. **Empirical npm Crawler (deps.dev \+ registry.npmjs.org):**  
   * Given a seed list of packages (or a Libraries.io CSV dump), recursively fetch dependencies and metadata up to depth $D$ or node limit $N$ (e.g., $N=10,000$ packages).  
   * Extract from package.json metadata:  
     * Package name and latest version.  
     * Dependency map (dependencies and devDependencies) along with **raw SemVer range strings** (e.g., ^1.2.0, \~1.2.0, \*, or exact pin 1.2.0).  
     * Lifecycle script flags: Check if scripts.preinstall, scripts.install, or scripts.postinstall exist (simulating *Shai-Hulud* lifecycle hook abuse).  
> 2. **Synthetic Scale-Free Generator (Benchmark Mode):**  
   * Use nx.scale\_free\_graph(n) to generate a realistic directed scale-free graph with heavy-tailed in-degree and narrow out-degree distributions that mirror npm's core-periphery topology, randomly assigning SemVer range attributes and lifecycle script booleans based on empirical proportions.

#### **3.2 Directed Graph Representation & Contagion Reversal**

* **Dependency Graph (${G}_{dep}$):** Node $u$ has a directed edge to Node $v$ ($u\rightarrow v$) if package $u$ imports/depends on package $v$.  
* **Contagion Graph (${G}_{contagion}$):** **Crucial requirement:** Vulnerability propagation flows *backwards* against the dependency arrow. If package $v$ is compromised, its dependent $u$ becomes exposed. Therefore, construct ${G}_{contagion}={G}_{dep}^{reverse()}$ where edges point from dependency $v\rightarrow$ dependent $u$.  
* **Node Attributes:**  
  * name: string (e.g., chalk, commander, express).  
  * state: Enum S (0), I (1), R (2).  
  * has\_lifecycle\_hook: bool (True if package uses preinstall/postinstall).  
  * has\_provenance: bool (True if protected by OIDC/Sigstore npm provenance).  
* **Edge Attributes (on $v\rightarrow u$):**  
  * semver\_type: categorical (exact, tilde, caret, wildcard).  
  * edge\_beta\_modifier: float multiplier representing how easily an automatic worm patch-bump crosses this link:  
    * exact (1.2.3 or frozen lockfile npm ci): multiplier \= 0.05 (requires manual update).  
    * tilde (\~1.2.3 \- allows patch updates, vulnerable to worm patch-bumping): multiplier \= 0.85.  
    * caret (^1.2.3 \- allows minor and patch updates): multiplier \= 1.0.  
    * wildcard (\* or latest): multiplier \= 1.0.

### **4\. Topological Analysis Module (src/topology\_analyzer.py)**

Before running contagion simulations, compute and export a comprehensive structural profile of the network:

> 1. **Degree Metrics:** In-degree (${k}_{in}$) and Out-degree (${k}_{out}$) distributions; fit power-law exponent $\alpha$ to confirm scale-free behavior.  
> 2. **Centrality Metrics:**  
   * **PageRank:** Measures transitive importance across deep dependency chains.  
   * **Betweenness Centrality:** Identifies "bridge" or bottleneck packages sitting between major sub-ecosystems.  
   * **Closeness / Harmonic Centrality:** Measures how few hops separate a package from the rest of the ecosystem.  
> 3. **Core-Periphery & Structural Metrics:**  
   * **$k$\-core Decomposition (nx.core\_number):** Identifies the deeply nested core vs. peripheral leaf packages.  
   * **Degree Assortativity Coefficient:** Tests whether high-degree hubs depend on other hubs or low-degree packages.  
   * **Local & Global Clustering Coefficients.**  
> 4. **Node Classification for Experiments:**  
   * **Super-Spreader Hubs:** Top 1% of nodes by out-degree in ${G}_{contagion}$ (most depended-upon packages, e.g., chalk, lodash).  
   * **Firebreak Candidates:** Nodes in the top 1% of **Betweenness Centrality** that connect high-core modules to large downstream consumer trees (e.g., middleware connecting utility libraries to frameworks like React or Express).  
   * **Periphery / Leaf Nodes:** Bottom 20% of nodes with non-zero out-degree in ${G}_{contagion}$.

### **5\. Epidemic Contagion Engine (src/sir\_engine.py)**

Implement two simulation backends:

#### **5.1 Baseline Homogeneous SIR (NDlib)**

* Use ndlib.models.epidemics.SIRModel over ${G}_{contagion}$ with uniform infection rate $\beta$ and recovery rate $\gamma$ as a baseline reference.

#### **5.2 Custom Supply-Chain-Aware SIR Engine**

Write a custom discrete-time Monte Carlo simulation loop over ticks \$t \= 0, 1, \\dots, T\_{\\max}\$:

> 1. **Initialization ($t=0$):**  
   * Set chosen "Patient Zero" node(s) to state I (simulating Account Takeover, Malicious Maintainer Handover, or Protestware).  
   * Set pre-immunized / "Firebreak" nodes (if any) to state R.  
   * Set all remaining nodes to state S.  
> 2. **Transmission Phase (per tick $t$):**  
   * For every currently infected node $v\in I(t)$, iterate over its outgoing neighbors $u$ in ${G}_{contagion}$ where $state(u)==S$.

Calculate effective transmission probability ${\beta }_{vu}$:

$${\beta }_{vu}=\min\limits_{}\left({1.0,{\beta }_{base}\times {w}_{semver}(v,u)\times {w}_{hook}(v)}\right)$$

*   
  where ${w}_{semver}(v,u)$ is the edge\_beta\_modifier and ${w}_{hook}(v)=1.25$ if has\_lifecycle\_hook is True (modeling automatic execution via preinstall/postinstall like *Shai-Hulud*), else $1.0$.  
  * Draw $p\sim Uniform(0,1)$. If $p$ is less than ${\beta }_{vu}$, mark $u$ to transition to I at $t+1$ and record the infection pathway $(v\rightarrow u,t)$.  
> 3. **Recovery / Intervention Phase (per tick $t$):**  
   * **Natural Patching:** Each node $v\in I(t)$ transitions to R with probability $\gamma$ (maintainer evicts attacker, publishes clean patch, or registry unpublishes malicious version).  
   * **Active Security Intervention (Budget $B$):** In addition to natural rate $\gamma$, the security team can forcefully transition up to $B$ nodes per tick from I (or S) to R according to a chosen **Patching Policy** (Random, Targeted-Hub, or Firebreak).  
> 4. **Termination:** Stop when \$\\vert{}I(t)\\vert{} \== 0\$ or $t=={T}_{\max\limits_{}}$. Run $M=100$ Monte Carlo realizations per parameter configuration to compute mean and 95% confidence intervals.

### **6\. Experimental Suite: The 3 Core Research Questions (src/experiments.py)**

The coding agent must implement automated experiment runners for these three experiments:

#### **Experiment 1: The "Super-Spreader" Effect (Origin Topology)**

* **Hypothesis:** Attacks originating in high-centrality hub packages spread exponentially faster and reach a much larger fraction of the ecosystem than attacks in middle-tier or leaf nodes.  
* **Setup:** Fix ${\beta }_{base}=0.15,\gamma =0.05$. Run 100 simulations each starting Patient Zero in:  
  1. Top 10 In-Degree / PageRank Hubs.  
  2. Top 10 High-Betweenness Bridge nodes.  
  3. 10 Randomly selected mid-tier ($k$\-core median) nodes.  
  4. 10 Periphery / Leaf nodes.

#### **Experiment 2: The SemVer & Lifecycle Script Risk ($\beta$ Sensitivity)**

* **Hypothesis:** Loose SemVer ranges (^ and \~) combined with unblocked postinstall lifecycle hooks significantly lower the epidemic threshold ($\beta /\gamma$), allowing self-propagating worms like *Shai-Hulud* to achieve ecosystem saturation before maintainers can react.  
* **Setup:** Compare four ecosystem regimes across a grid of $({\beta }_{base},\gamma )$ values:  
  1. **Status Quo npm:** 80% caret/tilde (^/\~), 20% exact pin, lifecycle hooks enabled.  
  2. **Strict Lockfile / Pinned Regime (npm ci):** 80% exact pin, 20% caret/tilde.  
  3. **Scripts Disabled (--ignore-scripts / @lavamoat/allow-scripts):** Status quo SemVer, but w\_hook reduced by 70%.  
  4. **Hardened Ecosystem:** Strict version pinning \+ lifecycle scripts disabled \+ OIDC provenance on top 5% hubs.

#### **Experiment 3: Patching & "Vaccine" Strategies (Intervention & Firebreaks)**

* **Hypothesis:** When security response teams have a fixed intervention capacity (e.g., $B=50$ packages per tick), targeting high-betweenness "Firebreak" bottlenecks or high-degree hubs halts contagion cascades drastically better than random patching.  
* **Setup:** Simulate an active outbreak from a major hub and compare four intervention strategies with budget $B$ nodes per tick:  
  1. **No Intervention:** Natural recovery $\gamma$ only.  
  2. **Random Patching:** Randomly transition $B$ currently infected (I) nodes to R per tick.  
  3. **Hub-Targeted Patching:** Transition the $B$ highest-degree currently infected (I) nodes to R per tick.  
  4. **Proactive Firebreak Immunization:** Pre-immunize (set to R at $t=0$) the top $K$ highest-betweenness bottleneck nodes so they act as structural firebreaks before the worm reaches major downstream frameworks.

### **7\. Complete Metrics & Inference Matrix (src/metrics\_logger.py)**

Every simulation run must compute and log the following metrics into structured CSVs, mapped directly to the scientific inferences required for the research paper:

| Metric Category | Metric Name & Formula / Definition | What We Observe | Scientific Inference for the Paper |
| :---- | :---- | :---- | :---- |
| **Spread Velocity** | **Time-to-Saturation (${T}_{80}$):** Number of ticks $t$ until $I(t)+R(t)\geq 0.80\times {N}_{reachable}$. | How fast a worm compromises 80% of its reachable dependency tree. | Quantifies the "Golden Hour" response window npm security teams have to pull a malicious package before ecosystem-wide compromise. |
| **Epidemic Severity** | **Peak Infection (${I}_{\max\limits_{}}$) & Time to Peak (${t}_{peak}$):** $\max\limits_{t}I(t)$ and $\arg \max\limits_{t}I(t)$. | Maximum simultaneous number of actively compromised packages. | Measures peak load on incident response teams and CI/CD pipelines at the height of a worm outbreak. |
| **Total Impact** | **Final Outbreak Size (${R}_{\infty }$):** \$\\frac{\\vert{}R(T\_{\\max})\\vert{}}{N}\$ as a percentage of total network nodes. | Total fraction of the ecosystem compromised by the end of the outbreak. | Demonstrates whether an attack fizzles out locally or triggers a global supply-chain cascade. |
| **Threshold Dynamics** | **Effective Epidemic Threshold (${\tau }_{c}=\beta /\gamma$):** Phase transition point where ${R}_{\infty }$ jumps above zero. | Critical ratio of infection-to-patching speed across different SemVer regimes. | Proves mathematically how loose SemVer (^/\~) lowers the barrier for self-sustaining npm worms. |
| **Structural Defense** | **Firebreak Cascade Reduction ($\Delta {R}_{\infty }$):** $\frac{{R}_{\infty }^{baseline}-{R}_{\infty }^{firebreak}}{{R}_{\infty }^{baseline}}$. | Percentage reduction in total infected packages when $K$ bottleneck nodes are hardened. | Identifies the exact ROI of enforcing mandatory 2FA, Sigstore provenance, and script-blocking on a tiny fraction of "bridge" packages. |
| **Chain Depth** | **Mean & Max Contagion Cascade Depth (${L}_{\max\limits_{}}$):** Longest directed path in the infection tree from Patient Zero. | How many transitive dependency hops the vulnerability travels downstream. | Reveals whether damage is caused by direct dependencies (hop 1\) or deep transitive dependencies (hops 3+). |

### **8\. Required Visualizations (src/visualizer.py)**

Auto-generate the following 5 publication-quality figures (saved as 300 DPI .png and vector .pdf):

> 1. **fig1\_degree\_distribution.pdf:** Log-log plot of In-Degree and Out-Degree distributions with fitted power-law slope $\alpha$.  
> 2. **fig2\_sir\_epidemic\_curves.pdf:** Classic $S(t),I(t),R(t)$ population trajectories over time with shaded 95% confidence bands across Monte Carlo runs.  
> 3. **fig3\_superspreader\_comparison.pdf:** Boxplots and violin plots comparing Final Outbreak Size (${R}_{\infty }$) and Time-to-Saturation (${T}_{80}$) across Hub, Bridge, Mid-tier, and Leaf origins (RQ1).  
> 4. **fig4\_semver\_phase\_transition.pdf:** 2D Heatmap of Final Outbreak Size (${R}_{\infty }$) across $\beta$ (x-axis) and $\gamma$ (y-axis) comparing Loose SemVer vs. Strict Lockfile regimes (RQ2).  
> 5. **fig5\_firebreak\_immunization.pdf:** Line plot showing Final Outbreak Size (${R}_{\infty }$) as a function of Intervention Budget $B$ across Random, Hub-Targeted, and Firebreak strategies (RQ3).

### **9\. Step-by-Step Execution Plan for the Coding Agent**

Instruct the agent to execute in these 5 sequential milestones, running unit tests after each step:

* **Milestone 1 (Setup & Data):** Create directory structure, requirements.txt, and src/data\_ingestion.py (implementing both the synthetic scale-free generator and the deps.dev / npm registry API fetcher).  
* **Milestone 2 (Graph & Topology):** Implement src/graph\_builder.py (ensuring dependency edges are reversed for contagion flow) and src/topology\_analyzer.py (computing centralities, $k$\-core, and selecting Super-Spreader and Firebreak nodes). Write a test verifying edge reversal.  
* **Milestone 3 (SIR Engine):** Implement src/sir\_engine.py with both the NDlib baseline and the custom SemVer/lifecycle-hook-weighted SIR engine. Write unit tests verifying state transitions ($S\rightarrow I\rightarrow R$).  
* **Milestone 4 (Experiments & Metrics):** Implement src/metrics\_logger.py and src/experiments.py to execute RQ1, RQ2, and RQ3 across Monte Carlo trials and output CSV summaries to results/metrics/.  
* **Milestone 5 (Visualization & CLI):** Implement src/visualizer.py to generate all 5 figures and wire everything into main.py with CLI flags (e.g., python main.py \--mode synthetic \--nodes 2000 \--runs 50).