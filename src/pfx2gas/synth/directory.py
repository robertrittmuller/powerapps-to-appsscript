"""Google People directory adapter; source identities are migrated, never guessed."""

SERVER = r'''
var DIRECTORY_STORE_ = '__pfx2gas_directory';
var DIRECTORY_FIELDS_ = 'metadata,names,emailAddresses,organizations,phoneNumbers,locations,photos';

function hasDirectory_() {
  return Object.keys(GOOGLE_SERVICE_ADAPTERS).some(function (name) {
    return GOOGLE_SERVICE_ADAPTERS[name].target === 'google-people-directory';
  });
}

function setupDirectory_(workbook) {
  if (!hasDirectory_() || workbook.getSheetByName(DIRECTORY_STORE_)) return;
  var sheet = workbook.insertSheet(DIRECTORY_STORE_);
  sheet.getRange(1,1,1,3).setValues([['kind','id','json']]);
  sheet.setFrozenRows(1);
}

function directoryText_(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(label + ' must be nonempty text');
  return value;
}

function validateDirectoryMappings_(users) {
  if (!Array.isArray(users)) throw new Error('Directory migration requires a users array');
  var keys = new Map(), resources = new Set(), emails = new Set();
  users.forEach(function (user) {
    assertRecord(user, 'Directory mapping');
    Object.keys(user).forEach(function (key) {
      if (!['id','google_email','resource_name','aliases'].includes(key)) throw new Error('Unknown directory mapping field: ' + key);
    });
    directoryText_(user.id, 'Source user ID');
    var email = directoryText_(user.google_email, 'Google email').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || emails.has(email)) throw new Error('Invalid or duplicate directory Google email');
    user.google_email = email; emails.add(email);
    if (typeof user.resource_name !== 'string' || !/^people\/[A-Za-z0-9_-]+$/.test(user.resource_name) ||
        user.resource_name === 'people/me' || resources.has(user.resource_name)) throw new Error('Invalid or duplicate Google resource name');
    resources.add(user.resource_name);
    if (user.aliases === undefined) user.aliases = [];
    if (!Array.isArray(user.aliases)) throw new Error('Directory aliases must be an array');
    [user.id,user.resource_name,email].concat(user.aliases).forEach(function (key) {
      key = directoryText_(key, 'Directory identity alias').trim().toLowerCase();
      if (keys.has(key) && keys.get(key) !== user) throw new Error('Ambiguous directory identity mapping');
      keys.set(key,user);
    });
    if (JSON.stringify(user).length > 49000) throw new Error('Directory mapping exceeds the Sheets cell limit');
  });
  return keys;
}

function directoryMappings_() {
  var sheet = ss().getSheetByName(DIRECTORY_STORE_);
  if (!sheet) throw new Error('Directory migration is not configured; run setup() and import identity mappings');
  var rows = sheet.getDataRange().getValues();
  if (JSON.stringify(rows[0]) !== JSON.stringify(['kind','id','json'])) throw new Error('Invalid directory storage headers');
  var configured = false, users = [], seen = new Set();
  rows.slice(1).forEach(function (row) {
    if (row.every(function (cell) { return cell === ''; })) return;
    var key = JSON.stringify([row[0],row[1]]);
    if (seen.has(key)) throw new Error('Duplicate directory storage key');
    seen.add(key);
    var value;
    try { value = JSON.parse(row[2]); } catch (_) { throw new Error('Invalid directory storage JSON'); }
    if (row[0] === 'config' && row[1] === 'v1' && value && value.ready === true) { configured=true; return; }
    if (row[0] !== 'users' || !value || value.id !== row[1]) throw new Error('Invalid directory storage record');
    users.push(value);
  });
  return {configured:configured,users:users,keys:validateDirectoryMappings_(users)};
}

function importDirectory_(data) {
  if (!hasDirectory_()) throw new Error('Directory adapter is not declared by this app');
  assertRecord(data, 'Directory migration');
  if (!Array.isArray(data.users)) throw new Error('Directory migration requires a users array');
  if (Object.keys(data).some(function (key) { return key !== 'users'; })) throw new Error('Unknown directory migration field');
  var users = JSON.parse(JSON.stringify(data.users));
  validateDirectoryMappings_(users);
  return withDataWriteLock_(function () {
    var existing = directoryMappings_();
    if (existing.configured || existing.users.length) throw new Error('Directory storage is already initialized or requires administrator repair');
    var rows = users.map(function (user) { return ['users',user.id,JSON.stringify(user)]; });
    rows.push(['config','v1',JSON.stringify({ready:true})]);
    ss().getSheetByName(DIRECTORY_STORE_).getRange(2,1,rows.length,3).setValues(rows);
    return {ok:true,users:users.length};
  });
}

function directorySession_() {
  var active = (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  var effective = (Session.getEffectiveUser().getEmail() || '').trim().toLowerCase();
  if (!active || active !== effective) throw new Error('Directory requires the identified accessing Google user; owner-delegated directory access is not supported');
  if (typeof People === 'undefined' || !People.People) throw new Error('Enable the Google People advanced service and directory sharing');
  return active;
}

function directoryPages_(query, limit) {
  var people = [], token, tokens = new Set(), resources = new Set(), deadline = Date.now()+20000;
  for (var page = 0; page < 100; page++) {
    if (Date.now() > deadline) throw new Error('Google directory pagination exceeded the request budget');
    var options = {readMask:DIRECTORY_FIELDS_,sources:['DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE'],
                   pageSize:Math.min(500,limit ? limit-people.length : 500)};
    if (token) options.pageToken = token;
    var response;
    if (query) { options.query=query; response=People.People.searchDirectoryPeople(options); }
    else response=People.People.listDirectoryPeople(options);
    assertRecord(response,'Google directory response');
    if (response.people !== undefined && !Array.isArray(response.people)) throw new Error('Invalid Google directory people');
    (response.people || []).forEach(function (person) {
      assertRecord(person,'Google directory person');
      directoryText_(person.resourceName,'Google person resource name');
      if (resources.has(person.resourceName)) throw new Error('Repeated Google directory person; retry the search');
      resources.add(person.resourceName); people.push(person);
    });
    if (people.length > 10000) throw new Error('Google directory exceeds the 10000-result adapter limit');
    if (limit && people.length >= limit) return people.slice(0,limit);
    token = response.nextPageToken;
    if (token === undefined || token === '') return people;
    if (typeof token !== 'string' || tokens.has(token)) throw new Error('Invalid or repeated Google directory page token');
    tokens.add(token);
  }
  throw new Error('Google directory pagination exceeded the page limit');
}

function directoryValues_(person, field) {
  var values = person[field] === undefined ? [] : person[field];
  if (!Array.isArray(values)) throw new Error('Invalid Google person field: ' + field);
  values.forEach(function (value) { assertRecord(value,'Google person ' + field + ' entry'); });
  return values;
}

function directoryPrimary_(person, field) {
  var values = directoryValues_(person,field);
  if (!values.length) return {};
  if (values.length === 1) return values[0];
  var primary = values.filter(function (value) { return value.metadata && value.metadata.primary === true; });
  if (primary.length !== 1) throw new Error('Ambiguous Google person primary field: ' + field);
  return primary[0];
}

function directoryPerson_(person, mappings) {
  assertRecord(person, 'Google person');
  var mapping = mappings.users.find(function (user) { return user.resource_name === person.resourceName; });
  if (!mapping) throw new Error('Google directory person requires a migrated source identity: ' + person.resourceName);
  if (person.metadata && person.metadata.deleted) throw new Error('Google directory person is deleted');
  if (!directoryValues_(person,'emailAddresses').some(function (email) {
    return typeof email.value === 'string' && email.value.toLowerCase() === mapping.google_email;
  })) throw new Error('Google directory identity does not match the migrated email');
  return mapping;
}

function directoryProfile_(person, mapping) {
  var name = directoryPrimary_(person,'names'), org = directoryPrimary_(person,'organizations');
  var location = directoryPrimary_(person,'locations'), phones = directoryValues_(person,'phoneNumbers');
  phones.forEach(function (phone) { directoryText_(phone.value,'Google phone number'); });
  var mobile = phones.filter(function (phone) { return phone.type === 'mobile'; });
  var primaryMobile = directoryPrimary_({phoneNumbers:mobile},'phoneNumbers');
  return {id:mapping.id,mail:mapping.google_email,user_principal_name:mapping.google_email,
    display_name:name.displayName || null,given_name:name.givenName || null,surname:name.familyName || null,
    job_title:org.title || null,department:org.department || null,company_name:org.name || null,
    office_location:location.value || null,
    business_phones:phones.filter(function (phone) { return phone.type === 'work'; }).map(function (phone) { return phone.value; }),
    mobile_phone:primaryMobile.value || null};
}

function directoryOperation_(operation, args) {
  directorySession_();
  var mappings = withDataWriteLock_(directoryMappings_);
  if (!mappings.configured) throw new Error('Directory migration is not configured; import source-to-Google identity mappings');
  if (operation === 'SearchUser') {
    var options = args[0] === undefined ? {} : args[0];
    assertRecord(options,'SearchUser options');
    Object.keys(options).forEach(function (key) { if (!['search_term','top'].includes(key)) throw new Error('Unsupported SearchUser option: ' + key); });
    var query = options.search_term == null ? '' : options.search_term;
    if (typeof query !== 'string') throw new Error('Directory search term must be text');
    var limit = options.top;
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 10000)) throw new Error('SearchUser top must be an integer from 1 to 10000');
    return directoryPages_(query,limit).map(function (person) { return directoryProfile_(person,directoryPerson_(person,mappings)); });
  }
  var key = directoryText_(args[0],'User identity').trim().toLowerCase(), mapping = mappings.keys.get(key);
  if (!mapping) throw new Error('User identity requires a migrated Google account mapping');
  var person = People.People.get(mapping.resource_name,{personFields:DIRECTORY_FIELDS_,sources:['READ_SOURCE_TYPE_PROFILE']});
  if (directoryPerson_(person,mappings) !== mapping) throw new Error('Google returned a different mapped identity');
  if (operation === 'UserProfileV2') {
    var profile = directoryProfile_(person,mapping), options = args[1] === undefined ? {} : args[1];
    assertRecord(options,'UserProfileV2 options');
    if (Object.keys(options).some(function (key) { return key !== 'select'; })) throw new Error('Unsupported UserProfileV2 option');
    if (options.select === undefined) return profile;
    var selection = directoryText_(options.select,'Profile select fields').split(',');
    var selected = {};
    selection.forEach(function (field) {
      var key = field.trim().replace(/([a-z0-9])([A-Z])/g,'$1_$2').toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(profile,key)) throw new Error('Unsupported Google profile field: ' + field);
      selected[key] = profile[key];
    });
    return selected;
  }
  if (operation === 'UserPhotoV2') {
    var photo = directoryPrimary_(person,'photos');
    if (!photo.url || photo.default === true) return null;
    if (typeof photo.url !== 'string' || !/^https:\/\/[a-z0-9.-]+\/(?:[^\s]*)$/i.test(photo.url)) throw new Error('Invalid Google profile photo URL');
    return photo.url;
  }
  throw new Error('Unsupported Google directory operation: ' + operation);
}
'''

