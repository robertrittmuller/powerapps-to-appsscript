const test = require('node:test');
const assert = require('node:assert/strict');
const FX = require('../../static/fx-stdlib.js');
const C = FX.collections;
function state() {
  const st = {};
  C.configureContracts(st, {Drafts:{aliases:{name:'name', msft_name:'name', budget:'budget', msft_budget:'budget', active:'active', msft_active:'active'}}});
  return st;
}

test('typed collections preserve aliases through writes and JSON restoration', () => {
  const st=state(), original={msft_name:'One',msft_active:false};
  C.collect(st,'Drafts',original);
  const row=st.Drafts[0];
  assert.equal(row.name,'One');
  assert.equal(row.msft_name,'One');
  assert.equal(row.active,false);
  assert.notEqual(row,original);
  assert.equal(FX.scopeValue([row],'msft_name',()=> 'wrong'),'One');
  C.patchCollection(st,'Drafts',row,{msft_budget:0,msft_name:null});
  assert.equal(st.Drafts[0],row);
  assert.equal(row.budget,0);
  assert.equal(row.msft_budget,0);
  assert.equal(row.name,null);
  assert.equal(row.msft_name,null);
  C.patchCollection(st,'Drafts',{msft_name:null},{name:'Updated'});
  assert.equal(row.msft_name,'Updated');
  const serialized=JSON.stringify(st.Drafts);
  assert.ok(!serialized.includes('msft_'));
  C.clearCollect(st,'Drafts',JSON.parse(serialized));
  assert.equal(st.Drafts[0].msft_name,'Updated');
  assert.equal(st.Drafts[0].msft_active,false);
  C.dropRecord(st,'Drafts',{msft_name:'Updated'});
  assert.deepEqual(st.Drafts,[]);
});

test('alias conflicts fail atomically for collect, clear and patch', () => {
  const st=state();
  C.collect(st,'Drafts',{name:'Kept',budget:0});
  const row=st.Drafts[0], bad={name:'A',msft_name:'B'};
  assert.throws(()=>C.collect(st,'Drafts',{name:'Would append'},bad),/Conflicting/);
  assert.throws(()=>C.clearCollect(st,'Drafts',bad),/Conflicting/);
  assert.throws(()=>C.patchCollection(st,'Drafts',row,bad),/Conflicting/);
  assert.deepEqual(st.Drafts,[row]);
  assert.equal(row.name,'Kept');
  assert.equal(row.budget,0);
});

test('UpdateIf applies only the first match using original row values', () => {
  const st=state();
  C.collect(st,'Drafts',{name:'One',budget:0},{msft_name:'Two',msft_budget:5});
  const first=st.Drafts[0];
  C.updateIf(st,'Drafts',[
    {condition:row=>row.name==='One',changes:row=>({msft_budget:row.budget+1})},
    {condition:row=>true,changes:row=>({name:row.msft_name+' updated'})},
    {condition:()=>{throw Error('Must not evaluate');},changes:()=>({})},
  ]);
  assert.equal(st.Drafts[0],first);
  assert.equal(first.msft_budget,1);
  assert.equal(first.name,'One');
  assert.equal(st.Drafts[1].msft_name,'Two updated');
  assert.equal(st.Drafts[1].budget,5);
  assert.throws(()=>C.updateIf(st,'Drafts',[{condition:()=>true,changes:row=>row===first?{budget:9}:{name:'A',msft_name:'B'}}]),/Conflicting/);
  assert.equal(first.budget,1);
  assert.throws(()=>C.updateIf(st,'Drafts',[{condition:()=>Promise.resolve(true),changes:()=>({})}]),/synchronous/);
});

test('IsError distinguishes successful Blank from thrown and asynchronous errors', async () => {
  assert.equal(FX.isError(()=>null),false);
  assert.equal(FX.isError(()=>0),false);
  assert.equal(FX.isError(()=>{throw Error('failed');}),true);
  assert.equal(await FX.isError(()=>Promise.resolve(false)),false);
  assert.equal(await FX.isError(()=>Promise.resolve(Infinity)),true);
  assert.equal(await FX.isError(()=>Promise.reject(Error('failed'))),true);
});
