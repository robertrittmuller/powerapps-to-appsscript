"""Runtime evidence for the generated native Google Chat adapter; no live posts."""
import copy
import json

import pytest

from pfx2gas.ir import DataSource
from test_data_contract import native_ir, run_backend

MAPPING={'teams':[{'id':'team-a','space_name':'spaces/ANCHOR'}, {'id':'team-b','space_name':'spaces/OTHER'}],
         'channels':[{'id':'general','team_id':'team-a','space_name':'spaces/ANCHOR'},
                     {'id':'repairs','team_id':'team-a','space_name':'spaces/REPAIRS'},
                     {'id':'general','team_id':'team-b','space_name':'spaces/OTHER'}]}
SPACES=[{'name':'spaces/ANCHOR','spaceType':'SPACE','displayName':'Facilities',
         'spaceDetails':{'description':'Building operations'},'spaceUri':'https://chat.google.com/room/ANCHOR'},
        {'name':'spaces/REPAIRS','spaceType':'SPACE','displayName':'Repairs'},
        {'name':'spaces/UNRELATED','spaceType':'SPACE','displayName':'Unrelated space'}]


@pytest.fixture
def chat_backend(native_ir,tmp_path):
    native_ir.data_sources.append(DataSource(name='MicrosoftTeams',origin='service'))
    yield from run_backend(native_ir,tmp_path)


def op(call,operation,*args):
    return call('connector','MicrosoftTeams',operation,list(args))


def responses(call,*items):
    call('__chatResponses',list(items))


def imported(call):
    assert call('__importChat',MAPPING)=={'result':{'ok':True,'teams':2,'channels':3}}


def post(call,content,kind='html',options=None):
    return op(call,'PostMessageToChannelV3','team-a','repairs',{'content':content,'content_type':kind},options or {})


def ready_post(call):
    responses(call,{'method':'list','result':{'spaces':SPACES}},
              {'method':'create','result':{'name':'spaces/REPAIRS/messages/created.1'}})


def test_missing_migration_private_storage_and_dispatch_whitelist(chat_backend):
    call=chat_backend
    assert 'migration is not configured' in op(call,'GetAllTeams')['error']
    imported(call)
    assert 'already initialized' in call('__importChat',MAPPING)['error']
    assert 'not configured' in op(call,'DeleteMessage','x')['error']
    assert 'Wrong number' in op(call,'GetAllTeams',{})['error']
    assert 'unknown test endpoint' in call('importChat_',MAPPING)['error']
    assert 'not part' in call('api','__pfx2gas_chat','list',{})['error']
    assert call('__chatRequests')['result']==[]


def test_joined_team_and_channel_selectors_keep_source_ids_and_native_names(chat_backend):
    call=chat_backend;imported(call)
    responses(call,{'method':'list','result':{'spaces':SPACES[:1],'nextPageToken':'more'}},
              {'method':'list','result':{'spaces':SPACES[1:]}})
    result=op(call,'GetAllTeams')['result']['value']
    assert result==[{'id':'team-a','display_name':'Facilities','description':'Building operations',
                     'web_url':'https://chat.google.com/room/ANCHOR'}]
    assert call('__chatRequests')['result']==[
        {'method':'list','args':[{'pageSize':1000,'filter':'spaceType = "SPACE"'}]},
        {'method':'list','args':[{'pageSize':1000,'filter':'spaceType = "SPACE"','pageToken':'more'}]}]
    responses(call,{'method':'list','result':{'spaces':SPACES}})
    assert op(call,'GetTeam','team-a')=={'result':result[0]}
    responses(call,{'method':'list','result':{'spaces':SPACES}})
    assert [(r['id'],r['display_name']) for r in op(call,'GetChannelsForGroup','team-a')['result']['value']]==[
        ('general','Facilities'),('repairs','Repairs')]
    responses(call,{'method':'list','result':{}})
    assert op(call,'GetAllTeams')=={'result':{'value':[]}}


def test_native_membership_checks_both_team_anchor_and_channel_before_posting(chat_backend):
    call=chat_backend;imported(call)
    for spaces in [SPACES[:1],SPACES[1:],[]]:
        responses(call,{'method':'list','result':{'spaces':spaces}})
        assert 'Access denied' in post(call,'repair')['error']
        assert [r['method'] for r in call('__chatRequests')['result']]==['list']
    responses(call,{'method':'list','result':{'spaces':SPACES}})
    assert 'Access denied' in op(call,'GetTeam','team-b')['error']
    responses(call)
    assert 'migrated Google Chat anchor' in op(call,'GetTeam','spaces/ANCHOR')['error']
    assert 'mapping for this team' in op(call,'PostMessageToChannelV3','team-a','missing',{'content':'x'})['error']
    assert call('__chatRequests')['result']==[]


