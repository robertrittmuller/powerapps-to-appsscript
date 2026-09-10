"""Generated-server ownership guards for source per-user views and settings."""
import pytest
from pfx2gas.ir import AppIR,DataSource,FieldDef,ScreenNode
from pfx2gas.synth.server import data_contracts
from test_data_contract import run_backend


def field(name,logical,kind='text',source_type=None,targets=None):
    return FieldDef(name=name,logical_name=logical,aliases=[logical],type=kind,
                    source_type=source_type,lookup_targets=targets or [])


@pytest.fixture
def owned_ir():
    return AppIR(name='OwnedSettings',start_screen='Main',screens=[ScreenNode(name='Main')],data_sources=[
        DataSource(name='Users',origin='dataverse',logical_name='systemuser',primary_key='User',
            metadata={'primaryNameAttribute':'fullname'},fields=[field('User','systemuserid'),
                field('Email','internalemailaddress'),field('Full Name','fullname')],sample_data=[
                    {'systemuserid':'user-a','internalemailaddress':'business.tester@example.test','fullname':'Ada'},
                    {'systemuserid':'user-b','internalemailaddress':'second@example.test','fullname':'Grace'}]),
        DataSource(name='Teams',origin='dataverse',logical_name='team',primary_key='Team',
            metadata={'primaryNameAttribute':'name'},fields=[field('Team','teamid'),field('Name','name')],
            sample_data=[{'teamid':'team-a','name':'Facilities'}]),
        DataSource(name='Settings',origin='dataverse',logical_name='test_setting',primary_key='Setting',fields=[
            field('Setting','test_settingid'),field('Name','test_name'),
            field('Owner','ownerid','lookup','Owner',['systemuser','team']),
            field('Owning User','owninguser','lookup','Lookup',['systemuser']),
            field('Owning Team','owningteam','lookup','Lookup',['team']),
            field('Owner Name','owneridname'),field('Owner Type','owneridtype')])])


@pytest.fixture
def owned_backend(owned_ir,tmp_path):
    yield from run_backend(owned_ir,tmp_path)


def test_default_owner_uses_google_caller_and_preserves_source_key_and_aliases(owned_backend):
    call=owned_backend
    first=call('api','Settings','create',{'record':{'Name':'My preference'}})['result']
    assert first['owner']['systemuserid']==first['owner']['user']=='user-a'
    assert first['owner']['fullname']=='Ada'
    assert first['owner']['internalemailaddress']=='business.tester@example.test'
    assert first['owninguser']==first['owner'] and first['owningteam'] is None
    assert first['owneridname']=='Ada' and first['owneridtype']=='systemuser'
    call('__setStorageIdentity','app-test','SECOND@EXAMPLE.TEST')
    second=call('api','Settings','patchRecord',{'record':{'test_settingid':'second-setting','Name':'Second user'}})['result']
    assert second['owner']['systemuserid']=='user-b'
    updated=call('api','Settings','patchRecord',{'record':{'test_settingid':first['test_settingid'],'Name':'Renamed'}})['result']
    assert updated['owner']['systemuserid']=='user-a' # editing does not take ownership
    assert call('api','Settings','list',{})['result']==[updated,second]


def test_explicit_user_and_team_assignment_recompute_derived_columns(owned_backend):
    call=owned_backend
    row=call('api','Settings','create',{'record':{'Name':'Assigned','ownerid':{'systemuserid':'user-b'},
        'owninguser':{'systemuserid':'user-a'},'owneridname':'Spoofed'}})['result']
    assert row['owner']['fullname']==row['owneridname']=='Grace'
    assert row['owninguser']['systemuserid']=='user-b' and row['owningteam'] is None
    row=call('api','Settings','patch',{'base':row,'record':{'ownerid':{'teamid':'team-a'}}})['result']
    assert row['owner']['teamid']=='team-a' and row['owneridname']=='Facilities'
    assert row['owningteam']==row['owner'] and row['owninguser'] is None
    assert row['owneridtype']=='team'
    # Read-only derived columns cannot replace an assignment on their own.
    patched=call('api','Settings','patch',{'base':row,'record':{'owninguser':{'systemuserid':'user-a'}}})['result']
    assert patched==row


@pytest.mark.parametrize('owner',[None,'',{'systemuserid':'missing'},
    {'systemuserid':'user-a','teamid':'team-a'}, {'systemuserid':'user-a','User':'user-b'}])
def test_invalid_owner_does_not_partially_create_or_update(owned_backend,owner):
    call=owned_backend
    row=call('api','Settings','create',{'record':{'Name':'Original'}})['result']
    before=call('api','Settings','list',{})['result']
    for op,payload in [('create',{'record':{'Name':'New','ownerid':owner}}),
                       ('patch',{'base':row,'record':{'Name':'Changed','ownerid':owner}})]:
        assert 'error' in call('api','Settings',op,payload)
        assert call('api','Settings','list',{})['result']==before


@pytest.mark.parametrize('email',['','missing@example.test'])
def test_unidentified_or_unmigrated_google_caller_cannot_create_owned_rows(owned_backend,email):
    call=owned_backend;call('__setStorageIdentity','app-test',email)
    assert 'Dataverse default ownership requires' in call('api','Settings','create',{'record':{'Name':'Blocked'}})['error']
    assert call('api','Settings','list',{})['result']==[]


def test_duplicate_user_mapping_and_failed_sheet_write_do_not_create_records(owned_backend):
    call=owned_backend
    call('__failNextMutation')
    assert 'error' in call('api','Settings','create',{'record':{'Name':'Failed'}})
    assert call('api','Settings','list',{})['result']==[]
    call('__duplicateSourceRow','Users',1)
    assert 'one migrated user' in call('api','Settings','create',{'record':{'Name':'Ambiguous'}})['error']
    assert call('api','Settings','list',{})['result']==[]


def test_owner_display_label_alone_does_not_enable_dataverse_ownership(owned_ir):
    settings=owned_ir.data_sources[-1]
    assert data_contracts(owned_ir)['Settings']['ownership']['owner']=='owner'
    settings.fields[2].source_type='Lookup';settings.fields[2].logical_name='custom_owner'
    assert 'ownership' not in data_contracts(owned_ir)['Settings']


def test_missing_user_table_fails_explicitly_but_preserves_explicit_team_assignment(owned_ir,tmp_path):
    owned_ir.data_sources=owned_ir.data_sources[1:]
    for call in run_backend(owned_ir,tmp_path):
        assert 'one migrated Users table' in call('api','Settings','create',{'record':{'Name':'No users'}})['error']
        result=call('api','Settings','create',{'record':{'Name':'Team-owned','ownerid':{'teamid':'team-a'}}})
        assert result['result']['owner']['teamid']=='team-a'


@pytest.mark.parametrize('artifact',['data-contract.json','conversion-ledger.json'])
def test_validator_rejects_silently_dropped_ownership_contract(owned_ir,tmp_path,artifact):
    import json
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project
    out=synthesize(owned_ir,tmp_path/'Owned')
    assert validate_project(out)['ok']
    document=json.loads((out/artifact).read_text());document.pop('dataverseOwnership')
    (out/artifact).write_text(json.dumps(document))
    verdict=validate_project(out)
    assert not verdict['ok'] and any('ownership adapter differs' in error for error in verdict['problems'])
