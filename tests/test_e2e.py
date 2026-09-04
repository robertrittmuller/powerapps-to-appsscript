"""End-to-end: fixture .msapp -> converted project + report, then validate."""
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


def test_cli_convert_fixture_a(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "pfx2gas", "convert", str(FIXTURES / "fixtureA.msapp"),
         "-o", str(tmp_path / "FixtureA"), "--no-llm"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    out_dir = tmp_path / "FixtureA"
    assert (out_dir / "Code.gs").exists()
    assert (out_dir / "conversion-report.md").exists()
    report = (out_dir / "conversion-report.md").read_text()
    assert "Conversion report" in report
    assert "Manual follow-ups" in report
    assert "None — every formula was rule-translated and wired by synthesis." in report


def test_cli_convert_fixture_b(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "pfx2gas", "convert", str(FIXTURES / "fixtureB.msapp"),
         "-o", str(tmp_path / "FixtureB"), "--no-llm"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    out_dir = tmp_path / "FixtureB"
    report = (out_dir / "conversion-report.md").read_text()
    assert "Tasks" in report
    # gallery formulas produce data-layer wiring
    assert "refreshData('Tasks')" in (out_dir / "App.js.html").read_text()


def test_cli_validate_passes(tmp_path):
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    ir = analyze(parse(unpack(FIXTURES / "fixtureA.msapp")))
    out = synthesize(ir, tmp_path / "V")
    result = validate_project(out)
    assert result["ok"], result["problems"]


def test_main_entry_point_exists():
    from pfx2gas.cli import main
    assert callable(main)
