"""Build paper/paper.docx from the LaTeX sources.

Usage:  python paper/build_docx.py
Needs:  pandoc (on PATH, via $PANDOC, or from `pip install pypandoc_binary`),
        python-docx, matplotlib.

Steps: copy the LaTeX into a temp dir, rewrite the parts pandoc cannot read
(cleveref, PDF figures, the TikZ diagram, the title block), convert with an
academic reference style and IEEE citations, then finish the layout with
python-docx (author block, booktabs-style tables, caption labels, centring).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

PAPER = Path(__file__).resolve().parent
ROOT = PAPER.parent
FIGS = ROOT / "results" / "figures" / "npm_hi_n10k_contagion"
OUT = PAPER / "paper.docx"

TITLE = ("Super-Spreaders, Firebreaks and Stolen Tokens: SIR Modelling of "
         "Self-Propagating Worms in the npm Dependency Network")
AUTHORS = "Sunil J,  Varun Sithaarth"
AFFILIATION = [
    "Department of Applied Mathematics and Computational Sciences",
    "PSG College of Technology, Peelamedu, Coimbatore 641004, Tamil Nadu, India",
]

FONT = "Times New Roman"
MONO = "Consolas"
BLACK = RGBColor(0, 0, 0)


# --------------------------------------------------------------------------
# pandoc
# --------------------------------------------------------------------------
def pandoc_exe() -> str:
    if os.environ.get("PANDOC"):
        return os.environ["PANDOC"]
    if shutil.which("pandoc"):
        return "pandoc"
    try:
        import pypandoc  # type: ignore
        return pypandoc.get_pandoc_path()
    except Exception:
        sys.exit("pandoc not found: install it or `pip install pypandoc_binary`")


# --------------------------------------------------------------------------
# LaTeX preprocessing
# --------------------------------------------------------------------------
PREFIX = {"fig": "Figure", "tab": "Table", "sec": "Section", "eq": "Eq."}


def _cref(match: re.Match) -> str:
    parts = []
    for label in match.group(1).split(","):
        label = label.strip()
        kind = label.split(":", 1)[0]
        ref = f"(\\ref{{{label}}})" if kind == "eq" else f"\\ref{{{label}}}"
        parts.append(f"{PREFIX.get(kind, '')}~{ref}")
    return " and ".join(parts)


def preprocess(tex: str) -> str:
    tex = re.sub(r"\\[cC]ref\{([^}]*)\}", _cref, tex)
    # \paragraph is a run-in heading in LaTeX; keep it inline (and unnumbered).
    tex = re.sub(r"\\paragraph\{([^}]*)\}\s*", r"\\textbf{\1} ", tex)
    tex = re.sub(r"(\\includegraphics(?:\[[^\]]*\])?\{[^}]*)\.pdf\}", r"\1.png}", tex)
    tex = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}",
                 r"\\includegraphics[width=0.75\\linewidth]{fig0_model.png}",
                 tex, flags=re.S)
    return tex


def draw_model_figure(path: Path) -> None:
    """Matplotlib redraw of the TikZ two-channel diagram in sections/model.tex."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

    plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm"})
    fig, ax = plt.subplots(figsize=(6.4, 2.9), dpi=250)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.3)
    ax.axis("off")

    def box(x, y, text, fill="white"):
        ax.add_patch(FancyBboxPatch((x - 0.45, y - 0.22), 0.9, 0.44,
                                    boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=fill, ec="black", lw=1))
        ax.text(x, y, text, ha="center", va="center", fontsize=12)

    blue = "#1f3f8f"
    # maintainer group
    ax.add_patch(FancyBboxPatch((4.55, 0.2), 4.9, 3.35,
                                boxstyle="round,pad=0.02,rounding_size=0.15",
                                fc="none", ec="0.6", lw=1, ls="--"))
    ax.text(7.0, 3.75, r"maintainer $m$'s packages", ha="center", fontsize=9, color="0.4")

    box(1.0, 2.5, r"$v$", fill="#fcd9b6")
    box(5.3, 2.5, r"$u$")
    box(5.3, 1.1, r"$w_1$")
    box(6.6, 1.1, r"$w_2$")
    ax.text(7.45, 1.1, r"$\cdots$", ha="center", va="center", fontsize=13)
    ax.add_patch(Circle((8.3, 2.4), 0.3, fc="white", ec="black", lw=1))
    ax.text(8.3, 2.4, r"$m$", ha="center", va="center", fontsize=12)

    def arrow(p, q, dashed=False, rad=0.0, color="black"):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12,
                                     lw=1.5, color=color, ls="--" if dashed else "-",
                                     connectionstyle=f"arc3,rad={rad}",
                                     shrinkA=0, shrinkB=0))

    arrow((1.47, 2.5), (4.83, 2.5))
    ax.text(3.15, 2.7, r"$\beta\, w_{\mathrm{semver}}\, w_{\mathrm{exec}}(u)$",
            ha="center", va="bottom", fontsize=10)
    arrow((5.77, 2.62), (7.99, 2.55), dashed=True, rad=-0.35, color=blue)
    ax.text(6.9, 3.2, r"token, $\beta_m$", ha="center", fontsize=9, color=blue)
    arrow((8.05, 2.22), (5.6, 1.34), dashed=True, color=blue)
    arrow((8.12, 2.15), (6.85, 1.34), dashed=True, color=blue)
    ax.text(6.55, 0.42, r"republish $\leq$ cap packages of $m$", ha="center", fontsize=9)

    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# --------------------------------------------------------------------------
