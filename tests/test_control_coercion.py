"""Exported control contracts and compatibility flags reach executable apps."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import UnpackError, unpack

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='module', autouse=True)
def build():
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)


@pytest.mark.parametrize('v1',[False,True])
def test_exported_primary_output_and_language_version_reach_generation(tmp_path,v1):
    ir=analyze(parse(unpack(FIXTURES/('fixtureControlCoercionV1.msapp' if v1 else 'fixtureControlCoercion.msapp'))))
    assert ir.power_fx_v1 is v1
    controls={c.name:c for c in ir.screens[0].walk_controls()}
    assert controls['Input'].primary_output=='Text'
    assert controls['Save'].primary_output=='Pressed'  # Button's primary output is not Text.
    assert controls['Rows'].primary_output=='Selected'
    assert ('FX.primaryOutput(' in controls['InputBlank'].properties['Text'].js) is (not v1)
    project=synthesize(ir,tmp_path/'generated')
    assert 'data-fx-primary-output="text"' in (project/'Screens.html').read_text()


def test_template_contracts_do_not_cross_versions_or_guess_ambiguous_outputs(tmp_path):
    path=tmp_path/'mismatch.msapp'
    with zipfile.ZipFile(FIXTURES/'fixtureControlCoercion.msapp') as src, zipfile.ZipFile(path,'w') as dst:
        for name in src.namelist():
            raw=src.read(name)
            if name=='References/Templates.json':
                data=json.loads(raw)
                data['UsedTemplates'][0]['Version']='9.0'
                data['UsedTemplates'][1]['Template']='<widget><property name="Text" isPrimaryOutputProperty="true"/><property name="Value" isPrimaryOutputProperty="true"/></widget>'
                raw=json.dumps(data)
            dst.writestr(name,raw)
    controls={c.name:c for c in parse(unpack(path)).screens[0].walk_controls()}
    assert controls['Input'].primary_output is None
    assert controls['InputBlank'].primary_output is None


@pytest.mark.parametrize('flag',[True,False,'false'])
def test_modern_exports_preserve_typed_powerfx_v1_setting(tmp_path,flag):
    path=tmp_path/'modern.msapp'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('Properties.json',json.dumps({'Name':'Modern','AppPreviewFlagsMap':{'powerfxv1':flag}}))
        archive.writestr('Src/Home.pa.yaml','Screens:\n  Home:\n    Children: []\n')
    if isinstance(flag,str):
        with pytest.raises(UnpackError,match='compatibility setting'):
            unpack(path)
    else:
        assert parse(unpack(path)).power_fx_v1 is flag
