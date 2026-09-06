"""Execute emitted formulas; scope correctness requires values, not JS strings."""
import json
from pathlib import Path
import subprocess

import pytest

from pfx2gas.fx import transpile

REPO = Path(__file__).resolve().parents[1]


def evaluate(formula, state=None, item=None, behavior=False, tail=""):
    result = transpile(formula, behavior=behavior, control_names=set(),
                       global_names=set(state or {}))
    assert not result.unmapped, result.unmapped
    script = """
const fs = require('node:fs');
const {formula, state, item, behavior, tail} = JSON.parse(fs.readFileSync(0, 'utf8'));
const FX = require('./static/fx-stdlib.js');
const FXRuntime = {setState: update => Object.assign(state, update)};
const apiPatch = async () => { throw new Error('failed save'); };
const apiRemoveIf = async (name, pred) => {state[name] = state[name].filter(row => !pred(row));};
(async () => {
  const body = behavior ? formula + ';' + tail : 'return (' + formula + ');';
  const fn = new (Object.getPrototypeOf(async function(){}).constructor)(
    'FX','state','item','FXRuntime','apiPatch','apiRemoveIf',body);
  const value = await fn(FX,state,item,FXRuntime,apiPatch,apiRemoveIf);
  process.stdout.write(JSON.stringify(value === undefined ? null : value));
})().catch(error => {console.error(error);process.exitCode=1;});
"""
    run = subprocess.run(["node", "-e", script], cwd=REPO,
        input=json.dumps({"formula": result.js, "state": state or {}, "item": item,
                          "behavior": behavior, "tail": tail}),
        capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr + "\n" + result.js
    return json.loads(run.stdout)


@pytest.mark.parametrize("record,expected", [
    ({"primary__image": {"full": "data:image/png;base64,original"}}, "data:image/png;base64,original"),
    ({"primary__image": None}, "fallback"), (None, "fallback"),
])
def test_inspection_nested_image_formula(record, expected):
    formula = "If(IsBlank(gblSelectedLocation.'Primary Image'.Full), areaInspectionDefaultImage, gblSelectedLocation.'Primary Image'.Full)"
    assert evaluate(formula, {"gblSelectedLocation": record, "areaInspectionDefaultImage": "fallback"}) == expected


def test_quoted_identifiers_and_nested_global_fields_keep_their_identity():
    assert evaluate("'Selected Project'.'Owner''s name'", {"Selected Project": {"owner_s_name": "Ada"}}) == "Ada"
    assert evaluate("Profile.Address.City", {"Profile": {"address": {"city": "Paris"}}}) == "Paris"
    assert evaluate('"Selected Project"', {"Selected Project": "ignored"}) == "Selected Project"


def test_nested_with_preserves_outer_fields_globals_and_shadowing():
    assert evaluate("With({rate: 2, info: {Value: 4}}, With({rate: 3}, rate + info.Value + tax))", {"tax": 5}) == 12
    assert evaluate("With({x: 7}, With({x: Blank()}, IsBlank(x)))", {"x": 9}) is True
    assert evaluate("With({value: 100}, Sum(Table({amount: 2}, {amount: 3}), amount + value))") == 205


def test_filter_preserves_global_predicate_and_all_conditions():
    state = {"Rows": [{"amount": 2}, {"amount": 5}, {"amount": 8}], "cutoff": 3, "limit": 7}
    assert evaluate("Filter(Rows, Amount > cutoff, Amount < limit)", state) == [{"amount": 5}]


def test_gallery_thisitem_is_not_shadowed_by_inner_record_functions():
    assert evaluate("With({Value: 3}, Sum(Table({Value: 2}), ThisRecord.Value + ThisItem.Amount))",
                    item={"amount": 10}) == 12


def test_lookup_projection_addcolumns_and_quoted_table_names():
    state = {"Student Tracker": [{"id": 1, "amount": 2}, {"id": 2, "amount": 3}], "factor": 4}
    assert evaluate("LookUp('Student Tracker', ID = 2, Amount * factor)", state) == 12
    assert evaluate("ShowColumns(AddColumns('Student Tracker', 'New Amount', Amount * factor), ID, 'New Amount')", state) == [
        {"id": 1, "new__amount": 8}, {"id": 2, "new__amount": 12}]


def test_removeif_preserves_outer_scope_and_filters_correct_records():
    assert evaluate("With({cutoff: 3}, RemoveIf(Rows, Amount > cutoff))", {"Rows": [{"amount": 2}, {"amount": 5}]},
                    behavior=True, tail="return state.Rows;") == [{"amount": 2}]


def test_async_iferror_and_with_await_failure_before_following_behavior():
    assert evaluate('With({fallback: "failed"}, Set(result, IfError(Patch(Tasks, Defaults(Tasks), {Name: "x"}), fallback))); Set(after, result)',
                    behavior=True, tail="return state;") == {"result": "failed", "after": "failed"}


def test_forall_awaits_async_results_and_retains_each_record_scope():
    assert evaluate('ForAll(Table({Name: "a"}, {Name: "b"}), '
                    'IfError(Patch(Tasks, Defaults(Tasks), {Name: ThisRecord.Name}), ThisRecord.Name))') == ["a", "b"]


def test_async_table_predicates_are_explicitly_unsupported_not_invalid_js():
    from pfx2gas.analyze import analyze
    from pfx2gas.ir import AppIR, FxExpr

    for formula in [
        "Filter(Rows, Patch(Tasks, Defaults(Tasks), {Name: Name}))",
        "LookUp(Rows, true, Patch(Tasks, Defaults(Tasks), {Name: Name}))",
        "AddColumns(Rows, Extra, Patch(Tasks, Defaults(Tasks), {Name: Name}))",
    ]:
        ir = analyze(AppIR(name="UnsupportedAsyncPredicate", on_start=FxExpr(raw=formula, kind="behavior")))
        assert ir.on_start.js is None and ir.on_start.translation_status == "stubbed"
        assert any("explicit adapter" in row.detail for row in ir.support_matrix)
