"""Execute the generated Google People adapter with strict API response fixtures."""
import copy
import json

import pytest

from pfx2gas.ir import DataSource
from test_data_contract import native_ir, run_backend

MAPPING={'users':[
    {'id':'source-ada','google_email':'ada@example.test','resource_name':'people/100',
     'aliases':['ada@old.example.test']},
    {'id':'source-grace','google_email':'grace@example.test','resource_name':'people/200','aliases':[]},
]}
ADA={'resourceName':'people/100','emailAddresses':[{'value':'ada@example.test'}],
     'names':[{'displayName':'Ada Lovelace','givenName':'Ada','familyName':'Lovelace','metadata':{'primary':True}}],
     'organizations':[{'name':'Analytical Engines','department':'Research','title':'Mathematician'}],
     'locations':[{'value':'London'}],'phoneNumbers':[{'type':'work','value':'+44 123'},{'type':'mobile','value':'+44 456'}],
     'photos':[{'url':'https://lh3.googleusercontent.com/photo-ada','default':False}]}
GRACE={'resourceName':'people/200','emailAddresses':[{'value':'grace@example.test'}],
       'names':[{'displayName':'Grace Hopper','givenName':'Grace','familyName':'Hopper'}],
       'photos':[{'url':'https://lh3.googleusercontent.com/default-grace','default':True}]}


@pytest.fixture
def directory_backend(native_ir,tmp_path):
    native_ir.data_sources.extend([DataSource(name=name,origin='service') for name in ['Office365Users','Microsoft365Users']])
    yield from run_backend(native_ir,tmp_path)


def op(call,operation,*args,service='Office365Users'):
    return call('connector',service,operation,list(args))


def responses(call,*pages):
    call('__peopleResponses',list(pages))


def imported(call):
    assert call('__importDirectory',MAPPING)=={'result':{'ok':True,'users':2}}


def test_missing_migration_and_unknown_identity_cannot_be_empty_success(directory_backend):
    call=directory_backend
    assert 'migration is not configured' in op(call,'SearchUser',{})['error']
    imported(call)
    assert 'already initialized' in call('__importDirectory',MAPPING)['error']
    assert 'migrated Google account mapping' in op(call,'UserProfileV2','unknown') ['error']
    assert call('__peopleRequests')['result']==[]
    assert 'unknown test endpoint' in call('importDirectory_',MAPPING)['error']
    assert 'not part' in call('api','__pfx2gas_directory','list',{})['error']


def test_profile_keeps_source_id_and_maps_current_google_fields(directory_backend):
    call=directory_backend;imported(call)
    expected={'id':'source-ada','mail':'ada@example.test','user_principal_name':'ada@example.test',
              'display_name':'Ada Lovelace','given_name':'Ada','surname':'Lovelace','job_title':'Mathematician',
              'department':'Research','company_name':'Analytical Engines','office_location':'London',
              'business_phones':['+44 123'],'mobile_phone':'+44 456'}
    for identity in ['source-ada','ADA@example.test','ada@old.example.test','people/100']:
        responses(call,{'method':'get','result':ADA})
        assert op(call,'UserProfileV2',identity)=={'result':expected}
        request=call('__peopleRequests')['result'][0]
        assert request['args'][0]=='people/100'
        assert request['args'][1]['sources']==['READ_SOURCE_TYPE_PROFILE']
    responses(call,{'method':'get','result':ADA})
    assert op(call,'UserProfileV2','source-ada',{'select':'id, displayName, department'},service='Microsoft365Users')=={
        'result':{'id':'source-ada','display_name':'Ada Lovelace','department':'Research'}}


