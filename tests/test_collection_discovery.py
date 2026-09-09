from pfx2gas.analyze import analyze
from pfx2gas.ir import AppIR, DataSource, FieldDef, FxExpr


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


def test_collection_aliases_follow_explicit_table_lineage_including_empty_and_transitive_reads():
    ir = analyze(AppIR(name='TypedDrafts', data_sources=[DataSource(name='Responses', origin='dataverse',
        fields=[FieldDef(name='Instructions', aliases=['msft_name'], logical_name='msft_name')])],
        on_start=FxExpr(raw='ClearCollect(Copy, Drafts); ClearCollect(Drafts, Filter(Responses, false)); '
                           'Collect(Drafts, {msft_name: "Title"}); Collect(Unrelated, {msft_name: "plain"})', kind='behavior')))
    sources = {ds.name: ds for ds in ir.data_sources}
    for name in ['Drafts', 'Copy']:
        assert sources[name].metadata['collectionSourceTables'] == ['Responses']
        assert sources[name].metadata['columnAliases']['msft_name'] == 'instructions'
        assert sources[name].metadata['columnAliases']['instructions'] == 'instructions'
    # Identical-looking column names alone are not evidence of a Dataverse type.
    assert 'columnAliases' not in sources['Unrelated'].metadata


def test_conflicting_exported_collection_aliases_are_reported_and_retained_for_runtime_rejection():
    ir = analyze(AppIR(name='ConflictingDrafts', data_sources=[
        DataSource(name='A', origin='dataverse', fields=[FieldDef(name='Title', aliases=['shared_name'])]),
        DataSource(name='B', origin='dataverse', fields=[FieldDef(name='Instructions', aliases=['shared_name'])])],
        on_start=FxExpr(raw='ClearCollect(Drafts, A); Collect(Drafts, B)', kind='behavior')))
    collection = next(ds for ds in ir.data_sources if ds.name == 'Drafts')
    error = collection.metadata['collectionContractError']
    assert 'shared_name' in error and error in ir.warnings


def test_updateif_infers_each_change_record_without_turning_external_tables_into_collections():
    ir = analyze(AppIR(name='Updates', data_sources=[DataSource(name='External', origin='dataverse')],
        on_start=FxExpr(raw='ClearCollect(Drafts, {Amount: 0}); '
            'UpdateIf(Drafts, Amount = 0, {Name: "one"}, true, {Active: false}); '
            'UpdateIf(External, true, {Title: "unsupported"})', kind='behavior')))
    sources = {ds.name: ds for ds in ir.data_sources}
    assert {'Amount', 'Name', 'Active'} <= {field.name for field in sources['Drafts'].fields}
    assert sources['External'].origin == 'dataverse'
    assert 'UpdateIf against an external data source' in ir.on_start.js
