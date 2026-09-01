"""Tests for unpack + parse + analyze stages."""
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


def test_unpack_fixture_a(tmp_path):
    from pfx2gas.unpack import unpack

    app = unpack(FIXTURES / "fixtureA.msapp")
    assert app.app_name == "FixtureA"
    assert set(app.screens) == {"Screen1", "Screen2"}
    assert "App" in app.app_yaml


def test_unpack_rejects_non_zip(tmp_path):
    from pfx2gas.unpack import UnpackError, unpack

    bad = tmp_path / "bad.msapp"
    bad.write_text("definitely not a zip")
    with pytest.raises(UnpackError):
        unpack(bad)


def test_unpack_missing_file():
    from pfx2gas.unpack import UnpackError, unpack

    with pytest.raises(UnpackError):
        unpack("/nonexistent/foo.msapp")


def test_parse_fixture_a_ir():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse

    ir = parse(unpack(FIXTURES / "fixtureA.msapp"))
    assert ir.name == "FixtureA"
    assert [s.name for s in ir.screens] == ["Screen1", "Screen2"]
    screen1 = ir.screens[0]
    names = [c.name for c in screen1.controls]
    assert names == ["Label1", "TextInput1", "Button1"]
    button = screen1.controls[2]
    assert button.type == "Button"
    assert button.properties["OnSelect"].raw == 'Set(counter, counter + 1); Navigate(Screen2)'
    assert button.properties["OnSelect"].kind == "behavior"
    assert button.properties["Text"].kind == "value"


def test_parse_app_onstart():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse

    ir = parse(unpack(FIXTURES / "fixtureA.msapp"))
    assert ir.on_start is not None
    assert "Set(greeting" in ir.on_start.raw


def test_analyze_fixture_a():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    ir = analyze(parse(unpack(FIXTURES / "fixtureA.msapp")))
    assert set(ir.global_vars) >= {"greeting", "counter", "visitedScreen1"}
    # all fixture-A formulas should transpile without stubs
    stubs = [e for e in ir.support_matrix if e.status in {"stubbed", "unmapped"}]
    assert stubs == []
    button = ir.screens[0].controls[2]
    assert button.properties["OnSelect"].js is not None
    assert "go('Screen2')" in button.properties["OnSelect"].js


def test_analyze_fixture_b_data_source():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    ir = analyze(parse(unpack(FIXTURES / "fixtureB.msapp")))
    assert ir.data_sources, "Tasks data source should be discovered"
    ds = ir.data_sources[0]
    assert ds.name == "Tasks"
    field_names = {f.name for f in ds.fields}
    assert "Name" in field_names and "Amount" in field_names and "Status" in field_names
    amount = next(f for f in ds.fields if f.name == "Amount")
    assert amount.type == "number"


def test_analyze_fixture_c_records_unmapped():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    ir = analyze(parse(unpack(FIXTURES / "fixtureC.msapp")))
    unmapped = [e for e in ir.support_matrix if e.status == "unmapped"]
    assert any("TimeZoneOffset" in e.subject for e in unmapped)
