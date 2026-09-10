"""Execute the generated Google Sheets task-board adapter, including failures."""
import copy

import pytest

from pfx2gas.ir import DataSource
from test_data_contract import native_ir, run_backend

MIGRATION = {
    'users':[{'id':'user-a','email':'business.tester@example.test'},
             {'id':'user-b','email':'second@example.test'},
             {'id':'user-c','email':'outside@example.test'}],
    'plans':[{'id':'plan-a','title':'Shared inspections','group_id':'group-a','members':['user-a','user-b']},
             {'id':'plan-secret','title':'Restricted','group_id':'group-a','members':['user-c']}],
    'buckets':[{'id':'bucket-a','name':'Repairs','plan_id':'plan-a'},
               {'id':'bucket-secret','name':'Hidden','plan_id':'plan-secret'}],
    'tasks':[{'id':'task-a','title':'Repair door','plan_id':'plan-a','bucket_id':'bucket-a',
              'percent_complete':50,'assignees':['user-a','user-b'],'description':'Existing notes',
              'due_date_time':'2026-09-10T16:30:00Z'},
             {'id':'task-secret','title':'Private task','plan_id':'plan-secret','bucket_id':'bucket-secret',
              'percent_complete':0,'assignees':['user-c'],'description':''}]
}


@pytest.fixture
def planner_backend(native_ir,tmp_path):
    native_ir.data_sources.append(DataSource(name='Planner',origin='service'))
    yield from run_backend(native_ir,tmp_path)


def call_op(call,op,*args):
    result=call('connector','Planner',op,list(args))
    assert 'error' not in result,result
    return result['result']


def test_missing_migration_cannot_report_empty_success(planner_backend):
    call=planner_backend
    assert 'migration is not configured' in call('connector','Planner','ListMyPlansV2',[])['error']
    assert call('__importPlanner',MIGRATION)['result']=={'ok':True,'plans':2,'tasks':2}
    assert 'already migrated' in call('__importPlanner',MIGRATION)['error']


def test_board_lists_preserve_membership_source_ids_and_data(planner_backend):
    call=planner_backend
    assert 'result' in call('__importPlanner',MIGRATION)
    expected=[{'id':'plan-a','title':'Shared inspections','owner':'group-a'}]
    assert call_op(call,'ListMyPlansV2')['value']==expected
    assert call_op(call,'ListGroupPlans','group-a')['value']==expected
    assert call_op(call,'ListGroupPlans','unknown')['value']==[]
    assert call_op(call,'ListBucketsV3','plan-a','group-a')['value']==[{'id':'bucket-a','plan_id':'plan-a','name':'Repairs'}]
    tasks=call_op(call,'ListTasksV3','plan-a','group-a')['value']
    assert tasks==call_op(call,'ListTasks','plan-a')['value']==call_op(call,'ListMyTasks')['value']
    assert tasks[0]['id']=='task-a' and tasks[0]['percent_complete']==50
    assert tasks[0]['due_date_time']=='2026-09-10T16:30:00.000Z'
    assert [a['user_id'] for a in tasks[0]['assignments']]==['user-a','user-b']
    for op,args in [('ListTasks',['plan-secret']),('ListBucketsV3',['plan-secret','group-a']),
                    ('CreateTaskV3',['group-a','plan-secret','Forbidden']),
                    ('UpdateTaskDetails',['task-secret',{'description':'Forbidden'}])]:
        assert 'access is denied' in call('connector','Planner',op,args)['error']


def test_create_assign_and_update_description_are_persisted(planner_backend):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    task=call_op(call,'CreateTaskV3','group-a','plan-a','Fix window',{
        'bucket_id':'bucket-a','due_date_time':'2026-09-12T15:45:00.0000000-04:00',
        'assignments':'SECOND@example.test;user-a;user-a;'})
    assert task['title']=='Fix window' and task['percent_complete']==0
    assert task['due_date_time']=='2026-09-12T19:45:00.000Z'
    assert [a['user_id'] for a in task['assignments']]==['user-b','user-a']
    assert call_op(call,'UpdateTaskDetails',task['id'],{'description':'Line one\nLine two'})=={
        'id':task['id'],'description':'Line one\nLine two'}
    persisted=call_op(call,'ListTasks','plan-a')['value'][-1]
    assert persisted['id']==task['id'] and persisted['has_description'] is True
    assert call('__plannerSnapshot')['result']['tasks'][-1]['description']=='Line one\nLine two'
    assert call('__setup')['result']=='already initialized'
    assert call_op(call,'ListTasks','plan-a')['value'][-1]==persisted


@pytest.mark.parametrize('options',[
    {'bucket_id':'bucket-secret'}, {'assignments':'outside@example.test'},
    {'assignments':'unknown@example.test'}, {'assignments':['user-a']},
    {'due_date_time':'2026-09-12'}, {'unrecognized':'must not be lost'},
    {'due_date_time':'2026-02-30T12:00:00Z'}, {'due_date_time':'2026-09-12T24:00:00Z'},
    {'bucket_id':False}, {'bucket_id':0},
    {'due_date_time':'2026-09-12T15:45:00.0000001Z'}, {'due_date_time':'9999-12-31T23:59:59-01:00'},
])
def test_invalid_task_inputs_make_no_write(planner_backend,options):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    before=call_op(call,'ListTasks','plan-a')
    assert 'error' in call('connector','Planner','CreateTaskV3',['group-a','plan-a','Bad task',options])
    assert call_op(call,'ListTasks','plan-a')==before


