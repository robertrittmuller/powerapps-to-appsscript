"""Execute emitted formulas; scope correctness requires values, not JS strings."""
import json
from pathlib import Path
import subprocess

import pytest

from pfx2gas.fx import transpile

REPO = Path(__file__).resolve().parents[1]


def evaluate(formula, state=None, item=None, behavior=False, tail="", collections=None):
    result = transpile(formula, behavior=behavior, control_names=set(),
                       global_names=set(state or {}), collections=set(collections or []))
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


def test_updateif_keeps_outer_gallery_item_inner_row_scope_and_first_matching_change():
    state = {'Rows': [{'id':1, 'amount':2}, {'id':2, 'amount':5}], 'increment':3}
    assert evaluate('UpdateIf(Rows As candidate, ThisItem.ID = candidate.ID, '
                    '{Amount: candidate.Amount + increment}, false, {Amount: 99}); Set(done, true)',
                    state, item={'id':2}, behavior=True, collections={'Rows'}, tail='return state;') == {
        'Rows':[{'id':1,'amount':2},{'id':2,'amount':8}], 'increment':3, 'done':True}
    assert evaluate('UpdateIf(Rows, Amount >= 0, {Amount: Amount + 1}, true, {Amount: 99})',
                    state, behavior=True, collections={'Rows'}, tail='return state.Rows;') == [
        {'id':1,'amount':3},{'id':2,'amount':6}]


@pytest.mark.parametrize('formula,behavior', [
    ('UpdateIf(Rows, true)', True), ('UpdateIf(Rows, true, {}, false)', True),
    ('UpdateIf(Rows, true, {})', False),
    ('UpdateIf(Rows, true, Patch(Tasks, Defaults(Tasks), {Name: "async"}))', True),
])
def test_updateif_rejects_incomplete_value_and_async_mutations(formula, behavior):
    from pfx2gas.fx.lexer import FxSyntaxError
    with pytest.raises(FxSyntaxError, match='UpdateIf'):
        transpile(formula, behavior=behavior, collections={'Rows'})


def test_iserror_defers_sync_and_async_failures_and_distinguishes_blank():
    assert evaluate('IsError(Find("x", "text", 0))') is True
    assert evaluate('IsError(Blank())') is False
    for formula in ['IsError(1 / 0)', 'IsError(0 / 0)', 'IsBlankOrError(1 / 0)']:
        assert evaluate(formula) is True
    assert evaluate('Set(failed, IsError(Patch(Tasks, Defaults(Tasks), {Name: "x"}))); Set(after, failed)',
                    behavior=True, tail='return state;') == {'failed':True,'after':True}


def test_async_iferror_and_with_await_failure_before_following_behavior():
    assert evaluate('With({fallback: "failed"}, Set(result, IfError(Patch(Tasks, Defaults(Tasks), {Name: "x"}), fallback))); Set(after, result)',
                    behavior=True, tail="return state;") == {"result": "failed", "after": "failed"}


def test_forall_awaits_async_results_and_retains_each_record_scope():
    assert evaluate('ForAll(Table({Name: "a"}, {Name: "b"}), '
                    'IfError(Patch(Tasks, Defaults(Tasks), {Name: ThisRecord.Name}), ThisRecord.Name))') == ["a", "b"]


def test_word_operators_and_function_forms_preserve_boolean_precedence():
    assert evaluate("true Or false And false") is True
    assert evaluate("And(true, Not(false)) And (false Or true)") is True
    assert evaluate("Not true Or false") is False


def test_sort_by_columns_normalizes_fields_orders_and_keeps_tiebreakers():
    rows = [{"first_name": "Grace", "rank": 1}, {"first_name": "Ada", "rank": 1},
            {"first_name": "Alan", "rank": 2}]
    assert evaluate('SortByColumns(Rows, "Rank", Descending, "FirstName", SortOrder.Ascending)',
                    {"Rows": rows}) == [rows[2], rows[1], rows[0]]
    assert evaluate('SortByColumns(Rows, "FirstName", If(reverse, SortOrder.Descending, Ascending))',
                    {"Rows": rows, "reverse": True}) == [rows[0], rows[2], rows[1]]
    assert evaluate('Sort(Rows, FirstName, Descending)', {"Rows": rows}) == [rows[0], rows[2], rows[1]]


def test_nested_behavior_chains_only_run_the_chosen_branch_and_await_saves():
    formula = '''/* same initialization grammar as Microsoft templates */
        If(true And Not(false),
            Set(result, IfError(Patch(Tasks, Defaults(Tasks), {Name: "x"}), "failed"));
            Set(after, result),
            Set(result, "wrong"); Set(after, "wrong"));
        Concurrent(Set(one, 1); Set(two, one + 1), Set(three, 3))'''
    assert evaluate(formula, behavior=True, tail="return state;") == {
        "result": "failed", "after": "failed", "one": 1, "two": 2, "three": 3}


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


def test_nested_aliases_preserve_outer_records_and_global_disambiguation():
    state = {"Rows": [{"amount": 2}, {"amount": 5}], "Amount": 100, "outer": 7}
    assert evaluate("ForAll(Rows As outer, With({Amount: 10} As inner, "
                    "outer.Amount + inner.Amount + ThisRecord.Amount + [@Amount] + [@outer]))", state) == [129, 132]
    assert evaluate("ForAll(Rows As r, Sum(Table({Amount: 3}) As r, r.Amount) + r.Amount)", state) == [5, 8]
    assert evaluate("With({Amount: 4} as 'a record', 'a record'.Amount)") == 4


