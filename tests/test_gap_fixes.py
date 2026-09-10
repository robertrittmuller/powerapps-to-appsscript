"""Regression tests for the gap-assessment fixes (Sept 2026).

Covers: legacy `text`-template input/label disambiguation, schema-driven
field inference from References/DataSources.json, sample-data seeding,
collection-vs-table distinction, snake_case Sheet headers, and validator
syntax checking of .gs files.
"""
from __future__ import annotations

import json
import base64
import subprocess
import zipfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([__import__("sys").executable, str(FIXTURES / "build.py")], check=True)


# ---------------------------------------------------------------------------
# Fixture E: legacy binary .msapp exercising the disambiguation + schema path
# ---------------------------------------------------------------------------

def _legacy_screen(name: str, children: list[dict]) -> str:
    return json.dumps({"TopParent": {
        "Type": "ControlInfo", "Name": name,
        "Template": {"Name": "screen"},
        "Rules": [{"Property": "Width", "InvariantScript": "640"}],
        "Children": children,
    }})


def _legacy_control(name: str, template: str, props: dict) -> dict:
    """A legacy child control node (the adapter reads Name/Template/Rules directly)."""
    return {
        "Name": name, "Template": {"Name": template},
        "Rules": [{"Property": k, "InvariantScript": v} for k, v in props.items()],
    }


def _legacy_datasources() -> str:
    return json.dumps({"DataSources": [
        {"Name": "Tickets", "Type": "StaticDataSourceInfo",
         "Schema": "*[Title:s, Amount:n, Due:d]",
         "Data": json.dumps([{"Title": "first", "Amount": 5, "Due": "2026-01-01"},
                             {"Title": "second", "Amount": 7, "Due": "2026-02-02"}])},
        {"Name": "colCache", "Type": "CollectionDataSourceInfo",
         "Schema": None, "Data": None},
    ]})


@pytest.fixture(scope="module")
def legacy_msapp(tmp_path_factory):
    d = tmp_path_factory.mktemp("legacy")
    path = d / "LegacyApp.msapp"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Properties.json", json.dumps({"Name": "LegacyApp"}))
        zf.writestr("Controls\\1.json", _legacy_screen("HOME", [
            _legacy_control("lblTitle", "label", {"Text": "Hello", "X": "10"}),
            _legacy_control("inpTitle", "text", {"Default": '""', "Mode": "TextMode.SingleLine",
                                                 "HintText": '"Title"'}),
            _legacy_control("inpNotes", "text", {"Default": '""', "Mode": "TextMode.MultiLine"}),
            _legacy_control("btnSave", "button", {"Text": '"Save"', "OnSelect": "Back()"}),
            _legacy_control("brand", "image", {"Image": "'brand-logo'"}),
            _legacy_control("pie", "pieChart", {"Items": "Tickets"}),
            _legacy_control("bars", "barChart", {"Items": "Tickets"}),
            _legacy_control("trend", "lineChart", {"Items": "Tickets"}),
            _legacy_control("legend", "legend", {"Items": "pie.SeriesLabels"}),
        ]))
        zf.writestr("Controls\\2.json", _legacy_screen("EDIT", []))
        zf.writestr("References\\DataSources.json", _legacy_datasources())
        zf.writestr("References\\Resources.json", json.dumps({"Resources": [{
            "Name": "brand-logo", "ResourceKind": "LocalFile", "Content": "Image",
            "FileName": "brand.png", "Path": "Assets\\Images\\brand.png",
            "RootPath": "https://expired.example.test/brand.png",
        }]}))
        zf.writestr("Assets\\Images\\brand.png", b"\x89PNG\r\n\x1a\nfixture")
    return path


@pytest.fixture(scope="module")
def legacy_ir(legacy_msapp):
    from pfx2gas.parse import parse
    from pfx2gas.unpack import unpack

    return parse(unpack(legacy_msapp))


