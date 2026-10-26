"""SIR contagion engines over G_contagion (spec §5).

* `simulate`: custom discrete-time, supply-chain-aware SIR (SemVer / lifecycle-hook
  weighted edges, provenance, optional maintainer-credential channel, patching policies).
* `run_ndlib_sir`: homogeneous NDlib SIRModel baseline (optional dependency).
* `run_monte_carlo`: M independent realisations with SeedSequence-spawned streams.

Tick t -> t+1, all computed from the state at t:
  1. transmission  : each I node v infects each S successor u w.p. beta_vu
  2. credentials   : (optional) each I node leaks each maintainer w.p. beta_maintainer; the
                     worm republishes all S packages of newly compromised maintainers
  3. recovery      : each I node -> R w.p. gamma from tick `recovery_start` on (detection;
                     newly infected nodes do not recover yet)
  4. intervention  : a PatchPolicy moves up to `budget` nodes (I and/or S) to R at t+1
Runs stop when no node is infected or t == t_max.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace

import networkx as nx
import numpy as np

from src.config import SIRParams
from src.graph_builder import State

S, I, R = int(State.S), int(State.I), int(State.R)

# channel codes for SimulationResult.channel
NEVER, SEED, DEPENDENCY, MAINTAINER = -1, 0, 1, 2


# =========================================================================== model
@dataclass(frozen=True, eq=False)
class ContagionModel:
    """Array (CSR) form of G_contagion, compiled once and shared by all runs."""

    nodes: tuple
    indptr: np.ndarray  # out-edges of node i: indices[indptr[i]:indptr[i+1]]
    indices: np.ndarray
    w_semver: np.ndarray  # edge_beta_modifier per edge
    hook: np.ndarray  # bool per node
    provenance: np.ndarray  # bool per node
    out_degree: np.ndarray
    pkg_maint_indptr: np.ndarray  # package -> maintainer ids
    pkg_maint: np.ndarray
    maint_pkg_indptr: np.ndarray  # maintainer id -> packages
    maint_pkg: np.ndarray
    index: dict = field(repr=False, compare=False, default_factory=dict)
    # bool per node: maintainers/CI block lifecycle scripts (used by hook_mode="injected")
    scripts_blocked: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.nodes)

    @classmethod
    def from_graph(cls, g: nx.DiGraph) -> ContagionModel:
        nodes = tuple(g)
        index = {u: i for i, u in enumerate(nodes)}
        indptr, indices, w = [0], [], []
        for u in nodes:
            for v, data in sorted(g[u].items(), key=lambda kv: index[kv[0]]):
                indices.append(index[v])
                w.append(float(data.get("edge_beta_modifier", 1.0)))
            indptr.append(len(indices))

        maint_ids: dict[str, int] = {}
        pm_ptr, pm = [0], []
        for u in nodes:
            for m in g.nodes[u].get("maintainers") or []:
                pm.append(maint_ids.setdefault(m, len(maint_ids)))
            pm_ptr.append(len(pm))
        pm_ptr, pm = np.array(pm_ptr, dtype=np.int64), np.array(pm, dtype=np.int64)
        owners = np.repeat(np.arange(len(nodes)), np.diff(pm_ptr))
        order = np.argsort(pm, kind="stable")
        mp_ptr = np.concatenate([[0], np.cumsum(np.bincount(pm, minlength=len(maint_ids)))])

        return cls(
            nodes=nodes,
            indptr=np.array(indptr, dtype=np.int64),
            indices=np.array(indices, dtype=np.int64),
            w_semver=np.array(w, dtype=float),
            hook=np.array([bool(g.nodes[u].get("has_lifecycle_hook")) for u in nodes]),
            provenance=np.array([bool(g.nodes[u].get("has_provenance")) for u in nodes]),
            out_degree=np.diff(np.array(indptr, dtype=np.int64)),
            pkg_maint_indptr=pm_ptr,
            pkg_maint=pm,
            maint_pkg_indptr=mp_ptr.astype(np.int64),
            maint_pkg=owners[order],
            index=index,
            scripts_blocked=np.zeros(len(nodes), dtype=bool),
        )

    def idx(self, names: Sequence) -> np.ndarray:
        """Node names -> integer indices."""
        return np.array([self.index[u] for u in names], dtype=np.int64)

    def with_overrides(self, w_semver=None, hook=None, provenance=None, scripts_blocked=None) -> ContagionModel:
        """Copy with replaced edge modifiers / node flags (used by RQ2 regimes)."""
        changes = {k: np.asarray(v) for k, v in
                   {"w_semver": w_semver, "hook": hook, "provenance": provenance,
                    "scripts_blocked": scripts_blocked}.items() if v is not None}
        return replace(self, **changes)

    def edge_betas(self, p: SIRParams) -> np.ndarray:
        """Per-edge transmission probability beta_vu.

        static   : beta * w_semver * w_hook(v) * w_prov(u), w_hook = hook_multiplier on packages
                   that declare install scripts (the spec formula).
        injected : the worm adds its install script to every package it republishes, so the
                   source-side boost is uniform (absorbed in beta); instead the *consumer* matters:
                   beta * w_semver * w_exec(u) * w_prov(u), with w_exec = blocked_susceptibility
                   for packages whose maintainers/CI block lifecycle scripts.
        """
        w = p.beta * self.w_semver * np.where(self.provenance[self.indices], p.provenance_factor, 1.0)
        if p.hook_mode == "static":
            src = np.repeat(np.arange(self.n), self.out_degree)
            w = w * np.where(self.hook[src], p.hook_multiplier, 1.0)
        elif p.hook_mode == "injected":
            if self.scripts_blocked is not None:
                w = w * np.where(self.scripts_blocked[self.indices], p.blocked_susceptibility, 1.0)
        else:
            raise ValueError(f"unknown hook_mode {p.hook_mode!r}")
        return np.minimum(1.0, w)


def _expand(indptr: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For CSR rows, return (row of each entry, entry position) for all their entries."""
    starts = indptr[rows]
    counts = indptr[rows + 1] - starts
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    offsets = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    return np.repeat(rows, counts), np.repeat(starts, counts) + offsets


