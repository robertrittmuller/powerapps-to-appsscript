from pfx2gas.analyze import analyze
from pfx2gas.ir import AppIR, DataSource, FxExpr


def test_nested_formula_collection_discovery_preserves_external_sources():
    ir = AppIR(name="Discovery", data_sources=[DataSource(name="Contacts", origin="sharepoint")],
               on_start=FxExpr(raw='If(true, ClearCollect(LocalRows, {Title: "one"}, {Title: "two"})); '
                                  'Collect(Contacts, {Title: "external"})', kind="behavior"))
    analyze(ir)
    assert {ds.name: ds.origin for ds in ir.data_sources} == {
        "Contacts": "sharepoint", "LocalRows": "collection",
    }
    assert {"LocalRows", "Contacts"}.issubset(ir.global_vars)
    assert "powerapps_clearCollect(state, 'LocalRows', {title: 'one'}, {title: 'two'})" in ir.on_start.js
    assert "apiCreate('Contacts'" in ir.on_start.js


def test_nested_quoted_source_mutations_infer_fields_without_becoming_collections():
    ir = AppIR(name="Schema", data_sources=[DataSource(name="Work Items", origin="sharepoint")],
        on_start=FxExpr(raw='With({fallback: "failed"}, IfError(Patch(\'Work Items\', Defaults(\'Work Items\'), '
                           '{Title: "Example", Amount: 2, Active: true}), fallback))', kind="behavior"))
    analyze(ir)
    assert ir.data_sources[0].origin == "sharepoint"
    assert {field.name: field.type for field in ir.data_sources[0].fields} == {
        "id": "text", "Title": "text", "Amount": "number", "Active": "bool"}