# Reference document (styles, page setup, footer)
# --------------------------------------------------------------------------
def _style_font(style, size=None, bold=None, italic=None, font=FONT, color=BLACK):
    rpr = style.element.get_or_add_rPr()
    for old in rpr.findall(qn("w:rFonts")):
        rpr.remove(old)
    fonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), font)
    rpr.insert(0, fonts)
    f = style.font
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color is not None:
        f.color.rgb = color


def _para(style, before=0, after=6, line=1.15, align=None, keep_next=None,
          left=None, right=None, first=None):
    pf = style.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if align is not None:
        pf.alignment = align
    if keep_next is not None:
        pf.keep_with_next = keep_next
    if left is not None:
        pf.left_indent = Cm(left)
    if right is not None:
        pf.right_indent = Cm(right)
    if first is not None:
        pf.first_line_indent = Cm(first)


def add_page_number(section) -> None:
    p = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
    run.font.name = FONT
    run.font.size = Pt(10)


def build_reference(pandoc: str, path: Path) -> None:
    raw = path.with_name("ref-default.docx")
    with open(raw, "wb") as fh:
        subprocess.run([pandoc, "--print-default-data-file", "reference.docx"],
                       stdout=fh, check=True)
    doc = Document(raw)
    st = doc.styles
    J, C = WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.CENTER

    for name in ("Normal", "Body Text", "First Paragraph", "Compact", "Block Text",
                 "Footnote Text", "Bibliography"):
        if name in st:
            _style_font(st[name], size=11)
    for name in ("Body Text", "First Paragraph"):
        _para(st[name], after=6, line=1.15, align=J)
    _para(st["Compact"], after=3, line=1.15, align=J)
    _para(st["Bibliography"], after=3, line=1.0, left=0.75, first=-0.75)
    _style_font(st["Bibliography"], size=10)

    _style_font(st["Title"], size=17, bold=True)
    _para(st["Title"], before=0, after=10, line=1.1, align=C)
    for name in ("Subtitle", "Author", "Date"):
        if name in st:
            _style_font(st[name], size=11)
            _para(st[name], after=2, align=C)
    _style_font(st["Abstract"], size=10)
    _para(st["Abstract"], after=4, line=1.1, align=J, left=1.0, right=1.0)
    if "Abstract Title" in st:
        _style_font(st["Abstract Title"], size=11, bold=True)
        _para(st["Abstract Title"], before=12, after=4, align=C, keep_next=True)

    for name, size, italic, before in (("Heading 1", 13, False, 14), ("Heading 2", 11.5, False, 10),
                                       ("Heading 3", 11, True, 8), ("Heading 4", 11, True, 6)):
        _style_font(st[name], size=size, bold=True, italic=italic)
        _para(st[name], before=before, after=4, line=1.0, keep_next=True)

    for name in ("Caption", "Table Caption", "Image Caption"):
        if name in st:
            _style_font(st[name], size=9.5, italic=False)
            _para(st[name], before=4, after=10, line=1.0, align=J, left=0.5, right=0.5)
    _para(st["Table Caption"], before=10, after=4, line=1.0, align=J, left=0.5, right=0.5,
          keep_next=True)
    for name in ("Figure", "Captioned Figure"):
        if name in st:
            _para(st[name], before=8, after=2, line=1.0, align=C, keep_next=True)
    if "Verbatim Char" in st:
        _style_font(st["Verbatim Char"], size=10, font=MONO)
    if "Hyperlink" in st:
        st["Hyperlink"].font.color.rgb = RGBColor(0x1F, 0x3F, 0x8F)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)  # A4
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2.5))
    add_page_number(sec)
    doc.save(path)


# --------------------------------------------------------------------------
# Post-processing of pandoc's output
# --------------------------------------------------------------------------
def _border(parent, edge, size):
    el = OxmlElement(f"w:{edge}")
    el.set(qn("w:val"), "single" if size else "nil")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), "000000")
    parent.append(el)


