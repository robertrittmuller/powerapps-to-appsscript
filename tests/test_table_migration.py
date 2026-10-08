import pytest

from pfx2gas.ir import AppIR, DataSource, FieldDef
from pfx2gas.synth.build import synthesize
from test_data_contract import run_backend


def migration_ir():
    return AppIR(name='Migration',data_sources=[DataSource(name='Users',origin='dataverse',
        primary_key='User',fields=[
            FieldDef(name='User',aliases=['systemuserid']),
            FieldDef(name='Email',required_level='SystemRequired'),
            FieldDef(name='Identity',type='number',required_level='SystemRequired',
                     writable_create=False,writable_update=False),
            FieldDef(name='Provisioned',type='date',writable_create=False,writable_update=False),
            FieldDef(name='Computed',type='number',calculated=True),
            FieldDef(name='Enabled',type='bool',has_default=True,default_value=True)])])


def test_import_preserves_source_readonly_values_without_inventing_defaults(tmp_path):
    for call in run_backend(migration_ir(),tmp_path):
        response=call('__importRows','Users',[{'systemuserid':'one','Email':'one@example.test',
            'Identity':0,'Provisioned':'2026-03-01T12:00:00Z','Computed':8}])
        assert response=={'result':{'ok':True,'source':'Users','rows':1}}
        row=call('api','Users','list',{})['result'][0]
        assert row['identity']==0 and row['computed']==8 and row['enabled'] is None
        assert row['provisioned']=='2026-03-01T12:00:00.000Z'
        updated=call('api','Users','patch',{'base':{'systemuserid':'one'},
            'record':{'Email':'edited@example.test','Identity':2,'Computed':3}})['result']
        assert updated['email']=='edited@example.test' and updated['identity']==0 and updated['computed']==8
        assert 'error' in call('api','Users','create',{'record':{'User':'two','Email':'two@example.test','Identity':1}})
        assert 'error' in call('api','Users','importRows',{'records':[]})
        assert 'error' in call('importTableRows_','Users',[])


@pytest.mark.parametrize('invalid',[
    {'User':'two','Email':'two@example.test'},
    {'User':'two','Email':'two@example.test','Identity':'bad'},
    {'User':'one','Email':'two@example.test','Identity':2},
    {'User':'two','systemuserid':'other','Email':'two@example.test','Identity':2},
    {'User':'two','Email':'two@example.test','Identity':2,'Unknown':3},
])
def test_entire_import_validates_before_any_row_is_written(tmp_path,invalid):
    for call in run_backend(migration_ir(),tmp_path):
        assert 'error' in call('__importRows','Users',[
            {'User':'one','Email':'one@example.test','Identity':1},invalid])
        assert call('api','Users','list',{})['result']==[]


def test_import_rejects_repeated_keys_and_releases_lock_after_failure(tmp_path):
    for call in run_backend(migration_ir(),tmp_path):
        record={'User':'one','Email':'one@example.test','Identity':1}
        assert call('__importRows','Users',[record])['result']['rows']==1
        assert 'error' in call('__importRows','Users',[{'User':'two','Email':'two@example.test','Identity':2},record])
        assert len(call('api','Users','list',{})['result'])==1
        assert call('__importRows','Users',[{'User':'two','Email':'two@example.test','Identity':2}])['result']['rows']==1


def test_operator_migration_file_survives_reconversion(tmp_path):
    out=synthesize(migration_ir(),tmp_path)
    migration=out/'TableMigration.gs'
    original=migration.read_text()+'\n// Reviewed operator data stays here.\n'
    migration.write_text(original)
    synthesize(migration_ir(),out)
    assert migration.read_text()==original
