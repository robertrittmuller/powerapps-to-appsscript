import json
from pathlib import Path

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.cli import main
from pfx2gas.ir import AppIR, ScreenNode, ControlNode, FxExpr, DataSource, FieldDef
from pfx2gas.preflight import assess
from pfx2gas.synth.build import synthesize
from pfx2gas.validate import validate_project
from pfx2gas.verification import verify_startup
from test_data_contract import run_backend


def app(control):
    return AppIR(name='Governance',start_screen='Main',screens=[ScreenNode(name='Main',controls=[control])])


def test_formula_free_capture_control_cannot_pass_strict_fidelity(tmp_path):
    out = synthesize(analyze(app(ControlNode(name='Upload',type='Attachments'))),tmp_path)
    validation = validate_project(out)
    assert validation['ok'] and validation['formula_gap_count'] == 0
    assert validation['capability_gap_count'] == 1
    assert verify_startup(out)['startup'] == 'pass'
    assert main(['validate',str(out),'--strict-fidelity']) == 1


def test_llm_wiring_does_not_promote_unverified_behavior(tmp_path):
    ir = app(ControlNode(name='Label',type='Label',properties={'Text':FxExpr(raw='Unsupported()',js='42',translation_status='llm')}))
    out = synthesize(ir,tmp_path)
    assert validate_project(out)['formula_gap_count'] == 1
    assert ir.screens[0].controls[0].properties['Text'].emission_status == 'approximated'


@pytest.mark.parametrize('key',['capabilities','formulas'])
def test_validator_rejects_deleted_capability_or_formula_census(tmp_path,key):
    ir = analyze(app(ControlNode(name='Upload',type='Attachments',properties={'Visible':FxExpr(raw='true')})))
    out = synthesize(ir,tmp_path)
    ledger = json.loads((out/'conversion-ledger.json').read_text())
    ledger[key] = []
    (out/'conversion-ledger.json').write_text(json.dumps(ledger))
    assert not validate_project(out)['ok']


def test_runtime_files_are_required_and_runtime_failures_are_recorded(tmp_path):
    ir = analyze(app(ControlNode(name='Broken',type='Label',properties={'Text':FxExpr(raw='Unsupported()')})))
    out = synthesize(ir,tmp_path)
    assert verify_startup(out)['startup'] == 'fail'
    assert main(['validate',str(out),'--require-stage','bootable']) == 1
    (out/'gas-runtime.js.html').unlink()
    assert not validate_project(out)['ok']


def test_report_only_does_not_bypass_strict_verification(tmp_path):
    assert main(['convert','tests/fixtures/fixtureA.msapp','--report-only','--strict-fidelity','--no-llm','-o',str(tmp_path)]) == 1


def test_preflight_classifies_source_gaps_and_connector_migration():
    ir = analyze(app(ControlNode(name='Picker',type='Dropdown',properties={'Items':FxExpr(raw="Choices('Missing'.Status)")})))
    ir.data_sources.append(DataSource(name='Planner',origin='service'))
    preflight = assess(ir)
    assert any(row['classification']=='source-incomplete' and 'Missing' in row['subject'] for row in preflight['issues'])
    assert any(row['classification']=='migration-required' and row['subject']=='Planner' for row in preflight['issues'])
    assert preflight['verification']['liveGoogle'] == 'unassessed'


def test_preflight_does_not_hide_untranslatable_formulas():
    ir=analyze(app(ControlNode(name='Label',type='Label',properties={'Text':FxExpr(raw='UnknownFunction()')})))
    result=assess(ir)
    assert result['status']=='needs-attention' and result['formulaGaps']


def test_general_field_constraints_defaults_and_ignored_readonly_writes_are_atomic(tmp_path):
    ir = AppIR(name='Rules',data_sources=[DataSource(name='Rows',origin='dataverse',primary_key='Key',fields=[
        FieldDef(name='Key'),FieldDef(name='Title',required_level='SystemRequired'),
        FieldDef(name='Business',required_level='ApplicationRequired'),
        FieldDef(name='Computed',writable_create=False,writable_update=False),
        FieldDef(name='Enabled',type='bool',has_default=True,default_value=False),
        FieldDef(name='Amount',type='number',has_default=True,default_value=0)],
        sample_data=[{'key':'one','title':'Original','computed':'Original value'}])])
    for call in run_backend(ir,tmp_path):
        assert 'error' in call('api','Rows','create',{'record':{'Key':'two'}})
        assert len(call('api','Rows','list',{})['result']) == 1
        row = call('api','Rows','create',{'record':{'Key':'two','Title':'New','Computed':'Ignored'}})['result']
        assert row['computed'] is None and row['business'] is None
        assert row['enabled'] is False and row['amount'] == 0
        updated = call('api','Rows','patch',{'base':{'Key':'one'},'record':{'Computed':'Ignored','Title':'Edited'}})['result']
        assert updated['computed']=='Original value' and updated['title']=='Edited'
        result = call('api','Rows','patch',{'base':{'Key':'one'},'record':{'Title':None,'Amount':8}})
        assert 'error' in result
        assert call('api','Rows','list',{})['result'][0]['title']=='Edited'


def test_source_constraints_are_validated_against_generated_contract(tmp_path):
    ir = AppIR(name='Rules',data_sources=[DataSource(name='Rows',origin='dataverse',primary_key='Key',fields=[
        FieldDef(name='Key'),FieldDef(name='Title',required_level='SystemRequired')])])
    out = synthesize(ir,tmp_path)
    gs = out/'Code.gs'
    gs.write_text(gs.read_text().replace('"requiredLevel": "SystemRequired"','"requiredLevel": null'))
    assert not validate_project(out)['ok']


def test_missing_data_contract_is_a_validation_failure_not_a_crash(tmp_path):
    out=synthesize(analyze(app(ControlNode(name='Label',type='Label'))),tmp_path)
    (out/'data-contract.json').unlink()
    assert not validate_project(out)['ok']


def test_exported_choice_defaults_false_and_no_default_sentinel_survive_parsing():
    from pfx2gas.data_contract import apply_source_contract
    attributes=[{'LogicalName':'key','AttributeType':'Uniqueidentifier'},
                {'LogicalName':'choice','AttributeType':'Picklist','DefaultFormValue':-1},
                {'LogicalName':'enabled','AttributeType':'Boolean'},
                {'LogicalName':'defaultchoice','AttributeType':'Picklist'}]
    raw={'Type':'NativeCDSDataSourceInfo','TableDefinition':{'EntityMetadata':{
        'LogicalName':'rows','PrimaryIdAttribute':'key','Attributes':attributes},
        'BooleanOptionSetAttribute':{'value':[{'LogicalName':'enabled','DefaultValue':False,'OptionSet':{}}]},
        'PicklistOptionSetAttribute':{'value':[{'LogicalName':'defaultchoice','DefaultFormValue':0,'OptionSet':{'Options':[{'Value':0}]}}]}}}
    source=DataSource(name='Rows'); apply_source_contract(source,raw)
    fields={field.name:field for field in source.fields}
    assert not fields['choice'].has_default
    assert fields['enabled'].has_default and fields['enabled'].default_value is False
    assert fields['defaultchoice'].has_default and fields['defaultchoice'].default_value==0
