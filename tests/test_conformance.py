"""Independent documented expectations, exercised through emitted/generated JS."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fx import transpile
from pfx2gas.fx.lexer import FxSyntaxError
from pfx2gas.fx.function_map import FUNCTION_MAP, SIGNATURES, validate_arity
from pfx2gas.ir import AppIR, ScreenNode, ControlNode, FxExpr
from pfx2gas.synth.build import synthesize
from pfx2gas.startup_sim import simulate_project
from pfx2gas.validate import validate_project

CASES = json.loads((Path(__file__).parent/'fixtures/powerfx-conformance.json').read_text())['cases']


@pytest.mark.parametrize('zone', ['UTC', 'America/New_York', 'Europe/Berlin', 'Asia/Kolkata'])
def test_reference_semantics_across_timezones(zone):
    expressions = [transpile(case['formula'], control_names=set()).js for case in CASES]
    program = "const FX=require('./static/fx-stdlib.js');const state={};console.log(JSON.stringify([" + ','.join(expressions) + ']));'
    run = subprocess.run(['node','-e',program], env={**os.environ,'TZ':zone,'LANG':'en_US.UTF-8'}, capture_output=True,text=True,check=True)
    assert json.loads(run.stdout) == [case['expected'] for case in CASES]


def test_generated_app_matches_reference_results(tmp_path):
    controls = [ControlNode(name='case_'+str(i),type='Label',properties={'Text':FxExpr(raw=case['formula'])}) for i,case in enumerate(CASES)]
    ir = analyze(AppIR(name='Conformance',start_screen='Main',screens=[ScreenNode(name='Main',controls=controls)]))
    out = synthesize(ir,tmp_path)
    assert validate_project(out)['ok']
    def display(value):
        return str(value).lower() if isinstance(value,bool) else str(value)
    journeys = [{'id':case['id'],'steps':[{'action':'expectText','control':'case_'+str(i),'equals':display(case['expected'])}]} for i,case in enumerate(CASES)]
    evidence = simulate_project(out,journeys)
    assert not evidence['allConsoleErrors']
    assert all(result['status']=='pass' for result in evidence['journeyResults']), evidence


def test_every_mapped_function_has_an_enforced_signature():
    assert set(FUNCTION_MAP) <= SIGNATURES.keys()
    for name,(minimum,maximum) in SIGNATURES.items():
        if minimum:
            with pytest.raises(FxSyntaxError): validate_arity(name,minimum-1)
        if maximum is not None:
            with pytest.raises(FxSyntaxError): validate_arity(name,maximum+1)


@pytest.mark.parametrize('formula', ['Value("1", "en-US", 9)', 'Weekday(Date(2026,1,1),1,2)', 'GUID("source-guid")', 'JSON({x:1}, 2)', 'Substitute("a","a","b",1,2)', 'Value([1,2])'])
def test_unsupported_overloads_are_explicit(formula):
    with pytest.raises(FxSyntaxError): transpile(formula)


def test_dynamic_table_overload_cannot_silently_coerce_to_scalar():
    result = transpile('IfError(Value(dynamic), -1)',global_names={'dynamic'},control_names=set())
    program = "const FX=require('./static/fx-stdlib.js');const state={dynamic:[1,2]};console.log("+result.js+");"
    assert subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout.strip() == '-1'


def test_mapping_cannot_drop_a_supported_optional_argument(monkeypatch):
    from pfx2gas.fx.function_map import FnSpec
    monkeypatch.setitem(FUNCTION_MAP,'Value',FnSpec('FX.value({a0})'))
    with pytest.raises(FxSyntaxError,match='discard an argument'):
        transpile('Value("123,456", "es-ES")')


@pytest.mark.parametrize('formula',[
    'Patch(Rows, row, {x:1}, {y:2})','Remove(Rows, row, other)',
    'Collect(Rows, {x:1}, {x:2})','ClearCollect(Rows, {x:1}, {x:2})'])
def test_special_data_mappings_cannot_drop_extra_record_arguments(formula):
    with pytest.raises(FxSyntaxError): transpile(formula,behavior=True)


def test_blank_uninitialized_dates_use_reference_epoch_before_onstart():
    result=transpile('DateDiff(uninitialized, Date(1899,12,31))',global_names={'uninitialized'},control_names=set())
    program="const FX=require('./static/fx-stdlib.js');const state={};console.log("+result.js+");"
    assert subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout.strip()=='1'


@pytest.mark.parametrize('formula',['Sum(1,2)','Average(1,2)','Filter({x:1}, true)'])
def test_table_projector_mappings_reject_scalar_overloads(formula):
    with pytest.raises(FxSyntaxError,match='requires a table'): transpile(formula)


def test_dynamic_scalar_cannot_silently_enter_table_aggregation():
    result=transpile('IfError(Sum(dynamic, 2), -1)',global_names={'dynamic'},control_names=set())
    program="const FX=require('./static/fx-stdlib.js');const state={dynamic:1};console.log("+result.js+");"
    assert subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout.strip()=='-1'


@pytest.mark.parametrize('formula,expected',[
    ('DateDiff(Date(2026,1,1),Date(2026,1,2),Hours)',24),
    ('With({x:1},DateDiff(Date(2026,1,1),Date(2026,1,2),Hours))',24),
    ('With({Hours:"Minutes"},DateDiff(Date(2026,1,1),Date(2026,1,2),Hours))',1440)])
def test_legacy_time_units_keep_record_scope_precedence(formula,expected):
    result=transpile(formula,control_names=set())
    program="const FX=require('./static/fx-stdlib.js');const state={};console.log("+result.js+");"
    assert int(subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout)==expected
