/* Tests for static/fx-charts.js — run with: node --test tests/js/ */
const test = require('node:test');
const assert = require('node:assert');
const FXCharts = require('../../static/fx-charts.js');

test('bar chart renders one rect per row', () => {
  const rows = [{ name: 'A', amount: 10 }, { name: 'B', amount: 30 }];
  const svg = FXCharts.svg(rows, { type: 'bar', cat: 'name', val: 'amount', width: 400, height: 300 });
  const rects = (svg.match(/<rect /g) || []).length;
  assert.strictEqual(rects, 2);
  assert.ok(svg.includes('<svg'));
});

test('pie chart renders a path per row plus legend', () => {
  const rows = [{ name: 'X', n: 1 }, { name: 'Y', n: 3 }];
  const svg = FXCharts.svg(rows, { type: 'pie', cat: 'name', val: 'n' });
  assert.strictEqual((svg.match(/<path /g) || []).length, 2);
  assert.ok(svg.includes('Y')); // legend label present
});

test('line chart renders polyline with points', () => {
  const rows = [{ m: 'Jan', v: 5 }, { m: 'Feb', v: 9 }, { m: 'Mar', v: 2 }];
  const svg = FXCharts.svg(rows, { type: 'line', cat: 'm', val: 'v' });
  assert.ok(svg.includes('<polyline'));
  assert.strictEqual((svg.match(/<circle /g) || []).length, 3);
});

test('columns auto-detected when not specified', () => {
  const rows = [{ cat: 'A', count: 4 }, { cat: 'B', count: 8 }];
  const svg = FXCharts.svg(rows, { type: 'bar' });
  assert.ok(!svg.includes('No data'));
  assert.strictEqual((svg.match(/<rect /g) || []).length, 2);
});

test('empty data renders a No data placeholder', () => {
  const svg = FXCharts.svg([], { type: 'bar' });
  assert.ok(svg.includes('No data'));
});

test('category labels are escaped', () => {
  const rows = [{ name: '<b>&', n: 1 }];
  const svg = FXCharts.svg(rows, { type: 'bar', cat: 'name', val: 'n' });
  assert.ok(svg.includes('&lt;b&gt;&amp;'));
  assert.ok(!svg.includes('<b>&'));
});
