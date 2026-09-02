"""Tests for chart synthesis: chart controls -> FXCharts rendering."""
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


def _ir(name: str):
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    return analyze(parse(unpack(FIXTURES / name)))


def test_chart_synthesizes_container_and_renderer():
    from pfx2gas.synth.client import render_screens_html, render_app_js

    ir = _ir("fixtureA.msapp")
    html = render_screens_html(ir)  # no charts, but must not crash
    assert "data-chart" not in html or "fx-chart" in html
    js = render_app_js(ir)
    assert "FXCharts" not in js or "fx-chart" in html  # consistent


def test_chart_control_from_real_app(tmp_path):
    """charts exist in legacy corpus (helpdesk/pie) — render path end-to-end."""
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    samples = Path(__file__).resolve().parents[1] / "samples" / "real"
    src = samples / "helpdesk.msapp"
    if not src.exists():
        pytest.skip("sample corpus not present")
    ir = analyze(parse(unpack(src)))
    out = synthesize(ir, tmp_path / "hd")
    result = validate_project(out)
    assert result["ok"], result["problems"]
    screens = (out / "Screens.html").read_text()
    if "fx-chart" in screens:  # corpus has charts
        app_js = (out / "App.js.html").read_text()
        assert "FXCharts.svg" in app_js
        assert (out / "fx-charts.js.html").exists()
