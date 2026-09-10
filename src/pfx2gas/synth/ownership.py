"""Dataverse user/team ownership over migrated Sheets records."""
from ..fx.naming import snake


def ownership_contract(source, tables):
    """Use exported logical/type metadata, never a display label named Owner."""
    if source.origin != 'dataverse':
        return None
    fields={field.logical_name:field for field in source.fields if field.logical_name}
    owner=fields.get('ownerid')
    if not owner or owner.type!='lookup' or owner.source_type!='Owner':
        return None
    principals={}
    for table in tables:
        if table.origin!='dataverse' or table.logical_name not in owner.lookup_targets:
            continue
        if table.logical_name not in {'systemuser','team'}:
            continue
        by_logical={field.logical_name:field for field in table.fields if field.logical_name}
        email=by_logical.get('internalemailaddress')
        display=by_logical.get(table.metadata.get('primaryNameAttribute'))
        principals[table.name]={'kind':table.logical_name,'key':snake(table.primary_key),
                                'email':snake(email.name) if email and email.type=='text' else None,
                                'display':snake(display.name) if display and display.type=='text' else None}
    derived={logical:snake(fields[logical].name) for logical in
             ('owninguser','owningteam','owneridname','owneridtype') if logical in fields}
    return {'owner':snake(owner.name),'principals':principals,'derived':derived,
            'limitations':['Ownership is record data, not Dataverse row security, assignment privileges or cascading reassignment',
                           'Owner snapshots retain the migrated key, primary name and email; business-unit ownership and audit defaults require separate adapters']}


SERVER = r'''
function defaultDataverseOwner_(contract) {
  var email = (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  if (!email) throw new Error('Dataverse default ownership requires an identified Google session');
  var users = Object.keys(contract.principals).filter(function (source) {
    return contract.principals[source].kind === 'systemuser';
  });
  if (users.length !== 1 || !contract.principals[users[0]].email)
    throw new Error('Dataverse default ownership requires one migrated Users table with an email field');
  var source = users[0], principal = contract.principals[source];
  var rows = listRows(source).filter(function (row) {
    return typeof row[principal.email] === 'string' && row[principal.email].trim().toLowerCase() === email;
  });
  if (rows.length !== 1 || recordIdentity(source, rows[0]) === null)
    throw new Error('Dataverse default ownership requires one migrated user matching the Google account email');
  var owner = {}; owner[principal.key] = recordIdentity(source, rows[0]);
  return owner;
}

function applyDataverseOwnership_(ds, record, creating) {
  var contract = DATA_CONTRACTS[ds].ownership;
  if (!contract) return record;
  // OwningUser/Team and the companion name/type are derived system fields.
  // Source SDK writes to these read-only columns are ignored, not authority
  // for assigning an owner independently of OwnerId.
  Object.keys(contract.derived).forEach(function (key) { delete record[contract.derived[key]]; });
  if (!creating && record[contract.owner] === undefined) return record;
  var owner = record[contract.owner] === undefined ? defaultDataverseOwner_(contract) : record[contract.owner];
  if (owner === null || owner === '') throw new Error('Dataverse owner cannot be Blank');
  var spec = DATA_CONTRACTS[ds].fields[contract.owner];
  var source = lookupTarget(spec, owner), principal = contract.principals[source];
  if (!principal) throw new Error('Dataverse owner requires an exported and migrated user or team target');
  owner = lookupValue(spec, owner, false, 0); // validate aliases before using the key
  var key = recordIdentity(source, owner);
  var matches = listRows(source).filter(function (row) { return String(recordIdentity(source, row)) === String(key); });
  if (key === null || matches.length !== 1) throw new Error('Dataverse owner record is missing or ambiguous in ' + source);
  var snapshot = {}; snapshot[principal.key] = key;
  [principal.display, principal.email].forEach(function (field) {
    if (field && matches[0][field] !== undefined) snapshot[field] = matches[0][field];
  });
  record[contract.owner] = snapshot;
  var values = {owninguser:principal.kind === 'systemuser' ? snapshot : null,
                owningteam:principal.kind === 'team' ? snapshot : null,
                owneridname:principal.display ? matches[0][principal.display] : null,
                owneridtype:principal.kind};
  Object.keys(contract.derived).forEach(function (key) { record[contract.derived[key]] = values[key]; });
  return record;
}
'''
