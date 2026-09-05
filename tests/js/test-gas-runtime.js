/* Tests for static/gas-runtime.js — DOM-dependent parts are exercised only
   where jsdom-free stubs suffice; serverRun contract is tested via injected
   fakes. Run with: node --test tests/js/test-gas-runtime.js */
const test = require('node:test');
const assert = require('node:assert');

// Minimal browser shim so the runtime file loads under Node.
const listeners = {};
global.document = {
  addEventListener: (ev, fn) => { listeners[ev] = fn; },
  querySelector: () => null,
  querySelectorAll: () => [],
  getElementById: () => null,
  createElement: () => ({ style: {}, appendChild: () => {} }),
  body: { appendChild: () => {} },
};
global.window = global;

require('../../static/fx-charts.js');
require('../../static/gas-runtime.js');
const RT = global.FXRuntime;

function installGoogleMock(mode) {
  const handlers = {};
  const runner = new Proxy({}, {
    get(_t, prop) {
      if (prop === 'withSuccessHandler') return (cb) => { handlers.ok = cb; return runner; };
      if (prop === 'withFailureHandler') return (cb) => { handlers.err = cb; return runner; };
      return (...args) => {
        if (mode === 'fail') {
          if (handlers.err) handlers.err(new Error('boom'));
          return;
        }
        if (handlers.ok) handlers.ok({ called: String(prop), args });
      };
    },
  });
  global.google = { script: { run: runner } };
  return handlers;
}

test('serverRun resolves via injected google.script.run', async () => {
  installGoogleMock('ok');
  const out = await RT.serverRun('api', 'Tasks', 'list', {});
  assert.strictEqual(out.called, 'api');
});

test('serverRun rejects when the failure handler fires', async () => {
  installGoogleMock('fail');
  await assert.rejects(RT.serverRun('api', 'Tasks', 'list', {}), /boom/);
});

test('apiChoices bridges the emitted client call to Apps Script', async () => {
  installGoogleMock('ok');
  const out = await global.apiChoices('Students', 'Subject');
  assert.strictEqual(out.called, 'apiChoices');
  assert.deepStrictEqual(out.args, ['Students', 'Subject']);
});

test('goBack without history is a no-op, not a crash', () => {
  RT.goBack();
  assert.ok(true);
});

test('setState immediately re-evaluates reactive bindings', () => {
  let observed = null;
  RT.addEvaluator(() => { observed = RT.state.reactiveValue; });
  RT.setState({ reactiveValue: 42 });
  assert.strictEqual(observed, 42);
});

test('component inputs remain reactive and val exposes control geometry', () => {
  const original = global.document.querySelector;
  const el = {
    tagName: 'DIV', textContent: '', style: { width: '210px', height: '52px', left: '16px', top: '20px' },
    selectedOptions: [],
  };
  global.document.querySelector = () => el;
  RT.setState({ progress: 42 });
  RT.registerControlProps('progress1', null, {
    bar_width: () => 200,
    bar_current_value: () => RT.state.progress,
  });
  assert.strictEqual(global.val('progress1').width, 210);
  assert.strictEqual(global.val('progress1').bar_width, 200);
  assert.strictEqual(global.val('progress1').bar_current_value, 42);
  RT.setState({ progress: 75 });
  assert.strictEqual(global.val('progress1').bar_current_value, 75);
  global.document.querySelector = original;
});

test('App.ActiveScreen reflects navigation for component menu inputs', () => {
  FXRuntime.showScreen('HOME');
  assert.equal(val('App').active_screen, 'HOME');
  go('DETAIL');
  assert.equal(val('App').active_screen, 'DETAIL');
});

