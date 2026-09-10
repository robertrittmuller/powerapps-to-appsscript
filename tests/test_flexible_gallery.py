from pathlib import Path
import subprocess
import sys

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import unpack


@pytest.mark.parametrize('name',['fixtureFlexibleGallery','fixtureScaledFlexibleGallery'])
def test_flexible_gallery_keeps_nested_actions_and_independent_rows(tmp_path,name):
    fixtures=Path(__file__).parent/'fixtures'
    subprocess.run([sys.executable,str(fixtures/'build.py')],check=True,capture_output=True)
    ir=analyze(parse(unpack(fixtures/(name+'.msapp'))))
    project=synthesize(ir,tmp_path/name)
    result=simulate_project(project,[{'id':'expand-collapse','steps':[
        {'action':'click','gallery':'Cards','row':1,'control':'Toggle'},
        {'action':'expectState','key':'expanded','equals':2},
        {'action':'click','gallery':'Cards','row':0,'control':'Toggle'},
        {'action':'expectState','key':'expanded','equals':1},
        {'action':'click','gallery':'Cards','row':0,'control':'Toggle'},
        {'action':'expectState','key':'expanded','equals':0},
    ]}])
    assert not result['consoleErrors'],result
    assert result['journeyResults'][0]['status']=='pass',result
