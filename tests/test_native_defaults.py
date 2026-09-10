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
from pfx2gas.unpack import UnpackError, unpack

FIXTURES=Path(__file__).parent/'fixtures'


@pytest.fixture(scope='module',autouse=True)
def build():
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True)


def test_native_rules_and_dynamic_properties_fill_only_missing_modern_layout(tmp_path):
    ir=analyze(parse(unpack(FIXTURES/'fixtureNativeLayout.msapp')))
    nodes={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert nodes['Header'].properties['Height'].raw=='48'
    assert nodes['Body'].properties['FillPortions'].raw=='1'
    assert nodes['Left__Press'].properties['Height'].raw=='32'
    assert nodes['Left__Press'].properties['OnSelect'].raw=='Set(count,count+1)'
    recovered=ir.source_metadata['nativeLayoutDefaults']
    assert any(row['control']=='Body' and row['property']=='FillPortions'
               and row['nativeField']=='DynamicProperties' for row in recovered)
    assert any(row['scope']=='component' and row['control']=='Press' and row['property']=='Height' for row in recovered)
    assert not any(row['property']=='OnSelect' or (row['control']=='Header' and row['property']=='Height') for row in recovered)
    project=synthesize(ir,tmp_path/'App')
    result=simulate_project(project,[{'id':'native-layout-actions','steps':[
        {'action':'expectText','control':'Header','equals':'Count 0'},
        {'action':'click','control':'Left__Press'},
        {'action':'expectText','control':'Header','equals':'Count 1'},
        {'action':'click','control':'Next'},
        {'action':'expectScreen','screen':'Other'},
        {'action':'click','control':'Back'},
        {'action':'expectScreen','screen':'Home'},
    ]}])
    assert not result['consoleErrors'],result
    assert result['journeyResults'][0]['status']=='pass',result


def test_mismatched_native_control_version_cannot_supply_defaults(tmp_path):
    path=tmp_path/'Version.msapp'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('Src/Home.pa.yaml',json.dumps({'Screens':{'Home':{'Children':[
            {'Button':{'Control':'Button@2.0','Properties':{'Text':'="Modern"'}}}]}}}))
        archive.writestr('Controls/Home.json',json.dumps({'TopParent':{'Name':'Home','Children':[
            {'Name':'Button','Template':{'Name':'button','Version':'1.0'},'Rules':[
                {'Property':'Height','InvariantScript':'32'}]}]}}))
    ir=analyze(parse(unpack(path)))
    assert 'Height' not in ir.screens[0].controls[0].properties
    assert any('version differs' in warning for warning in ir.warnings)


def test_conflicting_native_property_is_not_arbitrarily_selected(tmp_path):
    path=tmp_path/'Conflict.msapp'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('Src/Home.pa.yaml',json.dumps({'Screens':{'Home':{'Children':[
            {'Box':{'Control':'GroupContainer'}}]}}}))
        archive.writestr('Controls/Home.json',json.dumps({'TopParent':{'Name':'Home','Children':[
            {'Name':'Box','Rules':[{'Property':'FillPortions','InvariantScript':'1'}],
             'DynamicProperties':[{'Rule':{'Property':'FillPortions','InvariantScript':'2'}}]}]}}))
    with pytest.raises(UnpackError,match='conflicting native layout property'):
        unpack(path)
