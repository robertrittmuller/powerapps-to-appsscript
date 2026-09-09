import copy
from pathlib import Path

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fx import transpile
from pfx2gas.parse import parse
from pfx2gas.relationships import relationship_contracts
from pfx2gas.unpack import unpack
from test_data_contract import run_backend


@pytest.fixture
def relationship_ir():
    return analyze(parse(unpack(Path(__file__).parent / 'fixtures/fixtureRelationships.msapp')))


@pytest.fixture
def backend(relationship_ir, tmp_path):
    yield from run_backend(relationship_ir, tmp_path)


def change(call, source='Projects', key='users', base='project-two', target='user-two', remove=False):
    return call('api', source, 'unrelate' if remove else 'relate', {
        'relationship':key, 'base':{'id':base}, 'record':{'id':target}})


def test_native_relationship_aliases_preserve_schema_and_direction(relationship_ir):
    c = relationship_contracts(relationship_ir)
    assert c['Projects']['navigation']['users'] == c['Projects']['navigation']['msft_project_systemuser_members']
    assert c['Projects']['navigation']['users']['side'] == 1
    assert c['Users']['navigation']['projects']['side'] == 2
    assert c['Users']['keys'] == ['systemuserid','user']
    expr = next(control.properties['OnSelect'] for s in relationship_ir.screens for control in s.walk_controls()
                if control.name == 'AddMember')
    assert expr.translation_status == 'rule' and expr.approximations
    assert 'apiRelate(' in expr.js
    with pytest.raises(Exception, match='behavior formula'):
        transpile('Relate(First(Projects).Users, First(Users))')


def test_many_to_many_links_are_symmetric_persisted_and_do_not_mutate_records(backend):
    call = backend
    before = {ds: call('api',ds,'list',{})['result'] for ds in ['Projects','Users']}
    assert call('api','Projects','links',{})['result'] == []
    assert change(call) == {'result':None}
    assert change(call) == {'result':None}  # target retry is explicitly idempotent
    expected = [['msft_project_systemuser_members','project-two','user-two']]
    for ds in ['Projects','Users']:
        assert call('api',ds,'links',{})['result'] == expected
        assert call('api',ds,'list',{})['result'] == before[ds]
    assert change(call,base='project-one')['result'] is None
    assert len(call('api','Users','links',{})['result']) == 2
    assert change(call,'Users','projects','user-two','project-two',True) == {'result':None}
    assert call('api','Projects','links',{})['result'] == [['msft_project_systemuser_members','project-one','user-two']]
    assert change(call,'Users','projects','user-one','project-two') == {'result':None}
    assert ['msft_project_systemuser_members','project-two','user-one'] in call('api','Projects','links',{})['result']


def test_relationship_validation_and_write_failures_never_create_or_change_links(backend):
    call = backend
    before = {ds: call('api',ds,'list',{})['result'] for ds in ['Projects','Users']}
    for kwargs in [{'key':'invented'}, {'base':'missing'}, {'target':'missing'}, {'source':'Unexported'}]:
        assert 'error' in change(call, **kwargs)
    for record in [None, [], {}, {'id':'one','systemuserid':'two'}]:
        assert 'error' in call('api','Projects','relate',{'relationship':'users','base':{'id':'project-two'},'record':record})
    call('__failNextMutation')
    assert 'write failure' in change(call)['error']
    assert call('api','Projects','links',{})['result'] == []
    assert call('__lockState')['result']['held'] is False
    assert change(call) == {'result':None}
    call('__failNextMutation')
    assert 'write failure' in change(call,remove=True)['error']
    assert len(call('api','Projects','links',{})['result']) == 1
    for ds in before:
        assert call('api',ds,'list',{})['result'] == before[ds]
    call('__duplicateSourceRow','Users',2)
    assert 'ambiguous' in change(call)['error']
    assert len(call('api','Projects','links',{})['result']) == 1


def test_related_record_delete_requires_explicit_unlink_to_prevent_orphans(backend):
    call = backend
    change(call)
    for ds, identity in [('Projects','project-two'),('Users','user-two')]:
        for op,payload in [('remove',{'record':{'id':identity}}),('removeIf',{'ids':[identity]})]:
            assert 'Unrelate first' in call('api',ds,op,payload)['error']
    change(call,remove=True)
    assert call('api','Users','remove',{'record':{'id':'user-two'}})['result']['ok']


def test_ambiguous_or_unavailable_relationship_contracts_fail_explicitly(relationship_ir):
    project = relationship_ir.data_sources[0]
    rel = project.metadata['relationships']['ManyToManyRelationships'][0]
    other = copy.deepcopy(rel)
    other.update(SchemaName='other', Entity1NavigationPropertyName='other_members')
    project.metadata['relationships']['ManyToManyRelationships'].append(other)
    project.metadata['relationshipNames']['other_members'] = 'Users'
    assert 'ambiguous' in relationship_contracts(relationship_ir)['Projects']['navigation']['users']['error']
    relationship_ir.data_sources = [source for source in relationship_ir.data_sources if source.name != 'Users']
    assert 'exported tables' in relationship_contracts(relationship_ir)['Projects']['navigation']['msft_project_systemuser_members']['error']