test('dependent evaluators receive Parent control properties', () => {
  const original = global.document.querySelector;
  const parent = { tagName: 'DIV', textContent: '', style: {}, selectedOptions: [] };
  const child = { tagName: 'DIV', textContent: '', style: {}, selectedOptions: [] };
  global.document.querySelector = (selector) => selector.includes('Card1') ? parent
    : selector.includes('Child1') ? child : null;
  RT.registerControlProps('Card1', null, { required: () => true });
  RT.styleControl('Child1', 'display', () => global.parentRef.required ? '' : 'none', null, 'Card1');
  RT.updateBindings();
  assert.strictEqual(child.style.display, '');
  global.document.querySelector = original;
});

test('dynamic image sources are bound and unsafe or blank sources are removed', () => {
  const original = global.document.querySelector;
  const attrs = {};
  const el = {
    tagName: 'IMG', textContent: '', style: {}, selectedOptions: [],
    getAttribute: (name) => attrs[name] === undefined ? null : attrs[name],
    setAttribute: (name, value) => { attrs[name] = value; },
    removeAttribute: (name) => { delete attrs[name]; },
    addEventListener: () => {},
  };
  let source = 'https://example.test/avatar.png';
  global.document.querySelector = () => el;
  RT.attrControl('Avatar', 'src', () => source, null);
  assert.strictEqual(attrs.src, source);
  source = 'javascript:alert(1)';
  RT.updateBindings();
  assert.strictEqual(attrs.src, undefined);
  source = '';
  RT.updateBindings();
  assert.strictEqual(attrs.src, undefined);
  global.document.querySelector = original;
});

test('record-valued dropdown options choose a readable scalar label', () => {
  assert.deepStrictEqual(RT.optionRecord({ category: 'IT' }), { value: 'IT', label: 'IT' });
  assert.deepStrictEqual(RT.optionRecord({ Name: 'Friendly', Value: 'raw' }),
    { value: 'raw', label: 'Friendly' });
  assert.deepStrictEqual(RT.optionRecord({ id: 7, status: 'OPEN' }),
    { value: '7', label: '7' });
  assert.deepStrictEqual(RT.optionRecord('plain'), { value: 'plain', label: 'plain' });
  assert.deepStrictEqual(RT.optionRecord({ first_name: 'Ada' }, ['FirstName']),
    { value: 'Ada', label: 'Ada' });
});

test('Dropdown Selected and ComboBox SelectedItems preserve source records', () => {
  const original = global.document.querySelector;
  const records = [{ id: 1, name: 'Ada' }, { id: 2, name: 'Grace' }];
  const options = records.map((_, index) => ({
    index,
    selected: index === 1,
    getAttribute: (name) => name === 'data-fx-index' ? String(index) : null,
  }));
  const el = {
    tagName: 'SELECT', value: '2', style: {}, __fxRecords: records,
    options, selectedOptions: [options[1]], selectedIndex: 1,
  };
  global.document.querySelector = () => el;
  assert.deepStrictEqual(global.val('People').selected, records[1]);
  assert.deepStrictEqual(global.val('People').selected_items, [records[1]]);
  assert.deepStrictEqual(global.val('People').selected_text, { value: 'Grace' });

  RT.applyDefaultSelection(el, [records[0]]);
  assert.strictEqual(options[0].selected, true);
  assert.strictEqual(options[1].selected, false);
  global.document.querySelector = original;
});