def test_source_notification_html_is_translated_and_posted_once(chat_backend):
    call=chat_backend;imported(call);ready_post(call)
    content='A new campaign has been created!<br><b>Start Date: </b>September 9<br><b>Description</b><br>Repair &amp; maintain'
    assert post(call,content,options={'subject':'Maintenance'})=={'result':{'id':'spaces/REPAIRS/messages/created.1'}}
    requests=call('__chatRequests')['result']
    assert [r['method'] for r in requests]==['list','create']
    message,space,options=requests[1]['args']
    assert message=={'text':'**Maintenance**\n\nA new campaign has been created\\!  \n**Start Date:** September 9  \n**Description**  \nRepair \\& maintain',
                     'markupSyntax':'MARKUP_SYNTAX_MARKDOWN'}
    assert space=='spaces/REPAIRS' and options=={'requestId':'test-record-1'}
    assert len(call('__chatMessages')['result'])==1
    assert call('__lockState')['result']['held'] is False


@pytest.mark.parametrize(('content','kind','expected'),[
    ('A new inspection!<br></br><b>For the Location: </b>Building A','html',
     'A new inspection\\!  \n**For the Location:** Building A'),
    ('<p>One</p><div><i>Two</i> &lt;users/all&gt; &#x1f527;</div>','html',
     'One\n\n*Two* \\<users/all\\> 🔧'),
    ('<a href="https://example.test/repair(a)?x=1&amp;y=2">Repair [guide]</a>','html',
     '[Repair \\[guide\\]](https://example.test/repair%28a%29?x=1&amp;y=2)'),
    ('**plain**\r\n<users/all> &amp;','text','\\*\\*plain\\*\\*  \n\\<users/all\\> \\&amp;'),
])
def test_formatting_subset_and_literal_text_remain_distinct(chat_backend,content,kind,expected):
    call=chat_backend;imported(call);ready_post(call)
    assert 'result' in post(call,content,kind)
    assert call('__chatRequests')['result'][1]['args'][0]['text']==expected


@pytest.mark.parametrize('content',[
    '<script>alert(1)</script>','<img src="x">','<at>Everyone</at>',
    '<b style="color:red">red</b>','<a href="javascript:alert(1)">x</a>',
    '<a href="https://example.test" title="lost">x</a>','<b>unclosed',
    '<b><i>nested</i></b>','<b>line<br>break</b>','x &madeup;',
    '&#xD800;','<b>bad</i>','<!-- hidden -->','<b/>','<ul><li>Item</li></ul>',
])
def test_unsupported_html_fails_before_any_native_request(chat_backend,content):
    call=chat_backend;imported(call)
    assert 'error' in post(call,content)
    assert call('__chatRequests')['result']==[]


def test_native_byte_limit_counts_utf8_and_rejects_unknown_message_options(chat_backend):
    call=chat_backend;imported(call)
    assert '32000-byte' in post(call,'🔧'*8000,'text')['error']
    assert 'Unsupported Chat message options field' in post(call,'x',options={'attachments':[]})['error']
    assert 'single-line' in post(call,'x',options={'subject':'one\ntwo'})['error']
    assert 'empty' in post(call,'')['error']
    assert call('__chatRequests')['result']==[]
    ready_post(call)
    assert 'result' in post(call,'🔧'*7900,'text')


@pytest.mark.parametrize('change',[
    lambda d:d.pop('teams'),
    lambda d:d.update(unreviewed=True),
    lambda d:d['teams'][1].update(id='team-a'),
    lambda d:d['teams'][1].update(space_name='spaces/ANCHOR'),
    lambda d:d['channels'][1].update(space_name='spaces/OTHER'),
    lambda d:d['channels'][1].update(space_name='spaces/ANCHOR'),
    lambda d:d['channels'][1].update(team_id='missing'),
    lambda d:d['channels'][1].update(id='general'),
    lambda d:d['channels'][1].update(space_name='spaces/REPAIRS/messages/x'),
])
def test_invalid_migration_is_atomic_and_recoverable(chat_backend,change):
    data=copy.deepcopy(MAPPING);change(data)
    assert 'error' in chat_backend('__importChat',data)
    imported(chat_backend)


