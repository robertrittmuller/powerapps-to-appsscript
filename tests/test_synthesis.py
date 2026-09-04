"""Tests for synthesis: IR -> Apps Script project files."""
from pathlib import Path

import pytest
import re
import subprocess
import sys

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


@pytest.fixture(scope="module")
def ir_a():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    return analyze(parse(unpack(FIXTURES / "fixtureA.msapp")))


@pytest.fixture(scope="module")
def ir_b():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze

    return analyze(parse(unpack(FIXTURES / "fixtureB.msapp")))


def test_synthesize_fixture_a(ir_a, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    for name in ("Code.gs", "DataInit.gs", "appsscript.json", "Index.html",
                 "Screens.html", "App.js.html", "conversion-ledger.json",
                 "gas-runtime.js.html", "fx-stdlib.js.html"):
        assert (out / name).exists(), f"missing {name}"
    code = (out / "Code.gs").read_text()
    assert "function doGet()" in code
    assert "FixtureA" in code
    manifest = (out / "appsscript.json").read_text()
    assert "USER_ACCESSING" in manifest
    assert "auth/spreadsheets" in manifest


def test_js_files_pass_node_check(ir_a, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    app_js = (out / "App.js.html").read_text()
    # strip the wrapper <script> tags for syntax checking
    body = app_js.replace("<script>\n", "").replace("\n</script>", "")
    tmp = tmp_path / "check_App.js"
    tmp.write_text(body)
    result = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_manifest_is_valid_json_with_webapp_config(ir_a, tmp_path):
    """clasp and Apps Script read webapp/oauthScopes from here; it must parse."""
    import json

    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    manifest = json.loads((out / "appsscript.json").read_text())
    assert manifest["webapp"]["executeAs"] == "USER_ACCESSING"
    assert manifest["webapp"]["access"] == "ANYONE"
    assert any("spreadsheets" in s for s in manifest["oauthScopes"])
    assert all("container.ui" not in s for s in manifest["oauthScopes"])


def test_manifest_public_deployer_mode_is_explicit(ir_a):
    from pfx2gas.synth.server import render_manifest
    import json

    ir_a.webapp_access = "ANYONE_ANONYMOUS"
    ir_a.webapp_execute_as = "USER_DEPLOYING"
    manifest = json.loads(render_manifest(ir_a))
    assert manifest["webapp"] == {
        "executeAs": "USER_DEPLOYING", "access": "ANYONE_ANONYMOUS"
    }
    ir_a.webapp_access = "ANYONE"
    ir_a.webapp_execute_as = "USER_ACCESSING"


def test_index_includes_are_resolvable(ir_a, tmp_path):
    """Every file Index.html includes must exist, and Code.gs must define the
    include() helper the server-side template scriptlets call."""
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    index = (out / "Index.html").read_text()
    code = (out / "Code.gs").read_text()
    assert "function include(name)" in code
    for name in re.findall(r"include\('([^']+)'\)", index):
        assert (out / name).exists(), f"Index.html includes missing file: {name}"


def test_screens_contain_controls(ir_a, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    screens = (out / "Screens.html").read_text()
    assert 'data-screen="Screen1"' in screens
    assert 'data-control="Button1"' in screens
    assert 'data-control="TextInput1"' in screens


def test_bindings_transpiled(ir_a, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_a, tmp_path / "FixtureA")
    app_js = (out / "App.js.html").read_text()
    assert "go('Screen2')" in app_js
    assert "FXRuntime.setState({counter: (state.counter + 1)})" in app_js
    assert "bind('Button1'" in app_js


def test_server_api_whitelists_sources_and_remove_if_requires_ids(ir_b, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_b, tmp_path / "SafeServer")
    code = (out / "Code.gs").read_text()
    assert 'var ALLOWED_DATA_SOURCES = ["Tasks"]' in code
    assert "assertDataSource(ds)" in code
    assert "removeRowsByIds(ds, payload.ids)" in code
    assert "removeIf requires one or more explicit ids" in code
    assert "Object.keys(predicate" not in code


def test_strict_fidelity_cli_rejects_a_structurally_valid_gap(tmp_path):
    """CI gate: syntax-valid output is not release-ready with ledger gaps."""
    from pfx2gas.cli import main
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.synth.build import synthesize

    ir = AppIR(name="StrictGate", start_screen="S", screens=[
        ScreenNode(name="S", controls=[
            ControlNode(name="C", type="Label", properties={
                "UnwiredProperty": FxExpr(
                    raw="42", js="42", translation_status="rule"
                )
            })
        ])
    ])
    out = synthesize(ir, tmp_path / "StrictGate")
    assert main(["validate", str(out)]) == 0
    assert main(["validate", str(out), "--strict-fidelity"]) == 1


def test_data_init_lists_fields(ir_b, tmp_path):
    from pfx2gas.synth.build import synthesize

    out = synthesize(ir_b, tmp_path / "FixtureB")
    init = (out / "DataInit.gs").read_text()
    assert "Tasks" in init
    # headers are snake_case so transpiled {name: ..., amount: ...} records
    # land in the right columns
    assert "amount" in init
    assert "status" in init


def test_whoami_derives_a_display_name_from_email(ir_a):
    from pfx2gas.synth.server import render_code_gs

    code = render_code_gs(ir_a)
    assert "var local = email.split('@')[0]" in code
    assert ".replace(/[._-]+/g, ' ')" in code
    assert "fullName: fullName" in code