def test_mutation_failure_releases_lock_and_preserves_prior_records(planner_backend):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    call('__failNextMutation')
    assert 'Simulated Sheets write failure' in call('connector','Planner','CreateTaskV3',['group-a','plan-a','Retry me'])['error']
    assert len(call_op(call,'ListTasks','plan-a')['value'])==1
    call_op(call,'CreateTaskV3','group-a','plan-a','Retry me')
    call('__failNextMutation')
    assert 'Simulated Sheets write failure' in call('connector','Planner','UpdateTaskDetails',['task-a',{'description':'Lost'}])['error']
    assert call('__plannerSnapshot')['result']['tasks'][0]['description']=='Existing notes'
    assert call('__lockState')['result']['held'] is False


def test_invalid_migration_is_validated_before_storage_write(planner_backend):
    data=copy.deepcopy(MIGRATION)
    data['tasks'][0]['assignees']=['user-c']
    assert 'assignee is not a plan member' in planner_backend('__importPlanner',data)['error']
    assert 'migration is not configured' in planner_backend('connector','Planner','ListMyPlansV2',[])['error']
    assert 'result' in planner_backend('__importPlanner',MIGRATION)


def test_unknown_operations_and_arity_are_rejected(planner_backend):
    assert 'not configured' in planner_backend('connector','Planner','__importPlanner',[])['error']
    assert 'not configured' in planner_backend('connector','MicrosoftTeams','GetAllTeams',[])['error']
    assert 'Wrong number' in planner_backend('connector','Planner','CreateTaskV3',[])['error']


def test_identity_and_private_storage_are_not_browser_authority(planner_backend):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    for email,message in [('', 'identified Google session'), ('unmapped@example.test','migrated Google user mapping')]:
        call('__setStorageIdentity','test-script',email)
        assert message in call('connector','Planner','ListMyPlansV2',[])['error']
    call('__setStorageIdentity','test-script','outside@example.test')
    assert [p['id'] for p in call_op(call,'ListMyPlansV2')['value']]==['plan-secret']
    assert 'access is denied' in call('connector','Planner','ListTasks',['plan-a'])['error']
    assert 'unknown test endpoint' in call('importPlanner_',MIGRATION)['error']
    assert 'not part' in call('api','__pfx2gas_planner','list',{})['error']


def test_oversized_description_rejected_before_write(planner_backend):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    assert 'storage limit' in call('connector','Planner','UpdateTaskDetails',['task-a',{'description':'x'*50000}])['error']
    assert call('__plannerSnapshot')['result']['tasks'][0]['description']=='Existing notes'


def test_connector_compilation_is_declared_arity_checked_and_ledgered(native_ir):
    from pfx2gas.fx import transpile
    from pfx2gas.fx.lexer import FxSyntaxError
    from pfx2gas.services import service_contracts
    native_ir.data_sources.append(DataSource(name='Planner',origin='service'))
    adapters=service_contracts(native_ir)
    result=transpile('Planner.CreateTaskV3("group-a", "plan-a", "Title", {bucketId: "bucket-a"}).id',
                     behavior=True,service_adapters=adapters)
    assert 'await FXRuntime.connectorCall' in result.js and 'bucket_id:' in result.js
    assert not result.unmapped and any('Google Sheets' in item for item in result.approximations)
    result=transpile('First(Planner.ListTasksV3("plan-a", "group-a").value)._assignments',service_adapters=adapters)
    assert 'FXRuntime.connectorRead' in result.js and "'assignments'" in result.js
    for raw in ['Planner.CreateTaskV3("g","p","t")','Planner.ListTasksV3("p")']:
        with pytest.raises(FxSyntaxError):
            transpile(raw,service_adapters=adapters)
    assert transpile('Planner.ListMyPlansV2()').unmapped==['Planner.ListMyPlansV2']
    assert transpile('Planner.DeleteTask("task-a")',behavior=True,service_adapters=adapters).unmapped==['Planner.DeleteTask']


def test_corrupt_private_storage_is_not_a_successful_empty_board(planner_backend):
    call=planner_backend
    call('__importPlanner',MIGRATION)
    call('__duplicateSourceRow','__pfx2gas_planner',1)
    assert 'Duplicate Planner storage key' in call('connector','Planner','ListMyPlansV2',[])['error']


def test_migration_template_is_private_validated_and_operator_edits_survive(native_ir,tmp_path):
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project
    native_ir.data_sources.append(DataSource(name='Planner',origin='service'))
    project=synthesize(native_ir,tmp_path/'Planner')
    entry=project/'PlannerMigration.gs'
    assert 'function migratePlanner_()' in entry.read_text()
    assert 'var migration = null;' in entry.read_text()
    entry.write_text(entry.read_text()+'\n// reviewed operator edit\n')
    synthesize(native_ir,project)
    assert 'reviewed operator edit' in entry.read_text()
    entry.write_text('function broken( {')
    assert not validate_project(project)['ok']
