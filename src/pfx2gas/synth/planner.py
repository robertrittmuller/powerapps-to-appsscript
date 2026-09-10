"""Shared Planner semantics implemented in Google Sheets, behind plan membership.

The migration entry point ends in '_' so Apps Script hides it from script.run.
No source memberships or successful empty service are inferred from exports.
"""

SERVER = r'''
var PLANNER_STORE_ = '__pfx2gas_planner';

function setupPlanner_(workbook) {
  if (!GOOGLE_SERVICE_ADAPTERS.Planner) return;
  if (!workbook.getSheetByName(PLANNER_STORE_)) {
    var sheet = workbook.insertSheet(PLANNER_STORE_);
    sheet.getRange(1, 1, 1, 3).setValues([['kind', 'id', 'json']]);
    sheet.setFrozenRows(1);
  }
}

function plannerString_(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(label + ' must be nonempty text');
  return value;
}

function plannerDocument_() {
  var sheet = ss().getSheetByName(PLANNER_STORE_);
  if (!sheet) throw new Error('Planner migration is not configured; rerun setup() and import the task board');
  var rows = sheet.getDataRange().getValues();
  if (JSON.stringify(rows[0]) !== JSON.stringify(['kind','id','json'])) throw new Error('Invalid Planner storage headers');
  var result = {users:[],plans:[],buckets:[],tasks:[],configured:false};
  var seen = {};
  rows.slice(1).forEach(function (row, index) {
    if (row.every(function (cell) { return cell === ''; })) return;
    var kind = row[0], id = row[1], key = JSON.stringify([kind,id]);
    if (seen[key]) throw new Error('Duplicate Planner storage key');
    seen[key] = true;
    var value;
    try { value = JSON.parse(row[2]); } catch (_) { throw new Error('Invalid Planner storage JSON'); }
    if (kind === 'config' && id === 'v1' && value && value.ready === true) { result.configured = true; return; }
    if (!['users','plans','buckets','tasks'].includes(kind) || !value || value.id !== id)
      throw new Error('Invalid Planner storage record');
    result[kind].push(value);
  });
  return result;
}

function plannerDate_(value, label) {
  if (value === null || value === undefined || value === '') return null;
  var match = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,7})?(Z|[+-](\d{2}):(\d{2}))$/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value)))
    throw new Error(label + ' requires an ISO timestamp with a timezone');
  var calendar = new Date(0);
  calendar.setUTCFullYear(+match[1], +match[2]-1, +match[3]);
  if (calendar.getUTCFullYear() !== +match[1] || calendar.getUTCMonth() !== +match[2]-1 ||
      calendar.getUTCDate() !== +match[3] || +match[4] > 23 || +match[5] > 59 || +match[6] > 59 ||
      (match[8] && (+match[8] > 23 || +match[9] > 59))) throw new Error(label + ' contains an invalid calendar date');
  var fraction = /\.(\d+)/.exec(value);
  if (fraction && /[1-9]/.test(fraction[1].slice(3))) throw new Error(label + ' has unsupported sub-millisecond precision');
  var normalized = new Date(value).toISOString();
  if (!/^\d{4}-/.test(normalized)) throw new Error(label + ' is outside the supported calendar range');
  return normalized;
}

function plannerValidate_(data) {
  assertRecord(data, 'Planner migration');
  var by = {};
  ['users','plans','buckets','tasks'].forEach(function (kind) {
    if (!Array.isArray(data[kind])) throw new Error('Planner migration requires ' + kind);
    by[kind] = new Map();
    data[kind].forEach(function (record) {
      assertRecord(record, 'Planner ' + kind);
      plannerString_(record.id, 'Planner ID');
      if (by[kind].has(record.id)) throw new Error('Duplicate Planner migration ID');
      by[kind].set(record.id, record);
    });
  });
  var emails = new Set();
  data.users.forEach(function (user) {
    var email = plannerString_(user.email, 'Google user email').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || emails.has(email)) throw new Error('Invalid or duplicate Google user email');
    emails.add(email); user.email = email;
  });
  data.plans.forEach(function (plan) {
    plannerString_(plan.title, 'Plan title'); plannerString_(plan.group_id, 'Plan group ID');
    if (!Array.isArray(plan.members) || !plan.members.length || new Set(plan.members).size !== plan.members.length ||
        plan.members.some(function (id) { return !by.users.has(id); })) throw new Error('Plan requires distinct migrated members');
  });
  data.buckets.forEach(function (bucket) {
    plannerString_(bucket.name, 'Bucket name');
    if (!by.plans.has(bucket.plan_id)) throw new Error('Bucket plan does not exist');
  });
  data.tasks.forEach(function (task) {
    if (task.bucket_id !== undefined && task.bucket_id !== null && task.bucket_id !== '')
      plannerString_(task.bucket_id, 'Task bucket ID');
    var plan = by.plans.get(task.plan_id), bucket = task.bucket_id && by.buckets.get(task.bucket_id);
    if (!plan || (task.bucket_id && (!bucket || bucket.plan_id !== plan.id))) throw new Error('Task plan/bucket does not match');
    plannerString_(task.title, 'Task title');
    if (task.title.length > 255) throw new Error('Task title exceeds 255 characters');
    if (!Number.isInteger(task.percent_complete) || task.percent_complete < 0 || task.percent_complete > 100)
      throw new Error('Task progress must be an integer from 0 to 100');
    if (!Array.isArray(task.assignees) || new Set(task.assignees).size !== task.assignees.length ||
        task.assignees.some(function (id) { return !plan.members.includes(id); })) throw new Error('Task assignee is not a plan member');
    task.start_date_time = plannerDate_(task.start_date_time, 'Task start');
    task.due_date_time = plannerDate_(task.due_date_time, 'Task due');
    if (task.description !== undefined && typeof task.description !== 'string') throw new Error('Task description must be text');
  });
  ['users','plans','buckets','tasks'].forEach(function (kind) {
    data[kind].forEach(function (record) {
      if (JSON.stringify(record).length > 49000) throw new Error('Planner record exceeds the Sheets cell storage limit');
    });
  });
  return by;
}

function importPlanner_(data) {
  if (!GOOGLE_SERVICE_ADAPTERS.Planner) throw new Error('Planner is not declared by this app');
  // Validate a copy completely before a single write. This is an initial,
  // editor-only import, never a browser operation or a destructive reimport.
  data = JSON.parse(JSON.stringify(data));
  plannerValidate_(data);
  return withDataWriteLock_(function () {
    var existing = plannerDocument_();
    if (existing.configured) throw new Error('Planner is already migrated');
    if (['users','plans','buckets','tasks'].some(function (kind) { return existing[kind].length; }))
      throw new Error('Incomplete Planner storage requires administrator repair before import');
    var rows = [];
    ['users','plans','buckets','tasks'].forEach(function (kind) {
      data[kind].forEach(function (record) { rows.push([kind,record.id,JSON.stringify(record)]); });
    });
    rows.push(['config','v1',JSON.stringify({ready:true})]);
    ss().getSheetByName(PLANNER_STORE_).getRange(2,1,rows.length,3).setValues(rows);
    return {ok:true,plans:data.plans.length,tasks:data.tasks.length};
  });
}

function plannerTask_(task) {
  var assignments = task.assignees.map(function (id) { return {user_id:id,value:{}}; });
  // Connector responses use a table of assignments, unlike Graph's keyed map.
  return {id:task.id,plan_id:task.plan_id,bucket_id:task.bucket_id || null,title:task.title,
    percent_complete:task.percent_complete,start_date_time:task.start_date_time || null,
    due_date_time:task.due_date_time || null,assignments:assignments,
    has_description:!!task.description};
}

function plannerOptions_(value, allowed) {
  value = value === undefined ? {} : value;
  assertRecord(value, 'Planner options');
  Object.keys(value).forEach(function (key) {
    if (!allowed.includes(key)) throw new Error('Unsupported Planner option: ' + key);
  });
  return value;
}

function plannerOperation_(operation, args) {
  var data = plannerDocument_();
  if (!data.configured) throw new Error('Planner migration is not configured; import source plans and Google-user mappings');
  plannerValidate_(data);
  var email = Session.getActiveUser().getEmail().trim().toLowerCase();
  if (!email) throw new Error('Planner requires an identified Google session');
  var user = data.users.find(function (user) { return user.email === email; });
  if (!user) throw new Error('Planner requires a migrated Google user mapping');
  var plans = data.plans.filter(function (plan) { return plan.members.includes(user.id); });
  function plan(id) {
    plannerString_(id, 'Plan ID');
    var found = plans.find(function (p) { return p.id === id; });
    if (!found) throw new Error('Planner plan is missing or access is denied');
    return found;
  }
  function tasks(id) { plan(id); return data.tasks.filter(function (task) { return task.plan_id === id; }).map(plannerTask_); }
  function planResponse(p) { return {id:p.id,title:p.title,owner:p.group_id}; }
  if (operation === 'ListMyPlansV2') return {value:plans.map(planResponse)};
  if (operation === 'ListGroupPlans') {
    plannerString_(args[0], 'Group ID');
    return {value:plans.filter(function (plan) { return plan.group_id === args[0]; }).map(planResponse)};
  }
  if (operation === 'ListTasks' || operation === 'ListTasksV3') return {value:tasks(args[0])};
  if (operation === 'ListMyTasks') return {value:data.tasks.filter(function (task) {
    return task.assignees.includes(user.id) && plans.some(function (p) { return p.id === task.plan_id; });
  }).map(plannerTask_)};
  if (operation === 'ListBucketsV3') {
    plan(args[0]);
    return {value:data.buckets.filter(function (bucket) { return bucket.plan_id === args[0]; }).map(function (bucket) {
      return {id:bucket.id,plan_id:bucket.plan_id,name:bucket.name};
    })};
  }
  var sheet = ss().getSheetByName(PLANNER_STORE_);
  if (operation === 'CreateTaskV3') {
    var parent = plan(args[1]), options = plannerOptions_(args[3],['bucket_id','start_date_time','due_date_time','assignments']);
    var assignees = [];
    if (options.assignments !== null && options.assignments !== undefined && options.assignments !== '') {
      if (typeof options.assignments !== 'string') throw new Error('Planner assignments must be semicolon-separated IDs or emails');
      options.assignments.split(';').forEach(function (value) {
        value = value.trim();
        if (!value) return;
        var member = data.users.find(function (u) { return u.id === value || u.email === value.toLowerCase(); });
        if (!member || !parent.members.includes(member.id)) throw new Error('Task assignee is not a migrated plan member');
        if (!assignees.includes(member.id)) assignees.push(member.id);
      });
    }
    var task = {id:Utilities.getUuid(),plan_id:parent.id,title:args[2],bucket_id:options.bucket_id,
      start_date_time:options.start_date_time,due_date_time:options.due_date_time,
      percent_complete:0,assignees:assignees,description:''};
    data.tasks.push(task); plannerValidate_(data);
    sheet.appendRow(['tasks',task.id,JSON.stringify(task)]);
    return plannerTask_(task);
  }
  if (operation === 'UpdateTaskDetails') {
    var task = data.tasks.find(function (t) { return t.id === args[0]; });
    if (!task) throw new Error('Planner task is missing or access is denied');
    plan(task.plan_id);
    var options = plannerOptions_(args[1],['description']);
    if (options.description !== undefined) task.description = options.description;
    plannerValidate_(data);
    var rows = sheet.getDataRange().getValues();
    var row = rows.findIndex(function (r) { return r[0] === 'tasks' && r[1] === task.id; });
    sheet.getRange(row+1,3).setValue(JSON.stringify(task));
    return {id:task.id,description:task.description || ''};
  }
  throw new Error('Unsupported Planner operation: ' + operation);
}

function connector(service, operation, args) {
  var adapter = GOOGLE_SERVICE_ADAPTERS[service];
  if (!adapter || !Object.prototype.hasOwnProperty.call(GOOGLE_SERVICE_ADAPTERS,service) ||
      !Object.prototype.hasOwnProperty.call(adapter.operations, operation))
    throw new Error('Google adapter operation is not configured: ' + service + '.' + operation);
  if (!Array.isArray(args) || !adapter.operations[operation].arity.includes(args.length))
    throw new Error('Wrong number of connector arguments: ' + operation);
  if (adapter.target === 'google-people-directory') return directoryOperation_(operation,args);
  if (adapter.target !== 'google-sheets-task-board' || service !== 'Planner') throw new Error('Unsupported Google adapter');
  // Lock reads too, so the permission check and mutation see the same board.
  return withDataWriteLock_(function () { return plannerOperation_(operation,args); });
}
'''


