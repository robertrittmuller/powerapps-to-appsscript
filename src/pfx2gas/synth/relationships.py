"""Sheets lookup and join storage for explicit exported relationships."""

SERVER = r'''
function setupRelationships_(workbook) {
  if (!Object.keys(RELATIONSHIP_CONTRACTS).some(function (ds) {
    return Object.keys(RELATIONSHIP_CONTRACTS[ds].navigation).some(function (key) {
      var spec = RELATIONSHIP_CONTRACTS[ds].navigation[key];
      return !spec.error && spec.kind === 'many-to-many';
    });
  })) return;
  if (!workbook.getSheetByName('__pfx2gas_links')) {
    var sheet = workbook.insertSheet('__pfx2gas_links');
    sheet.appendRow(['schema', 'left_id', 'right_id']);
    sheet.setFrozenRows(1);
  }
}

function relationshipSpec_(ds, key) {
  assertDataSource(ds);
  var contract = RELATIONSHIP_CONTRACTS[ds];
  var spec = contract && Object.prototype.hasOwnProperty.call(contract.navigation, key) && contract.navigation[key];
  if (!spec) throw new Error('unknown exported relationship: ' + ds + '.' + key);
  if (spec.error) throw new Error(spec.error + ': ' + ds + '.' + key);
  if (['many-to-many', 'one-to-many'].indexOf(spec.kind) < 0) throw new Error('unsupported relationship kind');
  assertDataSource(spec.target);
  return spec;
}

function relationshipLinks_() {
  var sheet = ss().getSheetByName('__pfx2gas_links');
  if (!sheet) throw new Error('relationship storage is missing; run setup() to initialize it');
  var rows = sheet.getDataRange().getValues();
  if (JSON.stringify(rows[0]) !== JSON.stringify(['schema', 'left_id', 'right_id']))
    throw new Error('invalid relationship storage headers');
  var seen = {};
  return rows.slice(1).map(function (row) {
    if (row.length !== 3 || row.some(function (value) { return typeof value !== 'string' || !value; }))
      throw new Error('invalid stored relationship link');
    var identity = JSON.stringify(row);
    if (Object.prototype.hasOwnProperty.call(seen, identity)) throw new Error('duplicate stored relationship link');
    seen[identity] = true;
    return row;
  });
}

function relationshipSpecsFor_(ds) {
  var specs = [];
  Object.keys(RELATIONSHIP_CONTRACTS).forEach(function (source) {
    var navigation = RELATIONSHIP_CONTRACTS[source].navigation;
    Object.keys(navigation).forEach(function (key) {
      var spec = navigation[key];
      if (spec.error || spec.kind !== 'many-to-many') return;
      if (source === ds) specs.push({schema:spec.schema,side:spec.side});
      if (spec.target === ds) specs.push({schema:spec.schema,side:3-spec.side});
    });
  });
  return specs;
}

function listRelationshipLinks_(ds) {
  var schemas = relationshipSpecsFor_(ds).map(function (spec) { return spec.schema; });
  if (!schemas.length) return [];
  return relationshipLinks_().filter(function (row) { return schemas.indexOf(row[0]) >= 0; });
}

function existingRelationshipRecord_(ds, record) {
  assertRecord(record, 'relationship record');
  var id = recordIdentity(ds, record);
  if (typeof id !== 'string' || !id) throw new Error('relationship requires an explicit source primary key: ' + ds);
  var rows = listRows(ds).filter(function (row) { return recordIdentity(ds, row) === id; });
  if (rows.length !== 1) throw new Error('relationship record is missing or ambiguous in ' + ds);
  return id;
}

function relationshipParent_(ds, spec, record) {
  var value = record[spec.lookup];
  if (value === null || value === undefined || value === '') return null;
  var lookup = DATA_CONTRACTS[spec.target].fields[spec.lookup];
  var target = lookupTarget(lookup, value);
  if (target && target !== ds) return null;
  return typeof value === 'string' ? value : recordIdentity(ds, value);
}

function relationshipSnapshot_(ds) {
  var links = listRelationshipLinks_(ds), navigation = RELATIONSHIP_CONTRACTS[ds].navigation;
  var targets = {}, identities = {};
  Object.keys(navigation).forEach(function (key) {
    var spec = navigation[key];
    if (spec.error) return;
    if (!Object.prototype.hasOwnProperty.call(identities, spec.target)) identities[spec.target] = [];
    if (spec.kind === 'many-to-many') {
      if (identities[spec.target] !== null) links.forEach(function (link) { if (link[0] === spec.schema) identities[spec.target].push(link[3-spec.side]); });
    } else identities[spec.target] = null; // one-to-many projections require the child table snapshot
  });
  Object.keys(identities).forEach(function (target) {
    var ids = identities[target];
    targets[target] = ids === null ? listRows(target) : ids.length ? listRows(target).filter(function (record) {
      return ids.indexOf(recordIdentity(target, record)) >= 0;
    }) : [];
  });
  var children = {};
  Object.keys(navigation).forEach(function (key) {
    var spec = navigation[key];
    if (spec.error || spec.kind !== 'one-to-many') return;
    children[key] = targets[spec.target].map(function (record) { return relationshipParent_(ds, spec, record); });
  });
  return {links:links, targets:targets, parents:children};
}

function mutateRelationship_(ds, key, base, record, remove) {
  var spec = relationshipSpec_(ds, key);
  var sourceId = existingRelationshipRecord_(ds, base);
  var targetId = existingRelationshipRecord_(spec.target, record);
  if (spec.mutationError) throw new Error(spec.mutationError);
  if (spec.kind === 'one-to-many') {
    var child = listRows(spec.target).find(function (row) { return recordIdentity(spec.target, row) === targetId; });
    var currentParent = relationshipParent_(ds, spec, child);
    if (remove ? currentParent !== sourceId : currentParent === sourceId) return null;
    if (remove && spec.required) throw new Error('cannot clear a system-required relationship lookup');
    var change = {};
    change[spec.lookup] = remove ? null : listRows(ds).find(function (row) { return recordIdentity(ds, row) === sourceId; });
    patchRow(spec.target, record, change);
    return null;
  }
  var link = [spec.schema, spec.side === 1 ? sourceId : targetId, spec.side === 1 ? targetId : sourceId];
  var rows = relationshipLinks_();
  var index = rows.findIndex(function (row) { return JSON.stringify(row) === JSON.stringify(link); });
  var sheet = ss().getSheetByName('__pfx2gas_links');
  // Retried associations are idempotent in this target adapter. No record is
  // created, patched or deleted by a relationship operation.
  if (remove && index >= 0) sheet.deleteRow(index + 2);
  if (!remove && index < 0) sheet.appendRow(link);
  return null;
}

function assertNoRelationshipLinks_(ds, ids) {
  var navigation = RELATIONSHIP_CONTRACTS[ds].navigation;
  if (Object.keys(navigation).some(function (key) {
    var spec = navigation[key];
    return !spec.error && spec.kind === 'one-to-many' && listRows(spec.target).some(function (record) {
      return ids.indexOf(relationshipParent_(ds, spec, record)) >= 0;
    });
  })) throw new Error('delete requires explicit Unrelate first; relationship cascades are not implemented');
  var links = listRelationshipLinks_(ds);
  if (relationshipSpecsFor_(ds).some(function (spec) {
    return links.some(function (link) {
      return link[0] === spec.schema && ids.indexOf(link[spec.side]) >= 0;
    });
  })) throw new Error('delete requires explicit Unrelate first; relationship cascades are not implemented');
}
'''
