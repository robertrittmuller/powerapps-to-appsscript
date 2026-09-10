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
from pfx2gas.validate import validate_project
from pfx2gas.ir import AppIR, ScreenNode, ControlNode, FxExpr

FIXTURES=Path(__file__).parent/'fixtures'


def test_literal_await_text_is_a_synchronous_display_value(tmp_path):
    card=ControlNode(name='Card',type='ModernCard',properties={'Title':FxExpr(raw='"Please await review"')})
    ir=analyze(AppIR(name='Literal',start_screen='Home',screens=[ScreenNode(name='Home',controls=[card])]))
    project=synthesize(ir,tmp_path/'Literal')
    result=simulate_project(project,[{'id':'literal','steps':[{'action':'expectText','control':'Card','equals':'Please await review'}]}])
    assert not result['allConsoleErrors'],result
    assert result['journeyResults'][0]['status']=='pass',result


@pytest.mark.parametrize('fixture',['fixtureComposite.msapp','fixtureCompositeLegacy.msapp'])
def test_composite_source_types_actions_and_row_scope_boot_without_errors(tmp_path,fixture):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    ir=analyze(parse(unpack(FIXTURES/fixture)))
    controls={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    assert controls['PreviewCard'].type==controls['ProductCard'].type=='ModernCard'
    assert controls['PageHeader'].properties['OnSelectLogo'].kind=='behavior'
    project=synthesize(ir,tmp_path/'Composite')
    assert validate_project(project)['ok']
    result=simulate_project(project,[{'id':'card-action','steps':[
        {'action':'click','control':'PreviewCard'},
        {'action':'expectState','key':'lastSelected','equals':'preview'},
        {'action':'expectState','key':'clickCount','equals':1},
        {'action':'click','gallery':'ProductsGallery','row':1,'control':'ProductCard'},
        {'action':'expectState','key':'lastSelected','equals':'2'},
        {'action':'expectState','key':'clickCount','equals':2},
        {'action':'click','control':'StateToggle'},
        {'action':'click','control':'PreviewCard'},
        {'action':'click','gallery':'ProductsGallery','row':0,'control':'ProductCard'},
        {'action':'expectState','key':'clickCount','equals':2},
    ]}])
    assert not result['consoleErrors'],result['consoleErrors']
    assert result['journeyResults'][0]['status']=='pass',result['journeyResults']
    for name,props in [('PreviewCard',['Title','Subtitle','Description','Image','LayoutDirection','ImagePlacement']),('PageHeader',['Title','Logo','UserName','OnSelectLogo'])]:
        assert all(controls[name].properties[prop].emission_status in {'emitted','approximated'} for prop in props)


@pytest.mark.parametrize('version',['1.0.0','9.0'])
def test_native_card_defaults_match_version_and_preserve_authored_content(tmp_path,version):
    subprocess.run([sys.executable,str(FIXTURES/'build.py')],check=True,capture_output=True)
    target=tmp_path/'Defaults.msapp'
    with zipfile.ZipFile(FIXTURES/'fixtureComposite.msapp') as original,zipfile.ZipFile(target,'w') as result:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='Controls/Home.json':
                doc=json.loads(data)
                doc['TopParent']['Children'][0]['Template']['Version']=version
                data=json.dumps(doc).encode()
            result.writestr(entry.filename,data)
    ir=parse(unpack(target));controls={ctrl.name:ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    props=controls['PreviewCard'].properties
    assert props['TitleSize'].raw=='18'
    assert 'SampleCardHeaderImage' not in props['HeaderImage'].raw
    assert 'sample action' not in props['OnSelect'].raw
    assert controls['PageHeader'].properties['UserName'].raw=='TitleInput.Text'
    assert controls['PageHeader'].properties['TitleFontSize'].raw=='24'
    if version=='1.0.0':
        assert props['ImagePosition'].raw=='ImagePosition.Fit'
        assert props['BorderRadius'].raw=='20'
    else:
        assert 'ImagePosition' not in props and 'BorderRadius' not in props
