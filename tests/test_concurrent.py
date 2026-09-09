"""Generated Concurrent formulas must start both calls before either completes."""
import json
from pathlib import Path
import subprocess

from pfx2gas.fx import transpile


def test_emitted_concurrent_defers_network_calls_and_awaits_branch_chains():
    formula = transpile(
        'Set(result, Concurrent('
        'Set(first, Patch(Tasks, Defaults(Tasks), {Name: "first"})); Set(firstDone, true), '
        'Set(second, Patch(Tasks, Defaults(Tasks), {Name: "second"})); Set(secondDone, true))); '
        'Set(after, firstDone And secondDone)', behavior=True, control_names=set())
    assert not formula.unmapped
    # Unknown source settings/dependency validation must not be promoted to full fidelity.
    assert any('error-management settings' in note for note in formula.approximations)
    script = r'''
const assert = require('node:assert/strict');
const FX = require('./static/fx-stdlib.js');
const emitted = JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const state = {}, calls = [];
const FXRuntime = {setState:values=>Object.assign(state,values)};
const apiPatch = (ds,base,record)=>new Promise(resolve=>calls.push({ds,base,record,resolve}));
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
(async()=>{
  const work = new AsyncFunction('FX','FXRuntime','apiPatch','state',emitted)(FX,FXRuntime,apiPatch,state);
  await Promise.resolve();
  assert.equal(calls.length,2,'both server calls must start before either response');
  assert.deepEqual(calls.map(call=>call.record.name),['first','second']);
  calls[1].resolve({id:'second-row'});
  await Promise.resolve();
  assert.equal(state.secondDone,true);
  assert.equal(state.after,undefined);
  calls[0].resolve({id:'first-row'});
  await work;
  assert.deepEqual(state,{first:{id:'first-row'},second:{id:'second-row'},firstDone:true,secondDone:true,result:true,after:true});
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    run = subprocess.run(['node','-e',script], cwd=Path(__file__).resolve().parents[1],
                         input=json.dumps(formula.js), text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr
