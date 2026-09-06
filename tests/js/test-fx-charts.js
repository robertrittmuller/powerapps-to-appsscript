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

test('chart foreground color is used for labels on colored panels', () => {
  const svg = FXCharts.svg([{ name: 'A', amount: 10 }], {
    type: 'bar', cat: 'name', val: 'amount', foreground: '#ffffff',
  });
  assert.ok(svg.includes('fill="#ffffff"'));
});

test('pie chart renders a path per row plus legend', () => {
  const rows = [{ name: 'X', n: 1 }, { name: 'Y', n: 3 }];
  const svg = FXCharts.svg(rows, { type: 'pie', cat: 'name', val: 'n' });
  assert.strictEqual((svg.match(/<path /g) || []).length, 2);
  assert.ok(svg.includes('Y')); // legend label present
});

test('single-slice pie renders a visible circle instead of a degenerate arc', () => {
  const svg = FXCharts.svg([{ status: 'OPEN', n: 5 }], {
    type: 'pie', cat: 'status', val: 'n', width: 200, height: 120,
  });
  assert.ok(svg.includes('<circle'));
  assert.ok(svg.includes('OPEN'));
});

test('legend renders chart series-label records', () => {
  const rows = [
    { label: 'OPEN', value: 5, color: '#123456' },
    { label: 'CLOSED', value: 2, color: '#654321' },
  ];
  const svg = FXCharts.svg(rows, { type: 'legend', width: 300, height: 40 });
  assert.ok(svg.includes('OPEN'));
  assert.ok(svg.includes('CLOSED'));
  assert.ok(svg.includes('#123456'));
  assert.ok(!svg.includes('No data'));
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

test('all chart families honor hidden labels and the source palette', () => {
  for (const type of ['pie', 'bar', 'line']) {
    const svg = FXCharts.svg([{name:'A', n:2}, {name:'B', n:3}], {
      type, showLabels:false, colors:[{value:'#123456'}, {value:'#654321'}],
    });
    assert.ok(!svg.includes('<text'), type);
    assert.ok(svg.includes('#123456'), type);
    assert.ok(!svg.includes(FXCharts.palette[0]), type);
    if (type !== 'line') assert.ok(svg.includes('#654321'), type);
  }
});

test('bar geometry represents negatives below zero and zero with no invented magnitude', () => {
  const svg = FXCharts.svg([{k:'positive',v:5}, {k:'negative',v:-5}, {k:'zero',v:0}], {});
  const rects = [...svg.matchAll(/<rect ([^>]+)>/g)].map(match =>
    Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]])));
  const zero = Number(svg.match(/y1="([^"]+)"/)[1]);
  assert.strictEqual(Number(rects[0].y) + Number(rects[0].height), zero);
  assert.strictEqual(Number(rects[1].y), zero);
  assert.ok(Number(rects[1].height) > 1);
  assert.strictEqual(Number(rects[2].height), 0);
});

test('zero/negative-only pies and non-finite data have an explicit safe empty state', () => {
  for (const rows of [[{k:'A',v:0}], [{k:'A',v:-4}], [{k:'A',v:Infinity}]]) {
    const svg = FXCharts.svg(rows, {type:'pie'});
    assert.ok(svg.includes('No data'));
    assert.ok(!svg.includes('NaN'));
  }
});

test('single-line legend entries use the rendered line color', () => {
  const chart = FXCharts.model([{k:'Jan',v:1}, {k:'Feb',v:2}], {
    type:'line', colors:['#123456', '#654321'],
  });
  assert.deepStrictEqual(chart.series.map(entry => entry.color), ['#123456', '#123456']);
});