@pytest.fixture(scope="module")
def component_msapp(tmp_path_factory):
    """Legacy component definition + instance, shaped like the real progress bars."""
    d = tmp_path_factory.mktemp("legacy-component")
    path = d / "ComponentApp.msapp"
    template_id = "c08844b7dea64279b88b31d857d0bc4d"
    custom = [{"Name": name} for name in (
        "barMaxValue", "barCurrentValue", "barMaxFill", "barCurrentFill",
        "barWidth", "barHeight", "labelColor", "targetScreen",
    )]
    definition = {
        "TopParent": {
            "Name": "cmp_ProgressBar_hor",
            "Template": {"Name": template_id, "IsComponentDefinition": True,
                         "CustomProperties": custom},
            "Rules": [],
            "Children": [
                _legacy_control("track", "label", {
                    "Text": '""', "X": "5", "Y": "5",
                    "Width": "cmp_ProgressBar_hor.barWidth",
                    "Height": "cmp_ProgressBar_hor.barHeight",
                    "Fill": "cmp_ProgressBar_hor.barMaxFill",
                    "OnSelect": "Navigate(cmp_ProgressBar_hor.targetScreen)",
                }),
                _legacy_control("current", "label", {
                    "Text": 'RoundUp(100*(cmp_ProgressBar_hor.barCurrentValue/'
                            'cmp_ProgressBar_hor.barMaxValue),0) & "%"',
                    "X": "track.X", "Y": "track.Y",
                    "Width": "track.Width*cmp_ProgressBar_hor.barCurrentValue/"
                             "cmp_ProgressBar_hor.barMaxValue",
                    "Height": "track.Height", "Fill": "cmp_ProgressBar_hor.barCurrentFill",
                    "Color": "cmp_ProgressBar_hor.labelColor",
                }),
            ],
        }
    }
    instance = _legacy_control("progress1", template_id, {
        "barMaxValue": "100", "barCurrentValue": "42",
        "barMaxFill": 'ColorValue("#eee")',
        "barCurrentFill": 'ColorValue("#168aad")',
        "barWidth": "200", "barHeight": "42", "labelColor": "White",
        "targetScreen": "DETAIL",
        "X": "16", "Y": "20", "Width": "progress1.barWidth+10",
        "Height": "progress1.barHeight+10",
    })
    instance["Template"]["CustomProperties"] = custom
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Properties.json", json.dumps({"Name": "ComponentApp"}))
        zf.writestr("Controls\\1.json", _legacy_screen("HOME", [instance]))
        zf.writestr("Controls\\2.json", _legacy_screen("DETAIL", []))
        zf.writestr("Components\\1.json", json.dumps(definition))
        zf.writestr("ComponentsMetadata.json", json.dumps({"Components": [{
            "Name": "cmp_ProgressBar_hor", "TemplateName": template_id,
        }]}))
    return path


def test_legacy_text_disambiguation(legacy_ir):
    """`text` + input props -> TextInput/TextArea; plain `label` stays Label."""
    types = {c.name: c.type for s in legacy_ir.screens for c in s.walk_controls()}
    assert types["inpTitle"] == "TextInput"
    assert types["inpNotes"] == "TextArea"
    assert types["lblTitle"] == "Label"
    assert types["btnSave"] == "Button"


def test_legacy_chart_families_are_preserved(legacy_ir):
    types = {c.name: c.type for s in legacy_ir.screens for c in s.walk_controls()}
    assert types["pie"] == "PieChart"
    assert types["bars"] == "BarChart"
    assert types["trend"] == "LineChart"
    assert types["legend"] == "Legend"


def test_packaged_image_resource_beats_expired_url_and_icon_name(legacy_ir):
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.client import render_screens_html

    expected = "data:image/png;base64," + base64.b64encode(
        b"\x89PNG\r\n\x1a\nfixture"
    ).decode("ascii")
    assert legacy_ir.media_resources == {"brand-logo": expected}
    screens = render_screens_html(analyze(legacy_ir.model_copy(deep=True)))
    assert f'src="{expected}"' in screens
    assert 'data-control="brand"' in screens
    assert 'data-icon-name="brand-logo"' not in screens


