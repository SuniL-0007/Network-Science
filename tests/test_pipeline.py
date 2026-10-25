"""Milestone 5 tests: figures render from experiment tables, and main.py runs end to end."""

import json

import pytest

import main
from src.visualizer import make_all_figures

FIGURES = ["fig1_degree_distribution", "fig2_sir_epidemic_curves", "fig3_superspreader_comparison",
           "fig4_semver_phase_transition", "fig5_firebreak_immunization"]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("run")
    out = main.main(["--mode", "synthetic", "--nodes", "300", "--seed", "3", "--runs", "3", "--rq2-runs", "2",
                     "--maintainer", "0.05", "--quick", "--data-dir", str(root / "data"),
                     "--results-dir", str(root / "results")])
    return root, out


def test_pipeline_writes_all_stages(pipeline):
    root, out = pipeline
    assert out["tag"] == "synthetic_n300_s3_contagion"
    assert out["snapshot"].exists() and out["graph"].exists()
    metrics = root / "results" / "metrics"
    for k in (1, 2, 3):
        assert (metrics / f"{out['tag']}_rq{k}_summary.csv").exists()
    meta = json.loads((metrics / f"{out['tag']}_rq2_meta.json").read_text(encoding="utf-8"))
    assert meta["config"]["rq2_betas"] == [0.05, 0.2, 1.0]  # --quick grid
    assert meta["config"]["rq1_beta_maintainer"] == [0.0, 0.05]


def test_all_five_figures_pdf_and_png(pipeline):
    root, out = pipeline
    fig_dir = root / "results" / "figures" / out["tag"]
    for name in FIGURES:
        for ext in ("pdf", "png"):
            path = fig_dir / f"{name}.{ext}"
            assert path.exists() and path.stat().st_size > 5_000, path


def test_figures_only_rerender(pipeline):
    root, out = pipeline
    again = main.main(["--figures-only", "--tag", out["tag"], "--results-dir", str(root / "results")])
    assert len(again["figures"]) == 10


def test_missing_tables_render_nothing(tmp_path):
    assert make_all_figures("absent", tmp_path, tmp_path) == []


def test_cli_validation(tmp_path):
    with pytest.raises(SystemExit):
        main.main(["--figures-only"])
    with pytest.raises(SystemExit):
        main.main(["--mode", "snapshot", "--data-dir", str(tmp_path), "--results-dir", str(tmp_path)])
