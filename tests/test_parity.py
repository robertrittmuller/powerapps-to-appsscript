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
    assert "item.name" in js          # per-row text binding
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
