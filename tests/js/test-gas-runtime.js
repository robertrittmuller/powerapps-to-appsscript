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
require('../../static/fx-stdlib.js');
require('../../static/gas-runtime.js');
const RT = global.FXRuntime;

test('named values remain lazy, immutable and reactive, with forward references and cycle recovery', () => {
  assert.strictEqual(RT.registerNamedFormulas.length, 1);
  let base = 2, reads = 0, broken = true;
  RT.registerNamedFormulas({
    NamedLater: () => RT.state.NamedBase + 1,
    NamedBase: () => { reads++; return base; },
    NamedCycleA: () => RT.state.NamedCycleB,
    NamedCycleB: () => RT.state.NamedCycleA,
    NamedFailure: () => { if (broken) throw new Error('dependency unavailable'); return 8; },
    NamedPromise: () => Promise.resolve(1),
  });
  assert.strictEqual(reads, 0, 'registration must not evaluate unused dependencies');
  assert.strictEqual(RT.state.NamedLater, 3);
  base = 8;
  assert.strictEqual(RT.state.NamedLater, 9);
  assert.throws(() => { RT.state.NamedBase = 20; }, /read-only/);
  assert.strictEqual(RT.state.NamedBase, 8);
  assert.throws(() => RT.state.NamedCycleA, /Circular named formula: NamedCycleA -> NamedCycleB -> NamedCycleA/);
  assert.throws(() => RT.state.NamedFailure, /dependency unavailable/);
  broken = false;
  assert.strictEqual(RT.state.NamedFailure, 8, 'failed reads must release dependency stack');
  assert.throws(() => RT.state.NamedPromise, /Asynchronous named formula/);
  assert.throws(() => RT.registerNamedFormulas({NamedNew: () => 1, namedbase: () => 2}), /conflicting/);
  assert.strictEqual(Object.hasOwn(RT.state, 'NamedNew'), false, 'a rejected registry cannot partly install');
  assert(!Object.keys(RT.state).includes('NamedCycleA'), 'debug snapshots must not force unused formulas');
});

test('row property definitions resolve in their own scope and detect actual dependency cycles', () => {
  const first={tagName:'SPAN',textContent:'first',style:{}},second={tagName:'SPAN',textContent:'second',style:{}};
  const row1={querySelector:name=>name.includes('ScopedCaption')?first:null};
  const row2={querySelector:name=>name.includes('ScopedCaption')?second:null};
  let size=9;
  RT.registerRowProps(row1,'ScopedCaption',null,{size:()=>size,padding_left:(_read,self)=>self.size+2});
  RT.registerRowProps(row2,'ScopedCaption',null,{size:()=>RT.rowValue(row1,'ScopedCaption').size+3});
  assert.strictEqual(RT.rowValue(row1,'ScopedCaption').padding_left,11);
  assert.strictEqual(RT.rowValue(row2,'ScopedCaption').size,12,'same-named instances are independent dependencies');
  size=20;
  assert.strictEqual(RT.rowValue(row1,'ScopedCaption').padding_left,22);
  assert.strictEqual(RT.rowValue(row2,'ScopedCaption').size,23);
  RT.registerRowProps(row1,'ScopedCaption',null,{size:(read)=>read('ScopedCaption').size});
  assert.throws(()=>RT.rowValue(row1,'ScopedCaption').size,/Circular control property/);
});

test('control lookup caches stable nodes but observes replacements and reordered gallery instances', () => {
  const original=global.document.querySelector;
  let calls=0,current={isConnected:true,closest:()=>null};
  global.document.querySelector=()=>{calls++;return current;};
  try {
    assert.strictEqual(RT.controlElement('LookupContract'),current);
    assert.strictEqual(RT.controlElement('LookupContract'),current);
    assert.strictEqual(calls,1);
    current.isConnected=false;
    current={isConnected:true,closest:()=>null};
    assert.strictEqual(RT.controlElement('LookupContract'),current);
    assert.strictEqual(calls,2);
    current.isConnected=false;
    const first={isConnected:true,closest:()=>({})},second={isConnected:true,closest:()=>({})};
    current=first;
    assert.strictEqual(RT.controlElement('LookupContract'),first);
    current=second;
    assert.strictEqual(RT.controlElement('LookupContract'),second);
    assert.strictEqual(calls,4,'global gallery references must follow current row order');
  } finally { global.document.querySelector=original; }
});

