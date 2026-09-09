import json
from pathlib import Path
import subprocess

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack
from pfx2gas.synth.build import synthesize
from pfx2gas.synth.server import data_contracts
from pfx2gas.validate import validate_project


FIXTURE = Path(__file__).parent / "fixtures/fixtureDataverse.msapp"


@pytest.fixture
def native_ir():
    return analyze(parse(unpack(FIXTURE)))


def test_native_export_keeps_metadata_and_does_not_infer_duplicate_alias_columns(native_ir):
    sources = {ds.name: ds for ds in native_ir.data_sources}
    project = sources["Projects"]
    assert project.origin == "dataverse"
    assert project.primary_key == "Project"
    assert len(project.fields) == 8
    assert {field.logical_name for field in project.fields} == {
        "msft_projectid", "msft_name", "msft_status", "msft_active", "msft_budget", "msft_start", "msft_owner", "msft_tags"}
    fields = {field.name: field for field in project.fields}
    assert fields["Status"].choices == [{"name": "Open", "value": 0}, {"name": "Closed", "value": 1}]
    assert fields["Owner"].lookup_targets == ["systemuser"]
    assert project.metadata["relationships"]["ManyToOneRelationships"][0]["ReferencingAttribute"] == "msft_owner"
    assert sources["project_active"].option_values[0]["value"] is False
    assert sources["project_active"].aliases == ["Project Active"]
    assert sources["DirectoryService"].origin == "service"
    assert sources["Project Views"].origin == "view"
    assert list(data_contracts(native_ir)) == ["Projects"]


@pytest.fixture
def backend(native_ir, tmp_path):
    yield from run_backend(native_ir, tmp_path)


