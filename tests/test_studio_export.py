"""Regression tests for real-world Studio-export formats (fixture D)."""
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


@pytest.fixture(scope="module")
def ir_d():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse

    return parse(unpack(FIXTURES / "fixtureD.msapp"))


def test_unpack_studio_export_shape():
    from pfx2gas.unpack import unpack

    app = unpack(FIXTURES / "fixtureD.msapp")
    assert app.app_name == "FixtureD Studio Export"
    assert list(app.screens) == ["HomeScreen"]
    assert any("_EditorState" in w for w in app.warnings)


def test_versioned_control_types_normalized(ir_d):
    icon = ir_d.screens[0].controls[0]
    assert icon.type == "Icon"  # not Classic/Icon@2.5.0
    text = ir_d.screens[0].controls[1]
    assert text.type == "TextInput"


def test_empty_formula_parses(ir_d):
    text = ir_d.screens[0].controls[1]
    assert text.properties["Default"].raw == ""


def test_percent_literals_and_comments(ir_d):
    from pfx2gas.analyze import analyze

    ir = analyze(ir_d)
    icon = ir.screens[0].controls[0]
    x_js = icon.properties["X"].js
    assert x_js is not None and "FX.unsupported" not in x_js
    assert "(0.2)" in x_js  # -20% -> -(0.2) fraction passed to ColorFade


def test_rgba_colorfade_font_enum(ir_d):
    from pfx2gas.analyze import analyze

    ir = analyze(ir_d)
    icon = ir.screens[0].controls[0]
    fill = icon.properties["Color"].js
    assert fill is not None and "FX.unsupported" not in fill
    assert "'ForestGreen'" in fill  # enum member emitted as literal
    assert icon.properties["Font"].js == "'Open Sans'"


def test_quoted_member_on_thisitem():
    from pfx2gas.fx import transpile

    res = transpile("ThisItem.'File name with extension'")
    assert res.js == "FX.field(item, 'file_name_with_extension')"


def test_launch_and_select():
    from pfx2gas.fx import transpile

    out = transpile("Launch(ThisItem.'Link to item');", behavior=True).js
    assert "window.open(FX.field(item, 'link_to_item')" in out
    assert "selectControl('CollectionButton')" in transpile(
        "Select(CollectionButton)", behavior=True).js


def test_split_sequence():
    from pfx2gas.fx import transpile

    assert "FX.split" in transpile('Split(ThisItem.Name, ".")').js
    assert "FX.sequence(5, 1, 1)" in transpile("Sequence(5,1,1)").js


def test_fixture_d_converts_end_to_end(tmp_path):
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    ir = analyze(parse(unpack(FIXTURES / "fixtureD.msapp")))
    out = synthesize(ir, tmp_path / "D")
    result = validate_project(out)
    assert result["ok"], result["problems"]
