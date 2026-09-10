import subprocess
import sys
from pathlib import Path

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import unpack


def test_button_icons_keep_source_text_and_actions_in_standalone_and_row_scope(tmp_path):
    fixtures=Path(__file__).parent/'fixtures'
    subprocess.run([sys.executable,str(fixtures/'build.py')],check=True)
    ir=analyze(parse(unpack(fixtures/'fixtureButtonIcons.msapp')))
    assert ir.screens[0].controls[0].type=='Button'
    project=synthesize(ir,tmp_path/'App')
    result=simulate_project(project,[{'id':'button-icons','steps':[
        {'action':'expectText','control':'SourceCaption','equals':'Expand'},
        {'action':'click','control':'Expand'},
        {'action':'expectText','control':'Result','equals':'Expand/0'},
        {'action':'expectText','control':'SourceCaption','equals':'Collapse'},
        {'action':'click','control':'After'},
        {'action':'expectText','control':'Result','equals':'Save/0'},
        {'action':'click','control':'Plain'},
        {'action':'expectText','control':'Result','equals':'Plain/0'},
        {'action':'click','control':'Fallback'},
        {'action':'expectText','control':'Result','equals':'Delete/0'},
        {'action':'click','gallery':'Actions','row':1,'control':'RowAction'},
        {'action':'expectText','control':'Result','equals':'Row Beta/2'},
    ]}])
    assert not result['consoleErrors'],result
    assert result['journeyResults'][0]['status']=='pass',result
