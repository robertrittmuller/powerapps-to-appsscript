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
from pfx2gas.unpack import unpack

FIXTURES=Path(__file__).parent/'fixtures'


@pytest.mark.parametrize('version', ['2.2.3','9.0'])
def test_native_image_fit_and_fill_require_matching_version_and_keep_authored_values(tmp_path,version):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    target=tmp_path/'Images.msapp'
    with zipfile.ZipFile(FIXTURES/'fixtureSvgText.msapp') as original,zipfile.ZipFile(target,'w') as result:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='Controls/Home.json':
                doc=json.loads(data)
                for node in doc['TopParent']['Children']:node['Template']['Version']=version
                data=json.dumps(doc).encode()
            result.writestr(entry.filename,data)
    ir=parse(unpack(target))
    controls={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert controls['Nested'].properties['ImagePosition'].raw=='ImagePosition.Stretch'
    assert controls['Nested'].properties['Fill'].raw=='RGBA(255,0,0,1)'
    if version=='2.2.3':
        assert controls['Direct'].properties['ImagePosition'].raw=='ImagePosition.Fit'
        assert controls['Direct'].properties['Fill'].raw=='RGBA(0,0,0,0)'
        assert controls['Cdata'].properties['ImagePosition'].raw=='ImagePosition.Fill'
        assert {(row['control'],row['property']) for row in ir.source_metadata['nativeControlDefaults']}=={
            (name,prop) for name in ['Direct','Cdata'] for prop in ['ImagePosition','Fill']}
    else:
        assert all(prop not in controls[name].properties for name in ['Direct','Cdata'] for prop in ['ImagePosition','Fill'])
        assert not ir.source_metadata.get('nativeControlDefaults')


def test_native_timer_caption_is_retained_without_replacing_authored_text_or_actions(tmp_path):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    ir=analyze(parse(unpack(FIXTURES/'fixtureBareInputs.msapp')))
    controls={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert controls['Clock'].properties['Text'].raw=='Text(Time(0, 0, Self.Value/1000), "hh:mm:ss")'
    assert controls['Clock'].properties['Repeat'].raw=='false'
    assert controls['AuthoredClock'].properties['Text'].raw=='"Authored timer"'
    assert all('OnSelect' not in controls[name].properties for name in ['Clock','AuthoredClock'])
    assert {(row['control'],row['property']) for row in ir.source_metadata['nativeControlDefaults']}=={
        ('Clock','Text'),('Clock','Repeat'),('AuthoredClock','Repeat')}
    result=simulate_project(synthesize(ir,tmp_path/'TimerDefaults'),[{'id':'native-caption','steps':[
        {'action':'expectText','control':'Clock','equals':'00:00:00'},
    ]}])
    # The startup shim does not hydrate static HTML text. The Chromium fixture
    # checks the authored literal caption as well as this reactive caption.
    assert not result['consoleErrors'] and result['journeyResults'][0]['status']=='pass',json.dumps(result['journeyResults'])


def test_mismatched_timer_version_cannot_supply_native_defaults(tmp_path):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    target=tmp_path/'Mismatch.msapp'
    with zipfile.ZipFile(FIXTURES/'fixtureBareInputs.msapp') as original,zipfile.ZipFile(target,'w') as result:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='Controls/Home.json':
                doc=json.loads(data)
                for node in doc['TopParent']['Children']:node['Template']['Version']='9.0'
                data=json.dumps(doc).encode()
            result.writestr(entry.filename,data)
    ir=parse(unpack(target))
    clock=next(ctrl for screen in ir.screens for ctrl in screen.walk_controls() if ctrl.name=='Clock')
    assert 'Text' not in clock.properties and 'Repeat' not in clock.properties
