/* Tests for static/fx-stdlib.js — run with: node --test tests/js/ */
const test = require('node:test');
const assert = require('node:assert');
const FX = require('../../static/fx-stdlib.js');

test('Concurrent starts independent deferred branches and awaits every result', async () => {
  let releaseFirst, releaseSecond, finished = false;
  const events = [];
  const work = FX.concurrent([
    async () => {events.push('first:start'); await new Promise(resolve=>{releaseFirst=resolve;}); events.push('first:end');},
    async () => {events.push('second:start'); await new Promise(resolve=>{releaseSecond=resolve;}); events.push('second:end');},
  ]).then(result=>{finished=true; return result;});
  await Promise.resolve();
  assert.deepStrictEqual(events,['first:start','second:start']);
  releaseSecond();
  await Promise.resolve();
  assert.strictEqual(finished,false);
  releaseFirst();
  assert.strictEqual(await work,true);
  assert.deepStrictEqual(events,['first:start','second:start','second:end','first:end']);
});

test('Concurrent reports the first argument error after other branches finish', async () => {
  let releaseFirst, finished = false, survivor = false;
  const first = new Error('first argument'), second = new Error('second argument');
  const work = FX.concurrent([
    async () => {await new Promise(resolve=>{releaseFirst=resolve;}); throw first;},
    () => {throw second;},
    async () => {await Promise.resolve(); survivor=true;},
  ]).then(()=>assert.fail('expected rejection'), error=>{finished=true; return error;});
  await Promise.resolve();
  await Promise.resolve();
  assert.strictEqual(survivor,true);
  assert.strictEqual(finished,false);
  releaseFirst();
  assert.strictEqual(await work,first);
  let ran = false;
  await assert.rejects(FX.concurrent([()=>{ran=true;}, 0]),/deferred formulas/);
  assert.strictEqual(ran,false);
});

test('current-user views require one explicit source identity mapped to the Google email', () => {
  const users = [{user:'source-one', primary_email:'User@Example.test'}, {user:'source-two', primary_email:'other@example.test'}];
  const id = FX.userId(users, 'user@example.test', 'user', 'primary_email');
  assert.strictEqual(id, 'source-one');
  assert.throws(() => FX.userId(users, '', 'user', 'primary_email'), /identified Google session/);
  assert.throws(() => FX.userId(users, 'missing@example.test', 'user', 'primary_email'), /one migrated user/);
  assert.throws(() => FX.userId([...users, users[0]], 'user@example.test', 'user', 'primary_email'), /one migrated user/);
  const query = {identity:{key:'user'}, filter:{op:'eq-userid',field:'owner',type:'lookup',values:[]},order:[]};
  const rows = [{owner:{user:'source-one'}}, {owner:'source-two'}, {owner:null}, {owner:{id:'source-one'}}];
  assert.deepStrictEqual(FX.applyView(rows, query, id), [rows[0], rows[3]]);
  query.filter.op = 'ne-userid';
  assert.deepStrictEqual(FX.applyView(rows, query, id), [rows[1]]);
  assert.throws(() => FX.applyView([], query), /identity is missing/);
});

test('view failures are surfaced even for an empty table', () => {
  assert.throws(() => FX.applyView([], {error:'missing original filter'}), /missing original filter/);
  assert.throws(() => FX.applyView([], {filter:{op:'invented',values:[]},order:[]}), /Unsupported Dataverse view operator/);
});

test('filter + eq', () => {
  const rows = [{ amount: 150, status: 'Open' }, { amount: 50, status: 'Open' }];
  assert.deepStrictEqual(
    FX.filter(rows, (item) => FX.eq(item.status, 'Open') && item.amount > 100),
    [{ amount: 150, status: 'Open' }],
  );
});

test('sum/average over row lambda', () => {
  const rows = [{ amount: 100 }, { amount: 300 }];
  assert.strictEqual(FX.sum(rows, (item) => item.amount), 400);
  assert.strictEqual(FX.average(rows, (item) => item.amount), 200);
});

test('lookUp returns first match or null', () => {
  const rows = [{ id: 4 }, { id: 5, name: 'five' }];
  assert.deepStrictEqual(FX.lookUp(rows, (item) => FX.eq(item.id, 5)), { id: 5, name: 'five' });
  assert.strictEqual(FX.lookUp(rows, (item) => item.id === 99), null);
  assert.strictEqual(FX.lookUp(rows, item => item.id === 5, item => item.name), 'five');
  assert.strictEqual(FX.lookUp(rows, item => item.id === 99, () => {throw new Error('unreachable');}), null);
});

test('record scopes shadow globals only for own fields, including Blank', () => {
  const outer = {value: 8};
  assert.strictEqual(FX.scopeValue([{value: null}, outer], 'value', () => 9), null);
  assert.strictEqual(FX.scopeValue([{}, outer], 'value', () => 9), 8);
  assert.strictEqual(FX.scopeValue([Object.create({value: 1})], 'value', () => 9), 9);
  assert.strictEqual(FX.scopeValue([2], 'value', () => 9), 2);
});