test('gallery row selection exposes Selected and AllItems records', () => {
  const original = global.document.querySelector;
  const rows = [];
  function rowElement() {
    const child = { tagName: 'SPAN', style: { width: '60px', height: '20px' },
      textContent: '', selectedOptions: [] };
    return {
      style: {}, listeners: {}, child,
      addEventListener(ev, fn) { this.listeners[ev] = fn; },
      querySelector(selector) { return selector.includes('Name') ? child : null; },
      click() { this.listeners.click(); },
    };
  }
  const rowsEl = { style: {}, children: [] };
  Object.defineProperty(rowsEl, 'innerHTML', {
    set(markup) {
      const count = (String(markup).match(/class="fx-row"/g) || []).length;
      rows.length = 0;
      for (let i = 0; i < count; i += 1) rows.push(rowElement());
      this.children = rows;
    },
  });
  const template = { innerHTML: '<div class="fx-row"><span data-control="Name"></span></div>' };
  const attrs = { 'data-template-size': '87', 'data-template-padding': '3' };
  const host = {
    tagName: 'DIV', textContent: '', style: { width: '210px' }, selectedOptions: [],
    getAttribute(name) { return attrs[name] === undefined ? null : attrs[name]; },
    querySelector(selector) { return selector === 'template' ? template : rowsEl; },
  };
  global.document.querySelector = (selector) => selector.includes('PeopleGallery') ? host
    : rows[0] ? rows[0].child : null;
  const items = [{ id: 1, name: 'Ada' }, { id: 2, name: 'Grace' }];
  RT.gallery('PeopleGallery', () => items, (item, row) => {
    RT.rowControl(row, 'Name', 'PeopleGallery', {
      text: () => item.name,
      left: () => global.parentRef.template_width - 5,
    });
  }, null);
  RT.updateBindings();
  assert.strictEqual(rows.length, 2);
  assert.strictEqual(rows[0].style.minHeight, '87px');
  assert.strictEqual(rows[0].style.padding, '3px');
  assert.strictEqual(rows[0].child.textContent, 'Ada');
  assert.strictEqual(rows[1].child.textContent, 'Grace');
  assert.strictEqual(rows[0].child.style.left, '205px');
  rows[1].click();
  assert.deepStrictEqual(global.val('PeopleGallery').selected, items[1]);
  assert.deepStrictEqual(global.val('PeopleGallery').all_items, items);
  global.document.querySelector = original;
});

test('renderChart exposes SeriesLabels for a separate Legend control', () => {
  const original = global.document.querySelector;
  const chartEl = { tagName: 'DIV', style: {}, innerHTML: '', selectedOptions: [] };
  const legendEl = { tagName: 'DIV', style: {}, innerHTML: '', selectedOptions: [] };
  global.document.querySelector = (selector) => selector.includes('StatusPie') ? chartEl
    : selector.includes('StatusLegend') ? legendEl : null;
  RT.renderChart('StatusPie', [{ status: 'OPEN', count: 5 }], {
    type: 'pie', cat: 'status', val: 'count', width: 200, height: 120,
  });
  assert.ok(chartEl.innerHTML.includes('<circle'));
  assert.deepStrictEqual(global.val('StatusPie').series_labels, [
    { label: 'OPEN', value: 5, color: '#4e79a7' },
  ]);
  RT.renderChart('StatusLegend', global.val('StatusPie').series_labels, {
    type: 'legend', cat: 'label', val: 'value', width: 200, height: 40,
  });
  assert.ok(legendEl.innerHTML.includes('OPEN'));
  assert.ok(!legendEl.innerHTML.includes('No data'));
  global.document.querySelector = original;
});

test('dynamic HtmlText sanitizer keeps formatting and strips executable markup', () => {
  const clean = RT.sanitizeHtml(
    '<b>Ticket</b><img src="javascript:alert(1)" onerror="alert(2)">' +
    '<script>alert(3)</script>'
  );
  assert.ok(clean.includes('<b>Ticket</b>'));
  assert.ok(!clean.includes('javascript:'));
  assert.ok(!clean.includes('onerror'));
  assert.ok(!clean.includes('<script'));
});

test('reactive point font sizes retain Power Apps units', () => {
  const original = global.document.querySelector;
  const el = { tagName: 'SPAN', textContent: '', style: {}, selectedOptions: [] };
  global.document.querySelector = () => el;
  RT.styleControl('Title', 'fontSize', () => 15, 'pt', null);
  RT.updateBindings();
  assert.strictEqual(el.style.fontSize, '15pt');
  global.document.querySelector = original;
});

