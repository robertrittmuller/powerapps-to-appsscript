const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const runtime = fs.readFileSync(require.resolve('../../static/gas-runtime.js'), 'utf8');

function session(saved = new Map(), appId = 'app-one', user = 'user-one') {
  const storage = {
    get length() {return saved.size;}, key: i => [...saved.keys()][i] ?? null,
    getItem: key => saved.has(key) ? saved.get(key) : null,
    setItem: (key, value) => saved.set(key, String(value)), removeItem: key => saved.delete(key),
  };
  const context = vm.createContext({TextEncoder, localStorage: storage,
    document: {addEventListener() {}, getElementById: id => id === 'fx-storage-context'
      ? {textContent: JSON.stringify({appId, user})} : null},
  });
  context.window = context;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/fx-stdlib.js'), 'utf8'), context);
  vm.runInContext(runtime, context);
  return {saved, storage, context, rt: context.FXRuntime, run: code => vm.runInContext(code, context)};
}

test('cache reload appends all typed nested values without sharing object identities', () => {
  const first = session();
  first.run("state.Drafts=[{note:'same', empty:null, zero:0, done:false, when:new Date('2026-09-09T12:00:00Z'), nested:{rows:[{value:'date'}]}}]");
  first.rt.saveData(first.rt.state.Drafts, 'drafts');
  first.run("state.Drafts[0].note='unsaved'");
  const next = session(first.saved);
  next.rt.setState({Drafts: [{note: 'existing'}]});
  next.rt.loadData('Drafts', 'drafts', false);
  assert.equal(next.rt.state.Drafts.length, 2);
  assert.equal(next.rt.state.Drafts[1].note, 'same');
  assert.equal(next.run('state.Drafts[1].when instanceof Date'), true);
  assert.equal(next.rt.state.Drafts[1].when.toISOString(), '2026-09-09T12:00:00.000Z');
  assert.equal(next.run('state.Drafts[1].empty === null && state.Drafts[1].zero === 0 && state.Drafts[1].done === false'), true);
  assert.equal(next.rt.state.Drafts[1].nested.rows[0].value, 'date');
});

test('ignoreMissing only suppresses missing entries, not invalid or unavailable storage', () => {
  const s = session();
  s.rt.setState({Drafts: [{note: 'keep'}]});
  assert.throws(() => s.rt.loadData('Drafts', 'missing'), /No saved data/);
  assert.equal(s.rt.loadData('Drafts', 'missing', true), null);
  assert.equal(s.rt.state.Drafts.length, 1);
  s.rt.saveData([], 'empty');
  assert.equal(s.rt.loadData('Drafts', 'empty'), null);
  assert.equal(s.rt.state.Drafts.length, 1);
  s.saved.set([...s.saved.keys()][0], '{broken');
  assert.throws(() => s.rt.loadData('Drafts', 'empty', true), /corrupt or incompatible/);
  assert.equal(s.rt.state.Drafts.length, 1);
  Object.defineProperty(s.context, 'localStorage', {get() {throw new Error('denied');}});
  assert.throws(() => s.rt.loadData('Drafts', 'missing', true), /storage is unavailable/);
});

test('app and identified-user namespaces isolate reloads and ClearData', () => {
  const a = session(), b = session(a.saved, 'app-two'), c = session(a.saved, 'app-one', 'user-two');
  a.saved.set('unrelated-app-storage', 'keep');
  a.rt.saveData([{note: 'one'}], 'drafts');
  a.rt.saveData([{note: 'backup'}], 'backup');
  b.rt.saveData([{note: 'two'}], 'drafts');
  c.rt.saveData([{note: 'other user'}], 'drafts');
  a.rt.clearData('drafts');
  assert.throws(() => a.rt.loadData('Drafts', 'drafts'), /No saved data/);
  a.rt.loadData('Drafts', 'backup');
  assert.equal(a.rt.state.Drafts[0].note, 'backup');
  a.rt.clearData();
  assert.equal(a.saved.size, 3);
  b.rt.loadData('Drafts', 'drafts'); c.rt.loadData('Drafts', 'drafts');
  assert.equal(b.rt.state.Drafts[0].note, 'two');
  assert.equal(c.rt.state.Drafts[0].note, 'other user');
  assert.equal(a.saved.get('unrelated-app-storage'), 'keep');
});

test('cache limits and quota failures retain previously saved data', () => {
  const s = session();
  s.rt.saveData([{note: 'original'}], 'drafts');
  assert.throws(() => s.rt.saveData([{note: '界'.repeat(400000)}], 'drafts'), /1 MB/);
  s.rt.loadData('Drafts', 'drafts');
  assert.equal(s.rt.state.Drafts[0].note, 'original');
  s.storage.setItem = () => {throw new Error('QuotaExceededError');};
  assert.throws(() => s.rt.saveData([{note: 'replacement'}], 'drafts'), /QuotaExceededError/);
  s.rt.loadData('Drafts', 'drafts');
  assert.equal(s.rt.state.Drafts[1].note, 'original');
});

test('storage names and cyclic or malformed values fail before mutating cache or state', () => {
  const s = session();
  for (const name of ['', 'a/b', 'a.b', 'a?b', 'a\\b', 'a"b', 'a:b', 'a|b', 'a<b', 'a>b', 'a*b']) {
    assert.throws(() => s.rt.saveData([], name), /storage name/);
  }
  s.run('state.Drafts=[]; state.Drafts.push(state.Drafts)');
  assert.throws(() => s.rt.saveData(s.rt.state.Drafts, 'drafts'), /circular/);
  assert.equal(s.saved.size, 0);
  s.rt.saveData([], 'drafts');
  s.saved.set([...s.saved.keys()][0], JSON.stringify({version: 1, rows: ['table', [['string', 'ok'], ['unknown', 1]]]}));
  s.rt.setState({Drafts: [{note: 'untouched'}]});
  assert.throws(() => s.rt.loadData('Drafts', 'drafts'), /corrupt or incompatible/);
  assert.equal(s.rt.state.Drafts.length, 1);
  assert.equal(s.rt.state.Drafts[0].note, 'untouched');
  const anonymousContext = session(new Map(), '');
  assert.throws(() => anonymousContext.rt.loadData('Drafts', 'drafts', true), /storage identity/);
});