test('control references avoid layout measurement when inline geometry is available', () => {
  const original=global.document.querySelector;
  let measurements=0;
  const el={tagName:'SPAN',textContent:'Ready',style:{width:'120px',height:'30px',left:'8px',top:'12px'},
    getBoundingClientRect() { measurements++; return {width:130,height:40,left:18,top:22}; }};
  global.document.querySelector=()=>el;
  try {
    const inline=global.val('MeasuredLabel');
    assert.deepStrictEqual([inline.text,inline.width,inline.height,inline.x,inline.y],['Ready',120,30,8,12]);
    assert.strictEqual(measurements,0,'reading source-sized controls must not force browser layout');
    delete el.style.height;delete el.style.top;
    const fallback=global.val('MeasuredLabel');
    assert.deepStrictEqual([fallback.width,fallback.height,fallback.x,fallback.y],[120,40,8,22]);
    assert.strictEqual(measurements,1,'missing inline dimensions share one measured rectangle');
    el.style.width='240px';
    assert.strictEqual(global.val('MeasuredLabel').width,240);
    assert.strictEqual(measurements,2,'a later reference must observe current geometry');
  } finally { global.document.querySelector=original; }
});

test('gallery template dimensions exist before the first Items binding mounts rows', () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const gallery = {tagName:'DIV',style:{width:'390px'},textContent:'',
    getAttribute:name=>({'data-template-size':'182','data-template-padding':'8'}[name] ?? null)};
  const ctx = vm.createContext({document:{...global.document,querySelector:()=>gallery}});
  ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  const ref=ctx.val('Responses');
  assert.strictEqual(ref.template_height,182);
  assert.strictEqual(ref.template_size,182);
  assert.strictEqual(ref.template_padding,8);
  assert.strictEqual(ref.template_width,390);
  assert.strictEqual(2*(ref.template_height+ref.template_padding),380);
});

test('responsive gallery TemplateSize resolves before rows and updates without stale metadata', () => {
  const vm=require('node:vm'),fs=require('node:fs');
  const attrs={'data-gallery-layout':'vertical','data-template-padding':'0'};
  const host={tagName:'DIV',style:{width:'390px',height:'200px'},textContent:'',getAttribute:key=>attrs[key]??null};
  const ctx=vm.createContext({document:{...global.document,querySelector:()=>host}});ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  const rt=ctx.FXRuntime;
  assert.equal(rt.registerGalleryTemplate.length,3);
  let wide=true;
  rt.registerGalleryTemplate('ResponsiveRows','Card',(_val,self,parent)=>{
    assert.equal(self.width,390);assert.equal(parent.height,200);
    return wide?72:84;
  });
  assert.equal(ctx.val('ResponsiveRows').template_height,72);
  assert.equal(ctx.val('ResponsiveRows').template_height*0,0);
  wide=false;
  assert.equal(ctx.val('ResponsiveRows').template_height*2,168);
  attrs['data-gallery-layout']='horizontal';attrs['data-template-size']='999';
  assert.equal(ctx.val('ResponsiveRows').template_width,84);
  assert.equal(ctx.val('ResponsiveRows').template_height,200);
  rt.registerGalleryTemplate('ResponsiveRows','Card',()=>Infinity);
  assert.throws(()=>ctx.val('ResponsiveRows').template_width,/Non-finite gallery TemplateSize/);
  rt.registerGalleryTemplate('ResponsiveRows','Card',(_val,self)=>self.template_width);
  assert.throws(()=>ctx.val('ResponsiveRows').template_width,/Circular gallery TemplateSize/);
  rt.registerGalleryTemplate('ResponsiveRows','Card',()=>0);
  assert.equal(ctx.val('ResponsiveRows').template_width,1);
});

test('startup waits for session identity before source OnStart snapshots User()', async () => {
  const vm = require('node:vm'), fs = require('node:fs');
  let ready, success;
  const runner = new Proxy({}, {get(_target, name) {
    if (name === 'withSuccessHandler') return callback => {success=callback; return runner;};
    if (name === 'withFailureHandler') return () => runner;
    if (name === 'whoami') return () => {};
  }});
  const ctx = vm.createContext({document:{...global.document,addEventListener:(_ev,fn)=>{ready=fn;}},
    google:{script:{run:runner}},console,setTimeout,clearTimeout});
  ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  let observed;
  ctx.APP_MAIN=()=>{observed=ctx.FXUser().email;};
  const startup=ready();
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(observed,undefined);
  success({email:'actual@example.test',fullName:'Actual User',pictureUrl:'avatar'});
  await startup;
  assert.strictEqual(observed,'actual@example.test');
  assert.strictEqual(ctx.FXUser().full_name,'Actual User');
  assert.strictEqual(ctx.FXUser().image,'avatar');
});