def test_legacy_component_definition_is_expanded_and_namespaced(component_msapp, tmp_path):
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.report import render_report
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    ir = analyze(parse(unpack(component_msapp)))
    component = ir.screens[0].controls[0]
    assert component.type == "CanvasComponent"
    assert component.component_template == "cmp_ProgressBar_hor"
    assert [c.name for c in component.children] == ["progress1__track", "progress1__current"]
    assert component.children[1].properties["Width"].raw == (
        "progress1__track.Width*progress1.barCurrentValue/progress1.barMaxValue"
    )
    assert component.children[0].properties["OnSelect"].raw == (
        "Navigate(progress1.targetScreen)"
    )

    out = synthesize(ir, tmp_path / "ComponentOut")
    screens = (out / "Screens.html").read_text()
    app_js = (out / "App.js.html").read_text()
    assert 'class="fx-component" data-component-template="cmp_ProgressBar_hor"' in screens
    assert 'data-control="progress1__track"' in screens
    assert 'data-control="progress1__current"' in screens
    assert "FXRuntime.registerControlProps('progress1'" in app_js
    assert "val('progress1').bar_width" in app_js
    assert "val('progress1__track').width" in app_js
    assert "state.White" not in app_js and "return 'white'" in app_js
    assert "'target_screen': function () { return 'DETAIL'; }" in app_js
    assert "go(val('progress1').target_screen);" in app_js

    report = render_report(ir)
    assert "component templates x1 were expanded" in report
    assert "component instances x1 render as generic containers" not in report


def test_static_htmltext_renders_sanitized_markup():
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.synth.client import render_screens_html

    content = (
        "<div style='width:400px;box-shadow:0 5px 8px #ccc'>"
        "<img src='javascript:alert(1)' onerror='alert(2)'>"
        "<a href=javascript:alert(4)>Tile</a></div>"
        "<script>alert(3)</script>"
    )
    ir = AppIR(name="HtmlText", start_screen="HOME", screens=[
        ScreenNode(name="HOME", controls=[
            ControlNode(name="tile", type="HtmlText", properties={
                "HtmlText": FxExpr(raw=repr(content), js=repr(content),
                                   translation_status="rule"),
            }),
        ]),
    ])

    screens = render_screens_html(ir)
    assert "<div style='width:400px;box-shadow:0 5px 8px #ccc'>" in screens
    assert "<a>Tile</a></div>" in screens
    assert "data-static-html" not in screens
    assert "javascript:" not in screens
    assert "onerror=" not in screens
    assert "<script" not in screens


def test_dynamic_htmltext_is_runtime_bound_through_the_sanitizer():
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.synth.client import render_app_js

    expr = FxExpr(raw='"<b>" & title & "</b>"',
                  js="['<b>', state.title, '</b>'].join('')",
                  translation_status="rule")
    ir = AppIR(name="HtmlText", start_screen="HOME", screens=[
        ScreenNode(name="HOME", controls=[
            ControlNode(name="dynamicHtml", type="HtmlText", properties={"HtmlText": expr}),
        ]),
    ])
    app_js = render_app_js(ir)
    assert "FXRuntime.htmlControl('dynamicHtml'" in app_js
    assert expr.emission_status == "approximated"


def test_legacy_schema_fields_and_types(legacy_ir):
    by_name = {ds.name: ds for ds in legacy_ir.data_sources}
    tickets = by_name["Tickets"]
    assert [(f.name, f.type) for f in tickets.fields] == [
        ("Title", "text"), ("Amount", "number"), ("Due", "date")]
    # embedded sample rows are snake_case-normalized like the emitter's records
    assert tickets.sample_data == [
        {"title": "first", "amount": 5, "due": "2026-01-01"},
        {"title": "second", "amount": 7, "due": "2026-02-02"}]
    # collections are flagged, carry no fields/tab
    cache = by_name["colCache"]
    assert cache.origin == "collection"
    assert cache.fields == []


def test_legacy_collection_data_calls_route_locally(legacy_ir):
    """Collect against a collection compiles to the local runtime, not the API."""
    from pfx2gas.analyze import analyze

    ir = analyze(legacy_ir)
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            expr = ctrl.properties.get("OnSelect")
            if expr and expr.raw and "Collect(colCache" in expr.raw:
                assert "powerapps_collect(state, 'colCache'" in (expr.js or "")
                assert "apiCreate" not in expr.js