def test_target_deletion_checks_incoming_links_when_reverse_navigation_was_not_exported(relationship_ir, tmp_path):
    users = next(source for source in relationship_ir.data_sources if source.name == 'Users')
    users.metadata['relationships']['ManyToManyRelationships'] = []
    generator = run_backend(relationship_ir, tmp_path)
    call = next(generator)
    try:
        change(call)
        assert len(call('api','Users','links',{})['result']) == 1
        assert 'Unrelate first' in call('api','Users','remove',{'record':{'id':'user-two'}})['error']
    finally:
        generator.close()


def test_relationship_refresh_reads_related_record_values_without_refreshing_other_sources(backend):
    call = backend
    change(call)
    snapshot = call('api','Projects','relationshipSnapshot',{})['result']
    assert [r['fullname'] for r in snapshot['targets']['Users']] == ['Grace']
    call('api','Users','patch',{'base':{'id':'user-two'},'record':{'fullname':'Grace Hopper'}})
    assert [r['fullname'] for r in call('api','Projects','relationshipSnapshot',{})['result']['targets']['Users']] == ['Grace Hopper']
    assert snapshot['targets']['Users'][0]['fullname'] == 'Grace'


def test_conflicting_schema_endpoints_are_not_joined(relationship_ir):
    users = next(source for source in relationship_ir.data_sources if source.name == 'Users')
    users.metadata['relationships']['ManyToManyRelationships'][0]['Entity1LogicalName'] = 'wrong_entity'
    spec = relationship_contracts(relationship_ir)['Projects']['navigation']['users']
    assert 'conflicting exported relationship schema' == spec['error']


@pytest.mark.parametrize('formula, expected', [
    ('Concurrent(If(addVote, Relate(idea.Users, user)), Unrelate(idea.Users, user))',True),
    ('Concurrent(Relate(idea.Users, user), Unrelate(otherIdea.Users, user))',False),
    ('Concurrent(If(addVote, Relate(idea.Users, user), Unrelate(idea.Users, user)), Set(done, true))',False),
])
def test_opposing_relationship_writes_in_different_concurrent_branches_are_ledgered(formula, expected):
    result = transpile(formula, behavior=True, control_names=set())
    assert any('Concurrent may Relate and Unrelate' in note for note in result.approximations) is expected
    assert result.js.count('apiRelate(') == 2  # diagnosis never rewrites the source actions


def test_generated_relationships_boot_with_empty_join_storage(relationship_ir, tmp_path):
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    result = simulate_project(synthesize(relationship_ir, tmp_path/'Boot'))
    assert result['visible'] == ['RelationshipScreen'] and not result['allConsoleErrors'], result


def test_one_to_many_moves_only_the_selected_child_and_preserves_required_links(backend):
    call = backend
    key = 'assigned__projects'
    assert change(call,'Users',key,'user-two','project-one') == {'result':None}
    rows = call('api','Projects','list',{})['result']
    assert rows[0]['owner']['user'] == 'user-two' and rows[0]['owner']['fullname'] == 'Grace'
    assert rows[1]['owner'] is None
    call('api','Users','patch',{'base':{'id':'user-two'},'record':{'fullname':'Grace Hopper'}})
    call('__failNextMutation')
    assert change(call,'Users',key,'user-two','project-one') == {'result':None}
    assert call('api','Projects','list',{})['result'] == rows  # retry neither rewrites snapshots nor grows self-references
    assert 'write failure' in change(call,'Users',key,'user-one','project-one')['error']
    snapshot = call('api','Users','relationshipSnapshot',{})['result']
    assert snapshot['parents'][key] == ['user-two',None]
    assert 'Unrelate first' in call('api','Users','remove',{'record':{'id':'user-two'}})['error']
    assert change(call,'Users',key,'user-one','project-one') == {'result':None}
    assert change(call,'Users',key,'user-two','project-one',True) == {'result':None}
    assert call('api','Projects','list',{})['result'][0]['owner']['user'] == 'user-one'
    call('__failNextMutation')
    assert 'write failure' in change(call,'Users',key,'user-one','project-one',True)['error']
    assert call('api','Projects','list',{})['result'][0]['owner']['user'] == 'user-one'
    assert change(call,'Users',key,'user-one','project-one',True) == {'result':None}
    assert call('api','Projects','list',{})['result'][0]['owner'] is None


@pytest.mark.parametrize('restriction', ['readonly','required'])
def test_one_to_many_honors_source_lookup_write_and_required_flags(relationship_ir, tmp_path, restriction):
    project = relationship_ir.data_sources[0]
    owner = next(field for field in project.fields if field.logical_name == 'msft_owner')
    project.sample_data[0]['owner'] = {'systemuserid':'user-two'}
    if restriction == 'readonly': owner.writable_update = False
    else: owner.required_level = 'SystemRequired'
    generator = run_backend(relationship_ir, tmp_path)
    call = next(generator)
    try:
        result = change(call,'Users','assigned__projects','user-two','project-one',True)
        assert ('not writable' if restriction == 'readonly' else 'system-required') in result['error']
        assert call('api','Users','relationshipSnapshot',{})['result']['parents']['assigned__projects'] == ['user-two',None]
    finally: generator.close()