test('horizontal gallery template dimensions cannot recursively grow its source width', () => {
  const vm=require('node:vm'),fs=require('node:fs');
  const attrs={'data-gallery-layout':'horizontal','data-template-size':'48','data-template-padding':'20'};
  const host={tagName:'DIV',style:{width:'1px',height:'1px'},textContent:'',getAttribute:key=>attrs[key]??null};
  const ctx=vm.createContext({document:{...global.document,querySelector:()=>host}});ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  for (let pass=0;pass<50;pass++) {
    const self=ctx.val('LoadingLogos');
    host.style.width=((self.template_width+self.template_padding)*3+self.template_padding)+'px';
    host.style.height=(self.template_width+2*self.template_padding)+'px';
  }
  assert.equal(host.style.width,'224px');
  assert.equal(host.style.height,'88px');
  assert.equal(ctx.val('LoadingLogos').template_width,48);
  assert.equal(ctx.val('LoadingLogos').template_height,48);
  attrs['data-wrap-count']='2';host.style.height='156px';
  assert.equal(ctx.val('LoadingLogos').template_height,48);
});

test('launch parameters are case-sensitive text with Blank for absent keys', () => {
  const vm = require('node:vm');
  const fs = require('node:fs');
  const parameters = JSON.stringify({recordId: 'A + B', numeric: '42', empty: '', language: 'not-a-locale'});
  const context = vm.createContext({document: {...global.document,
    getElementById: name => name === 'fx-launch-parameters' ? {textContent: parameters} : null,
  }, navigator: {language: 'fr-CA'}});
  context.window = context;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'), 'utf8'), context);
  assert.strictEqual(context.FXRuntime.param('recordId'), 'A + B');
  assert.strictEqual(context.FXRuntime.param('RecordId'), null);
  assert.strictEqual(context.FXRuntime.param('numeric'), '42');
  assert.strictEqual(context.FXRuntime.param('empty'), '');
  assert.strictEqual(context.FXRuntime.param('toString'), null);
  assert.strictEqual(context.FXRuntime.language(), 'fr-CA');
  delete context.navigator;
  assert.strictEqual(context.FXRuntime.language(), 'en-US');
});

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