def run_backend(ir, tmp_path):
    out = synthesize(ir, tmp_path / "Native")
    assert validate_project(out)["ok"]
    server = subprocess.Popen(["node", str(Path(__file__).parent / "browser/gas-server.cjs"), str(out)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def call(fn, *args):
        server.stdin.write(json.dumps({"fn": fn, "args": args}) + "\n")
        server.stdin.flush()
        line = server.stdout.readline()
        assert line, "generated server process stopped"
        return json.loads(line)
    yield call
    server.stdin.close()
    server.wait(timeout=10)


@pytest.fixture
def lookup_ir(native_ir):
    from pfx2gas.ir import DataSource, FieldDef
    native_ir.data_sources.extend([
        DataSource(name='Users', origin='dataverse', logical_name='systemuser', primary_key='User', fields=[
            FieldDef(name='User', aliases=['systemuserid']), FieldDef(name='First Name', aliases=['firstname']),
            FieldDef(name='Active', type='bool', aliases=['isactive']),
            FieldDef(name='Manager', type='lookup', aliases=['managerid'], lookup_targets=['systemuser'])]),
        DataSource(name='Teams', origin='dataverse', logical_name='team', primary_key='Team', fields=[
            FieldDef(name='Team', aliases=['teamid']), FieldDef(name='Name', aliases=['teamname'])]),
    ])
    native_ir.data_sources[0].fields.append(FieldDef(name='Assignee', type='lookup', lookup_targets=['systemuser','team']))
    return native_ir


@pytest.fixture
def lookup_backend(lookup_ir, tmp_path):
    yield from run_backend(lookup_ir, tmp_path)


def test_lookup_snapshots_preserve_target_aliases_nested_values_and_extra_formula_columns(lookup_backend):
    call = lookup_backend
    response = call('api','Projects','patch',{'base':{'id':'project-two'},'record':{'owner':{
        'systemuserid':'user-two','firstname':'Grace','isactive':False,
        'managerid':{'systemuserid':'user-one','firstname':'Ada'},'app_note':'local extension'}}})
    assert 'error' not in response, response
    for record in [response['result'], call('api','Projects','list',{})['result'][1]]:
        owner = record['owner']
        assert owner['user'] == owner['systemuserid'] == owner['id'] == 'user-two'
        assert owner['first__name'] == owner['firstname'] == owner['First Name'] == 'Grace'
        assert owner['active'] is owner['isactive'] is False
        assert owner['manager']['first__name'] == owner['managerid']['firstname'] == 'Ada'
        assert owner['app_note'] == 'local extension'
    # A scalar key becomes a typed key-only snapshot, with no invented name.
    owner = call('api','Projects','patch',{'base':{'id':'project-two'},'record':{'owner':'user-three'}})['result']['owner']
    assert owner['user'] == owner['systemuserid'] == 'user-three'
    assert 'firstname' not in owner


def test_invalid_nested_lookup_values_fail_before_any_row_cells_are_written(lookup_backend):
    call = lookup_backend
    before = call('api','Projects','list',{})['result']
    nested = {'systemuserid':'user-one'}
    for _ in range(23):
        nested = {'systemuserid':'user-one','managerid':nested}
    for owner in [
        {'systemuserid':'one','user':'two'}, {'systemuserid':'one','firstname':'Ada','First Name':'Other'},
        {'systemuserid':'one','isactive':'false'}, {'firstname':'Missing key'},
        {'systemuserid':'one','managerid':{'user':'two','isactive':0}}, nested,
    ]:
        result = call('api','Projects','patch',{'base':{'id':'project-two'},'record':{'name':'Must not save','owner':owner}})
        assert 'error' in result, result
        assert call('api','Projects','list',{})['result'] == before


def test_polymorphic_lookup_requires_a_unique_exported_target_key(lookup_backend):
    call = lookup_backend
    for assignee, key, name in [({'systemuserid':'person','firstname':'Ada'},'user','person'),
                                ({'teamid':'group','teamname':'Group'},'team','group')]:
        result = call('api','Projects','patch',{'base':{'id':'project-two'},'record':{'assignee':assignee}})
        assert 'error' not in result, result
        assert result['result']['assignee'][key] == name
    before = call('api','Projects','list',{})['result']
    for assignee in ['ambiguous', {'id':'ambiguous'}, {'systemuserid':'person','teamid':'group'}]:
        result = call('api','Projects','patch',{'base':{'id':'project-two'},'record':{'assignee':assignee}})
        assert 'unambiguous' in result['error'], result
        assert call('api','Projects','list',{})['result'] == before


def test_generated_server_preserves_primary_keys_aliases_and_typed_values(backend):
    rows = backend("api", "Projects", "list", {})["result"]
    assert [(r["id"], r["project"], r["msft_projectid"], r["name"]) for r in rows] == [
        ("project-one", "project-one", "project-one", "First project"),
        ("project-two", "project-two", "project-two", "Second project")]
    assert rows[1]["active"] is False and rows[0]["budget"] == 0
    assert backend("apiChoices", "Projects", "msft_status")["result"] == [
        {"name": "Open", "value": 0}, {"name": "Closed", "value": 1}]
    response = backend("api", "Projects", "patch", {"base": {"msft_projectid": "project-two"},
        "record": {"msft_name": "Second edited", "msft_status": 0, "msft_active": False, "budget": 0,
                   "msft_start": "2026-09-09", "owner": {"user_id": "user-one", "full_name": "Grace"}, "tags": [0, 1]}})
    assert "result" in response, response
    saved = response["result"]
    assert saved["name"] == saved["msft_name"] == "Second edited"
    assert saved["active"] is False and saved["status"] == 0 and saved["budget"] == 0
    assert saved["msft_start"] == saved["Start Date"] == "2026-09-09T00:00:00.000Z"
    reloaded = backend("api", "Projects", "list", {})["result"]
    assert reloaded[0]["name"] == "First project"
    assert reloaded[1]["owner"] == {"user_id": "user-one", "full_name": "Grace"}
    assert reloaded[1]["tags"] == [0, 1]
    created = backend("api", "Projects", "create", {"record": {"name": "New", "status": 1}})["result"]
    assert created["project"] == created["id"] == created["msft_projectid"]
    assert created["id"] not in {"project-one", "project-two"}
    backend("api", "Projects", "remove", {"record": {"msft_projectid": created["id"]}})
    backend("api", "Projects", "removeIf", {"ids": ["project-two"]})
    assert [row["id"] for row in backend("api", "Projects", "list", {})["result"]] == ["project-one"]


def test_invalid_save_is_atomic_and_cannot_duplicate_or_reidentify_a_record(backend):
    before = backend("api", "Projects", "list", {})["result"]
    for record in ({"name": "Must not persist", "status": 999}, {"budget": "not a number"},
                   {"active": "false"}, {"tags": [999]}, {"owner": 123}, {"msft_start": "invalid"},
                   {"name": "one", "msft_name": "conflict"}, {"project": "replacement-id"}):
        result = backend("api", "Projects", "patch", {"base": {"id": "project-two"}, "record": record})
        assert "error" in result, result
        assert backend("api", "Projects", "list", {})["result"] == before
    assert "not found" in backend("api", "Projects", "patch", {"base": {"id": "missing"}, "record": {"name": "Duplicate"}})["error"]
    assert "duplicate" in backend("api", "Projects", "create", {"record": {"msft_projectid": "project-one"}})["error"]
    for source in ("DirectoryService", "Project Views", "project_status"):
        assert "not part" in backend("api", source, "list", {})["error"]
    assert backend("api", "Projects", "list", {})["result"] == before


def test_invalid_exported_metadata_does_not_silently_become_an_empty_table():
    from pfx2gas.data_contract import apply_source_contract
    from pfx2gas.ir import DataSource
    for definition in ("{broken", {}, {"EntityMetadata": {"Attributes": []}}):
        with pytest.raises(ValueError):
            apply_source_contract(DataSource(name="Broken"), {"Type": "NativeCDSDataSourceInfo", "TableDefinition": definition})


def test_validator_gates_contract_loss_and_alias_collisions(native_ir, tmp_path):
    out = synthesize(native_ir, tmp_path / "Native")
    contract = json.loads((out / "data-contract.json").read_text())
    contract["sources"][0]["primary_key"] = "Missing primary"
    (out / "data-contract.json").write_text(json.dumps(contract))
    verdict = validate_project(out)
    assert not verdict["ok"] and any("data-contract" in p for p in verdict["problems"])
    out = synthesize(native_ir, out)
    contract = json.loads((out / "data-contract.json").read_text())
    contract["sources"][0]["fields"][1]["aliases"].append("msft_projectid")
    (out / "data-contract.json").write_text(json.dumps(contract))
    assert not validate_project(out)["ok"]


def test_real_corpus_server_gate_executes_setup_not_only_syntax(native_ir, tmp_path):
    from pfx2gas.server_sim import simulate_server
    out = synthesize(native_ir, tmp_path / "Native")
    verdict = simulate_server(out)
    assert verdict["status"] == "pass" and verdict["tables"] == 1 and verdict["choiceFields"] == 3, verdict
    # A missing setup helper is legal JS and can leave the startup simulator
    # looking healthy. The real corpus must reject that broken server.
    code = (out / "Code.gs").read_text().replace("function encodeCell(", "function missingEncodeCell(")
    (out / "Code.gs").write_text(code)
    assert validate_project(out)["ok"]
    verdict = simulate_server(out)
    assert verdict["status"] == "fail" and "encodeCell" in str(verdict["errors"]), verdict


def test_generated_native_app_initializes_from_logical_seed_fields(native_ir, tmp_path):
    from pfx2gas.startup_sim import simulate_project
    out = synthesize(native_ir, tmp_path / "Native")
    result = simulate_project(out, [{"id": "native-input", "steps": [
        {"action": "expectValue", "control": "ContractName", "equals": "Second project"},
        {"action": "expectText", "control": "ContractCount", "equals": "2"},
    ]}])
    assert result["allConsoleErrors"] == [], result
    assert result["visible"] == ["ContractScreen"], result
    assert result["journeyResults"][0]["status"] == "pass", result