MIGRATION_TEMPLATE = '''// Run setup(), then supply reviewed identity mappings. See directory-migration.md.
// Keep the trailing underscore: this entry point must remain editor-only.
function migrateDirectory_() {
  var migration = null;
  if (migration === null) throw new Error('Supply reviewed directory identity mappings before importing');
  return importDirectory_(migration);
}
'''

MIGRATION_GUIDE = '''# Connect the Google domain directory

Office365Users and Microsoft365Users profile operations use the native Google
People advanced service. The generated manifest enables People v1 and requests
directory.readonly and userinfo.email scopes. Enable the People API in the
associated Google Cloud project if it is not enabled automatically. The domain
administrator must allow directory profile sharing. Deploy as the accessing
Google user, authorize the requested scopes, and verify visibility with each
intended user. Owner-delegated directory access and unidentified sessions are
rejected. The accessing user also needs access to the app workbook; direct
workbook access bypasses the app's data permissions.

Run setup() in the editor. Replace null in DirectoryMigration.gs with a reviewed
object such as:

```json
{"users":[{"id":"original-microsoft-user-id",
 "google_email":"person@example.com","resource_name":"people/123456",
 "aliases":["person@previous-domain.example"]}]}
```

Use the exact resourceName returned by Google's domain directory for that person;
never use people/me. Keep the source ID so existing assignments retain their
identity, and map it to the corresponding Google account email. Optional aliases
resolve former emails or principal names. Every source ID, resource name, email,
and alias must identify one person unambiguously. Each record must fit within
49,000 characters. Then run migrateDirectory_() in the editor. Import validates
all mappings before writing and refuses to overwrite an initialized directory.
Keep both migration functions private with their trailing underscores.

The returned id is the preserved source ID; mail and userPrincipalName are the
mapped Google email. Migrate other stored email fields in the app's data and
Planner user mappings to the same Google emails. Every directory person returned
by search must have a mapping; an unmapped person fails the search rather than
disappearing silently. An explicit empty import is allowed, but it cannot resolve
people. Missing migration is an error. Re-conversion preserves your existing
DirectoryMigration.gs. Mappings live in the reserved __pfx2gas_directory sheet,
which is excluded from the generic data API. Workbook editors can change it.

Supported calls: SearchUser (V1 array result), UserProfileV2, UserPhotoV2. Search
uses Google's prefix matching and caller-visible domain profiles, not Microsoft
search semantics or personal contacts. Empty search lists the directory. Pages
are read until completion or an explicit top limit; 10,000 results, 100 pages,
or a 20-second pagination budget are hard limits, never silent truncation.
Concurrent directory changes can cause a repeated-person error requiring retry.

Profiles map primary name, organization and location, work phones and a primary
mobile phone. Ambiguous primary fields fail. Microsoft-only fields such as
accountEnabled, guest status and manager information are not reproduced. The
optional select argument accepts only mapped fields. Photos return Google's
HTTPS image URL, not Microsoft binary content; absent custom photos are Blank.
Verify image visibility and URL lifetime in the deployed app. Native permission,
quota, missing-identity and API failures remain errors for source IfError logic.
Value-binding reads cache until connector invalidation or page reload.

Local tests execute the generated server with explicit Google API response
fixtures. They do not establish live domain permissions or deployment fidelity.
'''
