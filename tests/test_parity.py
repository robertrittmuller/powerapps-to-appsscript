"""Tests for UI-parity synthesis and the review seams."""
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


def test_static_positioning_emitted():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.client import render_screens_html, render_app_js

    ir = analyze(parse(unpack(FIXTURES / "fixtureA.msapp")))
    html = render_screens_html(ir)
    assert 'style="left:40px;top:40px"' in html  # Label1 X/Y
    assert 'style="left:40px;top:160px"' in html  # Button1
    js = render_app_js(ir)
    assert "styleControl('Label1', 'left'" not in js  # static stays in HTML


def test_gallery_renders_row_template():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.client import render_screens_html, render_app_js

    ir = analyze(parse(unpack(FIXTURES / "fixtureB.msapp")))
    html = render_screens_html(ir)
    assert 'class="fx-gallery"' in html and "<template>" in html
    assert 'data-control="LabelRow"' in html and 'data-control="BtnDelete"' in html
    js = render_app_js(ir)
    assert "FXRuntime.gallery(" in js
    assert "FX.field(item, 'name')" in js  # blank-safe per-row text binding
    assert "apiRemove('Tasks', item)" in js  # per-item handler


def test_reactive_styles_registered():
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.synth.client import render_app_js

    ir = analyze(parse(unpack(FIXTURES / "fixtureD.msapp")))
    js = render_app_js(ir)
    assert "styleControl('Icon1', 'color'" in js       # Color via Switch
    assert "styleControl('Icon1', 'left'" in js        # X is a formula (ColorFade) -> reactive
    assert "backgroundColor" not in js.split("styleControl")[0]  # sanity


def test_transparent_colors_sizing_line_height_and_dynamic_images():
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.synth.client import render_app_js, render_index_html, render_screens_html

    transparent = FxExpr(raw="RGBA(0,0,0,0)", js="FX.rgba(0, 0, 0, 0)",
                         translation_status="rule")
    ir = AppIR(name="Visual", start_screen="HOME", screens=[
        ScreenNode(name="HOME", controls=[
            ControlNode(name="Title", type="Label", properties={
                "Text": FxExpr(raw='"Title"', js="'Title'", translation_status="rule"),
                "Fill": transparent,
                "BorderColor": transparent,
                "BorderThickness": FxExpr(raw="2", js="2", translation_status="rule"),
                "BorderStyle": FxExpr(raw="BorderStyle.None", js="'None'",
                                      translation_status="rule"),
                "Align": FxExpr(raw="Center", js="state.Center", translation_status="rule"),
                "Font": FxExpr(raw="Font.'Segoe UI'", js="'Segoe UI'",
                               translation_status="rule"),
                "Size": FxExpr(raw="13", js="13", translation_status="rule"),
                "VerticalAlign": FxExpr(raw="VerticalAlign.Middle", js="'Middle'",
                                        translation_status="rule"),
                "LineHeight": FxExpr(raw="1.2", js="1.2", translation_status="rule"),
            }),
            ControlNode(name="Avatar", type="Image", properties={
                "Image": FxExpr(raw="User().Image", js="FXUser().image",
                                translation_status="rule"),
            }),
            ControlNode(name="Category", type="Dropdown", properties={
                "Items": FxExpr(raw="TicketCategory", js="state.TicketCategory",
                                translation_status="rule"),
            }),
        ]),
    ])

    screens = render_screens_html(ir)
    app_js = render_app_js(ir)
    index = render_index_html(ir, screens)
    assert "background-color:rgba(0,0,0,0.0)" in screens
    assert "border-color:rgba(0,0,0,0.0)" in screens
    assert "border-style:none" in screens
    assert "text-align:center" in screens
    assert "justify-content:center" in screens
    assert "font-family:'Segoe UI', Arial, system-ui, sans-serif" in screens
    assert "font-size:13pt" in screens and "font-size:13px" not in screens
    assert "line-height:1.2" in screens and "line-height:1.2px" not in screens
    assert "styleControl('Title', 'backgroundColor'" not in app_js
    assert "FXRuntime.attrControl('Avatar', 'src'" in app_js
    assert "FXRuntime.rowControl(document," in app_js
    assert "items: function () { return rows; }" in app_js
    assert 'class="fx-image"' in screens
    assert "[data-control] { box-sizing: border-box; }" in index
    assert "padding: 16px" not in index


def test_helpdesk_icon_names_have_visible_cross_platform_glyphs():
    from pfx2gas.icons import icon_glyph

    for name in ("AddDocument", "DocumentWithContent", "DetailList", "Trending",
                 "Sort", "Reload", "CancelBadge", "customer-service", "Settings",
                 "Filter", "EmojiSmile", "Home"):
        glyph = icon_glyph(name)
        assert glyph, name
        assert not 0xE000 <= ord(glyph) <= 0xF8FF, name


