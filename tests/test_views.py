import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack
from pfx2gas.views import compile_view, load_solution_views

FIXTURES = Path(__file__).parent / 'fixtures'
SOURCE = FIXTURES / 'fixtureViews.msapp'
SOLUTION = FIXTURES / 'fixtureViews.solution.zip'


def view_ir(solution=SOLUTION):
    return analyze(parse(unpack(SOURCE)), solution=solution)


def execute_view(query, rows):
    code = "const fs=require('fs'),FX=require('./static/fx-stdlib.js');const [q,r]=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(FX.applyView(r,q)));"
    run = subprocess.run(['node', '-e', code], input=json.dumps([query, rows]), capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_saved_views_use_exported_filter_order_aliases_and_provenance():
    ir = view_ir()
    query = ir.view_sets['Project Views']['open_by_budget']
    assert 'error' not in query
    assert ir.source_metadata['solutionSha256'] == hashlib.sha256(SOLUTION.read_bytes()).hexdigest()
    rows = [
        {'id':'zero','status':0,'active':True,'budget':0,'name':'Zero'},
        {'id':'closed','status':1,'active':True,'budget':100,'name':'Closed'},
        {'id':'lower','status':0,'active':False,'budget':10,'name':'Lower'},
        {'id':'first','status':0,'active':False,'budget':20,'name':'Alpha'},
        {'id':'second','status':0,'active':False,'budget':20,'name':'beta'},
        {'id':'missing','active':True,'budget':99},
    ]
    result = execute_view(query, rows)
    assert [r['id'] for r in result] == ['first','second','lower','zero']
    assert rows[0]['id'] == 'zero'  # sorting never changes the source table


@pytest.mark.parametrize('op,values,expected', [
    ('null', [], ['blank']), ('not-null', [], ['zero','false','one']),
    ('ne', [1], ['zero','false']), ('in', [0,1], ['zero','false','one']),
    ('not-in', [1], ['zero','false']), ('gt', [0], ['one']), ('le', [0], ['zero','false']),
])
def test_view_null_and_numeric_comparisons_do_not_coerce_blank(op, values, expected):
    query = {'filter':{'op':op,'field':'value','type':'number','values':values},'order':[]}
    rows = [{'id':'blank','value':None},{'id':'zero','value':0},{'id':'false','value':False},{'id':'one','value':1}]
    assert [r['id'] for r in execute_view(query, rows)] == expected


def test_date_view_compares_instants_and_honors_explicit_timezone():
    ir = view_ir()
    source = next(source for source in ir.data_sources if source.name == 'Projects')
    query = compile_view('''<fetch><entity name="msft_project"><filter>
      <condition attribute="msft_start" operator="ge" value="2026-09-09T00:00:00Z"/>
      </filter><order attribute="msft_start"/></entity></fetch>''', source)
    rows = [{'start__date':'2026-09-08T20:00:00-04:00'}, {'start__date':'2026-09-08T23:59:59Z'}, {'start__date':None}]
    assert execute_view(query, rows) == [rows[0]]


def test_choice_sort_requires_explicit_raw_order_and_ledger_retains_collation_limits(tmp_path):
    from pfx2gas.fidelity import iter_expressions
    from pfx2gas.synth.build import synthesize
    ir = view_ir()
    source = next(source for source in ir.data_sources if source.name == 'Projects')
    query = '<fetch%s><entity name="msft_project"><order attribute="msft_status"/></entity></fetch>'
    with pytest.raises(ValueError, match='localized choice-label ordering'):
        compile_view(query % '', source)
    raw = compile_view(query % ' useraworderby="true"', source)
    assert execute_view(raw, [{'status':1},{'status':0}]) == [{'status':0},{'status':1}]
    synthesize(ir, tmp_path / 'limits')
    expr = next(expr for _s,c,p,expr in iter_expressions(ir) if c == 'ViewRows' and p == 'Text')
    assert expr.emission_status == 'approximated' and 'tenant collation' in expr.fidelity_note
    unordered = compile_view('<fetch><entity name="msft_project"/></fetch>', source)
    assert 'implicit primary-key' in unordered['limitations'][0]


@pytest.mark.parametrize('fetch', [
    '<fetch aggregate="true"><entity name="msft_project"/></fetch>',
    '<fetch top="2"><entity name="msft_project"/></fetch>',
    '<fetch><entity name="wrong"/></fetch>',
    '<fetch><entity name="msft_project"><link-entity name="users"/></entity></fetch>',
    '<fetch><entity name="msft_project"><filter><condition attribute="msft_owner" operator="eq-useroruserteams"/></filter></entity></fetch>',
    '<fetch><entity name="msft_project"><filter><condition attribute="unknown" operator="eq" value="0"/></filter></entity></fetch>',
    '<fetch><entity name="msft_project"><filter><condition attribute="msft_budget" operator="eq" valueof="msft_status"/></filter></entity></fetch>',
    '<fetch><entity name="msft_project"><filter><condition attribute="msft_start" operator="eq" value="2026-09-09"/></filter></entity></fetch>',
    '<!DOCTYPE fetch [<!ENTITY x "bad">]><fetch/>',
])
def test_unsupported_view_features_are_rejected_instead_of_silently_broadened(fetch):
    source = next(source for source in view_ir().data_sources if source.name == 'Projects')
    with pytest.raises(ValueError):
        compile_view(fetch, source)


def test_missing_definition_is_ledgered_fails_empty_data_and_cannot_use_llm(tmp_path):
    from pfx2gas.cli import _llm_fallback
    from pfx2gas.fidelity import iter_expressions
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    ir = view_ir(None)
    for source in ir.data_sources:
        source.sample_data = []
    class NeverCall:
        def translate_formula(self, *args, **kwargs):
            raise AssertionError('A model must not invent a missing saved-query filter')
    _llm_fallback(ir, NeverCall())
    expr = next(expr for _s,c,p,expr in iter_expressions(ir) if c == 'ViewRows' and p == 'Text')
    assert expr.translation_status == 'stubbed' and expr.blocked_dependencies
    project = synthesize(ir, tmp_path / 'missing')
    assert expr.emission_status == 'unsupported'
    verdict = simulate_project(project)
    assert any('FetchXML is missing' in error for error in verdict['allConsoleErrors']), verdict


def test_generated_view_reacts_to_persisted_updates(tmp_path):
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    project = synthesize(view_ir(), tmp_path / 'views')
    verdict = simulate_project(project, [{'id':'filter-update','steps':[
        {'action':'expectText','control':'ViewRows','equals':'Third project, First project'},
        {'action':'expectText','control':'ViewCount','equals':'1'},
        {'action':'click','control':'OpenSecond'},
        {'action':'expectText','control':'ViewRows','equals':'Second project, Third project, First project'},
        {'action':'expectText','control':'ViewCount','equals':'2'},
        {'action':'expectDataRow','source':'Projects','where':{'id':'project-two','status':0}},
    ]}])
    assert not verdict['allConsoleErrors'], verdict
    assert verdict['journeyResults'][0]['status'] == 'pass', verdict


def test_native_gallery_template_action_survives_flattening(tmp_path):
    from pfx2gas.fidelity import iter_expressions
    from pfx2gas.synth.build import synthesize
    ir = view_ir()
    synthesize(ir, tmp_path / 'template')
    expr = next(expr for _s,c,p,expr in iter_expressions(ir)
                if c == 'ProjectTemplate' and p == 'OnSelect')
    assert expr.emission_status == 'emitted'
    # The matching Chromium saved-views journey clicks the second rendered
    # Select(Parent) button and verifies the template's ThisItem selection.


def test_current_user_view_compiles_and_executes_with_migrated_identity(tmp_path):
    from pfx2gas.fx import transpile
    from pfx2gas.ir import DataSource, FieldDef
    from pfx2gas.views import resolve_views
    ir = parse(unpack(SOURCE))
    ir.data_sources.append(DataSource(name='Users', origin='dataverse', logical_name='systemuser',
        primary_key='User', fields=[FieldDef(name='User', logical_name='systemuserid'),
                                   FieldDef(name='Primary Email', logical_name='internalemailaddress')]))
    xml = tmp_path / 'identity.xml'
    xml.write_text('''<ImportExportXml><savedquery><savedqueryid>11111111-1111-1111-1111-111111111111</savedqueryid>
      <fetchxml><fetch><entity name="msft_project"><filter>
      <condition attribute="msft_owner" operator="eq-userid"/>
      </filter></entity></fetch></fetchxml></savedquery></ImportExportXml>''')
    resolve_views(ir, xml)
    query = ir.view_sets['Project Views']['open_by_budget']
    assert query['identity'] == {'source':'Users','key':'user','emailField':'primary__email'}
    formula = transpile("Filter(Projects, 'Project Views'.'Open by budget')",
        global_names={'Projects','Users'}, view_sets=ir.view_sets)
    assert not formula.unmapped
    code = "const FX=require('./static/fx-stdlib.js');const state={Users:[{user:'USER-ID',primary__email:'USER@example.test'}],Projects:[{owner:'user-id'},{owner:'other-id'},{owner:null}]};const FXUser=()=>({email:'user@example.test'});console.log(JSON.stringify(" + formula.js + "));"
    run = subprocess.run(['node','-e',code],capture_output=True,text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [{'owner':'user-id'}]
    ir.data_sources.pop()
    resolve_views(ir, xml)
    assert 'requires the exported systemuser table' in ir.view_sets['Project Views']['open_by_budget']['error']


def test_solution_cli_and_malformed_metadata(tmp_path):
    from pfx2gas.cli import main
    assert main(['convert',str(SOURCE),'--solution',str(SOLUTION),'--no-llm','-o',str(tmp_path/'project')]) == 0
    ledger = json.loads((tmp_path/'project/conversion-ledger.json').read_text())
    assert ledger['sourceMetadata']['solutionSha256'] == hashlib.sha256(SOLUTION.read_bytes()).hexdigest()
    invalid = tmp_path/'bad.zip'
    invalid.write_text('not a zip')
    assert main(['convert',str(SOURCE),'--solution',str(invalid),'--no-llm']) == 1
    xml = tmp_path/'bad.xml'
    xml.write_text('<ImportExportXml>')
    with pytest.raises(ValueError, match='Invalid solution'):
        load_solution_views(xml)