test('IfError handles synchronous throws and awaited save rejections', async () => {
  const fail = () => {throw new Error('save failed');};
  assert.strictEqual(FX.ifError(() => 7, fail), 7);
  assert.strictEqual(FX.ifError(fail, e => e.message), 'save failed');
  assert.strictEqual(await FX.ifError(async () => fail(), async e => e.message), 'save failed');
  await assert.rejects(FX.ifError(async () => fail(), async () => {throw new Error('fallback failed');}), /fallback failed/);
});

test('concatStr handles null like Power Fx blank', () => {
  assert.strictEqual(FX.concatStr('a', null), 'a');
  assert.strictEqual(FX.concatStr(null, 'b'), 'b');
});

test('field reads on blank or missing records return Power Fx Blank', () => {
  assert.strictEqual(FX.field(null, 'name'), null);
  assert.strictEqual(FX.field(undefined, 'name'), null);
  assert.strictEqual(FX.field({}, 'name'), null);
  assert.strictEqual(FX.field({ name: 'Ada' }, 'name'), 'Ada');
});

test('table projection preserves row count, column name, and blank values', () => {
  assert.deepStrictEqual(FX.field([{name: 'Ada', extra: 1}, {name: null}, {}], 'name'),
    [{name: 'Ada'}, {name: null}, {name: null}]);
  assert.strictEqual(FX.field(0, 'value'), 0);
  assert.strictEqual(FX.field(false, 'value'), false);
});

test('membership compares single-column values and structural records', () => {
  assert.strictEqual(FX.contains('ADA', [{name: 'Ada'}]), true);
  assert.strictEqual(FX.contains('ADA', [{name: 'Ada'}], true), false);
  assert.strictEqual(FX.contains({name: 'Ada', id: 1}, [{id: 1, name: 'Ada'}]), true);
  assert.strictEqual(FX.contains(1, ['1']), false);
  assert.strictEqual(FX.contains(null, [{value: null}]), true);
  assert.strictEqual(FX.contains('Ada', [{name: 'Ada', id: 1}]), false);
});

test('groupBy handles multiple typed keys without collisions or mutating source rows', () => {
  const original = [
    {a: 'x|y', b: 'z', n: 1}, {a: 'x', b: 'y|z', n: 2},
    {a: 'x|y', b: 'z', n: 3}, {a: 1, b: null, n: 4}, {a: '1', b: null, n: 5},
    {a: {name: 'Ada', id: 1}, b: null, n: 6}, {a: {id: 1, name: 'Ada'}, b: null, n: 7},
  ];
  const snapshot = JSON.stringify(original);
  const groups = FX.groupBy(original, ['a', 'b'], 'entries');
  assert.strictEqual(groups.length, 5);
  assert.deepStrictEqual(groups[0], {a: 'x|y', b: 'z', entries: [{n: 1}, {n: 3}]});
  assert.deepStrictEqual(groups[4].entries, [{n: 6}, {n: 7}]);
  assert.deepStrictEqual(FX.ungroup(groups.slice(0, 1), 'entries'), [original[0], original[2]]);
  assert.strictEqual(JSON.stringify(original), snapshot);
  assert.deepStrictEqual(FX.groupBy([], ['a'], 'entries'), []);
  assert.deepStrictEqual(FX.ungroup([{a: 1, entries: []}], 'entries'), []);
  assert.throws(() => FX.groupBy(original, ['a'], 'a'), /distinct grouping columns/);
});

test('value coerces text numbers and currency', () => {
  assert.strictEqual(FX.value('$1,234.5'), 1234.5);
  assert.strictEqual(FX.value('abc'), 0);
});

test('rgba preserves transparency', () => {
  assert.strictEqual(FX.rgba(0, 0, 0, 0), 'rgba(0,0,0,0)');
  assert.strictEqual(FX.rgba(24, 124, 245, 0.5), 'rgba(24,124,245,0.5)');
  assert.strictEqual(FX.rgba(300, -2, 4), 'rgba(255,0,4,1)');
});

test('text number formatting', () => {
  assert.strictEqual(FX.text(3.14159, '0.00'), '3.14');
  assert.strictEqual(FX.text(new Date(2026, 8, 1), 'yyyy-mm-dd'), '2026-09-01');
});

test('dateAdd/dateDiff days', () => {
  const d = FX.dateAdd(new Date(2026, 0, 1), 31, 'days');
  assert.strictEqual(d.getMonth(), 1);
  assert.strictEqual(FX.dateDiff(new Date(2026, 0, 1), new Date(2026, 0, 31), 'days'), 30);
});

