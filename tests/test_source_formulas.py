"""Execute complete source formulas; helpers alone cannot prove their behavior."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from pfx2gas.fx import transpile
from pfx2gas.fx.lexer import FxSyntaxError

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / 'tests/fixtures'
FORMULAS = json.loads((FIXTURES / 'microsoft-formulas.json').read_text())


def execute(formula, setup, **kwargs):
    result = transpile(formula, **kwargs)
    assert not result.unmapped, result
    script = 'const assert=require("node:assert/strict"); const FX=require("./static/fx-stdlib.js");\n' + setup
    script += '\n(async()=>{const result = (' + result.js + '); process.stdout.write(JSON.stringify(result));})().catch(e=>{console.error(e);process.exit(1)});'
    run = subprocess.run(['node', '-e', script], cwd=REPO, capture_output=True, text=True, timeout=10, check=True)
    return json.loads(run.stdout)


def test_canvas_font_values_match_source_character_width_reference_records():
    setup = '''const state = {Widths:[
      {char:'W',char_font:"'Segoe UI', 'Open Sans', sans-serif",char_weight:'normal',size:'1.2'},
      {char:'W',char_font:"'Segoe UI', 'Open Sans', sans-serif",char_weight:'600',size:'1.4'}]};'''
    for weight, expected in [('Normal',1.2),('Semibold',1.4)]:
        formula = 'Value(LookUp(Widths, Char = "W" && CharFont = Font.\'Segoe UI\' && CharWeight = FontWeight.' + weight + ').Size, "en-US")'
        assert execute(formula,setup)==expected
    for weight,expected in [('Normal','normal'),('Semibold','600'),('Bold','bold'),('Lighter','lighter')]:
        assert execute('Text(FontWeight.'+weight+')','const state={};')==expected


def test_inspection_complete_source_validation_and_original_boundary():
    raw = next(f['raw'] for f in FORMULAS if f['app'] == 'inspection-manager')
    cases = [
        ('', None),
        ('not a URL', 'Please enter a valid URL'),
        ('https://contoso.sharepoint.com/sites/Team/extra', 'URL must have exactly 4 forward slashes, like https://contoso.sharepoint.com/sites/TeamName'),
        ('https://contoso.example.com/sites/Team', 'URL must include .sharepoint.com/sites/'),
        ('https://contoso.sharepoint.com/sites/Ab', 'URL must include at least a three character site name'),
        ('https://contoso.sharepoint.com/sites/Abc', None),
        ('https://contoso.sharepoint.com/sites/Team', None),
    ]
    for url, expected in cases:
        actual = execute(raw, 'const state={}; const val=()=>({text:' + json.dumps(url) + '});',
                         control_names={'txtSetupSharePoint_URL'})
        assert actual == expected, url


def test_milestones_complete_source_timestamp_today_older_localized_and_blank():
    raw = next(f['raw'] for f in FORMULAS if f['app'] == 'milestones')
    setup = '''
const now = new Date(2026,8,9,13,5,0); FX.now = () => new Date(now);
const state = {gblUserLanguage:LANG, colLocalization:LOCALIZATION,
  locSelectedWorkItem:{project__work_item:'work-1'},
  'Project Work Items':[{project__work_item:'work-1',created__on:DATE}]};
'''
    for date, lang, localization, expected in [
        ('new Date(now)', 'en-US', [], 'Created at 01:05 PM'),
        ('null', 'en-US', [], 'Created at 01:05 PM'),
        ('new Date(2014,8,9)', 'en-US', [], 'Created on 09 Sep'),
        ('new Date(2014,8,9)', 'fr-FR', [{'oobtext_id':'lblEditWorkItemCreatedOn1__locText','localized_text':'Créé le'}], 'Créé le 09 sept.'),
        ('new Date(2014,8,9)', 'ja-JP', [], 'Created on 09 9月'),
    ]:
        actual = execute(raw, setup.replace('LANG', json.dumps(lang)).replace('LOCALIZATION', json.dumps(localization)).replace('DATE', date), control_names=set())
        assert actual == expected


def test_matching_constants_and_deferred_errors_survive_emission():
    assert execute('IsMatch("x42y", Match.MultipleDigits, MatchOptions.Contains & MatchOptions.IgnoreCase)', 'const state={};') is True
    assert execute('Match("id=42", "id=(?<ItemId>\\d+)").ItemId', 'const state={};') == '42'
    assert execute('Text(TimeValue("13:05"), DateTimeFormat.ShortTime24, "en-US")', 'const state={};') == '13:05'
    assert execute('IsBlankOrError(Patch(Contacts, Defaults(Contacts), {Name: "broken"}))',
                   'const state={Contacts:[]}; const apiPatch=async()=>{throw new Error("save failed")};') is True
    for raw in ['IsMatch("x", dynamicPattern)', 'MatchAll("x", Match.Email)',
                'IsMatch("x", "x", dynamicOptions)']:
        with pytest.raises(FxSyntaxError, match='constant supported canvas'):
            transpile(raw)


def test_every_dateadd_timeunit_executes_as_a_constant_in_generated_formulas():
    from pfx2gas.fx.emitter import TIME_UNITS
    expected = {'Milliseconds':'2026-01-15T12:00:00.001Z', 'Seconds':'2026-01-15T12:00:01.000Z',
        'Minutes':'2026-01-15T12:01:00.000Z', 'Hours':'2026-01-15T13:00:00.000Z',
        'Days':'2026-01-16T12:00:00.000Z', 'Months':'2026-02-15T12:00:00.000Z',
        'Quarters':'2026-04-15T12:00:00.000Z', 'Years':'2027-01-15T12:00:00.000Z'}
    assert set(expected) == TIME_UNITS
    for member, timestamp in expected.items():
        assert execute(f'DateAdd(Now(), 1, TimeUnit.{member})',
            "process.env.TZ='UTC';const state={TimeUnit:{Minutes:'days'}};FX.now=()=>new Date('2026-01-15T12:00:00Z');",
            screen_name='Screen', global_names={'TimeUnit'}) == timestamp
    assert execute('DateAdd(Now(), -1, TimeUnit.Minutes)',
        "FX.now=()=>new Date('2026-03-08T16:00:00Z');", screen_name='Screen') == '2026-03-08T15:59:00.000Z'
    for invalid in ['TimeUnit.Weeks','TimeUnit.Minutes.Unknown']:
        with pytest.raises(FxSyntaxError,match='Unsupported TimeUnit'):
            transpile(f'DateAdd(Now(), 1, {invalid})')


def test_retained_formulas_match_pinned_original_exports_when_available():
    from pfx2gas.parse import parse
    from pfx2gas.unpack import unpack
    for retained in FORMULAS:
        assert hashlib.sha256(retained['raw'].encode()).hexdigest() == retained['formulaSha256']
        source = REPO / 'samples/microsoft' / (retained['app'] + '.msapp')
        if source.exists():
            assert hashlib.sha256(source.read_bytes()).hexdigest() == retained['inputSha256']
            ir = parse(unpack(source))
            screen = next(s for s in ir.screens if s.name == retained['screen'])
            control = next(c for c in screen.walk_controls() if c.name == retained['control'])
            assert control.properties[retained['property']].raw == retained['raw']


def test_generated_source_formula_ui_boots_and_reacts_to_validation(tmp_path):
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack
    ir = analyze(parse(unpack(FIXTURES / 'fixtureSourceFormulas.msapp')))
    project = synthesize(ir, tmp_path / 'SourceFormulas')
    result = simulate_project(project, [{'id':'source-validation','steps':[
        {'action':'expectText','control':'lblEditWorkItemCreatedOn','equals':'Created on 09 Sep'},
        {'action':'setValue','control':'txtSetupSharePoint_URL','value':'bad'},
        {'action':'expectText','control':'lblSetupSharePoint_ErrorURL','equals':'Please enter a valid URL'},
        {'action':'setValue','control':'txtSetupSharePoint_URL','value':'https://contoso.sharepoint.com/sites/Team'},
        {'action':'expectText','control':'lblSetupSharePoint_ErrorURL','equals':''},
    ]}])
    assert result['consoleErrors'] == [], result
    assert result['journeyResults'][0]['status'] == 'pass', result
