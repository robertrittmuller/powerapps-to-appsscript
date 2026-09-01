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
