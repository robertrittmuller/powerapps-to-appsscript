import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import UnpackError, UnpackedApp, unpack

FIXTURES = Path(__file__).parent/'fixtures'


@pytest.fixture(scope='module', autouse=True)
def build():
    subprocess.run([sys.executable, str(FIXTURES/'build.py')], check=True)


def test_modern_definitions_are_not_screens_and_each_instance_has_its_own_namespace():
    source = unpack(FIXTURES/'fixtureModernComponents.msapp')
    assert set(source.component_definitions) == {'CounterCard','Wrapper','Shared'}
    assert source.screen_order == ['Home','Other']
    ir = analyze(parse(source))
    assert [screen.name for screen in ir.screens] == ['Home','Other']
    controls = {ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert controls['First'].properties['Caption'].control_aliases == {}
    assert controls['First'].properties['Caption'].js.endswith("val('EntryInput').text")
    assert 'First__EntryInput' in controls['First__SaveButton'].properties['OnSelect'].js
    assert 'Second__EntryInput' in controls['Second__SaveButton'].properties['OnSelect'].js
    assert controls['First__Title'].properties['Text'].raw == 'CounterCard.Caption & " EntryInput"'
    assert 'EntryInput' in controls['First__Title'].properties['Text'].js
    assert controls['First__Html'].type == 'HtmlText'
    assert controls['Nested__Inner'].properties['Caption'].component_owner == 'Nested'
    assert controls['Nested__Inner__SaveButton'].properties['OnSelect'].component_owner == 'Nested__Inner'
    collections = [source.name for source in ir.data_sources if source.origin == 'collection']
    assert len(collections) == 4 and len(set(collections)) == 4
    assert all(record['status'] == 'expanded' for record in ir.source_metadata['canvasComponents'])


def test_generated_component_instances_keep_inputs_outputs_variables_collections_and_select_local(tmp_path):
    project = synthesize(analyze(parse(unpack(FIXTURES/'fixtureModernComponents.msapp'))), tmp_path/'App')
    result = simulate_project(project,[{'id':'component-instances','steps':[
        {'action':'expectText','control':'First__Title','equals':'Host EntryInput'},
        {'action':'expectText','control':'Second__Title','equals':'Second EntryInput'},
        {'action':'expectText','control':'Nested__Inner__Title','equals':'nested EntryInput'},
        {'action':'setValue','control':'First__EntryInput','value':'First draft'},
        {'action':'setValue','control':'Second__EntryInput','value':'Second draft'},
        {'action':'click','control':'First__SaveButton'},
        {'action':'expectText','control':'First__Counts','equals':'1/1'},
        {'action':'expectText','control':'Second__Counts','equals':'0/0'},
        {'action':'click','control':'Second__SelectButton'},
        {'action':'expectText','control':'Second__Counts','equals':'1/1'},
        {'action':'click','control':'Nested__Inner__SaveButton'},
        {'action':'expectText','control':'Nested__Inner__Counts','equals':'1/1'},
        {'action':'expectText','control':'AppCounts','equals':'900/1'},
        {'action':'click','control':'SharedInstance__Increment'},
        {'action':'expectText','control':'AppCounts','equals':'901/1'},
        {'action':'expectText','control':'Outputs','equals':'1/1/Host/record'},
    ]}])
    assert not result['consoleErrors'], result
    assert result['journeyResults'][0]['status'] == 'pass', result['journeyResults']


@pytest.mark.parametrize('definition,reason', [
    (None, 'not exported'),
    ({'DefinitionType':'CodeComponent'}, 'definition type'),
    ({'DefinitionType':'CanvasComponent','AccessAppScope':'false'}, 'must be boolean'),
    ({'DefinitionType':'CanvasComponent','CustomProperties':{'Run':{'PropertyKind':'Action'}}}, 'custom property'),
    ({'DefinitionType':'CanvasComponent','Children':[{'Again':{'Control':'CanvasComponent','ComponentName':'Card'}}]}, 'circular component'),
])
def test_missing_and_unsupported_components_are_visible_runtime_failures(tmp_path, definition, reason):
    source = UnpackedApp(app_name='Missing', screens={'Home':{'Home':{'Children':[
        {'Instance':{'Control':'CanvasComponent','ComponentName':'Card','Properties':{'Width':'=200','Height':'=100'}}}]}}},
        component_definitions={} if definition is None else {'Card':definition})
    ir = analyze(parse(source))
    project = synthesize(ir,tmp_path/'App')
    assert 'data-unsupported-control="CanvasComponent"' in (project/'Screens.html').read_text()
    result = simulate_project(project)
    assert any(reason in message for message in result['consoleErrors']), result
    assert any(record.get('error') and reason in record['error'] for record in ir.source_metadata['canvasComponents'])


def test_duplicate_definitions_fail_before_one_can_overwrite_the_other(tmp_path):
    path = tmp_path/'Duplicate.msapp'
    with zipfile.ZipFile(path,'w') as archive:
        for filename,name in [('First','Card'),('Second','card')]:
            archive.writestr('Src/'+filename+'.pa.yaml',json.dumps({'ComponentDefinitions':{name:{'DefinitionType':'CanvasComponent'}}}))
    with pytest.raises(UnpackError,match='duplicate canvas component'):
        unpack(path)


def test_modern_references_retain_services_and_seeded_tables(tmp_path):
    path = tmp_path/'References.msapp'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Src/Home.pa.yaml', json.dumps({'Screens':{'Home':{'Children':[
            {'Email':{'Control':'Text@0.0.51','Properties':{'Text':'=Office365Users.MyProfileV2().mail'}}}]}}}))
        archive.writestr('References\\DataSources.json', json.dumps({'DataSources':[
            {'Name':'Office365Users','Type':'ServiceInfo'},
            {'Name':'Options','Type':'StaticDataSourceInfo','Schema':'*[Title:s,Amount:n]',
             'Data':json.dumps([{'Title':'One','Amount':5}])}]}))
    ir = analyze(parse(unpack(path)))
    assert [(source.name, source.origin) for source in ir.data_sources] == [('Office365Users','service'),('Options','static')]
    assert ir.data_sources[1].sample_data == [{'title':'One','amount':5}]
    assert 'connectorRead' in ir.screens[0].controls[0].properties['Text'].js


