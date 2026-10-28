"""Static checks for the LaTeX sources (no TeX installation needed).

Verifies that every \\cite key exists in docs/references.bib, every custom macro used is defined
(generated numbers or main.tex), every \\input and \\includegraphics target exists, every \\ref /
\\cref has a matching \\label, and reports pending numbers.

Usage: python paper/check_paper.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PAPER = Path(__file__).resolve().parent
ROOT = PAPER.parent
BUILTIN = set("""
begin end section subsection paragraph label ref cref Cref cite citep citet input includegraphics caption
centering toprule midrule bottomrule cmidrule multicolumn emph textbf texttt textit item small url today
maketitle title author date documentclass usepackage usetikzlibrary graphicspath newcommand
providecommand bibliographystyle bibliography leq geq times min max top pm infty lambda tau beta gamma
alpha in le ge quad mathrm text cdot cdots dots footnote linewidth hline node draw scope fill path
captionsetup label midway etc hspace vspace noindent newline textsc mathbf left right big Big bigl bigr
frac sum log ldots rightarrow to ell infty Rinf pkg sigma mu delta Delta prime ast pending
""".split())


def main() -> int:
    tex_files = [PAPER / "main.tex", *sorted((PAPER / "sections").glob("*.tex"))]
    text = {p: p.read_text(encoding="utf-8") for p in tex_files}
    alltext = "\n".join(text.values())
    problems: list[str] = []

    bib = (ROOT / "docs" / "references.bib").read_text(encoding="utf-8")
    keys = set(re.findall(r"@\w+\{([^,\s]+),", bib))
    cited = {k.strip() for grp in re.findall(r"\\cite[pt]?\{([^}]*)\}", alltext) for k in grp.split(",")}
    problems += [f"missing bib key: {k}" for k in sorted(cited - keys)]

    numbers = (PAPER / "generated" / "numbers.tex").read_text(encoding="utf-8")
    defined = set(re.findall(r"\\(?:newcommand|providecommand)\{\\(\w+)\}", numbers + alltext))
    used = set(re.findall(r"\\([A-Za-z]+)", alltext))
    candidates = {m for m in used if m not in BUILTIN and m[0].isupper()}
    problems += [f"undefined macro: \\{m}" for m in sorted(candidates - defined)]

    for target in re.findall(r"\\input\{([^}]+)\}", alltext):
        p = PAPER / (target if target.endswith(".tex") else target + ".tex")
        if not p.exists():
            problems.append(f"missing \\input: {target}")
    fig_dirs = [ROOT / "results" / "figures" / "npm_hi_n10k_contagion", ROOT / "results" / "figures"]
    for fig in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", alltext):
        if not any((d / fig).exists() for d in fig_dirs):
            problems.append(f"missing figure: {fig}")

    labels = set(re.findall(r"\\label\{([^}]+)\}", alltext))
    refs = {r.strip() for grp in re.findall(r"\\[cC]?ref\{([^}]+)\}", alltext) for r in grp.split(",")}
    problems += [f"undefined reference: {r}" for r in sorted(refs - labels)]

    pending = sorted(m for m in re.findall(r"\\newcommand\{\\(\w+)\}\{\\textbf\{\[pending\]\}\}", numbers)
                     if m in used)
    gen_pending = [p.name for p in (PAPER / "generated").glob("tab_*.tex")
                   if "[pending]" in p.read_text(encoding="utf-8")]

    print(f"{len(tex_files)} files, {len(cited)} citations, {len(candidates & defined)} number macros used")
    for p in problems:
        print("  PROBLEM:", p)
    if pending or gen_pending:
        print("  pending numbers:", ", ".join(pending + gen_pending))
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