test('resetControl restores the generated default value', () => {
  const original = global.document.querySelector;
  const el = {
    type: 'text', value: 'changed', style: {},
    getAttribute: (name) => name === 'data-fx-default' ? 'original' : null,
  };
  global.document.querySelector = () => el;
  global.resetControl('TextInput1');
  assert.strictEqual(el.value, 'original');
  global.document.querySelector = original;
});

function installRemoveIfMock(initialRows) {
  let rows = initialRows.slice();
  const calls = [];
  let ok = null;
  let fail = null;
  const runner = new Proxy({}, {
    get(_t, prop) {
      if (prop === 'withSuccessHandler') return (cb) => { ok = cb; return runner; };
      if (prop === 'withFailureHandler') return (cb) => { fail = cb; return runner; };
      return (...args) => {
        calls.push({ fn: String(prop), args });
        const success = ok;
        ok = null; fail = null;
        if (String(prop) !== 'api') return success(undefined);
        const op = args[1];
        if (op === 'list') return success(rows.slice());
        if (op === 'removeIf') {
          const ids = args[2].ids.map(String);
          rows = rows.filter((row) => !ids.includes(String(row.id)));
          return success({ ok: true });
        }
        return success({ ok: true });
      };
    },
  });
  global.google = { script: { run: runner } };
  return calls;
}

test('external RemoveIf sends explicit matching ids only', async () => {
  const calls = installRemoveIfMock([{ id: 1, status: 'open' }, { id: 2, status: 'done' }]);
  const remaining = await global.apiRemoveIf('Tasks', (row) => row.status === 'done');
  const mutation = calls.find((call) => call.args[1] === 'removeIf');
  assert.deepStrictEqual(mutation.args[2], { ids: [2] });
  assert.deepStrictEqual(remaining, [{ id: 1, status: 'open' }]);
});

test('external RemoveIf with no matches performs no mutation', async () => {
  const calls = installRemoveIfMock([{ id: 1, status: 'open' }]);
  await global.apiRemoveIf('Tasks', (row) => row.status === 'missing');
  assert.strictEqual(calls.some((call) => call.args[1] === 'removeIf'), false);
});

// --- collection mutation helpers (called as generated code calls them) ------
// The transpiler emits powerapps_collect(state, 'Name', record); these tests
// pin the (state, name, ...) signature so it can never drift from the emitter.
test('powerapps_collect appends into state under the collection name', () => {
  const st = {};
  global.powerapps_collect(st, 'colCache', { id: 1 });
  global.powerapps_collect(st, 'colCache', [{ id: 2 }, { id: 3 }]);
  assert.deepStrictEqual(st.colCache, [{ id: 1 }, { id: 2 }, { id: 3 }]);
});

test('powerapps_clearCollect resets then appends', () => {
  const st = { colCache: [{ id: 9 }] };
  global.powerapps_clearCollect(st, 'colCache', { id: 1 });
  assert.deepStrictEqual(st.colCache, [{ id: 1 }]);
});

test('powerapps_remove drops by identity then value', () => {
  const rec = { id: 2 };
  const st = { colCache: [{ id: 1 }, rec] };
  global.powerapps_remove(st, 'colCache', { id: 1 });
  assert.deepStrictEqual(st.colCache, [rec]);
  global.powerapps_remove(st, 'colCache', rec);
  assert.deepStrictEqual(st.colCache, []);
});

test('powerapps_removeIf filters the array in place', () => {
  const st = { colCache: [{ n: 1 }, { n: 2 }] };
  global.powerapps_removeIf(st, 'colCache', (item) => item.n > 1);
  assert.deepStrictEqual(st.colCache, [{ n: 1 }]);
});

test('registerScreenHandler + showScreen invokes handler', async () => {
  let called = false;
  RT.registerScreenHandler('S1', () => { called = true; });
  RT.showScreen('S1');
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(called);
});