def style_table(table) -> None:
    tbl_pr = table._tbl.tblPr
    for tag in ("w:tblStyle", "w:tblBorders", "w:tblW", "w:tblLayout"):
        for old in tbl_pr.findall(qn(tag)):
            tbl_pr.remove(old)
    width = OxmlElement("w:tblW")
    width.set(qn("w:type"), "auto")
    width.set(qn("w:w"), "0")
    tbl_pr.append(width)
    borders = OxmlElement("w:tblBorders")
    for edge, size in (("top", 12), ("left", 0), ("bottom", 12), ("right", 0),
                       ("insideH", 0), ("insideV", 0)):
        _border(borders, edge, size)
    tbl_pr.append(borders)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for r, row in enumerate(table.rows):
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            mar = OxmlElement("w:tcMar")
            for side in ("left", "right"):
                m = OxmlElement(f"w:{side}")
                m.set(qn("w:w"), "80")
                m.set(qn("w:type"), "dxa")
                mar.append(m)
            tc_pr.append(mar)
            if r == 0:
                cb = OxmlElement("w:tcBorders")
                _border(cb, "bottom", 6)
                tc_pr.append(cb)
            for p in cell.paragraphs:
                pf = p.paragraph_format
                pf.space_before, pf.space_after, pf.line_spacing = Pt(1.5), Pt(1.5), 1.0
                pf.first_line_indent = None
                pf.keep_with_next = r < len(table.rows) - 1  # don't split tables
                for run in p.runs:
                    run.font.size = Pt(9)
                    if r == 0:
                        run.font.bold = True
        if r == 0:
            tr_pr = row._tr.get_or_add_trPr()
            hdr = OxmlElement("w:tblHeader")
            tr_pr.append(hdr)


def label_caption(paragraph, label: str) -> None:
    first = paragraph.runs[0] if paragraph.runs else None
    run = paragraph.add_run(label + " ")
    run.font.bold = True
    if first is not None:
        first._r.addprevious(run._r)


def postprocess(path: Path) -> None:
    doc = Document(path)
    body = doc.paragraphs

    # Title block: authors and affiliation under the title.
    title = next(p for p in body if p.style.name == "Title")
    anchor = title
    for i, (text, size, bold, italic) in enumerate(
            [(AUTHORS, 12, True, False)] + [(a, 10.5, False, True) for a in AFFILIATION]):
        p = doc.add_paragraph(style="Author")
        r = p.add_run(text)
        r.font.size, r.font.bold, r.font.italic = Pt(size), bold, italic
        p.paragraph_format.space_after = Pt(8 if i == 0 else 1)
        anchor._p.addnext(p._p)
        anchor = p

    fig_n = tab_n = 0
    for p in doc.paragraphs:
        name = p.style.name
        if name == "Image Caption" and p.text.strip():
            fig_n += 1
            label_caption(p, f"Figure {fig_n}.")
        elif name == "Table Caption" and p.text.strip():
            tab_n += 1
            label_caption(p, f"Table {tab_n}.")
        if p._p.findall(".//" + qn("w:drawing")):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.keep_with_next = True

    for table in doc.tables:
        style_table(table)

    doc.save(path)
    print(f"figures: {fig_n}, tables: {tab_n}")


# --------------------------------------------------------------------------
def main() -> None:
    pandoc = pandoc_exe()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        work = tmp / "paper"
        shutil.copytree(PAPER, work, ignore=shutil.ignore_patterns("*.docx", "__pycache__"))
        for tex in list(work.glob("sections/*.tex")) + [work / "main.tex"]:
            tex.write_text(preprocess(tex.read_text(encoding="utf-8")), encoding="utf-8")
        main_tex = work / "main.tex"
        text = main_tex.read_text(encoding="utf-8")
        text = re.sub(r"\\title\{.*?\}\s*\\author\{.*?\}\}\s*\\date\{[^}]*\}",
                      lambda _: f"\\title{{{TITLE}}}", text, flags=re.S)
        main_tex.write_text(text, encoding="utf-8")
        draw_model_figure(work / "fig0_model.png")

        ref = tmp / "reference.docx"
        build_reference(pandoc, ref)
        cmd = [pandoc, "main.tex", "-f", "latex", "-t", "docx",
               "--reference-doc", str(ref), "--number-sections",
               "--citeproc", "--bibliography", str(ROOT / "docs" / "references.bib"),
               "--csl", str(PAPER / "ieee.csl"),
               "-M", "reference-section-title=References",
               "--resource-path", os.pathsep.join([".", str(FIGS)]),
               "-o", str(OUT)]
        subprocess.run(cmd, cwd=work, check=True)
    postprocess(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
