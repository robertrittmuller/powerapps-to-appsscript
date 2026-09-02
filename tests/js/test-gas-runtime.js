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

test('goBack without history is a no-op, not a crash', () => {
  RT.goBack();
  assert.ok(true);
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