# =========================================================================== policies
@dataclass(frozen=True, eq=False)
class PatchPolicy:
    """Active intervention: move up to `budget` nodes to R each tick from `start_tick` on.

    `order` is a node-index priority list (highest first); None means uniformly random.
    `target` picks which states are eligible: 'infected' (patching), 'susceptible'
    (vaccination) or 'any'.
    """

    budget: int
    target: str = "infected"
    order: np.ndarray | None = None
    start_tick: int = 1
    name: str = "policy"

    def select(self, state: np.ndarray, t: int, rng: np.random.Generator) -> np.ndarray:
        if self.budget <= 0 or t < self.start_tick:
            return np.empty(0, np.int64)
        eligible = {"infected": state == I, "susceptible": state == S, "any": state != R}[self.target]
        if self.order is None:
            pool = np.flatnonzero(eligible)
            return pool if len(pool) <= self.budget else rng.choice(pool, self.budget, replace=False)
        ranked = self.order[eligible[self.order]]
        return ranked[: self.budget]


def make_policy(model: ContagionModel, kind: str, budget: int, scores: dict | None = None,
                target: str = "infected", start_tick: int = 1) -> PatchPolicy:
    """kind: 'random', 'hub' (contagion out-degree), or 'score' (descending `scores`)."""
    if kind == "random":
        order = None
    elif kind == "hub":
        order = np.argsort(-model.out_degree, kind="stable")
    elif kind == "score":
        if scores is None:
            raise ValueError("kind='score' needs `scores`")
        vals = np.array([scores.get(u, -np.inf) for u in model.nodes], dtype=float)
        order = np.argsort(-vals, kind="stable")
    else:
        raise ValueError(f"unknown policy kind {kind!r}")
    return PatchPolicy(budget, target, order, start_tick, name=kind)