def test_component_expansion_cannot_collide_with_an_existing_app_control(tmp_path):
    source = UnpackedApp(app_name='Collision', component_definitions={'Card':{
        'DefinitionType':'CanvasComponent','Children':[{'Child':{'Control':'Label','Properties':{'Text':'="internal"'}}}]}},
        screens={'Home':{'Home':{'Children':[
            {'Instance':{'Control':'CanvasComponent','ComponentName':'Card'}},
            {'Instance__Child':{'Control':'Label','Properties':{'Text':'="external"'}}}]}}})
    ir = analyze(parse(source))
    assert len(list(ir.screens[0].walk_controls())) == 2
    project = synthesize(ir, tmp_path/'App')
    result = simulate_project(project)
    assert any('collides with an app control' in message for message in result['consoleErrors'])


def test_modern_reference_table_with_null_optional_option_metadata_retains_records(tmp_path):
    from pfx2gas.server_sim import simulate_server
    source = tmp_path/'NullOptions.msapp'
    definition = {'EntityMetadata':json.dumps({'LogicalName':'note','PrimaryIdAttribute':'noteid','Attributes':[
        {'LogicalName':'noteid','AttributeType':'Uniqueidentifier'},
        {'LogicalName':'title','AttributeType':'String'}]})}
    definition.update({category+'OptionSetAttribute':None for category in
                       ('Boolean','Picklist','MultiSelectPicklist','State','Status')})
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('Src/Home.pa.yaml', json.dumps({'Screens':{'Home':{'Children':[
            {'Title':{'Control':'Label','Properties':{'Text':'=First(Notes).title'}}}]}}}))
        archive.writestr('References/DataSources.json', json.dumps({'DataSources':[
            {'Name':'Notes','Type':'NativeCDSDataSourceInfo','TableDefinition':json.dumps(definition),
             'SampleData':[{'noteid':'source-one','title':'Exported note'}]}]}))
    ir = analyze(parse(unpack(source)))
    assert ir.data_sources[0].primary_key == 'noteid'
    project = synthesize(ir,tmp_path/'App')
    server = simulate_server(project)
    assert server['status'] == 'pass', server
    result = simulate_project(project,[{'id':'exported-note','steps':[
        {'action':'expectText','control':'Title','equals':'Exported note'}]}])
    assert not result['consoleErrors'], result
    assert result['journeyResults'][0]['status'] == 'pass', result
