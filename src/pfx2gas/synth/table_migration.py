"""Private, append-only import of reviewed records, including native read-only values."""

SERVER = r'''
function importTableRows_(ds, records) {
  assertDataSource(ds);
  if (!Array.isArray(records) || !records.length) throw new Error('Table import requires a nonempty records array');
  return withDataWriteLock_(function () {
    var contract = DATA_CONTRACTS[ds], sheet = sheetFor(ds);
    var values = sheet.getDataRange().getValues(), headers = values[0] || [];
    if (JSON.stringify(headers) !== JSON.stringify(Object.keys(contract.fields)))
      throw new Error('Table import headers differ from the generated contract: ' + ds);
    var primary = contract.primaryKey, keyIndex = headers.indexOf(primary), keys = new Set();
    if (keyIndex < 0) throw new Error('Table import requires a primary key: ' + ds);
    values.slice(1).forEach(function (row) {
      if (row.every(function (value) { return value === ''; })) return;
      var key = row[keyIndex];
      if (key === '' || key === null || key === undefined || keys.has(String(key)))
        throw new Error('Existing table has missing or duplicate keys; repair before importing: ' + ds);
      keys.add(String(key));
    });
    // Preserve imported read-only/calculated values. Client CRUD continues to
    // use applyColumnRules_, ownership and state defaults. Import guesses none.
    var rows = records.map(function (record) {
      assertRecord(record, 'Imported record');
      var normalized = normalizeRecord(ds, record), key = normalized[primary];
      if (key === '' || key === null || key === undefined || keys.has(String(key)))
        throw new Error('Imported table has missing or duplicate keys: ' + ds);
      keys.add(String(key));
      var cells = headers.map(function (field) { return encodeCell(ds, field, normalized[field]); });
      validateRequiredColumns_(ds, headers, cells);
      return cells;
    });
    // All records must validate before extending or writing the sheet.
    ensureSheetCapacity_(sheet, values.length + rows.length, headers.length);
    sheet.getRange(values.length + 1, 1, rows.length, headers.length).setValues(rows);
    return {ok:true, source:ds, rows:rows.length};
  });
}
'''

MIGRATION_TEMPLATE = '''/** Operator-edited, private table migration; preserved by re-conversion. */
function migrateTableData_() {
  // Replace with reviewed source rows keyed by the generated table name.
  // Keep original primary keys and read-only values, and map stored identities
  // deliberately. Each table is validated before its append; tables are separate writes.
  var tables = {};
  if (!Object.keys(tables).length) throw new Error('Supply reviewed source table records first');
  return Object.keys(tables).map(function (name) { return importTableRows_(name, tables[name]); });
}
'''

MIGRATION_GUIDE = '''# Import source table records

Run `setup()` in the Apps Script editor, then fill `TableMigration.gs` with
reviewed rows keyed by the generated table name and run `migrateTableData_()`.
Use logical, display or canonical field names from `data-contract.json`.
Preserve original primary keys. Supply required stored columns, including
read-only user provisioning values, from the source data. The importer adds
no defaults, IDs, names, ownership, audit values or calculated values.

Unlike client CRUD, this private import preserves read-only and calculated
values already present in the source snapshot. Derived lookup labels may be
blank; imported labels and calculated values remain snapshots. Importing does
not implement subsequent calculations, lookup propagation or Dataverse roles.

Each table append holds the script lock and validates every row's columns,
types, choices, required stored values and unique keys before writing any rows.
Duplicates against existing data fail; a repeated import never overwrites rows.
Tables are separate writes, with no multi-table transaction. A Sheets write or
flush failure can leave an uncertain outcome; inspect keys before retrying.
Reconcile counts, identities, lookups and relationships after import. The helper
does not check foreign-key existence or migrate many-to-many membership.

Functions ending in `_` cannot be called through `google.script.run`; this
import is an administrator action in the editor, outside the app's data API.
Re-conversion preserves `TableMigration.gs`. Test fixture records are synthetic
examples and must never be substituted for a real tenant export.
'''