MIGRATION_TEMPLATE = '''// Run setup(), then replace null below with your reviewed migration object.
// Required arrays: users, plans, buckets, tasks. See planner-migration.md.
// Keep this function private (trailing underscore); browser RPC cannot invoke it.
function migratePlanner_() {
  var migration = null;
  if (migration === null) throw new Error('Supply reviewed Planner migration data before importing');
  return importPlanner_(migration);
}
'''

MIGRATION_GUIDE = '''# Import the shared task board

Run `setup()` in the Apps Script editor first. In `PlannerMigration.gs`, replace
`null` with a reviewed JSON object containing `users`, `plans`, `buckets` and
`tasks` arrays, then run `migratePlanner_()` in the editor. The import validates
all records before writing and refuses to overwrite an initialized board.
Do not remove the trailing underscore from either migration function.

Use source IDs so existing app settings and links still address the same plans,
buckets and users. Map each user ID to the corresponding Google account email.
The app must have an identified Google session; missing or unmapped identities
are denied. Plan members can read and change that plan's tasks. This membership
model does not reproduce separate Planner administrative roles. Verify identity
and workbook access with each intended user before deployment acceptance.
Google may withhold active-user email from an app executing as its owner,
especially across domains; that configuration is denied, never replaced by the
owner's identity. Execution as the accessing user requires that user's workbook
permissions and can grant direct storage access outside plan checks. Do not
claim per-plan isolation for users with direct workbook access. A restricted
owner-executed deployment with verified same-domain identities, or a separate
authenticated storage service, is needed for stronger isolation.

Record schema (all IDs are nonempty strings):

- users: `id`, unique Google `email`.
- plans: `id`, `title`, `group_id`, nonempty `members` array of user IDs.
- buckets: `id`, `name`, `plan_id`.
- tasks: `id`, `title` (up to 255 characters), `plan_id`, optional `bucket_id`,
  integer `percent_complete` (0–100), `assignees` array of plan-member IDs,
  optional `description`, `start_date_time`, `due_date_time`.

Dates are ISO timestamps with an explicit timezone, preserving time of day.
Microsoft timestamps with extra zero fractional digits are accepted; nonzero
sub-millisecond precision and UTC years outside 0000–9999 are rejected.
Missing dates may be null. Each JSON record must fit within 49,000 characters.
An empty board is valid only after an explicit import; missing migration is
an error. An export usually does not contain live Planner records or membership;
obtain and review those records separately before importing.

Storage is the app workbook's reserved `__pfx2gas_planner` sheet. It is excluded
from the generic data API. Workbook editors can change this data directly;
grant workbook edit access only to board administrators. Re-running setup
retains the board. Conversion preserves an existing PlannerMigration.gs file;
retain reviewed migration data separately as well.

Supported operations are recorded in `data-contract.json`. The converted app
is the shared task interface; tasks do not appear in native Google Tasks.
Assignment audit metadata, ordering hints, Planner roles, categories and external
notifications are not reproduced. Task creation is not retried automatically:
after an uncertain transport or flush failure, inspect the board before retrying
to avoid duplicates. Value-binding reads cache results until an app write,
`FXRuntime.refreshConnector('Planner')` or page reload.
'''
