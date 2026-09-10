from pfx2gas.analyze import analyze
from pfx2gas.ir import AppIR, DataSource, FxExpr


def test_browser_storage_only_accepts_declared_or_inferred_local_collections():
    ir = analyze(AppIR(name="Cache", on_start=FxExpr(kind="behavior", raw=
        'LoadData(Drafts, "draft", true); ClearCollect(Drafts, Table()); SaveData([@Drafts], "draft"); ClearData()')))
    assert ir.on_start.translation_status == "rule"
    assert [(ds.name, ds.origin) for ds in ir.data_sources] == [("Drafts", "collection")]
    assert "FXRuntime.loadData('Drafts', 'draft', true)" in ir.on_start.js
    assert "FXRuntime.saveData(state.Drafts, 'draft')" in ir.on_start.js
    assert "apiCreate" not in ir.on_start.js
    for formula in ['LoadData(Contacts, "cache", true)', 'SaveData(Contacts, "cache")']:
        external = analyze(AppIR(name="External", data_sources=[DataSource(name="Contacts", origin="sharepoint")],
            on_start=FxExpr(kind="behavior", raw=formula)))
        assert external.on_start.translation_status == "stubbed"
        assert any("local collection" in entry.detail for entry in external.support_matrix)


def test_generated_draft_input_defaults_reset_without_erasing_unrelated_edits(tmp_path):
    from pathlib import Path
    from pfx2gas.parse import parse
    from pfx2gas.unpack import unpack
    from pfx2gas.synth.build import synthesize
    from pfx2gas.startup_sim import simulate_project

    fixture = Path(__file__).parent / "fixtures/fixtureStorage.msapp"
    ir = analyze(parse(unpack(fixture)))
    project = synthesize(ir, tmp_path / "Draft")
    result = simulate_project(project, [{"id": "draft-defaults", "steps": [
        {"action": "setValue", "control": "DraftNote", "value": "Saved inspection"},
        {"action": "click", "control": "SaveDraft"},
        {"action": "expectState", "key": "cacheStatus", "equals": "saved"},
        {"action": "setValue", "control": "DraftNote", "value": "Unsaved inspection"},
        {"action": "click", "control": "DraftUnrelated"},
        {"action": "expectValue", "control": "DraftNote", "equals": "Unsaved inspection"},
        {"action": "click", "control": "DraftReset"},
        {"action": "expectValue", "control": "DraftNote", "equals": "Saved inspection"},
    ]}])
    assert result["allConsoleErrors"] == [], result
    assert result["journeyResults"][0]["status"] == "pass", result
    note = next(c for s in ir.screens for c in s.walk_controls() if c.name == "DraftNote")
    assert note.properties["Default"].emission_status == "emitted"
