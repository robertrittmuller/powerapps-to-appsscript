"""Canvas metadata and formulas must reach the generated runtime and ledger."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fidelity import ledger_rows
from pfx2gas.parse import parse
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import UnpackError, unpack

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='module', autouse=True)
def build():
    subprocess.run([sys.executable, str(FIXTURES / 'build.py')], check=True, capture_output=True)


def test_generated_canvas_reads_typed_toggle_and_hidden_screen_properties(tmp_path):
    ir = analyze(parse(unpack(FIXTURES / 'fixtureCanvas.msapp')))
    assert ir.layout['designWidth'] == 1200 and ir.layout['scaleToFit'] is False
    assert ir.screens[0].properties['Size'].raw.startswith('1 + CountRows')
    project = synthesize(ir, tmp_path / 'canvas')
    result = simulate_project(project, [{'id': 'canvas-navigation', 'steps': [
        {'action': 'expectText', 'control': 'ThemeCaption', 'equals': 'Light theme'},
        {'action': 'click', 'control': 'OpenDetails'},
        {'action': 'expectScreen', 'screen': 'Details Screen'},
        {'action': 'expectText', 'control': 'DetailsTitle', 'equals': 'Light details'},
    ]}])
    assert result['consoleErrors'] == [], result
    assert result['journeyResults'][0]['status'] == 'pass', result
    rows = ledger_rows(ir)
    for owner, prop in [('App', 'MinScreenWidth'), ('App', 'SizeBreakpoints'),
                        ('Responsive Screen', 'Width'), ('Responsive Screen', 'Orientation'),
                        ('ManualPanel', 'LayoutMode')]:
        assert next(r for r in rows if r['control'] == owner and r['property'] == prop)['emission'] == 'emitted'
    # A dormant direction setting must not be credited as an active layout.
    assert next(r for r in rows if r['control'] == 'ManualPanel' and r['property'] == 'LayoutDirection')['emission'] == 'ignored'
    assert json.loads((project / 'conversion-ledger.json').read_text())['sourceLayout'] == ir.layout


def test_legacy_layout_and_screen_properties_are_preserved(tmp_path):
    source = tmp_path / 'legacy.msapp'
    def node(name, template, properties):
        return {'TopParent': {'Name': name, 'Template': {'Name': template},
            'Rules': [{'Property': key, 'InvariantScript': value} for key, value in properties.items()]}}
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('Properties.json', json.dumps({'Name': 'LegacyCanvas', 'DocumentLayoutWidth': 640,
            'DocumentLayoutHeight': 1136, 'DocumentLayoutScaleToFit': False}))
        z.writestr('Controls\\1.json', json.dumps(node('App', 'appinfo', {'MinScreenWidth': '320'})))
        z.writestr('Controls\\2.json', json.dumps(node('Home', 'screen', {'Width': 'Max(App.Width, App.MinScreenWidth)',
            'OnHidden': 'Set(wasHidden, true)'})))
    ir = analyze(parse(unpack(source)))
    synthesize(ir, tmp_path / 'project')
    assert ir.layout == {'designWidth': 640, 'designHeight': 1136, 'scaleToFit': False}
    assert ir.properties['MinScreenWidth'].raw == '320'
    assert ir.screens[0].properties['Width'].emission_status == 'emitted'
    assert ir.screens[0].properties['OnHidden'].emission_status == 'emitted'


def test_generated_native_card_layout_boots_and_ledgers_card_coordinates(tmp_path):
    ir = analyze(parse(unpack(FIXTURES / 'fixtureCardLayout.msapp')))
    host = next(c for c in ir.screens[0].walk_controls() if c.name == 'CardCanvas')
    assert host.type == 'FluidGrid'
    project = synthesize(ir, tmp_path / 'cards')
    result = simulate_project(project)
    assert result['consoleErrors'] == [], result
    assert result['visible'] == [ir.screens[0].name], result
    for prop in ['X', 'Y', 'Width', 'Height', 'WidthFit']:
        entry = next(row for row in ledger_rows(ir) if row['control'] == 'WideCard' and row['property'] == prop)
        assert entry['emission'] == 'emitted', entry


def test_legacy_fluidgrid_type_uses_card_layout_instead_of_pixel_positioned_generic_div(tmp_path):
    source = tmp_path / 'legacy-grid.msapp'
    def node(name, template, children=None):
        return {'Name':name, 'Template':{'Name':template}, 'Children':children or [], 'Rules':[]}
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('Properties.json', json.dumps({'Name':'LegacyGrid'}))
        z.writestr('Controls\\1.json', json.dumps({'TopParent':node('Screen', 'screen', [
            node('ScrollingCanvas', 'fluidGrid', [node('Card', 'dataCard')])])}))
    ir = analyze(parse(unpack(source)))
    assert ir.screens[0].controls[0].type == 'FluidGrid'
    project = synthesize(ir, tmp_path / 'legacy-cards')
    result = simulate_project(project)
    assert result['consoleErrors'] == [], result


def test_screen_size_enum_comparisons_use_numbers_and_navigation_keeps_screen_identity():
    from pfx2gas.fx import transpile
    formula = transpile("If('Wide Screen'.Size >= ScreenSize.ExtraLarge, App.ActiveScreen.Width, App.MinScreenWidth)",
                        control_names=set(), screen_names={'Wide Screen'})
    script = '''const assert=require('node:assert/strict'); const FX=require('./static/fx-stdlib.js');
const values={App:{active_screen:'Wide Screen',min_screen_width:320}, 'Wide Screen':{size:4,width:1440}};
const val=name=>values[name];
'''
    script += 'assert.equal((' + formula.js + '), 1440); values["Wide Screen"].size=3;'
    script += 'assert.equal((' + formula.js + '), 320);'
    navigation = transpile("Navigate('Wide Screen')", control_names=set(), screen_names={'Wide Screen'})
    script += "const go = name => assert.equal(name, 'Wide Screen');" + navigation.js
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize('key,value', [('DocumentLayoutWidth', -10), ('DocumentLayoutHeight', float('inf')),
    ('DocumentLayoutScaleToFit', 'false'), ('DocumentLayoutOrientation', '</script>')])
def test_invalid_canvas_metadata_fails_explicitly(tmp_path, key, value):
    with zipfile.ZipFile(FIXTURES / 'fixtureCanvas.msapp') as original, zipfile.ZipFile(tmp_path / 'bad.msapp', 'w') as z:
        for name in original.namelist():
            z.writestr(name, json.dumps({'Name': 'Bad', key: value}) if name == 'Properties.json' else original.read(name))
    with pytest.raises(UnpackError, match='invalid canvas layout setting'):
        unpack(tmp_path / 'bad.msapp')
