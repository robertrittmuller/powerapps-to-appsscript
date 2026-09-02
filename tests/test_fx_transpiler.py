"""Table-driven tests: Power Fx string -> expected JS."""
import pytest

from pfx2gas.fx import transpile, TranspileError


def js(fx: str, behavior: bool = False) -> str:
    return transpile(fx, behavior=behavior).js


def test_concat_operator():
    assert js('"hello " & Name') == "FX.concatStr('hello ', state.Name)"


def test_arithmetic():
    assert js("1 + 2 * 3") == "(1 + (2 * 3))"


def test_this_item():
    assert js("ThisItem.Name") == "item.name"


def test_control_property_ref():
    assert js("TextInput1.Text") == "val('TextInput1').text"


def test_set_behavior():
    assert js("Set(counter, counter + 1)", behavior=True) == "state.counter = (state.counter + 1);"


def test_navigate():
    assert js("Navigate(Screen2)", behavior=True) == "go('Screen2');"


def test_back():
    assert js("Back()", behavior=True) == "goBack();"


def test_if():
    assert js('If(x > 1, "a", "b")') == "((state.x > 1) ? ('a') : ('b'))"


def test_filter_lambda():
    assert js('Filter(Tasks, Amount > 100 && Status = "Open")') == (
        "FX.filter(state.Tasks, (item) => ((item.amount > 100) && FX.eq(item.status, 'Open')))"
    )


def test_lookup_chain():
    assert js("LookUp(Tasks, Id = 5).Name") == (
        "FX.lookUp(state.Tasks, (item) => FX.eq(item.id, 5)).name"
    )


def test_sum():
    assert js("Sum(Tasks, Amount)") == "FX.sum(state.Tasks, (item) => item.amount)"


def test_count_rows():
    assert js("CountRows(Tasks)") == "FX.countRows(state.Tasks)"


def test_data_source_ident_is_state():
    # bare data source references read like variables in generated state
    assert js("CountRows(Tasks)").count("state.") == 1


def test_patch_emits_server_call():
    out = js(
        'Patch(Tasks, Defaults(Tasks), {Name: TextInput1.Text, Status: "Open"})',
        behavior=True,
    )
    assert "apiPatch('Tasks'" in out
    assert "name:" in out and "status:" in out


def test_remove():
    out = js("Remove(Tasks, ThisItem)", behavior=True)
    assert "apiRemove('Tasks'" in out


def test_collection_calls_route_to_local_runtime():
    """Data calls against a collection mutate state, not the Sheet API."""
    colls = {"colCache"}
    out = transpile("Collect(colCache, {Key: TextInput1.Text, Value: 5})",
                    behavior=True, collections=colls).js
    assert "powerapps_collect(state, 'colCache'" in out
    assert "apiCreate" not in out
    out = transpile("ClearCollect(colCache, {Key: \"a\"})", behavior=True,
                    collections=colls).js
    assert "powerapps_clearCollect(state, 'colCache'" in out
    out = transpile("Remove(colCache, ThisItem)", behavior=True,
                    collections=colls).js
    assert "powerapps_remove(state, 'colCache'" in out
    out = transpile("RemoveIf(colCache, Key = \"a\")", behavior=True,
                    collections=colls).js
    assert "powerapps_removeIf(state, 'colCache'" in out
    # a non-collection source keeps server routing
    out = transpile("Collect(Tasks, {Name: \"x\"})", behavior=True,
                    collections=colls).js
    assert "apiCreate('Tasks'" in out


def test_refresh_on_collection_is_local():
    out = transpile("Refresh(colCache)", behavior=True,
                    collections={"colCache"}).js
    assert "refreshCollection(state, 'colCache')" in out
    assert "refreshData" not in out


def test_unmapped_function_recorded():
    res = transpile("TimeZoneOffset()")
    assert res.js == "FX.unsupported('TimeZoneOffset')"
    assert res.unmapped == ["TimeZoneOffset"]


def test_char_literal_arg():
    assert js("Char(39)") == "String.fromCharCode(39)"


def test_multi_statement_value_formula():
    out = js('Set(a, 1); a + 1')
    assert "state.a = 1" in out


def test_concat_chain():
    assert js('Concat(Tasks, Name & ", ", "")').startswith("FX.concat(state.Tasks")


def test_parse_error_raises_transpile_error():
    with pytest.raises(TranspileError):
        transpile("Filter(Tasks, Amount > )")


def test_snake_case_fields():
    assert js("ThisItem.FullName") == "item.full_name"