def test_named_table_disambiguation_uses_each_tables_active_record():
    state = {"Projects": [{"id": 1}, {"id": 2}],
             "Tasks": [{"id": 20, "project": 2}, {"id": 21, "project": 1}, {"id": 22, "project": 2}]}
    formula = "ForAll(Projects, CountRows(Filter(Tasks, Tasks[@Project] = Projects[@ID])))"
    assert evaluate(formula, state) == [1, 2]
    assert evaluate("ForAll([@Projects], LookUp(Tasks, Project = Projects[@ID], Tasks[@ID]))", state) == [21, 20]
    # Same table nested twice resolves to its innermost active scope.
    assert evaluate("ForAll(Projects, Sum(Projects, Projects[@ID]))", state) == [3, 3]


def test_employee_ideas_disambiguated_remove_and_projection_membership():
    state = {"colVoteCounter": [{"app_idea": "first"}, {"app_idea": "second"}],
             "colIdeas": [{"employee__idea": "SECOND"}]}
    assert evaluate("RemoveIf(colVoteCounter, colVoteCounter[@appIdea] in colIdeas.'Employee Idea')",
                    state, behavior=True, tail="return state.colVoteCounter;") == [{"app_idea": "first"}]
    assert evaluate("ForAll(colVoteCounter As vote, vote.appIdea in colIdeas.'Employee Idea')", state) == [False, True]


def test_removeif_alias_and_multiple_conditions_do_not_delete_other_records():
    state = {"Rows": [{"amount": 2}, {"amount": 5}, {"amount": 8}]}
    assert evaluate("RemoveIf([@Rows] As r, r.Amount > 3, Rows[@Amount] < 7)", state,
                    behavior=True, tail="return state.Rows;") == [{"amount": 2}, {"amount": 8}]


def test_membership_precedence_case_and_single_column_projection():
    state = {"Rows": [{"name": "Alpha", "active": True}, {"name": "Beta", "active": False}]}
    assert evaluate('Filter(Rows, Active And Name in ["alpha"])', state) == [state["Rows"][0]]
    assert evaluate('"alpha" in Rows.Name', state) is True
    assert evaluate('"alpha" exactin Rows.Name', state) is False
    assert evaluate('"PHA" in "Alpha"') is True
    assert evaluate('"PHA" exactin "Alpha"') is False
    assert evaluate('First(Rows.Name).Name', state) == "Alpha"
    assert evaluate('Sum([1, 2, 3] As number, number.Value)') == 6


def test_groupby_aggregates_nested_rows_and_ungroup_restores_fields():
    state = {"Ideas": [{"campaign": "One", "author": "Ada", "votes": 2},
                       {"campaign": "Two", "author": "Ada", "votes": 3},
                       {"campaign": "One", "author": "Grace", "votes": 4}]}
    assert evaluate('ShowColumns(AddColumns(GroupBy(Ideas, "Campaign", "Entries") As campaign, '
                    'Total, Sum(campaign.Entries As idea, idea.Votes)), Campaign, Total)', state) == [
        {"campaign": "One", "total": 6}, {"campaign": "Two", "total": 3}]
    assert evaluate('Ungroup(Filter(GroupBy(Ideas, Campaign, Entries), Campaign = "One"), Entries)', state) == [
        state["Ideas"][0], state["Ideas"][2]]


def test_documented_nested_forall_disambiguation_and_ungroup_example():
    assert evaluate('Concat(Ungroup(ForAll(X, ForAll(Y, '
                    'Y[@Value] & Text(X[@Value]) & [@Value])), "Value"), Value, ",")',
                    {"X": [1, 2], "Y": ["A", "B"], "Value": "!"}) == "A1!,B1!,A2!,B2!"


@pytest.mark.parametrize("choice,expected", [(1, "first"), (2, "second"), (3, "third"), (4, "fallback")])
def test_multibranch_if_preserves_every_result_and_optional_fallback(choice, expected):
    assert evaluate('If(choice = 1, "first", choice = 2, "second", choice = 3, "third", "fallback")',
                    {"choice": choice}) == expected
    assert evaluate('If(false, 1, false, 2)') is None


def test_multibranch_if_only_evaluates_selected_actions_and_awaits_them():
    assert evaluate('If(false, Set(result, "wrong"), true, '
                    'Set(result, IfError(Patch(Tasks, Defaults(Tasks), {Name: "x"}), "failed")); Set(after, result), '
                    'Set(unreachable, true), Set(result, "wrong"), Set(result, "wrong fallback")); Set(done, after)',
                    behavior=True, tail="return state;") == {"result": "failed", "after": "failed", "done": "failed"}


def test_switch_evaluates_subject_once_and_awaits_only_the_selected_result():
    assert evaluate('Set(result, Switch(With({}, Set(reads, reads + 1); reads), '
                    '0, "wrong", 1, IfError(Patch(Tasks, Defaults(Tasks), {Name: "x"}), "failed"), '
                    '2, "wrong", "fallback")); Set(after, result)',
                    {"reads": 0}, behavior=True, tail="return state;") == {"reads": 1, "result": "failed", "after": "failed"}


def test_out_of_scope_disambiguation_is_ledgered_instead_of_reading_global_table():
    from pfx2gas.analyze import analyze
    from pfx2gas.ir import AppIR, FxExpr
    for formula in ["Set(x, Rows[@ID])", "Set(x, Filter(Rows, true)[@ID])"]:
        ir = analyze(AppIR(name="InvalidScope", on_start=FxExpr(raw=formula, kind="behavior")))
        assert ir.on_start.js is None and ir.on_start.translation_status == "stubbed"
        assert any("no active record scope" in row.detail for row in ir.support_matrix)
