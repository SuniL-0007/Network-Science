"""Publication figures (spec §8): 300 DPI PNG + vector PDF in results/figures/.

fig1  degree distributions: log-log CCDF with fitted power-law tails
fig2  S/I/R trajectories with 95% bands, one panel per origin group (RQ1)
fig3  R_inf and T80 by origin group, violins + boxes, per credential-channel setting (RQ1)
fig4  R_inf heatmaps over (beta, gamma), one panel per ecosystem regime (RQ2)
fig5  R_inf vs. intervention budget per strategy, one panel per response delay (RQ3)

Colours follow the entity across figures (validated categorical palette, see the
`dataviz` reference palette); lighter hues carry direct labels and markers, and every
plotted value is also in the matching results/metrics CSV (the table view).
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from src.config import FIGURES_DIR, METRICS_DIR  # noqa: E402

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- tokens
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

COMPARTMENT = {"S": SLOTS[0], "I": SLOTS[1], "R": SLOTS[2]}
GROUP = {"hub": SLOTS[0], "bridge": SLOTS[1], "mid": SLOTS[2], "leaf": SLOTS[3]}
GROUP_ORDER = ["hub", "bridge", "mid", "leaf"]
STRATEGY = {  # colour, marker, label
    "hub_patch": (SLOTS[0], "o", "Hub patching"),
    "random_patch": (SLOTS[1], "s", "Random patching"),
    "firebreak_immunize": (SLOTS[2], "D", "Firebreak immunization"),
    "hub_immunize": (SLOTS[3], "^", "Hub immunization"),
    "acquaintance_immunize": (SLOTS[4], "v", "Acquaintance immunization"),
}
REGIME_LABEL = {"status_quo": "Status quo", "strict_lockfile": "Strict lockfile",
                "scripts_disabled": "Scripts disabled", "hardened": "Hardened"}
SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "axes.titleweight": "semibold", "axes.titlecolor": INK, "axes.labelcolor": INK_2,
        "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "axes.axisbelow": True, "lines.linewidth": 1.5, "lines.markersize": 5,
        "legend.frameon": False, "legend.fontsize": 8,
        "pdf.fonttype": 42, "ps.fonttype": 42,  # embed TrueType for journal submission
    })


def save(fig, name: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.pdf", out_dir / f"{name}.png"]
    fig.savefig(paths[0], bbox_inches="tight")
    fig.savefig(paths[1], dpi=300, bbox_inches="tight")
    plt.close(fig)
    return paths


def _ccdf(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(x[x > 0])
    vals, idx = np.unique(x, return_index=True)
    return vals, 1.0 - idx / len(x)


# =========================================================================== fig1
def fig1_degree_distribution(nodes: pd.DataFrame, topology: dict, out_dir: Path, name: str) -> list[Path]:
    """CCDF P(K >= k) of contagion out-degree (dependents) and in-degree (dependencies)."""
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    series = [("out_degree", "powerlaw_out_degree", "Dependents (out-degree)", SLOTS[0]),
              ("in_degree", "powerlaw_in_degree", "Dependencies (in-degree)", SLOTS[1])]
    for col, fit_key, label, color in series:
        k, p = _ccdf(nodes[col].to_numpy())
        fit = topology.get(fit_key, {})
        alpha, xmin = fit.get("alpha"), fit.get("xmin")
        has_fit = bool(alpha and xmin and not math.isnan(alpha))
        ax.plot(k, p, "o", ms=3, mfc=color, mec="none", alpha=0.75,
                label=f"{label}, α = {alpha:.2f} (k ≥ {xmin:g})" if has_fit else label)
        if has_fit:  # CCDF of a power law with exponent alpha has slope 1 - alpha
            p0 = p[np.searchsorted(k, xmin)] if xmin <= k[-1] else p[-1]
            kk = np.geomspace(xmin, k[-1], 50)
            ax.plot(kk, p0 * (kk / xmin) ** (1 - alpha), color=color, lw=1.5)
    ax.set(xscale="log", yscale="log", xlabel="Degree k", ylabel="P(K ≥ k)",
           title="Degree distributions")
    ax.legend(loc="lower left")
    return save(fig, name, out_dir)


# =========================================================================== fig2
def fig2_sir_curves(curves: pd.DataFrame, n_nodes: int, out_dir: Path, name: str,
                    beta_maintainer: float = 0.0, t_max: int | None = None) -> list[Path]:
    """Mean S/I/R share over time with the 95% CI of the mean and the 2.5-97.5% run envelope."""
    data = curves[np.isclose(curves["beta_maintainer"], beta_maintainer)]
    groups = [g for g in GROUP_ORDER if g in set(data["group"])]
    fig, axes = plt.subplots(1, len(groups), figsize=(2.3 * len(groups) + 0.6, 2.8), sharey=True, squeeze=False)
    if t_max is None:  # trim the flat tail: last tick where mean I is still >= 0.1% of N
        alive = data.loc[data["I_mean"] >= 1e-3 * n_nodes, "tick"]
        t_max = int(min(data["tick"].max(), (alive.max() if len(alive) else 50) * 1.1 + 5))
    for ax, group in zip(axes[0], groups):
        d = data[(data["group"] == group) & (data["tick"] <= t_max)]
        for comp, color in COMPARTMENT.items():
            ax.fill_between(d["tick"], d[f"{comp}_p025"] / n_nodes, d[f"{comp}_p975"] / n_nodes,
                            color=color, alpha=0.10, lw=0)
            ax.fill_between(d["tick"], d[f"{comp}_ci_lo"] / n_nodes, d[f"{comp}_ci_hi"] / n_nodes,
                            color=color, alpha=0.30, lw=0)
            ax.plot(d["tick"], d[f"{comp}_mean"] / n_nodes, color=color, label=comp)
        ax.set_title(f"{group.capitalize()} origin")
        ax.set_xlabel("Tick t")
        ax.set_xlim(0, t_max)
    axes[0][0].set_ylabel("Share of packages (log)")
    axes[0][0].set_yscale("log")  # S stays near 1 while I and R span 1/N .. 1
    axes[0][0].set_ylim(0.5 / n_nodes, 1.5)
    handles, _ = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, ["Susceptible", "Infected", "Recovered"], loc="lower center",
               ncol=3, bbox_to_anchor=(0.5, -0.15))
    sub = "" if beta_maintainer == 0 else f", credential channel β_m = {beta_maintainer:g}"
    fig.suptitle(f"SIR trajectories by origin (mean, 95% CI, 2.5–97.5% of runs{sub})",
                 fontsize=10, fontweight="semibold", color=INK, y=1.03)
    return save(fig, name, out_dir)


# =========================================================================== fig3
def _violin_box(ax, values: list[np.ndarray], colors: list[str]) -> None:
    pos = np.arange(1, len(values) + 1)
    keep = [i for i, v in enumerate(values) if len(v) > 1 and np.ptp(v) > 0]
    if keep:
        parts = ax.violinplot([values[i] for i in keep], positions=pos[keep], widths=0.8,
                              showextrema=False, bw_method=0.25)
        for body, i in zip(parts["bodies"], keep):
            body.set(facecolor=colors[i], edgecolor="none", alpha=0.35)
    ax.boxplot([v if len(v) else [np.nan] for v in values], positions=pos, widths=0.18,
               showfliers=False, patch_artist=True,
               boxprops=dict(facecolor=SURFACE, edgecolor=INK_2, lw=0.8),
               medianprops=dict(color=INK, lw=1.2), whiskerprops=dict(color=INK_2, lw=0.8),
               capprops=dict(color=INK_2, lw=0.8))


def fig3_superspreader_comparison(runs: pd.DataFrame, out_dir: Path, name: str) -> list[Path]:
    """Rows: R_inf and T80 (reached runs only); columns: credential-channel settings."""
    bms = sorted(runs["beta_maintainer"].unique())
    groups = [g for g in GROUP_ORDER if g in set(runs["group"])]
    colors = [GROUP[g] for g in groups]
    fig, axes = plt.subplots(2, len(bms), figsize=(2.9 * len(bms) + 0.4, 5.2), sharey="row", squeeze=False)
    for j, bm in enumerate(bms):
        d = runs[np.isclose(runs["beta_maintainer"], bm)]
        r_inf = [d.loc[d["group"] == g, "r_inf"].to_numpy() for g in groups]
        t80 = [d.loc[d["group"] == g, "t80"].dropna().to_numpy() for g in groups]
        _violin_box(axes[0][j], r_inf, colors)
        _violin_box(axes[1][j], t80, colors)
        reached = [d.loc[d["group"] == g, "t80"].notna().mean() for g in groups]
        axes[0][j].set_title("Dependency channel only" if bm == 0 else f"+ credential channel β_m = {bm:g}")
        axes[0][j].set_xticks(range(1, len(groups) + 1), [g.capitalize() for g in groups])
        axes[1][j].set_xticks(range(1, len(groups) + 1),
                              [f"{g.capitalize()}\n{r:.0%}" for g, r in zip(groups, reached)])
        for ax in axes[:, j]:
            ax.grid(axis="x", visible=False)
    axes[0][0].set_ylabel("Final outbreak size R∞")
    axes[0][0].set_ylim(-0.02, 1.02)
    axes[1][0].set_ylabel("Time to 80% of reachable set T₈₀\n(% under group = runs reaching it)")
    fig.suptitle("Outbreak size and speed by patient-zero topology (RQ1)",
                 fontsize=10, fontweight="semibold", color=INK, y=1.01)
    fig.tight_layout()
    return save(fig, name, out_dir)


# =========================================================================== fig4
def fig4_semver_phase_transition(summary: pd.DataFrame, thresholds: pd.DataFrame, out_dir: Path,
                                 name: str, beta_maintainer: float = 0.0) -> list[Path]:
    """Mean R_inf over the (beta, gamma) grid per regime; markers = empirical beta_c."""
    s = summary[np.isclose(summary["beta_maintainer"], beta_maintainer)]
    th = thresholds[np.isclose(thresholds["beta_maintainer"], beta_maintainer)]
    regimes = [r for r in REGIME_LABEL if r in set(s["regime"])]
    betas, gammas = sorted(s["beta"].unique()), sorted(s["gamma"].unique())
    fig, axes = plt.subplots(1, len(regimes), figsize=(2.7 * len(regimes) + 0.8, 3.0), sharey=True, squeeze=False)
    # one colour scale for all panels, fitted to the data so small outbreaks stay readable
    vmax = min(1.0, math.ceil(max(s["r_inf_mean"].max(), 1e-3) * 20) / 20)
    mesh = None
    for ax, regime in zip(axes[0], regimes):
        grid = (s[s["regime"] == regime].pivot_table(index="gamma", columns="beta", values="r_inf_mean")
                .reindex(index=gammas, columns=betas))
        mesh = ax.pcolormesh(np.arange(len(betas) + 1) - 0.5, np.arange(len(gammas) + 1) - 0.5,
                             grid.to_numpy(), cmap=SEQ_CMAP, vmin=0, vmax=vmax, edgecolors=SURFACE, linewidth=1)
        t = th[th["regime"] == regime].set_index("gamma").reindex(gammas)
        bc = t["beta_c"].to_numpy(float)
        xs = np.interp(bc, betas, np.arange(len(betas)), left=np.nan, right=np.nan)
        ok = np.isfinite(xs) & (t["censored"].fillna("").to_numpy() == "")
        ax.plot(xs[ok], np.arange(len(gammas))[ok], "o", ms=5, mfc=INK, mec=SURFACE, mew=1.2,
                label="Empirical β_c (R∞ = 5%)")
        ax.set_title(REGIME_LABEL[regime])
        ax.set_xticks(range(len(betas)), [f"{b:g}" for b in betas], rotation=90)
        ax.set_yticks(range(len(gammas)), [f"{g:g}" for g in gammas])
        ax.set_xlabel("Infection rate β")
        ax.grid(False)
        ax.spines[["left", "bottom"]].set_visible(False)
        ax.tick_params(length=0)
    axes[0][0].set_ylabel("Patching rate γ")
    cbar = fig.colorbar(mesh, ax=axes[0].tolist(), fraction=0.025, pad=0.02)
    cbar.set_label("Mean final outbreak size R∞")
    cbar.outline.set_visible(False)
    handles, labels = axes[0][0].get_legend_handles_labels()
    if handles:
        fig.legend(handles[:1], labels[:1], loc="lower center", bbox_to_anchor=(0.45, -0.18))
    sub = "" if beta_maintainer == 0 else f", credential channel β_m = {beta_maintainer:g}"
    fig.suptitle(f"Phase transition across SemVer / lifecycle-script regimes (RQ2{sub})",
                 fontsize=10, fontweight="semibold", color=INK, y=1.04)
    return save(fig, name, out_dir)


# =========================================================================== fig5
def fig5_firebreak_immunization(summary: pd.DataFrame, out_dir: Path, name: str) -> list[Path]:
    """Mean R_inf (95% bootstrap CI) vs. budget B per strategy; panels = response delays."""
    delays = sorted(summary["delay"].unique()) if "delay" in summary else [None]
    fig, axes = plt.subplots(1, len(delays), figsize=(2.7 * len(delays) + 0.6, 3.1), sharey=True, squeeze=False)
    for ax, delay in zip(axes[0], delays):
        d = summary if delay is None else summary[summary["delay"] == delay]
        none = d[d["strategy"] == "none"]
        if len(none):
            ax.axhline(none["r_inf_mean"].iloc[0], color=MUTED, lw=1.0, zorder=1)
            ax.annotate("No intervention", xy=(0, none["r_inf_mean"].iloc[0]), xycoords=("axes fraction", "data"),
                        xytext=(2, 3), textcoords="offset points", fontsize=7, color=MUTED)
        for strategy, (color, marker, label) in STRATEGY.items():
            g = d[d["strategy"] == strategy].sort_values("budget_frac")
            if g.empty:
                continue
            x = g["budget_frac"] * 100
            ax.fill_between(x, g["r_inf_ci_lo"], g["r_inf_ci_hi"], color=color, alpha=0.18, lw=0)
            ax.plot(x, g["r_inf_mean"], color=color, marker=marker, ms=5, mec=SURFACE, mew=0.8, label=label)
        ax.set_xscale("log")
        ax.set_title("Detection at t = 1" if delay in (None, 1) else f"Detection delay {delay} ticks")
        ax.set_xlabel("Budget B (% of packages per tick)")
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    axes[0][0].set_ylabel("Final outbreak size R∞")
    axes[0][0].set_ylim(bottom=0)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.16))
    fig.suptitle("Interventions against a hub outbreak at matched budget (RQ3; immunization K = treated by hub patching)",
                 fontsize=10, fontweight="semibold", color=INK, y=1.03)
    return save(fig, name, out_dir)


# =========================================================================== all
def make_all_figures(tag: str, metrics_dir: Path = METRICS_DIR, figures_dir: Path = FIGURES_DIR,
                     beta_maintainer: float = 0.0) -> list[Path]:
    """Render every figure whose input tables exist for `tag`; returns written paths."""
    apply_style()
    out_dir = figures_dir / tag
    m = lambda suffix: metrics_dir / f"{tag}_{suffix}"  # noqa: E731
    written: list[Path] = []

    if m("node_metrics.csv").exists() and m("topology_summary.json").exists():
        nodes = pd.read_csv(m("node_metrics.csv"), keep_default_na=False, na_values=[""])
        topo = json.loads(m("topology_summary.json").read_text(encoding="utf-8"))
        written += fig1_degree_distribution(nodes, topo, out_dir, "fig1_degree_distribution")
    if m("rq1_curves.csv").exists():
        meta = json.loads(m("rq1_meta.json").read_text(encoding="utf-8"))
        written += fig2_sir_curves(pd.read_csv(m("rq1_curves.csv")), meta["n_nodes"], out_dir,
                                   "fig2_sir_epidemic_curves", beta_maintainer)
    if m("rq1_runs.csv").exists():
        runs = pd.read_csv(m("rq1_runs.csv"), usecols=["beta_maintainer", "group", "r_inf", "t80"])
        written += fig3_superspreader_comparison(runs, out_dir, "fig3_superspreader_comparison")
    if m("rq2_summary.csv").exists():
        written += fig4_semver_phase_transition(pd.read_csv(m("rq2_summary.csv")),
                                                pd.read_csv(m("rq2_thresholds.csv"), keep_default_na=False,
                                                            na_values=[""]),
                                                out_dir, "fig4_semver_phase_transition", beta_maintainer)
    if m("rq3_summary.csv").exists():
        written += fig5_firebreak_immunization(pd.read_csv(m("rq3_summary.csv")), out_dir,
                                               "fig5_firebreak_immunization")
    log.info("Wrote %d figure files to %s", len(written), out_dir)
    return written