test('connector bindings coalesce reads, surface failures, and discard snapshots invalidated by writes', async () => {
  const requests=[];
  global.google={script:{get run() {
    const handlers={};
    const runner={withSuccessHandler(fn){handlers.ok=fn;return runner;},
      withFailureHandler(fn){handlers.fail=fn;return runner;},
      connector(...args){requests.push({...handlers,args});}};
    return runner;
  }}};
  RT.configureServices({Planner:{operations:{ListTasks:{arity:[1],write:false},CreateTaskV3:{arity:[3],write:true}}}});
  assert.strictEqual(RT.connectorCall.length,3);
  assert.strictEqual(RT.connectorRead.length,3);
  assert.strictEqual(RT.connectorRead('Planner','ListTasks',['p']),null);
  assert.strictEqual(RT.connectorRead('Planner','ListTasks',['p']),null);
  assert.strictEqual(requests.length,1);
  const pendingWrite=RT.connectorCall('Planner','CreateTaskV3',['g','p','new']);
  requests[1].ok({id:'new'});
  assert.deepStrictEqual(await pendingWrite,{id:'new'});
  requests[0].ok({value:[{id:'stale'}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.strictEqual(RT.connectorRead('Planner','ListTasks',['p']),null);
  requests[2].ok({value:[{id:'new'}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepStrictEqual(RT.connectorRead('Planner','ListTasks',['p']),{value:[{id:'new'}]});
  assert.throws(()=>RT.connectorRead('Planner','CreateTaskV3',['g','p','bad']),/behavior/);
  assert.throws(()=>RT.connectorRead('Planner','ListTasks',[]),/number/);
  RT.refreshConnector('Planner');
  const oldError=console.error;
  try {
    console.error=()=>{};
    RT.connectorRead('Planner','ListTasks',['p']);
    requests[3].fail(new Error('migration missing'));
    await new Promise(resolve=>setImmediate(resolve));
    assert.throws(()=>RT.connectorRead('Planner','ListTasks',['p']),/migration missing/);
    assert.strictEqual(requests.length,4);
    RT.refreshConnector('Planner');
    RT.connectorRead('Planner','ListTasks',['p']);
    requests[4].ok({value:[]});
    await new Promise(resolve=>setImmediate(resolve));
    assert.deepStrictEqual(RT.connectorRead('Planner','ListTasks',['p']),{value:[]});
    const failedWrite=RT.connectorCall('Planner','CreateTaskV3',['g','p','uncertain']);
    requests[5].fail(new Error('uncertain write'));
    await assert.rejects(failedWrite,/uncertain write/);
    assert.strictEqual(requests.length,6); // No automatic mutation retry.
    assert.strictEqual(RT.connectorRead('Planner','ListTasks',['p']),null);
    requests[6].ok({value:[{id:'saved-before-timeout'}]});
    await new Promise(resolve=>setImmediate(resolve));
  } finally {console.error=oldError; RT.configureServices({});}
});

test('apiPatchRecord sends the keyed overload and does not refresh state on failure', async () => {
  assert.strictEqual(global.apiPatchRecord.length,2);
  installGoogleMock('ok');
  const record = {project:'source-key',budget:0,active:false};
  const saved = await global.apiPatchRecord('Keyed',record);
  assert.strictEqual(saved.called,'api');
  assert.deepStrictEqual(saved.args,['Keyed','patchRecord',{record}]);
  assert.deepStrictEqual(global.state.Keyed.args,['Keyed','list',{}]);
  const before = global.state.Keyed;
  installGoogleMock('fail');
  await assert.rejects(global.apiPatchRecord('Keyed',record),/boom/);
  assert.strictEqual(global.state.Keyed,before);
});

test('relationship projections refresh only the first side and require typed, unambiguous records', async () => {
  const contracts = {
    People:{primaryKey:'key',keys:['key'],navigation:{groups:{kind:'many-to-many',schema:'members',side:2,target:'Groups'}}},
    Groups:{primaryKey:'key',keys:['key'],navigation:{people:{kind:'many-to-many',schema:'members',side:1,target:'People'},
      unsupported:{error:'one-to-many adapter missing'}}},
  };
  const rows = {People:[{key:'p',name:'Ada'}],Groups:[{key:'g',name:'Group'}]};
  let links = [], calls = [], failure = false, handlers = {};
  const runner = new Proxy({}, {get(_target,name) {
    if (name === 'withSuccessHandler') return cb=>{handlers.ok=cb;return runner;};
    if (name === 'withFailureHandler') return cb=>{handlers.fail=cb;return runner;};
    return (ds,op,payload)=>{
      const captured=handlers; handlers={}; calls.push([ds,op,payload]);
      queueMicrotask(()=>{
        if (failure) {captured.fail(new Error('relationship service failed'));return;}
        if (op === 'relate') links=[['members','g','p']];
        if (op === 'unrelate') links=[];
        captured.ok(JSON.parse(JSON.stringify(op==='list'?rows[ds]:op==='relationshipSnapshot'?{links,targets:rows}:null)));
      });
    };
  }});
  global.google={script:{run:runner}};
  RT.configureRelationships(contracts);
  try {
    await Promise.all([global.refreshData('People'),global.refreshData('Groups')]);
    assert.strictEqual(global.apiRelate.length,3);
    const group=global.state.Groups[0], person=global.state.People[0];
    assert.deepStrictEqual(FX.field(group,'people'),[]);
    calls=[];
    assert.strictEqual(await global.apiRelate(FX.field(group,'people'),person,false),null);
    assert.deepStrictEqual(calls.map(c=>c.slice(0,2)),[['Groups','relate'],['Groups','list'],['Groups','relationshipSnapshot']]);
    assert.deepStrictEqual(calls[0][2],{relationship:'people',base:{key:'g'},record:person});
    assert.deepStrictEqual(FX.field(group,'people').map(r=>r.name),['Ada']);
    assert.deepStrictEqual(FX.field(person,'groups'),[]);
    await global.refreshData('People');
    assert.deepStrictEqual(FX.field(person,'groups').map(r=>r.name),['Group']);
    assert.deepStrictEqual(FX.scopeValue([group],'people',()=>null).map(r=>r.name),['Ada']);
    failure=true;
    await assert.rejects(global.apiRelate(FX.field(group,'people'),person,true),/service failed/);
    assert.strictEqual(FX.field(group,'people').length,1);
    failure=false;
    await global.apiRelate(FX.field(group,'people'),person,true);
    assert.deepStrictEqual(FX.field(group,'people'),[]);
    await assert.rejects(global.apiRelate([],person,false),/direct exported relationship/);
    assert.throws(()=>FX.field(group,'unsupported'),/adapter missing/);
    contracts.People.navigation.people=contracts.Groups.navigation.people;
    assert.throws(()=>FX.field({key:'g'},'people'),/ambiguous relationship record/);
    // Typed loaded rows still resolve when different tables share a key label.
    assert.deepStrictEqual(FX.field(group,'people'),[]);
    assert.throws(()=>FX.field({key:17},'people'),/invalid relationship primary key/);
  } finally {RT.configureRelationships({});}
});

test('serverRun encodes nested dates without changing client records or hiding invalid values', async () => {
  installGoogleMock('ok');
  const record = {when: new Date('2026-09-09T12:34:56Z'), nested: [{done: false, count: 0, blank: null}]};
  const out = await RT.serverRun('api', 'Projects', 'patch', {record});
  assert.strictEqual(out.args[2].record.when, '2026-09-09T12:34:56.000Z');
  assert.deepStrictEqual(out.args[2].record.nested, [{done: false, count: 0, blank: null}]);
  assert.ok(record.when instanceof Date);
  await assert.rejects(RT.serverRun('api', {when: new Date('invalid')}), /invalid date/);
  await assert.rejects(RT.serverRun('api', {callback() {}}), /argument type/);
  const cyclic = {}; cyclic.self = cyclic;
  await assert.rejects(RT.serverRun('api', cyclic), /circular/);
});

test('apiChoices bridges the emitted client call to Apps Script', async () => {
  installGoogleMock('ok');
  const out = await global.apiChoices('Students', 'Subject');
  assert.strictEqual(out.called, 'apiChoices');
  assert.deepStrictEqual(out.args, ['Students', 'Subject']);
});

test('goBack without history is a no-op, not a crash', () => {
  assert.strictEqual(RT.goBack(), false);
});

test('navigation contexts preserve Blank, false, zero, scope and history', async () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const ctx = vm.createContext({document: {...global.document}, console});
  ctx.window = ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'), 'utf8'), ctx);
  const rt = ctx.FXRuntime;
  assert.strictEqual(ctx.go.length, 2);
  assert.strictEqual(rt.updateContext.length, 2);
  rt.configureCanvas({}, {}, {Browse: {}, Detail: {}});
  rt.configureContexts({Browse:['selected', 'shared'], Detail:['selected', 'shared', 'CamelCase']});
  let fallbacks = 0;
  const fallback = () => { fallbacks++; return 'global'; };
  assert.strictEqual(rt.variable('Detail', 'selected', fallback), null);
  assert.strictEqual(fallbacks, 0);
  assert.strictEqual(rt.variable('Detail', 'undeclared', fallback), 'global');
  assert.strictEqual(ctx.goBack(), false);
  ctx.go('Browse', {shared:'browse'});
  const record = {id:'two', first_name:'Grace'};
  let entered;
  rt.registerScreenHandler('Detail', () => { entered = rt.variable('Detail','selected'); });
  assert.strictEqual(ctx.go('Detail', {selected:record, shared:false, CamelCase:0}), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(entered, record);
  assert.strictEqual(rt.variable('Detail', 'SHARED', fallback), false);
  assert.strictEqual(rt.variable('Detail', 'camelcase', fallback), 0);
  assert.strictEqual(rt.variable('Browse', 'shared'), 'browse');
  assert.strictEqual(ctx.go('missing', {shared:'lost'}), false);
  assert.strictEqual(ctx.val('App').active_screen, 'Detail');
  assert.strictEqual(ctx.goBack(), true);
  assert.strictEqual(ctx.val('App').active_screen, 'Browse');
  // An awaited old-screen handler explicitly retains its defining screen.
  rt.updateContext('Detail', {selected:null});
  assert.strictEqual(rt.variable('Detail', 'selected', fallback), null);
  assert.strictEqual(rt.variable('Browse', 'selected', fallback), null);
  assert.strictEqual(rt.variable('Detail', 'shared'), false);
  assert.strictEqual(ctx.goBack(), false);
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

test('checkbox Value is boolean, slider Value is numeric, and button Text is its caption', () => {
  const checkbox = {tagName:'INPUT',type:'checkbox',value:'on',checked:false,style:{}};
  assert.strictEqual(val('Toggle', checkbox).value, false);
  checkbox.checked = true;
  assert.strictEqual(val('Toggle', checkbox).value, true);
  assert.strictEqual(val('Slider', {tagName:'INPUT',type:'range',value:'42',style:{}}).value, 42);
  assert.strictEqual(val('Button', {tagName:'BUTTON',value:'',textContent:'Continue',style:{}}).text, 'Continue');
});

test('canvas dimensions are available before navigation and update on viewport resize', () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const events = {};
  const screen = {style:{}};
  const context = vm.createContext({innerWidth:1000,innerHeight:700,
    addEventListener:(name,fn)=>{events[name]=fn;},
    document:{...global.document,querySelector:()=>screen},console});
  context.window = context;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),context);
  context.FXRuntime.configureCanvas({designWidth:1366,designHeight:768,scaleToFit:false}, {
    min_screen_width:()=>320, min_screen_height:()=>320, size_breakpoints:()=>[600,900,1200,1400],
  }, {'Home':{width:read=>Math.max(read('App').width,read('App').min_screen_width)}});
  assert.strictEqual(context.val('App').width,1000);
  assert.strictEqual(context.val('Home').width,1000);
  assert.strictEqual(context.val('Home').size,3);
  assert.strictEqual(context.val('Home').orientation,'Horizontal');
  context.innerWidth=300; context.innerHeight=700; events.resize();
  assert.strictEqual(context.val('App').width,300);
  assert.strictEqual(context.val('Home').width,320);
  assert.strictEqual(context.val('Home').orientation,'Vertical');
  assert.strictEqual(screen.style.width,'320px');
  context.innerWidth=1500; events.resize();
  assert.strictEqual(context.val('Home').size,5);
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
  assert.deepStrictEqual(RT.optionRecord({id:'source-team',display_name:'Facilities'}, 'displayName'),
    {value:'source-team',label:'Facilities'});
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

test('Reset restores single-record, table and Blank select defaults without stringifying them', () => {
  const vm=require('node:vm'),fs=require('node:fs');
  const records=[{id:'a',name:'Ada'},{id:'b',name:'Grace'}],attrs={};
  const options=records.map((record,index)=>({value:record.id,index,selected:false,
    getAttribute:()=>String(index)}));
  const el={tagName:'SELECT',style:{},options,__fxRecords:records,
    get selectedOptions() {return options.filter(option=>option.selected);},
    get selectedIndex() {return options.findIndex(option=>option.selected);},
    set selectedIndex(index) {options.forEach((option,i)=>{option.selected=i===index;});},
    get value() {return this.selectedOptions[0]?.value || '';},
    set value(value) {options.forEach(option=>{option.selected=option.value===value;});},
    getAttribute:key=>attrs[key]??null,setAttribute:(key,value)=>{attrs[key]=value;}};
  const document={querySelector:()=>el,getElementById:()=>null,addEventListener:()=>{}};
  const ctx=vm.createContext({document});ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  const rt=ctx.FXRuntime;
  for (const defaults of [records[1],records,null]) {
    rt.rowControl(document,'People',null,{default:()=>defaults});
    rt.applyDefaultSelection(el,records[0]);
    rt.resetRowControl(document,'People');
    const expected=defaults===null?[]:Array.isArray(defaults)?['a','b']:['b'];
    assert.deepStrictEqual(options.filter(option=>option.selected).map(option=>option.value),expected);
  }
});

test('date controls expose local dates and Blank, including pre-100 years and invalid values', () => {
  const previous=global.document.querySelector;
  const attrs={'data-fx-date-value':'local'};
  const el={type:'date',tagName:'INPUT',style:{},value:'2026-03-10',getAttribute:key=>attrs[key]??null};
  global.document.querySelector=()=>el;
  try {
    let value=global.val('Due');
    assert.ok(value.value instanceof Date);
    assert.strictEqual(value.value.getFullYear(),2026);
    assert.strictEqual(value.value.getMonth(),2);
    assert.strictEqual(value.value.getDate(),10);
    assert.strictEqual(value.value.getHours(),0);
    assert.strictEqual(value.selected_date.getTime(),value.value.getTime());
    el.value='';assert.strictEqual(global.val('Due').value,null);
    el.value='0099-01-01';assert.strictEqual(global.val('Due').value.getFullYear(),99);
    el.value='2026-02-30';assert.throws(()=>global.val('Due'),/Invalid date picker/);
    delete attrs['data-fx-date-value'];el.value='2026-03-10';
    assert.ok(global.val('Classic').selected_date instanceof Date);
  } finally {global.document.querySelector=previous;}
});

test('Self semantic properties resolve forward dependencies and reject cycles', () => {
  const vm=require('node:vm'),fs=require('node:fs');
  const el={tagName:'SPAN',textContent:'Header',style:{},getAttribute:()=>null};
  const ctx=vm.createContext({document:{...global.document,querySelector:()=>el},console:{error:()=>{}}});
  ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  const rt=ctx.FXRuntime;
  let fontSize=12, reads=0;
    rt.registerControlProps('SelfHeader','ParentHeader',{
      width:()=>ctx.selfRef.size*6+ctx.selfRef.padding_left,
      size:()=>{reads++;return fontSize;},
      padding_left:()=>3,
    });
    assert.strictEqual(ctx.val('SelfHeader').width,75);
    reads=0;
    const snapshot=ctx.val('SelfHeader');
    assert.strictEqual(snapshot.size+snapshot.size,24);
    assert.strictEqual(reads,1);
    fontSize=16;
    assert.strictEqual(ctx.val('SelfHeader').size,16);
    rt.updateBindings();assert.strictEqual(ctx.val('SelfHeader').width,99);
    rt.registerControlProps('CircularHeader','ParentHeader',{size:()=>ctx.selfRef.size});
    assert.throws(()=>ctx.val('CircularHeader').size,/Circular control property/);
});

test('gallery row selection exposes Selected and row-specific AllItems control records', () => {
  const original = global.document.querySelector;
  const originalCreate = global.document.createElement;
  const rows = [];
  function rowElement() {
    const child = { tagName: 'SPAN', style: { width: '60px', height: '20px' },
      textContent: '', selectedOptions: [] };
    return {
      style: {}, listeners: {}, child,
      addEventListener(ev, fn) { this.listeners[ev] = fn; },
      querySelector(selector) { return selector.includes('Name') ? child : null; },
      querySelectorAll() { return []; },
      click() { this.listeners.click(); },
    };
  }
  const rowsEl = { style: {}, children: rows,
    insertBefore(row, before) {
      const existing = rows.indexOf(row);
      if (existing >= 0) rows.splice(existing, 1);
      rows.splice(before ? rows.indexOf(before) : rows.length, 0, row);
    },
  };
  global.document.createElement = () => ({
    set innerHTML(markup) {
      assert.strictEqual(markup, template.innerHTML, 'new rows must use the owning gallery template');
    },
    firstElementChild: rowElement(),
  });
  const template = { innerHTML: '<div class="fx-row"><span data-control="Name"></span></div>' };
  const attrs = { 'data-template-size': '87', 'data-template-padding': '3' };
  const host = {
    tagName: 'DIV', textContent: '', style: { width: '210px' }, selectedOptions: [],
    getAttribute(name) { return attrs[name] === undefined ? null : attrs[name]; },
    querySelector(selector) {
      if (selector === ':scope > template') return template;
      // Once rows are mounted, a descendant query finds a nested gallery first.
      if (selector === 'template') return rows.length ? {innerHTML:'nested rating template'} : template;
      if (selector === ':scope > .fx-rows' || selector === '.fx-rows') return rowsEl;
      return null;
    },
  };
  global.document.querySelector = (selector) => selector.includes('PeopleGallery') ? host
    : rows[0] ? rows[0].child : null;
  const items = [{ id: 1, name: 'Ada' }, { id: 2, name: 'Grace' }];
  items.forEach(item => Object.defineProperty(item, 'source_name', {
    configurable:true, get() { return this.name; },
  }));
  const rowScopes = [];
  RT.gallery('PeopleGallery', () => items, (item, row) => {
    rowScopes.push(item);
    RT.rowControl(row, 'Name', 'PeopleGallery', {
      text: () => item.name,
      left: (_read, _self, parent) => parent.template_width - 5,
      height: (_read, _self, parent) => parent.template_height,
    });
  }, null, {Name:'name_control'});
  assert.strictEqual(RT.gallery.length,6);
  assert.strictEqual(RT.rowGallery.length,7);
  RT.updateBindings();
  assert.strictEqual(rows.length, 2);
  assert.strictEqual(rows[0].style.minHeight, '87px');
  assert.strictEqual(rows[0].style.padding, '3px');
  assert.strictEqual(rows[0].child.textContent, 'Ada');
  assert.strictEqual(rows[1].child.textContent, 'Grace');
  assert.strictEqual(rowScopes[0].source_name,'Ada','ThisItem must retain non-enumerable source aliases');
  assert.strictEqual(rowScopes[1].source_name,'Grace');
  assert.strictEqual(rowScopes[0].is_selected,true);
  assert.strictEqual(rowScopes[1].is_selected,false);
  assert.strictEqual(items[0].is_selected,undefined,'selection metadata must not mutate data records');
  assert.strictEqual(rows[0].child.style.left, '205px');
  const retained = rows.slice();
  RT.setState({unrelatedUpdate: 1});
  assert.strictEqual(rows[0], retained[0]);
  assert.strictEqual(rows[1], retained[1]);
  assert.strictEqual(RT.rowValue(rows[1], 'Name').text, 'Grace');
  rows[1].click();
  assert.deepStrictEqual(global.val('PeopleGallery').selected, items[1]);
  const loaded=global.val('PeopleGallery').all_items;
  assert.deepStrictEqual(loaded.map(row=>row.source_name),['Ada','Grace'],'AllItems must retain source aliases');
  assert.deepStrictEqual(loaded.map(row=>[row.id,row.name,row.name_control.text]),[[1,'Ada','Ada'],[2,'Grace','Grace']]);
  assert.strictEqual(global.val('PeopleGallery').all_items_count,2);
  assert.strictEqual(loaded[1].name_control.el,undefined);
  assert.doesNotThrow(()=>JSON.stringify(loaded));
  rows[1].child.textContent='Edited after reading AllItems';
  assert.strictEqual(loaded[1].name_control.text,'Edited after reading AllItems');
  assert.deepStrictEqual(items,[{id:1,name:'Ada'},{id:2,name:'Grace'}],'control columns cannot mutate source records');
  items.push({id:3, name:'Katherine'});
  RT.updateBindings();
  assert.strictEqual(rows.length,3);
  assert.strictEqual(rows[2].child.textContent,'Katherine');
  assert.strictEqual(rows[0],retained[0]);
  assert.strictEqual(rows[1],retained[1]);
  attrs['data-gallery-layout']='horizontal';
  host.style.height='50px';
  RT.styleControl('PeopleGallery','height',()=>100,'px');
  RT.updateBindings();
  assert.strictEqual(rows[0].child.style.height,'94px','row geometry must see the height set by a later style binding');
  assert.strictEqual(rows[0].child.style.left,'82px');
  global.document.querySelector = original;
  global.document.createElement = originalCreate;
});

test('formula-created unkeyed gallery records retain controls without stealing existing identities', () => {
  const original=global.document.querySelector, create=global.document.createElement;
  const rows=[];
  const rowsEl={children:rows,style:{},insertBefore(row,before) {
    const prior=rows.indexOf(row);if(prior>=0) rows.splice(prior,1);
    rows.splice(before ? rows.indexOf(before) : rows.length,0,row);
  }};
  function rowElement() { return {style:{},draft:'',addEventListener(){},querySelectorAll:()=>[],
    remove(){const index=rows.indexOf(this);if(index>=0)rows.splice(index,1);}}; }
  const host={tagName:'DIV',style:{},getAttribute:()=>null,querySelector:selector=>
    selector===':scope > template' ? {innerHTML:'<div></div>'} : selector===':scope > .fx-rows' ? rowsEl : null};
  global.document.querySelector=selector=>selector.includes('FreshRecords') ? host : null;
  global.document.createElement=()=>({firstElementChild:rowElement()});
  const first={name:'same',info:{active:true,day:new Date('2026-09-09T00:00:00Z')}},second={...first};
  let items=[first,second];
  try {
    RT.gallery('FreshRecords',()=>items,null,{});RT.updateBindings();
    const retained=rows.slice();retained[0].draft='first unsaved';retained[1].draft='second unsaved';
    // A new equal record must not take the control of the existing later object.
    items=[{info:{day:new Date('2026-09-09T00:00:00Z'),active:true},name:'same'},second];
    RT.updateBindings();assert.deepStrictEqual(rows,retained);
    items=items.map(item=>({name:item.name,info:{...item.info}}));
    RT.updateBindings();assert.deepStrictEqual(rows,retained);
    assert.deepStrictEqual(rows.map(row=>row.draft),['first unsaved','second unsaved']);
    items.reverse();RT.updateBindings();assert.deepStrictEqual(rows,[retained[1],retained[0]]);
    // A date and its text spelling are different typed values.
    items=[{name:'same',info:{active:true,day:'2026-09-09T00:00:00.000Z'}}];
    RT.updateBindings();assert.strictEqual(rows.length,1);assert.ok(!retained.includes(rows[0]));
  } finally {global.document.querySelector=original;global.document.createElement=create;}
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

test('collection helpers retain every record and flatten table arguments in order', () => {
  const st = { colCache: [{ id: 99 }] };
  global.powerapps_clearCollect(st, 'colCache', { id: 1 }, [{ id: 2 }, { id: 3 }], { id: 4 });
  global.powerapps_collect(st, 'colCache', { id: 5 }, { id: 6 });
  assert.deepStrictEqual(st.colCache.map(row => row.id), [1, 2, 3, 4, 5, 6]);
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

test('screen exit awaits its work before entry and runs only on an actual exit', async () => {
  const events = [];
  RT.configureCanvas({}, {}, {ExitA: {}, ExitB: {}, ExitC: {}});
  RT.registerScreenHiddenHandler('ExitA', async (read, self) => {
    events.push('hide:' + self.name);
    await Promise.resolve();
    events.push('saved');
  });
  RT.registerScreenHandler('ExitB', (read, self) => events.push('show:' + self.name));
  RT.showScreen('ExitA');
  RT.showScreen('ExitA');
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(events, []);
  RT.showScreen('ExitB');
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(events, ['hide:ExitA', 'saved', 'show:ExitB']);
  let finish;
  RT.registerScreenHiddenHandler('ExitB', () => new Promise(resolve => { finish = resolve; }));
  RT.registerScreenHandler('ExitA', () => events.push('obsolete'));
  RT.showScreen('ExitA');
  await Promise.resolve();
  RT.showScreen('ExitC');
  finish();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(!events.includes('obsolete'));
});
