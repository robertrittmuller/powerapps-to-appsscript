"""Regression tests for the gap-assessment fixes (Sept 2026).

Covers: legacy `text`-template input/label disambiguation, schema-driven
field inference from References/DataSources.json, sample-data seeding,
collection-vs-table distinction, snake_case Sheet headers, and validator
syntax checking of .gs files.
"""
from __future__ import annotations

import json
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
        ]))
        zf.writestr("Controls\\2.json", _legacy_screen("EDIT", []))
        zf.writestr("References\\DataSources.json", _legacy_datasources())
    return path


@pytest.fixture(scope="module")
def legacy_ir(legacy_msapp):
    from pfx2gas.parse import parse
    from pfx2gas.unpack import unpack

    return parse(unpack(legacy_msapp))


def test_legacy_text_disambiguation(legacy_ir):
    """`text` + input props -> TextInput/TextArea; plain `label` stays Label."""
    types = {c.name: c.type for s in legacy_ir.screens for c in s.walk_controls()}
    assert types["inpTitle"] == "TextInput"
    assert types["inpNotes"] == "TextArea"
    assert types["lblTitle"] == "Label"
    assert types["btnSave"] == "Button"


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