# =========================================================================== results
@dataclass
class SimulationResult:
    S: np.ndarray  # counts per tick, length T+1
    I: np.ndarray
    R: np.ndarray
    infection_time: np.ndarray  # per node, -1 if never infected
    recovery_time: np.ndarray  # per node, -1 if never moved to R
    infector: np.ndarray  # per node, -1 for seeds / never
    channel: np.ndarray  # NEVER / SEED / DEPENDENCY / MAINTAINER
    generation: np.ndarray  # infection-tree depth (seeds = 0, never = -1)
    patient_zero: np.ndarray
    immunized: np.ndarray
    n_patched: np.ndarray  # intervention moves per tick
    n_maint_compromised: int = 0  # maintainer tokens leaked (credential channel)

    @property
    def duration(self) -> int:
        return len(self.I) - 1

    @property
    def ever_infected(self) -> int:
        """Nodes infected at any time. Unlike |R(T)|, excludes immunized/vaccinated nodes."""
        return int((self.infection_time >= 0).sum())

    def pathways(self) -> list[tuple[int, int, int, int]]:
        """(infector, node, tick, channel) for every non-seed infection, in time order."""
        hit = np.flatnonzero(self.channel > SEED)
        hit = hit[np.argsort(self.infection_time[hit], kind="stable")]
        return [(int(self.infector[u]), int(u), int(self.infection_time[u]), int(self.channel[u])) for u in hit]

    def padded(self, length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """S, I, R curves extended to `length` ticks by holding the final value."""
        def pad(x):
            return x[:length] if len(x) >= length else np.concatenate([x, np.full(length - len(x), x[-1])])
        return pad(self.S), pad(self.I), pad(self.R)


# =========================================================================== custom engine
def simulate(
    model: ContagionModel,
    params: SIRParams,
    patient_zero: Sequence,
    rng: np.random.Generator | int | None = None,
    immunized: Sequence = (),
    policy: PatchPolicy | None = None,
    edge_beta: np.ndarray | None = None,
) -> SimulationResult:
    """One realisation. `patient_zero` / `immunized` are node names or index arrays.

    Pre-immunized nodes start in R, except patient-zero nodes (already compromised).
    `edge_beta` lets Monte Carlo loops reuse precomputed per-edge probabilities.
    """
    rng = rng if isinstance(rng, np.random.Generator) else np.random.default_rng(rng)
    n = model.n
    pz = _as_idx(model, patient_zero)
    imm = np.setdiff1d(_as_idx(model, immunized), pz)
    beta_e = model.edge_betas(params) if edge_beta is None else edge_beta
    use_maint = params.beta_maintainer > 0 and len(model.pkg_maint) > 0

    state = np.full(n, S, dtype=np.int8)
    state[imm] = R
    state[pz] = I
    inf_t = np.full(n, -1, np.int64)
    rec_t = np.full(n, -1, np.int64)
    infector = np.full(n, -1, np.int64)
    channel = np.full(n, NEVER, np.int8)
    gen = np.full(n, -1, np.int64)
    inf_t[pz], channel[pz], gen[pz] = 0, SEED, 0
    rec_t[imm] = 0
    maint_done = np.zeros(len(model.maint_pkg_indptr) - 1, dtype=bool)

    counts = [np.bincount(state, minlength=3)]
    patched = [0]
    t = 0
    while t < params.t_max and counts[-1][I] > 0:
        infected = np.flatnonzero(state == I)
        new_nodes, new_src, new_ch = [], [], []

        # 1. dependency transmission
        src, edge = _expand(model.indptr, infected)
        dst = model.indices[edge]
        open_ = state[dst] == S
        src, edge, dst = src[open_], edge[open_], dst[open_]
        hit = rng.random(len(edge)) < beta_e[edge]
        new_nodes.append(dst[hit])
        new_src.append(src[hit])
        new_ch.append(np.full(hit.sum(), DEPENDENCY))

        # 2. maintainer-credential channel
        if use_maint:
            owner, pos = _expand(model.pkg_maint_indptr, infected)
            maint = model.pkg_maint[pos]
            fresh = ~maint_done[maint]
            owner, maint = owner[fresh], maint[fresh]
            leak = rng.random(len(maint)) < params.beta_maintainer
            owner, maint = owner[leak], maint[leak]
            maint, first = np.unique(maint, return_index=True)
            owner = owner[first]
            maint_done[maint] = True
            if len(maint):
                m_row, pos = _expand(model.maint_pkg_indptr, maint)
                victims = model.maint_pkg[pos]
                cap = params.maintainer_publish_cap
                if cap > 0 and len(victims) > cap:  # worm republishes <= cap random packages per token
                    order = np.lexsort((rng.random(len(victims)), m_row))
                    starts = np.flatnonzero(np.r_[True, np.diff(m_row[order]) != 0])
                    rank = np.arange(len(order)) - np.repeat(starts, np.diff(np.r_[starts, len(order)]))
                    keep = order[rank < cap]
                    victims, m_row = victims[keep], m_row[keep]
                leaker = owner[np.searchsorted(maint, m_row)]
                ok = state[victims] == S
                victims, leaker = victims[ok], leaker[ok]
                p_pub = np.where(model.provenance[victims], params.provenance_factor, 1.0)
                pub = rng.random(len(victims)) < p_pub
                new_nodes.append(victims[pub])
                new_src.append(leaker[pub])
                new_ch.append(np.full(pub.sum(), MAINTAINER))

        # one infector per newly infected node, chosen uniformly among successful attempts
        nodes, srcs, chans = (np.concatenate(x) for x in (new_nodes, new_src, new_ch))
        if len(nodes):
            perm = rng.permutation(len(nodes))
            nodes, srcs, chans = nodes[perm], srcs[perm], chans[perm]
            nodes, first = np.unique(nodes, return_index=True)
            srcs, chans = srcs[first], chans[first]

        # 3. natural recovery of nodes infected at t
        gamma = params.gamma if t >= params.recovery_start else 0.0  # no patching before detection
        recovered = infected[rng.random(len(infected)) < gamma]

        t += 1
        state[recovered] = R
        rec_t[recovered] = t
        state[nodes] = I
        inf_t[nodes], infector[nodes], channel[nodes] = t, srcs, chans
        gen[nodes] = gen[srcs] + 1

        # 4. active intervention on the state at t
        moved = policy.select(state, t, rng) if policy is not None else np.empty(0, np.int64)
        state[moved] = R
        rec_t[moved] = t
        patched.append(len(moved))
        counts.append(np.bincount(state, minlength=3))

    c = np.array(counts)
    return SimulationResult(
        S=c[:, S], I=c[:, I], R=c[:, R],
        infection_time=inf_t, recovery_time=rec_t, infector=infector, channel=channel,
        generation=gen, patient_zero=pz, immunized=imm, n_patched=np.array(patched),
        n_maint_compromised=int(maint_done.sum()),
    )


def _as_idx(model: ContagionModel, nodes) -> np.ndarray:
    arr = np.asarray(nodes)
    if arr.size == 0:
        return np.empty(0, np.int64)
    if np.issubdtype(arr.dtype, np.integer):
        return arr.astype(np.int64).ravel()
    return model.idx(list(arr.ravel()))


# =========================================================================== monte carlo
PatientZero = Sequence | Callable[[np.random.Generator], Sequence]
_WORKER: dict = {}


@dataclass(frozen=True, eq=False)
class MCJob:
    """One Monte Carlo configuration: `n_runs` realisations sharing params/policy/model.

    `patient_zero` and `immunized` are node lists or functions `rng -> nodes` drawn per run.
    Run i uses child i of `SeedSequence(seed)`, so jobs with the same seed are paired: run i
    gets the same origin draw and random stream regardless of strategy, model or `n_jobs`.
    """

    params: SIRParams
    patient_zero: PatientZero
    n_runs: int = 100
    seed: int = 0
    immunized: Sequence | Callable[[np.random.Generator], Sequence] = ()
    policy: PatchPolicy | None = None
    model_key: str = "base"
    tag: dict = field(default_factory=dict)  # labels for downstream tables


def _init_worker(models, policies, reducer):
    _WORKER.clear()
    _WORKER.update(models=models, policies=policies, reducer=reducer, betas={})


def _run_one(task):
    model_key, params, policy_id, seed_seq, pz, immunized = task
    w = _WORKER
    model = w["models"][model_key]
    betas = w["betas"]
    if (model_key, params) not in betas:
        betas[(model_key, params)] = model.edge_betas(params)
    res = simulate(model, params, pz, np.random.default_rng(seed_seq), immunized,
                   w["policies"].get(policy_id), betas[(model_key, params)])
    return w["reducer"](res) if w["reducer"] else res


def run_batch(
    models: dict[str, ContagionModel] | ContagionModel,
    jobs: Sequence[MCJob],
    reducer: Callable[[SimulationResult], object] | None = None,
    n_jobs: int = 1,
) -> list[list]:
    """Run every job through one worker pool; returns one result list per job.

    Models and policies are shipped to each worker once; tasks only carry seeds and node
    indices. `reducer` (picklable when n_jobs > 1) summarises each result in the worker.
    """
    models = {"base": models} if isinstance(models, ContagionModel) else models
    policies = {id(j.policy): j.policy for j in jobs if j.policy is not None}
    tasks, owner = [], []
    for j, job in enumerate(jobs):
        model = models[job.model_key]
        for child in np.random.SeedSequence(job.seed).spawn(job.n_runs):
            pz_seq, sim_seq, imm_seq = child.spawn(3)
            pz = job.patient_zero(np.random.default_rng(pz_seq)) if callable(job.patient_zero) else job.patient_zero
            imm = job.immunized(np.random.default_rng(imm_seq)) if callable(job.immunized) else job.immunized
            tasks.append((job.model_key, job.params, id(job.policy) if job.policy else None,
                          sim_seq, _as_idx(model, pz), _as_idx(model, imm)))
            owner.append(j)

    if n_jobs == 1:
        _init_worker(models, policies, reducer)
        try:
            flat = [_run_one(t) for t in tasks]
        finally:
            _WORKER.clear()
    else:
        with ProcessPoolExecutor(n_jobs, initializer=_init_worker,
                                 initargs=(models, policies, reducer)) as pool:
            flat = list(pool.map(_run_one, tasks, chunksize=max(1, len(tasks) // (8 * n_jobs))))

    out: list[list] = [[] for _ in jobs]
    for j, r in zip(owner, flat):
        out[j].append(r)
    return out


def run_monte_carlo(
    model: ContagionModel,
    params: SIRParams,
    patient_zero: PatientZero,
    n_runs: int = 100,
    seed: int = 0,
    immunized: Sequence = (),
    policy: PatchPolicy | None = None,
    reducer: Callable[[SimulationResult], object] | None = None,
    n_jobs: int = 1,
) -> list:
    """Run `n_runs` independent realisations of one configuration (see `MCJob`)."""
    job = MCJob(params, patient_zero, n_runs, seed, immunized, policy)
    return run_batch(model, [job], reducer, n_jobs)[0]


# =========================================================================== ndlib baseline
def run_ndlib_sir(g: nx.DiGraph, params: SIRParams, patient_zero: Sequence, seed: int = 0) -> SimulationResult:
    """Homogeneous SIR via NDlib (uniform beta on every edge; no SemVer/hook weights).

    NDlib draws from NumPy's global RNG, which this function seeds. Infector and generation
    are not tracked by NDlib and are left as -1.
    """
    try:
        import ndlib.models.epidemics as ep
        import ndlib.models.ModelConfig as mc
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("NDlib baseline needs `pip install ndlib`") from exc

    nodes = list(g)
    index = {u: i for i, u in enumerate(nodes)}
    gi = nx.relabel_nodes(g, index, copy=True)
    pz = sorted(index[u] for u in patient_zero)

    np.random.seed(seed)
    model = ep.SIRModel(gi, seed=seed)
    cfg = mc.Configuration()
    cfg.add_model_parameter("beta", params.beta)
    cfg.add_model_parameter("gamma", params.gamma)
    cfg.add_model_initial_configuration("Infected", pz)
    model.set_initial_status(cfg)

    n = len(nodes)
    inf_t, rec_t = np.full(n, -1, np.int64), np.full(n, -1, np.int64)
    inf_t[pz] = 0
    counts = []
    for t in range(params.t_max + 1):
        it = model.iteration(node_status=True)
        if t > 0:
            for u, st in it["status"].items():
                if st == I and inf_t[u] < 0:
                    inf_t[u] = t
                elif st == R:
                    rec_t[u] = t
                    if inf_t[u] < 0:  # infected and recovered within the same NDlib step
                        inf_t[u] = t
        nc = it["node_count"]
        counts.append((nc.get(0, 0), nc.get(1, 0), nc.get(2, 0)))
        if nc.get(1, 0) == 0:
            break

    c = np.array(counts)
    channel = np.where(inf_t >= 0, DEPENDENCY, NEVER).astype(np.int8)
    channel[pz] = SEED
    return SimulationResult(
        S=c[:, 0], I=c[:, 1], R=c[:, 2], infection_time=inf_t, recovery_time=rec_t,
        infector=np.full(n, -1, np.int64), channel=channel, generation=np.full(n, -1, np.int64),
        patient_zero=np.array(pz, np.int64), immunized=np.empty(0, np.int64),
        n_patched=np.zeros(len(c), np.int64),
    )
