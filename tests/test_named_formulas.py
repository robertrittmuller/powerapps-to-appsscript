import json

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fidelity import ledger_rows
from pfx2gas.fx import transpile
from pfx2gas.fx.lexer import FxSyntaxError
from pfx2gas.named_formulas import declarations, validate_value
from pfx2gas.parse import parse
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import UnpackedApp


def named_app(formulas, on_start=None):
    props = {'Formulas': '=' + formulas}
    if on_start:
        props['OnStart'] = '=' + on_start
    return analyze(parse(UnpackedApp(app_name='Named', app_yaml={'App': {'Properties': props}},
                                    screens={'Home': {'Home': {'Properties': {}}}})))


def test_declarations_preserve_quoted_text_comments_records_and_comparisons():
    source = '''// ignored = ;
    Later = Base + 1; Base = 2; 'Menu title' = "Base; ""quoted""";
    Rows = [{Title:";", Ready: Base = 2}]; /* ; fake = 1 */
    Selected = Filter(Rows, Ready);'''
    values = declarations(source)
    assert list(values) == ['Later', 'Base', 'Menu title', 'Rows', 'Selected']
    assert values['Menu title'] == '"Base; ""quoted"""'
    assert values['Rows'] == '[{Title:";", Ready: Base = 2}]'
    for value in values.values():
        validate_value(value)


@pytest.mark.parametrize('source', [
    'X=1;x=2;', 'X=;', 'X.Y=1;', 'Fn(x:Number):Number=x;',
    'Kind := Type({X:Number});', 'X = [1,2;', 'X=(1];', '__runtime=1;',
    'X "=" 1;', "''=1;", 'Self=1;',
])
def test_invalid_declarations_are_not_comparisons_or_partial_success(tmp_path, source):
    with pytest.raises(FxSyntaxError):
        declarations(source)
    ir = named_app(source)
    assert ir.named_formula_error and not ir.named_formulas
    synthesize(ir, tmp_path / 'App')
    row = next(row for row in ledger_rows(ir) if row['property'] == 'Formulas')
    assert row['emission'] == 'unsupported' and row['translation'] == 'stubbed'
    assert ir.properties['Formulas'].blocked_dependencies


@pytest.mark.parametrize('source', [
    'Set(x,1)', 'If(true, Notify("side effect"), 0)',
    '{Record: ClearCollect(Rows,{Title:"bad"})}', 'Concurrent(Set(x,1),Set(y,2))',
    'With({x:1}, x; x+1)', 'Rand()', 'Now()', 'GUID()',
])
def test_named_values_reject_effects_and_unimplemented_volatile_scheduling(tmp_path, source):
    ir = named_app('ValueName = ' + source + ';')
    expr = ir.named_formulas['ValueName']
    assert expr.js is None and expr.blocked_dependencies
    synthesize(ir, tmp_path / 'App')
    assert ledger_rows(ir)[0]['emission'] == 'unsupported'


def test_named_formula_cannot_be_assigned_or_mutated():
    for behavior in ['Set(Total,5)', 'Clear(TOTAL)', 'Collect(total,{x:1})', 'Patch(Total,{x:1})']:
        ir = named_app('Total=3;', behavior)
        assert ir.on_start.js is None
        assert ir.on_start.blocked_dependencies
    assert named_app('Total=3;', 'Set(Total,5)').named_formula_error


def test_named_lookup_is_case_insensitive_without_stealing_record_scope():
    result = transpile('With({Total:7}, total + [@TOTAL])', named_formulas={'Total'})
    assert 'state.Total' in result.js
    assert 'scopeValue' in result.js


def test_each_named_declaration_has_its_own_fidelity_row(tmp_path):
    ir = named_app('Later=Base+1;Base=2;')
    project = synthesize(ir, tmp_path / 'App')
    rows = json.loads((project/'conversion-ledger.json').read_text())['formulas']
    assert [row['property'] for row in rows] == ['Formulas.Later', 'Formulas.Base']
    assert all(row['translation'] == 'rule' and row['emission'] == 'approximated' for row in rows)


def test_literal_await_text_does_not_become_an_async_dependency(tmp_path):
    ir = named_app('Message="await response";')
    synthesize(ir, tmp_path/'App')
    assert ir.named_formulas['Message'].translation_status == 'rule'
    assert ir.named_formulas['Message'].emission_status == 'approximated'


def test_llm_cannot_replace_invalid_declarations_or_purity_guards():
    from pfx2gas.cli import _llm_fallback
    class ForbiddenClient:
        def translate_formula(self, *_args, **_kwargs):
            raise AssertionError('A model cannot repair invalid declarations or make named values writable')
    for ir in [named_app('X=Set(y,1);'), named_app('Fn(x:Number):Number=x;'),
               named_app('Total=3;', 'Clear(Total)')]:
        _llm_fallback(ir, ForbiddenClient())


@pytest.mark.parametrize('formula,error', [
    ('A=B;B=A;', 'Circular named formula'),
    ('A=Set(changed,1);', 'Named formulas cannot call behavior function'),
    ('Fn(x:Number):Number=x;', 'user-defined functions/types are unsupported'),
])
def test_invalid_named_formulas_fail_in_the_generated_runtime(tmp_path, formula, error):
    from pfx2gas.ir import ControlNode, FxExpr
    from pfx2gas.startup_sim import simulate_project
    ir = named_app(formula)
    ir.screens[0].controls.append(ControlNode(name='Caption', type='Label', properties={'Text':FxExpr(raw='A')}))
    project = synthesize(analyze(ir), tmp_path/'App')
    verdict = simulate_project(project)
    assert any(error in text for text in verdict['consoleErrors']), verdict