def test_my_profile_uses_the_accessing_google_identity_and_retains_select_fields(directory_backend):
    call = directory_backend
    assert 'migration is not configured' in op(call,'MyProfileV2')['error']
    imported(call)
    call('__setStorageIdentity','script','ada@example.test')
    responses(call,{'method':'get','result':ADA})
    profile = op(call,'MyProfileV2')['result']
    assert profile['id'] == 'source-ada' and profile['mail'] == 'ada@example.test'
    assert call('__peopleRequests')['result'][0]['args'][0] == 'people/100'
    call('__setStorageIdentity','script','grace@example.test')
    responses(call,{'method':'get','result':GRACE})
    assert op(call,'MyProfileV2',{'select':'mail,displayName'}, service='Microsoft365Users') == {
        'result':{'mail':'grace@example.test','display_name':'Grace Hopper'}}
    call('__setStorageIdentity','script','unknown@example.test')
    assert 'migrated Google account mapping' in op(call,'MyProfileV2')['error']
    call('__setEffectiveUser','owner@example.test')
    assert 'owner-delegated' in op(call,'MyProfileV2')['error']


def test_search_pages_and_top_preserve_records_and_exact_request_contract(directory_backend):
    call=directory_backend;imported(call)
    responses(call,{'method':'searchDirectoryPeople','result':{'people':[ADA],'nextPageToken':'page-two'}},
              {'method':'searchDirectoryPeople','result':{'people':[GRACE]}})
    result=op(call,'SearchUser',{'search_term':'a'})
    assert [r['id'] for r in result['result']]==['source-ada','source-grace']
    requests=call('__peopleRequests')['result']
    assert requests[0]['args'][0]['query']=='a' and requests[0]['args'][0]['pageSize']==500
    assert requests[0]['args'][0]['sources']==['DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE']
    assert requests[1]['args'][0]['pageToken']=='page-two'
    responses(call,{'method':'listDirectoryPeople','result':{'people':[ADA],'nextPageToken':'more'}})
    assert len(op(call,'SearchUser',{'top':1})['result'])==1
    assert call('__peopleRequests')['result'][0]['args'][0]['pageSize']==1
    responses(call,{'method':'searchDirectoryPeople','result':{}})
    assert op(call,'SearchUser',{'search_term':'nobody'})=={'result':[]}


def test_photo_absence_is_blank_and_custom_photo_is_google_url(directory_backend):
    call=directory_backend;imported(call)
    for person,identity,expected in [(ADA,'source-ada','https://lh3.googleusercontent.com/photo-ada'),(GRACE,'source-grace',None)]:
        responses(call,{'method':'get','result':person})
        assert op(call,'UserPhotoV2',identity)=={'result':expected}
    invalid=copy.deepcopy(ADA);invalid['photos'][0]['url']='javascript:alert(1)'
    responses(call,{'method':'get','result':invalid})
    assert 'Invalid Google profile photo URL' in op(call,'UserPhotoV2','source-ada')['error']


def test_native_authorization_failures_and_pagination_errors_remain_errors(directory_backend):
    call=directory_backend;imported(call)
    responses(call,{'error':'403 Directory sharing is disabled'})
    assert '403 Directory sharing is disabled' in op(call,'SearchUser',{'search_term':'Ada'})['error']
    responses(call,{'method':'searchDirectoryPeople','result':{'people':[ADA],'nextPageToken':'same'}},
              {'method':'searchDirectoryPeople','result':{'people':[],'nextPageToken':'same'}})
    assert 'repeated' in op(call,'SearchUser',{'search_term':'Ada'})['error']
    assert call('__lockState')['result']['held'] is False


def test_directory_cannot_borrow_an_owners_authorization(directory_backend):
    call=directory_backend;imported(call)
    call('__setEffectiveUser','owner@example.test')
    assert 'owner-delegated' in op(call,'SearchUser',{})['error']
    assert call('__peopleRequests')['result']==[]
    call('__setEffectiveUser',None)
    call('__setStorageIdentity','script','')
    assert 'identified accessing Google user' in op(call,'UserProfileV2','source-ada')['error']