def test_form_modes_transpiled():
    from pfx2gas.fx import transpile

    js = transpile("NewForm(Form1);", behavior=True).js
    assert js == "setFormMode('Form1', 'new');"
    assert "setFormMode('F2', 'edit')" in transpile("EditForm(F2);", behavior=True).js


def test_review_is_review_only(tmp_path, monkeypatch):
    """The review seam receives formulas but cannot alter the IR."""
    from pfx2gas.unpack import unpack
    from pfx2gas.parse import parse
    from pfx2gas.analyze import analyze
    from pfx2gas.review import review_behavioral_equivalence

    monkeypatch.chdir(tmp_path)
    ir = analyze(parse(unpack(FIXTURES / "fixtureA.msapp")))
    before = {c.name: c.properties["OnSelect"].js for s in ir.screens
              for c in s.walk_controls() if "OnSelect" in c.properties}

    class _FakeCompletions:
        def create(self, **kwargs):
            import json

            verdicts = [{"context": "Screen1.Button1.OnSelect", "risk": "low",
                         "reason": "direct mapping", "suggestion": "none"}]
            payload = json.dumps({"verdicts": verdicts})

            class _Resp:
                choices = [type("C", (), {"message": type("M", (), {"content": payload})()})()]

            return _Resp()

    client = type("Client", (), {})()
    client.model = "mock"
    client._get_client = lambda: type("C", (), {"chat": type("Ch", (), {"completions": _FakeCompletions()})()})()
    client._log = lambda *a, **k: None
    rows = review_behavioral_equivalence(ir, client)
    assert rows and rows[0]["risk"] == "low"
    after = {c.name: c.properties["OnSelect"].js for s in ir.screens
             for c in s.walk_controls() if "OnSelect" in c.properties}
    assert before == after  # review did not modify anything


def test_report_includes_review_and_qa_sections():
    from pfx2gas.report import render_report

    ir = type("IR", (), {"name": "X", "screens": [], "data_sources": [],
                         "global_vars": [], "support_matrix": []})()
    md = render_report(ir, review_rows=[{"context": "S.C.OnSelect", "risk": "high",
                                         "reason": "r", "suggestion": "s"}],
                       qa_scenarios=[{"title": "T", "steps": ["a", "b"],
                                      "expected": "e", "covers": "c"}])
    assert "Behavioral-equivalence review" in md
    assert "**high**" in md
    assert "Manual QA scenarios" in md and "### 1. T" in md


def test_report_without_review_notes_it():
    from pfx2gas.report import render_report

    ir = type("IR", (), {"name": "X", "screens": [], "data_sources": [],
                         "global_vars": [], "support_matrix": []})()
    md = render_report(ir)
    assert "Behavioral review not run" in md


def test_report_separates_translation_from_runtime_wiring():
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.report import render_report
    from pfx2gas.synth.build import assess_fidelity

    ir = AppIR(name="Ledger", screens=[ScreenNode(name="S", controls=[
        ControlNode(name="C", type="CanvasComponent", properties={
            "CustomValue": FxExpr(raw='"x"', js="'x'", translation_status="rule")
        })
    ])])
    assess_fidelity(ir)
    md = render_report(ir)
    assert "| rule | ignored |" in md
    assert "component instances x1 render as generic containers" in md
    assert "None — every formula" not in md


def test_capture_inputs_render_and_report_explicit_blockers():
    from pfx2gas.ir import AppIR, ControlNode, ScreenNode
    from pfx2gas.report import render_report
    from pfx2gas.synth.client import render_screens_html

    ir = AppIR(name="Capture", start_screen="S", screens=[
        ScreenNode(name="S", controls=[
            ControlNode(name="Signature", type="PenInput"),
            ControlNode(name="ScanCode", type="BarcodeReader"),
        ])
    ])
    html = render_screens_html(ir)
    report = render_report(ir)
    assert 'data-unsupported-control="PenInput"' in html
    assert "Unsupported input: BarcodeReader" in html
    assert "unsupported input controls** x2" in report
    assert "S.Signature (PenInput)" in report


def test_submit_form_without_a_card_contract_is_reported_unsupported():
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.synth.client import render_app_js

    submit = FxExpr(
        raw="SubmitForm(BrokenForm)", kind="behavior",
        js="await submitForm('BrokenForm');", translation_status="rule",
    )
    ir = AppIR(name="Broken", start_screen="S", screens=[
        ScreenNode(name="S", controls=[
            ControlNode(name="BrokenForm", type="Form"),
            ControlNode(name="Save", type="Button", properties={"OnSelect": submit}),
        ])
    ])
    render_app_js(ir)
    assert submit.emission_status == "unsupported"
    assert "no generated DataSource/DataCard contract" in submit.fidelity_note
