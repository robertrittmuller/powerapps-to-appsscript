/* Tests for static/fx-stdlib.js — run with: node --test tests/js/ */
const test = require('node:test');
const assert = require('node:assert');
const FX = require('../../static/fx-stdlib.js');

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
});

test('concatStr handles null like Power Fx blank', () => {
  assert.strictEqual(FX.concatStr('a', null), 'a');
  assert.strictEqual(FX.concatStr(null, 'b'), 'b');
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
