const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

function runtime() {
  const errors=[],requests=[],names=['First','Details','Recovery'];
  const screens=names.map(name=>({style:{},getAttribute:key=>key==='data-screen'?name:null}));
  const toast={style:{},classList:{add(){},remove(){}},textContent:''};
  const document={addEventListener(){},querySelectorAll:()=>screens,
    querySelector:selector=>screens[names.findIndex(name=>selector.includes('"'+name+'"'))]||screens[0],
    getElementById:id=>id==='fx-toast'?toast:null};
  const ctx=vm.createContext({document,console:{error:(...args)=>errors.push(args.map(String).join(' '))},setTimeout,clearTimeout,innerWidth:900,innerHeight:600});
  ctx.window=ctx;
  ctx.google={script:{run:{withSuccessHandler:ok=>({withFailureHandler:fail=>({connector:(service,operation,args)=>requests.push({ok,fail,service,operation,args})})})}}};
  for(const name of ['fx-stdlib','gas-runtime'])vm.runInContext(fs.readFileSync(require.resolve('../../static/'+name+'.js'),'utf8'),ctx);
  ctx.FXRuntime.configureCanvas({}, {}, {First:{},Details:{},Recovery:{}});
  ctx.FXRuntime.configureServices({Directory:{operations:{Read:{arity:[1],write:false}}}});
  return {ctx,rt:ctx.FXRuntime,errors,requests,screens};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('startup waits for chained connector reads through named formulas and commits one destination',async()=>{
  const {ctx,rt,errors,requests}=runtime();
  assert.equal(rt.resolveStartScreen.length,3);assert.equal(rt.finishStartup.length,1);
  rt.registerNamedFormulas({Destination:()=>{
    const user=rt.connectorRead('Directory','Read',['user']);
    if(!user)return 'First';
    const access=rt.connectorRead('Directory','Read',[user.id]);
    return access?.allowed?'Details':'Recovery';
  }});
  let complete=false;
  const result=rt.resolveStartScreen(()=>ctx.state.Destination,'First',[]).then(value=>{complete=true;return value;});
  assert.equal(requests.length,1);assert.equal(complete,false);
  requests[0].ok({id:'mapped-google-user'});await flush();
  assert.equal(requests.length,2);assert.equal(complete,false);
  assert.equal(requests[1].args[0],'mapped-google-user');
  requests[1].ok({allowed:true});assert.equal(await result,'Details');
  rt.finishStartup('First');assert.equal(ctx.val('App').active_screen,'Details');
  rt.updateBindings();assert.equal(requests.length,2);
  assert.deepEqual(errors,[]);
});

test('source IfError can recover from a failed startup connector without an unhandled error',async()=>{
  const {ctx,rt,errors,requests}=runtime();
  const result=rt.resolveStartScreen(()=>ctx.FX.ifError(
    ()=>rt.connectorRead('Directory','Read',['user'])?'Details':'First',()=> 'Recovery'),'First',[]);
  requests[0].fail({message:'Directory denied'});
  assert.equal(await result,'Recovery');rt.finishStartup('First');
  assert.equal(ctx.val('App').active_screen,'Recovery');assert.deepEqual(errors,[]);
});

test('startup guards globals through named formulas and restores state descriptors after failure',async()=>{
  const {ctx,rt,errors}=runtime();
  ctx.state.Later='Details';const descriptor=Object.getOwnPropertyDescriptor(ctx.state,'Later');
  rt.registerNamedFormulas({Destination:()=>ctx.state.Later});
  assert.equal(await rt.resolveStartScreen(()=>ctx.state.Destination,'First',['Later']),'First');
  assert.match(errors[0],/cannot read global variable or collection: Later/);
  assert.deepEqual(Object.getOwnPropertyDescriptor(ctx.state,'Later'),descriptor);
  ctx.state.Later='Recovery';assert.equal(ctx.state.Destination,'Recovery');
});

test('blank startup uses source order and invalid targets retain an error',async()=>{
  const {ctx,rt,errors}=runtime();
  assert.equal(await rt.resolveStartScreen(()=>null,'First',[]),'First');
  assert.deepEqual(errors,[]);
  assert.equal(await rt.resolveStartScreen(()=> 'Missing','First',[]),'First');
  assert.match(errors[0],/unknown screen/);
  const child={el:{closest:()=>({getAttribute:()=> 'Details'})}};
  assert.equal(await rt.resolveStartScreen(()=>child,'First',[]),'First');
  assert.match(errors[1],/unknown screen/);
  rt.finishStartup('First');assert.equal(ctx.val('App').active_screen,'First');
});