test('date operators preserve civil days, fractional offsets and source dates across DST', () => {
  const {execFileSync}=require('node:child_process');
  const output=execFileSync(process.execPath,['-e',`
    const FX=require('./static/fx-stdlib.js');
    const start=new Date(2026,2,7,12), next=FX.add(start,1), half=FX.add(start,1.5);
    const gap=FX.add(new Date(2026,2,7,2,30),1);
    const earlier=FX.subtract(next,2);
    const added=FX.dateAdd(start,7);
    console.log(JSON.stringify({start:start.toISOString(),next:next.toISOString(),half:half.toISOString(),
      gap:gap.toISOString(),difference:FX.subtract(next,start),earlier:earlier.toISOString(),added:added.toISOString()}));
  `],{cwd:require('node:path').resolve(__dirname,'../..'),env:{...process.env,TZ:'America/New_York'},encoding:'utf8'});
  assert.deepStrictEqual(JSON.parse(output),{
    start:'2026-03-07T17:00:00.000Z',next:'2026-03-08T16:00:00.000Z',half:'2026-03-09T04:00:00.000Z',
    gap:'2026-03-08T07:00:00.000Z',difference:1,earlier:'2026-03-06T17:00:00.000Z',added:'2026-03-14T16:00:00.000Z'});
  assert.strictEqual(FX.add('3',2),5);
  assert.strictEqual(FX.add(undefined,2),2);
  assert.strictEqual(FX.subtract(null,2),-2);
  assert.throws(()=>FX.add('invalid',2),/finite number/);
  assert.throws(()=>FX.subtract(2,new Date()),/subtract a date/);
  assert.throws(()=>FX.add(new Date(NaN),1),/Invalid date/);
});

test('trim collapses whitespace like Power Fx Trim', () => {
  assert.strictEqual(FX.trim('  hello   world '), 'hello world');
});

test('switch-like coalesce', () => {
  assert.strictEqual(FX.coalesce([null, '', 'x']), 'x');
});

test('mod follows sign-of-dividend behavior', () => {
  assert.strictEqual(FX.mod(-3, 2), 1);
});

test('round family', () => {
  assert.strictEqual(FX.round(2.345, 2), 2.35);
  assert.strictEqual(FX.roundUp(2.1, 0), 3);
  assert.strictEqual(FX.roundDown(2.9, 0), 2);
});

test('distinct by key', () => {
  const rows = [{ s: 'a' }, { s: 'b' }, { s: 'a' }];
  assert.strictEqual(FX.distinct(rows, (item) => item.s).length, 2);
});

test('sort ascending/descending', () => {
  const rows = [{ n: 2 }, { n: 1 }];
  const asc = FX.sort(rows, (item) => item.n, 'SortOrder.Ascending');
  assert.strictEqual(asc[0].n, 1);
  const desc = FX.sort(rows, (item) => item.n, 'SortOrder.Descending');
  assert.strictEqual(desc[0].n, 2);
});

test('unsupported throws with function name', () => {
  assert.throws(() => FX.unsupported('TimeZoneOffset'), /TimeZoneOffset/);
});

// --- collections (client-side Power Apps collections) -----------------------
const C = FX.collections;

test('collections: collect appends records and tables', () => {
  const state = {};
  C.collect(state, 'colLetters', { id: 1 });
  C.collect(state, 'colLetters', [{ id: 2 }, { id: 3 }]);
  assert.deepStrictEqual(state.colLetters, [{ id: 1 }, { id: 2 }, { id: 3 }]);
});

test('collections: clearCollect resets then appends', () => {
  const state = { colLetters: [{ id: 9 }] };
  C.clearCollect(state, 'colLetters', { id: 1 }, { id: 2 });
  assert.deepStrictEqual(state.colLetters, [{ id: 1 }, { id: 2 }]);
});

test('collections: clearCollection empties the array', () => {
  const state = { cache: [1, 2, 3] };
  C.clearCollection(state, 'cache');
  assert.deepStrictEqual(state.cache, []);
});

test('collections: removeItems drops only matching rows', () => {
  const state = { col: [{ n: 1 }, { n: 2 }, { n: 3 }] };
  C.removeItems(state, 'col', (item) => item.n > 1);
  assert.deepStrictEqual(state.col, [{ n: 1 }]);
});

test('collections: dropRecord removes by identity then by value', () => {
  const rec = { id: 2 };
  const state = { col: [{ id: 1 }, rec, { id: 2, extra: true }] };
  C.dropRecord(state, 'col', { id: 2, extra: true }); // value match (last row)
  assert.deepStrictEqual(state.col, [{ id: 1 }, rec]);
  C.dropRecord(state, 'col', rec); // identity match
  assert.deepStrictEqual(state.col, [{ id: 1 }]);
});

test('collections: patchCollection merges into matching row, appends otherwise', () => {
  const state = { col: [{ id: 1, status: 'OPEN' }] };
  const out = C.patchCollection(state, 'col', { id: 1 }, { status: 'CLOSED' });
  assert.deepStrictEqual(state.col, [{ id: 1, status: 'CLOSED' }]);
  assert.strictEqual(out.status, 'CLOSED');
  C.patchCollection(state, 'col', null, { id: 2, status: 'NEW' });
  assert.strictEqual(state.col.length, 2);
  // no matching row + base given: Power Apps appends a merged record
  C.patchCollection(state, 'col', { id: 3 }, { status: 'X' });
  assert.deepStrictEqual(state.col[2], { id: 3, status: 'X' });
});

test('collections: refreshCollection returns existing rows (no server call)', () => {
  const state = { col: [{ n: 7 }] };
  assert.strictEqual(C.refreshCollection(state, 'col'), state.col);
  C.refreshCollection(state, 'empty');
  assert.deepStrictEqual(state.empty, []);
});
