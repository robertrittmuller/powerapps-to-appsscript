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
from pfx2gas.template_defaults import selection_defaults
from pfx2gas.unpack import unpack

FIXTURES=Path(__file__).parent/'fixtures'


@pytest.mark.parametrize('name',['fixtureSelectionDefaults','fixtureModernSelectionDefaults'])
def test_exported_selection_default_preserves_explicit_overrides_and_boots(tmp_path,name):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    ir=analyze(parse(unpack(FIXTURES/(name+'.msapp'))))
    controls={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert controls['Picker'].properties['SelectMultiple'].raw=='true'
    assert controls['RowPicker'].properties['SelectMultiple'].raw=='true'
    assert controls['Single'].properties['SelectMultiple'].raw=='false'
    assert controls['Dynamic'].properties['SelectMultiple'].raw=='allowMany'
    assert 'OnSelect' not in controls['Picker'].properties
    assert len(ir.source_metadata['nativeSelectionDefaults'])==2
    project=synthesize(ir,tmp_path/name)
    result=simulate_project(project,[{'id':'selector-startup','steps':[
        {'action':'expectText','control':'Selection','equals':'0/'},
        {'action':'click','control':'Toggle'},
        {'action':'expectState','key':'allowMany','equals':True},
        {'action':'click','control':'ResetPicker'},
        {'action':'expectText','control':'Selection','equals':'0/'},
    ]}])
    assert not result['consoleErrors'],result
    assert result['journeyResults'][0]['status']=='pass',result


def test_template_defaults_reject_conflicting_or_unsafe_declarations():
    def doc(value):
        return {'Name':'combobox','Version':'2.4','Template':'<widget><property name="SelectMultiple" datatype="Boolean" defaultValue="'+value+'"/></widget>'}
    with pytest.raises(ValueError,match='conflicting SelectMultiple'):
        selection_defaults({'References/Templates.json':json.dumps({'UsedTemplates':[doc('true'),doc('false')]})})
    with pytest.raises(ValueError,match='unsupported SelectMultiple'):
        selection_defaults({'References/Templates.json':json.dumps({'UsedTemplates':[doc('unknown')]})})
    unsafe=doc('true');unsafe['Template']='<!DOCTYPE widget [<!ENTITY x "true">]>'+unsafe['Template']
    with pytest.raises(ValueError,match='unsafe'):
        selection_defaults({'References/Templates.json':json.dumps({'UsedTemplates':[unsafe]})})


def test_mismatched_template_version_cannot_supply_selection_defaults(tmp_path):
    source=FIXTURES/'fixtureModernSelectionDefaults.msapp'
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    path=tmp_path/'DifferentVersion.msapp'
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(path,'w') as target:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='References/Templates.json':
                doc=json.loads(data);doc['UsedTemplates'][0]['Version']='9.0';data=json.dumps(doc).encode()
            target.writestr(entry.filename,data)
    ir=parse(unpack(path))
    assert all('SelectMultiple' not in ctrl.properties for screen in ir.screens
               for ctrl in screen.walk_controls() if ctrl.name in ['Picker','RowPicker'])


@pytest.mark.parametrize('name',['fixtureSelectionDefaults','fixtureModernSelectionDefaults'])
@pytest.mark.parametrize('script',['false','allowMany',''])
def test_native_dynamic_selection_is_authoritative_even_when_blank(tmp_path,name,script):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    path=tmp_path/'DynamicSelection.msapp'
    with zipfile.ZipFile(FIXTURES/(name+'.msapp')) as original,zipfile.ZipFile(path,'w') as target:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='Controls/Home.json':
                doc=json.loads(data)
                picker=next(ctrl for ctrl in doc['TopParent']['Children'] if ctrl['Name']=='Picker')
                picker['DynamicProperties']=[{'Rule':{'Property':'SelectMultiple','InvariantScript':script}}]
                data=json.dumps(doc).encode()
            target.writestr(entry.filename,data)
    ir=parse(unpack(path))
    picker=next(ctrl for screen in ir.screens for ctrl in screen.walk_controls() if ctrl.name=='Picker')
    assert picker.properties['SelectMultiple'].raw==script
    provenance=next(entry for entry in ir.source_metadata['nativeSelectionDefaults'] if entry['control']=='Picker')
    assert provenance['nativeField']=='DynamicProperties'
