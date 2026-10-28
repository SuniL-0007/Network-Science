"""Generate every number and table the paper cites from results/metrics/.

Writes paper/generated/numbers.tex (\\newcommand macros) and paper/generated/tab_*.tex
(booktabs tables). Results that are missing, or were produced by smoke runs, render as a
visible [pending] marker so unfinished numbers cannot slip into the text.

Usage: python -m src.paper_numbers
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import METRICS_DIR, PROJECT_ROOT, RAW_DIR
from src.paper_suite import SENSITIVITY_RUNS, SH1, SH2

OUT = PROJECT_ROOT / "paper" / "generated"
PENDING = r"\textbf{[pending]}"
MAIN, SYN = "npm_hi_n10k_contagion", "synthetic_n2000_s42_contagion"
FULL_RUNS = 100

_macros: dict[str, str] = {}


# =========================================================================== helpers
def macro(name: str, value) -> None:
    if not re.fullmatch(r"[A-Za-z]+", name):
        raise ValueError(f"LaTeX macro names must be letters only: {name}")
    if name in _macros:
        raise ValueError(f"duplicate macro {name}: two quantities would share one name")
    _macros[name] = PENDING if value is None else str(value)


def num(x, digits: int = 2) -> str | None:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    if isinstance(x, (int, np.integer)) or float(x).is_integer() and abs(x) >= 100:
        return f"{int(round(x)):,}".replace(",", "{,}")
    return f"{x:.{digits}f}"


def pct(x, digits: int = 0) -> str | None:
    return None if x is None or not math.isfinite(x) else f"{100 * x:.{digits}f}\\%"


def read(tag: str, table: str, full: bool = True, runs: int = FULL_RUNS) -> pd.DataFrame | None:
    """Load <tag>_<table>.csv; None if absent or (for rq tables) not run with `runs` runs."""
    path = METRICS_DIR / f"{tag}_{table}.csv"
    if not path.exists():
        return None
    rq = re.match(r"(rq\w+?)_", table)
    if full and rq:
        meta = METRICS_DIR / f"{tag}_{rq.group(1)}_meta.json"
        if not meta.exists() or json.loads(meta.read_text(encoding="utf-8"))["config"]["n_runs"] != runs:
            return None
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def topo(tag: str) -> dict | None:
    path = METRICS_DIR / f"{tag}_topology_summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_table(name: str, body: str) -> None:
    (OUT / f"{name}.tex").write_text(body, encoding="utf-8")


def ci(row, col: str, digits: int = 2, as_pct: bool = False) -> str:
    f = (lambda v: pct(v, 1)) if as_pct else (lambda v: num(v, digits))
    m, lo, hi = row[f"{col}_mean"], row[f"{col}_ci_lo"], row[f"{col}_ci_hi"]
    if not all(map(math.isfinite, (m, lo, hi))):
        return "--"
    return f"{f(m)} [{f(lo)}, {f(hi)}]"


# =========================================================================== sections
def data_and_topology() -> None:
    for key, tag in (("Main", MAIN), ("Five", "npm_hi_n5k_contagion"), ("Full", "npm_hi_n14660_contagion"),
                     ("Syn", SYN)):
        s = topo(tag)
        if s is None:
            continue
        macro(f"{key}N", num(s["n_nodes"]))
        macro(f"{key}E", num(s["n_edges"]))
        macro(f"{key}MaxReach", num(s["max_transitive_dependents"]))
        macro(f"{key}MeanReach", num(s["mean_transitive_dependents"], 1))
        macro(f"{key}LambdaW", num(s["lambda_max_weighted"]))
        macro(f"{key}TauTheory", num(s["tau_c_theory"], 3) if math.isfinite(s["tau_c_theory"]) else r"$\infty$")
        macro(f"{key}LargestSCC", num(s["largest_scc_size"]))
        macro(f"{key}NontrivialSCC", num(s["n_nontrivial_scc"]))
        macro(f"{key}MaxCore", num(s["max_core"]))
        macro(f"{key}Hooks", pct(s["frac_lifecycle_hook"], 1))
        macro(f"{key}Provenance", pct(s["frac_provenance"], 1))
        mix = s.get("semver_mix", {})
        for t in ("caret", "tilde", "exact", "wildcard"):
            macro(f"{key}Semver{t.capitalize()}", pct(mix.get(t, 0.0), 1))
        for d, k in (("out", "Out"), ("in", "In")):
            fit = s[f"powerlaw_{d}_degree"]
            macro(f"{key}Alpha{k}", num(fit.get("alpha")))
            macro(f"{key}Xmin{k}", num(fit.get("xmin"), 0))
            macro(f"{key}LLRLognormal{k}", num(fit.get("llr_vs_lognormal")))
            macro(f"{key}PLognormal{k}", num(fit.get("p_vs_lognormal"), 3))
        macro(f"{key}AssortOutIn", num(s["assortativity_out_in"], 3))

    full_records = RAW_DIR / "npm_hi_n14660.jsonl"
    s = topo("npm_hi_n14660_contagion")
    if full_records.exists() and s:
        with full_records.open(encoding="utf-8") as fh:
            n_raw = sum(1 for line in fh if line.strip())
        macro("FullRaw", num(n_raw))
        macro("SpamRemoved", num(n_raw - s["n_nodes"]))

    seeds = RAW_DIR / "seeds_high_impact_dependents.txt"
    if seeds.exists():
        n = sum(1 for ln in seeds.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#"))
        macro("NSeeds", num(n))


def calibration_and_validation() -> None:
    cal = METRICS_DIR / f"{MAIN}_calibration.json"
    if cal.exists():
        best = json.loads(cal.read_text(encoding="utf-8"))["best"]
        for w in ("SH1", "SH2"):
            b = best.get(w)
            if b:
                k = "One" if w == "SH1" else "Two"
                macro(f"Cal{k}Tninety", num(b["t90_median"], 1))
                macro(f"Cal{k}Share", pct(b["maint_share_mean"]))
                macro(f"Cal{k}Pmajor", pct(b["p_major"]))
    grid = read(MAIN, "calibration_grid", full=False)
    if grid is not None:
        for w, k in (("SH1", "One"), ("SH2", "Two")):
            g = grid[grid["wave"] == w]
            ok = g[g["loss"] <= g["loss"].min() + 0.1]
            macro(f"Cal{k}BetaRange", f"[{num(ok['beta'].min(), 3)}, {num(ok['beta'].max(), 3)}]")
            macro(f"Cal{k}BetaMRange", f"[{num(ok['beta_maintainer'].min(), 3)}, {num(ok['beta_maintainer'].max(), 3)}]")
            macro(f"Cal{k}SizeRange", f"{num(int(ok['size_median'].min()))}--{num(int(ok['size_median'].max()))}")
    for p, k in ((SH1, "One"), (SH2, "Two")):
        macro(f"Cal{k}Beta", num(p.beta, 2))
        macro(f"Cal{k}BetaM", num(p.beta_maintainer, 2))
        macro(f"Cal{k}Gamma", num(p.gamma, 2))
        macro(f"Cal{k}Cap", num(p.maintainer_publish_cap, 0))
        macro(f"Cal{k}Detect", num(p.recovery_start, 0))

    val = METRICS_DIR / "validation_incidents.csv"
    if val.exists():
        v = pd.read_csv(val).set_index("incident")
        for inc, k in (("shai-hulud-1", "One"), ("shai-hulud-2", "Two")):
            if inc not in v.index:
                continue
            r = v.loc[inc]
            macro(f"Val{k}Listed", num(int(r["n_listed"])))
            macro(f"Val{k}N", num(int(r["n_metadata"])))
            macro(f"Val{k}CoMaint", pct(r["share_co_maintained"]))
            macro(f"Val{k}CoMaintNull", pct(r["null_share_co_maintained"]))
            macro(f"Val{k}DepLinked", pct(r["share_installed_dependency_linked"]))
            macro(f"Val{k}DepLinkedNull", pct(r["null_share_installed_dependency_linked"]))
            macro(f"Val{k}InMain", num(int(r[f"{MAIN}:n_in_graph"])))
            macro(f"Val{k}InFull", num(int(r["npm_hi_n14660_contagion:n_in_graph"])))
        rows = []
        for inc, label in (("shai-hulud-1", "Shai-Hulud 1"), ("shai-hulud-2", "Shai-Hulud 2")):
            if inc in v.index:
                r = v.loc[inc]
                rows.append(f"{label} & {int(r['n_metadata'])} & {pct(r['share_co_maintained'])} & "
                            f"{pct(r['null_share_co_maintained'])} & {pct(r['share_installed_dependency_linked'])} & "
                            f"{pct(r['null_share_installed_dependency_linked'])} & "
                            f"{int(r['npm_hi_n14660_contagion:n_in_graph'])} \\\\")
        write_table("tab_validation", "\n".join([
            r"\begin{tabular}{lrrrrrr}", r"\toprule",
            r" & & \multicolumn{2}{c}{Co-maintained} & \multicolumn{2}{c}{Dependency-linked} & In core \\",
            r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}",
            r"Wave & $n$ & observed & null & observed & null & graph \\", r"\midrule", *rows,
            r"\bottomrule", r"\end{tabular}", ""]))


SCEN_LABEL = {"spec_reference": "Spec reference", "dependency_only": "Dependency only",
              "SH1_calibrated": "SH1-calibrated", "SH2_calibrated": "SH2-calibrated"}
SCEN_KEY = {"spec_reference": "SpecRef", "dependency_only": "DepOnly",
            "SH1_calibrated": "ShOne", "SH2_calibrated": "ShTwo"}
GROUPS = ("hub", "bridge", "mid", "leaf")


def rq1(tag: str = MAIN, prefix: str = "RQOne") -> None:
    s = read(tag, "rq1_summary")
    if s is None:
        return
    rows = []
    for scen in SCEN_LABEL:
        d = s[s["scenario"] == scen].set_index("group")
        if d.empty:
            continue
        cells = [ci(d.loc[g], "r_inf", as_pct=True) + f" ({pct(d.loc[g, 'p_major'])})" if g in d.index else "--"
                 for g in GROUPS]
        rows.append(f"{SCEN_LABEL[scen]} & " + " & ".join(cells) + r" \\")
        k = SCEN_KEY[scen]
        for g in GROUPS:
            if g in d.index:
                macro(f"{prefix}{k}{g.capitalize()}", pct(d.loc[g, "r_inf_mean"], 1))
                macro(f"{prefix}{k}{g.capitalize()}Pmajor", pct(d.loc[g, "p_major"]))
                macro(f"{prefix}{k}{g.capitalize()}Maint", pct(d.loc[g, "maint_share_mean"]))
    write_table("tab_rq1", "\n".join([
        r"\begin{tabular}{lcccc}", r"\toprule",
        r"Scenario & Hub & Bridge & Mid-tier & Leaf \\", r"\midrule", *rows, r"\bottomrule", r"\end{tabular}", ""]))


REGIME_LABEL = {"status_quo": "Status quo", "strict_lockfile": "Strict lockfile",
                "scripts_disabled": "Scripts disabled", "hardened": "Hardened"}


def _threshold_cell(r, col: str) -> str:
    if r["censored"] == "never":
        return "none"
    if r["censored"] == "below_grid":
        return f"$\\leq${num(r[col], 3)}"
    return num(r[col], 3)


def rq2() -> None:
    th = read(MAIN, "rq2_thresholds")
    if th is not None:
        th = th[np.isclose(th["beta_maintainer"], 0.0)]
        gammas = sorted(th["gamma"].unique())
        rows = []
        for reg, label in REGIME_LABEL.items():
            d = th[th["regime"] == reg].set_index("gamma")
            if not d.empty:
                rows.append(f"{label} & " + " & ".join(_threshold_cell(d.loc[g], "beta_c") for g in gammas) + r" \\")
        write_table("tab_rq2", "\n".join([
            r"\begin{tabular}{l" + "c" * len(gammas) + "}", r"\toprule",
            r"Regime & " + " & ".join(f"$\\gamma={num(g)}$" for g in gammas) + r" \\", r"\midrule", *rows,
            r"\bottomrule", r"\end{tabular}", ""]))
        sq = th[(th["regime"] == "status_quo")].set_index("gamma")
        sl = th[(th["regime"] == "strict_lockfile")].set_index("gamma")
        sd = th[(th["regime"] == "scripts_disabled")].set_index("gamma")
        g0 = gammas[0]
        macro("RQTwoGammaLow", num(g0))
        macro("RQTwoBetaSQ", num(sq.loc[g0, "beta_c"], 3))
        macro("RQTwoBetaSL", num(sl.loc[g0, "beta_c"], 3))
        macro("RQTwoBetaSD", num(sd.loc[g0, "beta_c"], 3))
        macro("RQTwoLockFactor", num(sl.loc[g0, "beta_c"] / sq.loc[g0, "beta_c"], 0))
        macro("RQTwoScriptsFactor", num(sd.loc[g0, "beta_c"] / sq.loc[g0, "beta_c"], 0))
        macro("RQTwoTauTheory", num(th["tau_c_theory"].iloc[0], 3))
    full = read(MAIN, "rq2_thresholds")
    if full is not None:
        cred = full[~np.isclose(full["beta_maintainer"], 0.0)]
        macro("RQTwoCredCollapsed", pct((cred["censored"] == "below_grid").mean()))

    t2b = read(MAIN, "rq2b_thresholds")
    if t2b is None:
        macro("RQTwoBDone", None)
        write_table("tab_rq2b", PENDING + "\n")
        return
    macro("RQTwoBDone", "")
    t = t2b.set_index(["regime", "gamma"])["beta_m_c"]
    for reg, k in (("status_quo", "SQ"), ("strict_lockfile", "SL"), ("scripts_disabled", "SD"), ("hardened", "Hard")):
        for g, gk in ((0.1, "Mid"), (0.4, "High")):
            if (reg, g) in t.index:
                macro(f"RQTwoB{k}{gk}", num(t[(reg, g)], 3))
    if ("hardened", 0.1) in t.index and ("status_quo", 0.1) in t.index:
        macro("RQTwoBHardFactor", num(t[("hardened", 0.1)] / t[("status_quo", 0.1)], 0))
    gammas = sorted(t2b["gamma"].unique())
    rows = []
    for reg, label in REGIME_LABEL.items():
        d = t2b[t2b["regime"] == reg].set_index("gamma")
        if not d.empty:
            rows.append(f"{label} & " + " & ".join(_threshold_cell(d.loc[g], "beta_m_c") for g in gammas) + r" \\")
    write_table("tab_rq2b", "\n".join([
        r"\begin{tabular}{l" + "c" * len(gammas) + "}", r"\toprule",
        r"Regime & " + " & ".join(f"$\\gamma={num(g)}$" for g in gammas) + r" \\", r"\midrule", *rows,
        r"\bottomrule", r"\end{tabular}", ""]))


STRAT_LABEL = {"hub_patch": "Hub patching", "random_patch": "Random patching",
               "firebreak_immunize": "Firebreak (betweenness)", "hub_immunize": "Hub immunization",
               "acquaintance_immunize": "Acquaintance"}


def rq3(tag: str = MAIN, budget_frac: float = 0.005) -> None:
    red = read(tag, "rq3_reductions")
    summ = read(tag, "rq3_summary")
    if red is None or summ is None:
        return
    b = red.loc[(red["budget_frac"] - budget_frac).abs().idxmin(), "budget"]
    macro("RQThreeBudget", num(int(b)))
    macro("RQThreeBudgetPct", pct(budget_frac, 1))
    r = red[red["budget"] == b]
    delays = sorted(r["delay"].unique())
    rows = []
    for st, label in STRAT_LABEL.items():
        d = r[r["strategy"] == st].set_index("delay")
        if not d.empty:
            rows.append(f"{label} & " + " & ".join(pct(d.loc[x, "delta_r_inf"]) for x in delays) + r" \\")
    none = summ[summ["strategy"] == "none"].set_index("delay")["r_inf_mean"]
    rows.append(r"\midrule")
    rows.append(r"No intervention $R_\infty$ & " + " & ".join(pct(none.get(x, np.nan)) for x in delays) + r" \\")
    write_table("tab_rq3", "\n".join([
        r"\begin{tabular}{l" + "c" * len(delays) + "}", r"\toprule",
        r"Strategy & " + " & ".join(f"{x}\\,h" for x in delays) + r" \\", r"\midrule", *rows,
        r"\bottomrule", r"\end{tabular}", ""]))
    for x in delays:
        d = r[r["delay"] == x].set_index("strategy")["delta_r_inf"]
        word = {1: "One", 6: "Six", 12: "Twelve", 24: "TwentyFour", 48: "FortyEight"}.get(int(x))
        if word:
            for st in STRAT_LABEL:
                if st in d.index:
                    k = re.sub(r"[^A-Za-z]", "", STRAT_LABEL[st].title())
                    macro(f"RQThree{k}{word}", pct(d[st]))
            macro(f"RQThreeNone{word}", pct(none.get(x, np.nan)))


def rq3_budget_crossover(tag: str = MAIN) -> None:
    red = read(tag, "rq3_reductions")
    if red is None:
        return
    n = topo(tag)["n_nodes"]
    x = red[red["delay"] == 24].pivot_table(index="budget", columns="strategy", values="delta_r_inf")
    k = red[(red["delay"] == 24) & (red["strategy"] == "hub_immunize")].set_index("budget")["k_immunized"]
    bmax = x.index.max()
    macro("RQThreeMaxBudget", num(int(bmax)))
    macro("RQThreeMaxBudgetPct", pct(bmax / n, 1))
    macro("RQThreeMaxK", num(int(k[bmax])))
    macro("RQThreeHubImmMaxBudget", pct(x.loc[bmax, "hub_immunize"]))
    macro("RQThreeFirebreakMaxBudget", pct(x.loc[bmax, "firebreak_immunize"]))
    b50 = k.index[(k.index.to_series() - 50).abs().argmin()]
    macro("RQThreeKAtBudget", num(int(k[b50])))
    macro("RQThreeKAtBudgetPct", pct(k[b50] / n, 1))
    wins = [b for b in x.index if x.loc[b, "hub_immunize"] > x.loc[b, "firebreak_immunize"]]
    macro("RQThreeDegreeWinsUpTo", pct(max(wins) / n, 1) if wins else None)


def robustness() -> None:
    # synthetic ensemble: hub/leaf contrast and RQ3 ranking per seed (SH1 scenario)
    hub_leaf, ranks = [], []
    for s in (1, 2, 3, 4, 5, 42):
        t = f"synthetic_n2000_s{s}_contagion"
        rs = read(t, "rq1_summary")
        if rs is not None:
            d = rs[rs["scenario"] == "SH1_calibrated"].set_index("group")["r_inf_mean"]
            hub_leaf.append((d.get("hub", np.nan), d.get("leaf", np.nan)))
        rr = read(t, "rq3_reductions")
        if rr is not None:
            x = rr[(rr["delay"] == 24) & (rr["budget"] == rr["budget"].max())]
            if len(x):
                ranks.append(x.sort_values("delta_r_inf", ascending=False)["strategy"].iloc[0])
    if hub_leaf:
        a = np.array(hub_leaf)
        macro("SynSeeds", num(len(a)))
        macro("SynHubMean", pct(np.nanmean(a[:, 0]), 1))
        macro("SynHubSD", pct(np.nanstd(a[:, 0]), 1))
        macro("SynLeafMean", pct(np.nanmean(a[:, 1]), 1))
        macro("SynLeafSD", pct(np.nanstd(a[:, 1]), 1))
    if ranks:
        top = pd.Series(ranks).value_counts()
        macro("SynRQThreeBest", STRAT_LABEL.get(top.index[0], top.index[0]))
        macro("SynRQThreeBestCount", f"{top.iloc[0]}/{len(ranks)}")

    # sample sizes and null models: SH1 hub and leaf R_inf
    rows = []
    for tag, label in (("npm_hi_n5k_contagion", "npm 5k"), (MAIN, "npm 10k (main)"),
                       ("npm_hi_n14660_contagion", "npm full closure"),
                       *[(f"{MAIN}_null{k}", f"null model {k}") for k in range(5)]):
        rs = read(tag, "rq1_summary")
        rr = read(tag, "rq3_reductions")
        if rs is None:
            rows.append(f"{label} & \\multicolumn{{4}}{{c}}{{{PENDING}}} \\\\")
            continue
        d = rs[rs["scenario"] == "SH1_calibrated"].set_index("group")
        best = "--"
        if rr is not None:
            x = rr[(rr["delay"] == 24) & (rr["budget"] == rr["budget"].max())]
            if len(x):
                best = STRAT_LABEL[x.sort_values("delta_r_inf", ascending=False)["strategy"].iloc[0]]
        dep = rs[rs["scenario"] == "dependency_only"].set_index("group")
        rows.append(f"{label} & {pct(dep.loc['hub', 'r_inf_mean'], 1)} & {pct(d.loc['hub', 'r_inf_mean'], 1)} & "
                    f"{pct(d.loc['leaf', 'r_inf_mean'], 1)} & {best} \\\\")
    nulls = [read(f"{MAIN}_null{k}", "rq1_summary") for k in range(5)]
    nulls = [n for n in nulls if n is not None]
    if nulls:
        dep = [n[(n["scenario"] == "dependency_only") & (n["group"] == "hub")]["r_inf_mean"].iloc[0] for n in nulls]
        leaf = [n[(n["scenario"] == "SH1_calibrated") & (n["group"] == "leaf")]["r_inf_mean"].iloc[0] for n in nulls]
        macro("NullCount", num(len(nulls)))
        macro("NullDepHubMin", pct(min(dep), 1))
        macro("NullDepHubMax", pct(max(dep), 1))
        macro("NullLeafMin", pct(min(leaf), 0))
        macro("NullLeafMax", pct(max(leaf), 0))
    sizes = {}
    for tag, key in (("npm_hi_n5k_contagion", "Five"), (MAIN, "Main"), ("npm_hi_n14660_contagion", "Full")):
        rs = read(tag, "rq1_summary")
        if rs is not None:
            sizes[key] = rs[(rs["scenario"] == "SH1_calibrated") & (rs["group"] == "leaf")]["r_inf_mean"].iloc[0]
    for key, v in sizes.items():
        macro(f"Size{key}LeafShOne", pct(v, 1))
    write_table("tab_robustness", "\n".join([
        r"\begin{tabular}{lcccl}", r"\toprule",
        r" & Hub $R_\infty$ & Hub $R_\infty$ & Leaf $R_\infty$ & Best RQ3 strategy \\",
        r"Graph & (dep.\ only) & (SH1) & (SH1) & (24\,h, max.\ budget) \\", r"\midrule", *rows,
        r"\bottomrule", r"\end{tabular}", ""]))

    # sensitivity around SH1
    sens = []
    for b in (0.01, 0.02, 0.05):
        for g in (0.05, 0.1, 0.2):
            t = f"{MAIN}_sens_b{b:g}_g{g:g}"
            rs = read(t, "rq1_summary", runs=SENSITIVITY_RUNS)
            rr = read(t, "rq3_reductions", runs=SENSITIVITY_RUNS)
            if rs is None or rr is None:
                sens.append(None)
                continue
            d = rs.set_index("group")["r_inf_mean"]
            x = rr[(rr["delay"] == 24) & (rr["budget"] == rr["budget"].max())]
            mid = rr[(rr["delay"] == 24) & (rr["budget"] == 50)].set_index("strategy")["delta_r_inf"]
            sens.append((b, g, d["hub"] / max(d["leaf"], 1e-9),
                         x.sort_values("delta_r_inf", ascending=False)["strategy"].iloc[0],
                         mid["hub_immunize"] > mid["firebreak_immunize"],
                         mid["hub_immunize"] > mid["hub_patch"]))
    if all(sens):
        proactive = sum(s[3].endswith("immunize") for s in sens)
        macro("SensProactiveBest", f"{proactive}/{len(sens)}")
        macro("SensHubLeafMin", num(min(s[2] for s in sens), 1))
        macro("SensHubLeafMax", num(max(s[2] for s in sens), 1))
        macro("SensDegreeBeatsFirebreak", f"{sum(s[4] for s in sens)}/{len(sens)}")
        macro("SensImmBeatsPatch", f"{sum(s[5] for s in sens)}/{len(sens)}")
    else:
        macro("SensProactiveBest", None)
        macro("SensHubLeafMin", None)
        macro("SensHubLeafMax", None)
        macro("SensDegreeBeatsFirebreak", None)
        macro("SensImmBeatsPatch", None)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data_and_topology()
    calibration_and_validation()
    rq1()
    rq2()
    rq3()
    rq3_budget_crossover()
    robustness()
    lines = ["% Generated by `python -m src.paper_numbers` -- do not edit by hand.",
             r"\providecommand{\pending}{" + PENDING + "}"]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(_macros.items())]
    (OUT / "numbers.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    n_pending = sum(v == PENDING for v in _macros.values())
    print(f"wrote {len(_macros)} macros ({n_pending} pending) and tables to {OUT}")


if __name__ == "__main__":
    main()
