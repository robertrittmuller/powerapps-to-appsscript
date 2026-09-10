const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function runtime() {
  const elements = {};
  const document = {addEventListener(){}, querySelectorAll:()=>[], getElementById:()=>null,
    querySelector:selector=>elements[(selector.match(/data-control="([^"]+)"/) || [])[1]] || null,
    createElement:()=>({style:{},appendChild(){}}),body:{appendChild(){}}};
  const errors=[];
  const context=vm.createContext({document,console:{error:(...args)=>errors.push(args.join(' ')),warn(){}},setTimeout,clearTimeout});
  context.window=context;
  for (const file of ['fx-stdlib.js','gas-runtime.js']) vm.runInContext(fs.readFileSync(require.resolve('../../static/'+file),'utf8'),context);
  function checkbox(name) {
    const listeners={},attrs={'data-fx-default':'false'};
    return elements[name]={tagName:'INPUT',type:'checkbox',checked:false,style:{},value:'',
      getAttribute:key=>attrs[key]??null,setAttribute:(key,value)=>{attrs[key]=String(value);},
      addEventListener:(event,fn)=>{(listeners[event] ||= []).push(fn);},
      change(value) {this.checked=value;for (const fn of listeners.change || []) fn();}};
  }
  return {context,checkbox,errors};
}
const settle=()=>new Promise(resolve=>setTimeout(resolve,15));

test('checkbox transitions run exactly the matching handler with captured Self through awaits',async()=>{
  const {context:c,checkbox,errors}=runtime(),el=checkbox('Flag'),seen=[];
  c.bind('Flag','OnCheck',async(_val,self)=>{await settle();seen.push(['on',self.value]);});
  c.bind('Flag','OnUncheck',async(_val,self)=>{await settle();seen.push(['off',self.value]);});
  el.change(true);el.change(true);el.change(false);
  await settle();await settle();
  assert.deepEqual(seen,[['on',true],['off',false]]);
  el.disabled=true;el.change(true);await settle();
  assert.equal(seen.length,2);
  assert.deepEqual(errors,[]);
});

test('Default and Reset transitions run check handlers without synthetic OnChange or duplicates',async()=>{
  const {context:c,checkbox,errors}=runtime(),el=checkbox('Flag'),seen=[];
  let initial=false,changed=0;
  c.FXRuntime.inputControl('Flag',null,{default:()=>initial});
  c.bind('Flag','OnCheck',()=>seen.push('on'));
  c.bind('Flag','OnUncheck',()=>seen.push('off'));
  c.bind('Flag','OnChange',()=>changed++);
  initial=true;c.FXRuntime.updateBindings();await settle();
  c.FXRuntime.updateBindings();await settle();
  assert.deepEqual(seen,['on']);assert.equal(changed,0);
  el.change(false);await settle();
  c.FXRuntime.resetControl('Flag');await settle();
  c.FXRuntime.resetControl('Flag');await settle();
  assert.deepEqual(seen,['on','off','on']);assert.equal(changed,1);
  assert.deepEqual(errors,[]);
});