def test_owner_identity_and_native_errors_cannot_produce_success(chat_backend):
    call=chat_backend;imported(call)
    call('__setEffectiveUser','owner@example.test')
    assert 'owner-delegated' in op(call,'GetAllTeams')['error']
    assert call('__chatRequests')['result']==[]
    call('__setEffectiveUser',None)
    responses(call,{'method':'list','error':'403 Google Chat disabled'})
    assert '403 Google Chat disabled' in op(call,'GetAllTeams')['error']
    responses(call,{'method':'list','result':{'spaces':SPACES}}, {'method':'create','error':'429 Chat quota'})
    assert '429 Chat quota' in post(call,'x')['error']
    assert len(call('__chatRequests')['result'])==2 and call('__chatMessages')['result']==[]
    responses(call,{'method':'list','result':{'spaces':SPACES}}, {'method':'create','result':{'name':'spaces/WRONG/messages/x'}})
    assert 'delivery may have succeeded' in post(call,'x')['error']
    assert len(call('__chatRequests')['result'])==2


def test_pagination_changes_never_silently_truncate_spaces(chat_backend):
    call=chat_backend;imported(call)
    for pages,expected in [
        ([{'spaces':SPACES,'nextPageToken':'same'},{'nextPageToken':'same'}],'repeated Google Chat page token'),
        ([{'spaces':SPACES,'nextPageToken':'more'},{'spaces':SPACES}],'Repeated Google Chat space'),
        ([{'spaces':[{'name':'spaces/ANCHOR','spaceType':'DIRECT_MESSAGE','displayName':'Wrong'}]}],'Invalid named Google Chat space'),
    ]:
        responses(call,*[{'method':'list','result':page} for page in pages])
        assert expected in op(call,'GetAllTeams')['error']


def test_chat_manifest_coexists_with_people_and_migration_edits_survive(native_ir,tmp_path):
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project
    native_ir.data_sources.extend([DataSource(name=name,origin='service') for name in ['MicrosoftTeams','Office365Users']])
    project=synthesize(native_ir,tmp_path/'Chat')
    manifest=json.loads((project/'appsscript.json').read_text())
    assert manifest['dependencies']['enabledAdvancedServices']==[
        {'userSymbol':'People','serviceId':'peopleapi','version':'v1'},
        {'userSymbol':'Chat','serviceId':'chat','version':'v1'}]
    assert {'https://www.googleapis.com/auth/chat.spaces.readonly','https://www.googleapis.com/auth/chat.messages.create'}<=set(manifest['oauthScopes'])
    entry=project/'ChatMigration.gs'
    assert 'function migrateChat_()' in entry.read_text()
    entry.write_text(entry.read_text()+'\n// reviewed mapping\n')
    synthesize(native_ir,project)
    assert 'reviewed mapping' in entry.read_text() and validate_project(project)['ok']
    entry.write_text('function broken( {')
    assert not validate_project(project)['ok']


def test_chat_compilation_is_declared_guarded_and_ledgered(native_ir):
    from pfx2gas.fx import transpile
    from pfx2gas.fx.lexer import FxSyntaxError
    from pfx2gas.services import service_contracts
    native_ir.data_sources.append(DataSource(name='MicrosoftTeams',origin='service'))
    adapters=service_contracts(native_ir)
    value=transpile('MicrosoftTeams.GetAllTeams().value',service_adapters=adapters)
    assert not value.unmapped and 'FXRuntime.connectorRead' in value.js
    assert any('Google Chat' in note for note in value.approximations)
    raw='MicrosoftTeams.PostMessageToChannelV3("team","channel",{content:"Idea",contentType:"html"},{subject:"Title"}).id'
    behavior=transpile(raw,behavior=True,service_adapters=adapters)
    assert not behavior.unmapped and 'await FXRuntime.connectorCall' in behavior.js and 'content_type:' in behavior.js
    for invalid in [raw,'MicrosoftTeams.GetTeam()','MicrosoftTeams.GetChannelsForGroup("team", {})']:
        with pytest.raises(FxSyntaxError): transpile(invalid,service_adapters=adapters)
    assert transpile('MicrosoftTeams.GetAllTeams()').unmapped==['MicrosoftTeams.GetAllTeams']


def test_corrupt_mapping_storage_and_failed_import_are_not_empty_success(chat_backend):
    call=chat_backend
    call('__failNextMutation')
    assert 'Simulated Sheets write failure' in call('__importChat',MAPPING)['error']
    assert 'migration is not configured' in op(call,'GetAllTeams')['error']
    imported(call)
    call('__setup')
    call('__duplicateSourceRow','__pfx2gas_chat',1)
    assert 'Duplicate Chat storage key' in op(call,'GetAllTeams')['error']
    assert call('__chatRequests')['result']==[]