@pytest.mark.parametrize('change',[
    lambda p:p.update(resourceName='people/unknown'),
    lambda p:p.update(emailAddresses=[{'value':'wrong@example.test'}]),
    lambda p:p.update(metadata={'deleted':True}),
    lambda p:p.update(names=[{'displayName':'One'},{'displayName':'Two'}]),
])
def test_ambiguous_or_mismatched_google_identity_is_not_used(directory_backend,change):
    call=directory_backend;imported(call)
    person=copy.deepcopy(ADA);change(person)
    responses(call,{'method':'get','result':person})
    assert 'error' in op(call,'UserProfileV2','source-ada')


def test_manifest_adds_only_the_required_native_service_and_scopes(native_ir):
    from pfx2gas.synth.server import render_manifest
    baseline=json.loads(render_manifest(native_ir))
    assert baseline['dependencies']=={}
    assert 'https://www.googleapis.com/auth/userinfo.email' in baseline['oauthScopes']
    native_ir.data_sources.append(DataSource(name='Office365Users',origin='service'))
    manifest=json.loads(render_manifest(native_ir))
    assert manifest['dependencies']['enabledAdvancedServices']==[{'userSymbol':'People','serviceId':'peopleapi','version':'v1'}]
    assert set(manifest['oauthScopes'])==set(baseline['oauthScopes'])|{'https://www.googleapis.com/auth/directory.readonly'}


@pytest.mark.parametrize('change',[
    lambda d:d.pop('users'),
    lambda d:d.update(unreviewed=True),
    lambda d:d['users'][1].update(aliases=['SOURCE-ADA']),
    lambda d:d['users'][1].update(google_email='ADA@example.test'),
    lambda d:d['users'][0].update(resource_name='people/me'),
    lambda d:d['users'][0].update(aliases=[None]),
])
def test_invalid_migration_leaves_store_ready_for_valid_import(directory_backend,change):
    data=copy.deepcopy(MAPPING);change(data)
    assert 'error' in directory_backend('__importDirectory',data)
    imported(directory_backend)


def test_directory_changes_and_malformed_fields_do_not_produce_ambiguous_results(directory_backend):
    call=directory_backend;imported(call)
    responses(call,{'method':'listDirectoryPeople','result':{'people':[ADA],'nextPageToken':'next'}},
              {'method':'listDirectoryPeople','result':{'people':[ADA]}})
    assert 'Repeated Google directory person' in op(call,'SearchUser')['error']
    for field in ['names','locations','organizations','photos','phoneNumbers','emailAddresses']:
        person=copy.deepcopy(ADA);person[field]=[None]
        responses(call,{'method':'get','result':person})
        operation='UserPhotoV2' if field=='photos' else 'UserProfileV2'
        assert 'error' in op(call,operation,'source-ada')


def test_native_primary_fields_are_selected_independently_of_array_order(directory_backend):
    call=directory_backend;imported(call)
    person=copy.deepcopy(ADA)
    person['names'].insert(0,{'displayName':'Alternate'})
    person['phoneNumbers'] += [{'type':'mobile','value':'+44 999','metadata':{'primary':True}}]
    responses(call,{'method':'get','result':person})
    profile=op(call,'UserProfileV2','source-ada')['result']
    assert profile['display_name']=='Ada Lovelace' and profile['mobile_phone']=='+44 999'
    person['phoneNumbers'][-1].pop('metadata')
    responses(call,{'method':'get','result':person})
    assert 'Ambiguous Google person primary field' in op(call,'UserProfileV2','source-ada')['error']


def test_directory_migration_template_remains_private_and_preserves_operator_edits(native_ir,tmp_path):
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project
    native_ir.data_sources.append(DataSource(name='Microsoft365Users',origin='service'))
    project=synthesize(native_ir,tmp_path/'Directory')
    entry=project/'DirectoryMigration.gs'
    assert 'function migrateDirectory_()' in entry.read_text()
    assert 'var migration = null;' in entry.read_text()
    entry.write_text(entry.read_text()+'\n// reviewed operator edit\n')
    synthesize(native_ir,project)
    assert 'reviewed operator edit' in entry.read_text()
    assert validate_project(project)['ok']
    entry.write_text('function broken( {')
    assert not validate_project(project)['ok']