def test_legacy_sample_data_seeds_datainit(legacy_ir, tmp_path):
    from pfx2gas.synth.build import synthesize

    ir = __import__("pfx2gas.analyze", fromlist=["analyze"]).analyze(legacy_ir)
    out = synthesize(ir, tmp_path / "LegacyOut")
    init = (out / "DataInit.gs").read_text()
    assert '"title"' in init and '"amount"' in init          # snake_case headers
    assert "first" in init and "second" in init               # embedded rows survive
    assert "colCache" not in init                             # no tab for collections


# ---------------------------------------------------------------------------
# Validator: .gs files are syntax-checked
# ---------------------------------------------------------------------------

def test_validator_rejects_broken_gs(legacy_ir, tmp_path):
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    ir = __import__("pfx2gas.analyze", fromlist=["analyze"]).analyze(legacy_ir)
    out = synthesize(ir, tmp_path / "Broken")
    (out / "DataInit.gs").write_text(
        (out / "DataInit.gs").read_text().replace("function setup()", "function setup("))
    result = validate_project(out)
    assert not result["ok"], "validator must catch broken .gs syntax"
    assert any("DataInit.gs" in p for p in result["problems"])


def test_validator_accepts_good_project(legacy_ir, tmp_path):
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    ir = __import__("pfx2gas.analyze", fromlist=["analyze"]).analyze(legacy_ir)
    out = synthesize(ir, tmp_path / "Good")
    assert validate_project(out)["ok"]


def test_start_screen_is_first_in_screen_order(legacy_ir):
    """Power Apps opens the first screen in screen order (legacy Index field)."""
    assert legacy_ir.start_screen == "HOME"


def test_generated_app_navigates_to_start_screen(legacy_ir, tmp_path):
    from pfx2gas.synth.build import synthesize

    ir = __import__("pfx2gas.analyze", fromlist=["analyze"]).analyze(legacy_ir)
    out = synthesize(ir, tmp_path / "StartScreen")
    from pfx2gas.startup_sim import simulate_project
    result = simulate_project(out)
    assert result['visible'] == ['HOME'] and not result['consoleErrors'], result
    # every screen section is hidden in static markup; runtime reveals HOME
    screens_html = (out / "Screens.html").read_text()
    assert 'data-screen="HOME" style="display:none"' in screens_html


# ---------------------------------------------------------------------------
# Icon-name rendering (Power Apps icon names -> Unicode glyphs)
# ---------------------------------------------------------------------------

def test_icon_glyph_known_and_unknown():
    from pfx2gas.icons import icon_glyph, is_icon_name

    assert icon_glyph("customer-service") is not None
    assert icon_glyph("Icon.Filter") is not None
    assert icon_glyph("EmojiSmile") is not None
    assert icon_glyph("totally-made-up-icon-xyz") is None
    assert is_icon_name("customer-service") is True
    assert is_icon_name("https://example.com/a.png") is False
    assert is_icon_name("logo.png") is False
    assert is_icon_name("/img/logo") is False


def test_packaged_helpdesk_logo_renders_the_original_image():
    """A packaged asset wins over the fallback icon-name heuristic.

    Uses the real helpdesk sample (local soak corpus) when present; skipped in
    CI where samples are fetched separately."""
    from pathlib import Path

    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    sample = Path(__file__).parent.parent / "samples" / "real" / "helpdesk.msapp"
    if not sample.exists():
        import pytest

        pytest.skip("helpdesk.msapp sample not present")
    ir = analyze(parse(unpack(sample)))
    out = synthesize(ir, Path(__file__).parent.parent / "output" / "_icon-test")
    screens = (out / "Screens.html").read_text()
    assert 'src="customer-service"' not in screens
    assert 'src="data:image/png;base64,' in screens
    assert 'data-icon-name="customer-service"' not in screens
    # Icon-type controls render their glyph too
    assert 'data-icon-name="Filter"' in screens
    assert 'data-icon-name="Settings"' in screens
    assert 'data-icon-name="EmojiSmile"' in screens
