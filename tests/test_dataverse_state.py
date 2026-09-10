import json
from pathlib import Path
import subprocess
import sys

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack
from pfx2gas.synth.build import synthesize
from pfx2gas.synth.server import data_contracts
from pfx2gas.validate import validate_project
from test_data_contract import run_backend

FIXTURES=Path(__file__).parent/'fixtures'


@pytest.fixture(scope='module',autouse=True)
def build():
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)


@pytest.fixture
def ir():
    return analyze(parse(unpack(FIXTURES/'fixtureDataverseState.msapp')))


@pytest.fixture
def backend(ir,tmp_path):
    yield from run_backend(ir,tmp_path)


def test_exported_state_defaults_and_reason_membership_survive_parsing(ir):
    contract=data_contracts(ir)['Work']['stateModel']
    assert contract['initialState']==0
    assert contract['defaults']=={'0':101,'1':202}
    assert contract['statusStates']=={'101':0,'202':1,'303':0}
    assert contract['writableCreate']['status'] is False
    assert ir.data_sources[0].metadata['stateModel']['statuses'][2]['state']==0


def test_create_uses_exported_default_reason_and_ignores_readonly_state_input(backend):
    # SDK Create ignores IsValidForCreate=false; do not treat it as a requested state.
    for record in [{'Name':'First'},{'new_name':'Second','statecode':1,'statuscode':303}]:
        result=backend('api','Work','create',{'record':record})
        assert 'error' not in result,result
        row=result['result']
        assert row['status']==row['statecode']==0
        assert row['Status Reason']==row['statuscode']==(303 if record.get('statuscode') else 101)
    assert len(backend('api','Work','list',{})['result'])==2


def test_state_changes_choose_the_metadata_default_but_ordinary_edits_preserve_reason(backend):
    row=backend('api','Work','create',{'record':{'Name':'Review','Status Reason':303}})['result']
    def patch(record): return backend('api','Work','patch',{'base':row,'record':record})['result']
    assert patch({'Name':'Renamed'})['statuscode']==303
    assert patch({'statecode':1})['statuscode']==202
    assert patch({'statecode':0,'statuscode':303})['statuscode']==303
    assert patch({'statecode':0})['statuscode']==101
    assert patch({'statuscode':303})['statecode']==0


@pytest.mark.parametrize('record',[{'Status Reason':202},{'Status Reason':999},{'Status Reason':None},
                                 {'Status':None},{'Status':False},{'Status':1,'Status Reason':101}])
def test_invalid_pairs_fail_before_changing_any_row(backend,record):
    row=backend('api','Work','create',{'record':{'Name':'Original'}})['result']
    before=backend('api','Work','list',{})
    result=backend('api','Work','patch',{'base':row,'record':{'Name':'Must not save',**record}})
    assert 'error' in result,result
    assert backend('api','Work','list',{})==before


def test_create_validation_and_keyed_upsert_share_state_defaults(backend):
    assert 'error' in backend('api','Work','create',{'record':{'Name':'No row','Status Reason':202}})
    row=backend('api','Work','patchRecord',{'record':{'new_workid':'fixed','Name':'New'}})['result']
    assert row['statecode']==0 and row['statuscode']==101
    updated=backend('api','Work','patchRecord',{'record':{'new_workid':'fixed','statecode':1}})['result']
    assert updated['statuscode']==202
    assert len(backend('api','Work','list',{})['result'])==1


def test_alternative_exported_initial_state_and_zero_status_are_not_replaced(ir,tmp_path):
    source=ir.data_sources[0]
    state=next(f for f in source.fields if f.source_type=='State')
    status=next(f for f in source.fields if f.source_type=='Status')
    state.choices.append({'name':'Draft','value':2})
    status.choices.append({'name':'Draft','value':0})
    source.metadata['stateModel']['states'].append({'value':2,'defaultStatus':0,'invariantName':'Draft'})
    source.metadata['stateModel']['statuses'].append({'value':0,'state':2,'transitionData':None})
    source.metadata['stateModel']['defaultState']=2
    for call in run_backend(ir,tmp_path):
        row=call('api','Work','create',{'record':{'Name':'Draft'}})['result']
        assert row['statecode']==2 and row['statuscode']==0


def test_unknown_initial_model_and_custom_transitions_fail_without_writes(ir,tmp_path):
    model=ir.data_sources[0].metadata['stateModel']
    model['states'][0]['invariantName']='Open'
    for call in run_backend(ir,tmp_path):
        assert 'state is missing' in call('api','Work','create',{'record':{'Name':'No guess'}})['error']
        assert call('api','Work','list',{})['result']==[]
    model['defaultState']=0
    model['enforceTransitions']=True
    for call in run_backend(ir,tmp_path/'custom'):
        row=call('api','Work','create',{'record':{'Name':'Original'}})['result']
        result=call('api','Work','patch',{'base':row,'record':{'Name':'No change','statecode':1}})
        assert 'custom state transitions' in result['error']
        assert call('api','Work','list',{})['result']==[row]


@pytest.mark.parametrize('fault',['missing','duplicate-state','invalid-default','invalid-status-state'])
def test_incomplete_state_metadata_cannot_silently_create_blank_or_invalid_rows(ir,tmp_path,fault):
    model=ir.data_sources[0].metadata['stateModel']
    if fault=='missing':
        model.clear()
    elif fault=='duplicate-state':
        model['states'].append(dict(model['states'][0]))
    elif fault=='invalid-default':
        model['states'][0]['defaultStatus']=202
    else:
        model['statuses'][0]['state']=9
    assert 'error' in data_contracts(ir)['Work']['stateModel']
    for call in run_backend(ir,tmp_path):
        result=call('api','Work','create',{'record':{'Name':'No partial row'}})
        assert 'Dataverse state model' in result['error']
        assert call('api','Work','list',{})['result']==[]


def test_readonly_update_fields_are_ignored_and_ordinary_edits_remain_possible(ir,tmp_path):
    for field in ir.data_sources[0].fields:
        if field.source_type in {'State','Status'}:
            field.writable_update=False
    for call in run_backend(ir,tmp_path):
        row=call('api','Work','create',{'record':{'Name':'Original'}})['result']
        result=call('api','Work','patch',{'base':row,'record':{'Name':'Renamed','statecode':1,'statuscode':202}})
        assert 'error' not in result,result
        assert result['result']['name']=='Renamed'
        assert result['result']['statecode']==0 and result['result']['statuscode']==101


@pytest.mark.parametrize('artifact',['Code.gs','data-contract.json','conversion-ledger.json'])
def test_validator_rejects_state_contract_drift(ir,tmp_path,artifact):
    out=synthesize(ir,tmp_path/'generated')
    assert validate_project(out)['ok']
    path=out/artifact
    if artifact=='Code.gs':
        path.write_text(path.read_text().replace('"initialState": 0','"initialState": 1'))
    else:
        data=json.loads(path.read_text());data['dataverseStateModels']['Work']['initialState']=1
        path.write_text(json.dumps(data))
    assert not validate_project(out)['ok']
