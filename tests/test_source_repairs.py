import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fx import transpile
from pfx2gas.fx.lexer import FxSyntaxError, parse_formula
from pfx2gas.fx.source_repairs import apply_source_repairs, EMPLOYEE_VOTE_HASHES, VOTE_REPAIR_NOTE
from pfx2gas.ir import AppIR, ScreenNode, ControlNode, FxExpr
from pfx2gas.synth.build import synthesize
from pfx2gas.validate import validate_project


FORMULAS = json.loads((Path(__file__).parent/'fixtures/microsoft-voting-formulas.json').read_text())


def converted(raw):
    return transpile(raw, behavior=True, collections={'colVotes','colVoteCounter'},
        row_fields={'Vote Count','Employee Idea'},
        global_names={'gblRecordCampaignIdea','gblUserRecord','Employee Ideas'},
        relationship_keys={'users'}, screen_name='Main')


@pytest.mark.parametrize('source', FORMULAS, ids=lambda row:row['control'])
def test_all_retained_voting_actions_cast_and_withdraw_exclusively(source):
    # Execute each complete upstream action, including its local optimistic
    # collection mutations and count branch, with isolated relationship/CRUD
    # callbacks. Generated-server persistence/reload is covered by Chromium.
    raw=source['raw']
    assert hashlib.sha256(raw.encode()).hexdigest()==source['formulaSha256']
    result=converted(raw)
    assert result.source_repairs[0]['sourceFormulaSha256']==source['formulaSha256']
    assert VOTE_REPAIR_NOTE in result.approximations
    program=r'''
const FX=require('./static/fx-stdlib.js');
const assert=require('node:assert/strict');
const item={employee__idea:'idea-one', vote__count:0, users:[]};
const state={gblRecordCampaignIdea:item,gblUserRecord:{id:'user-one'},
             colVotes:[],colVoteCounter:[],'Employee Ideas':[item]};
const contexts={};
const FXRuntime={variable:(_screen,name,fallback)=>Object.hasOwn(contexts,name)?contexts[name]:fallback(),
    updateContext:(_screen,patch)=>Object.assign(contexts,patch),
    setState:patch=>Object.assign(state,patch)};
const powerapps_collect=(...args)=>FX.collections.collect(...args);
const powerapps_removeIf=(st,name,predicate)=>st[name]=st[name].filter(row=>!predicate(row));
const membership=new Set(), operations=[];
async function apiRelate(_related,record,remove) {
    operations.push(remove?'unrelate':'relate');
    if (remove) membership.delete(record.id); else membership.add(record.id);
}
async function apiPatchRecord(ds,record) {
    assert.equal(ds,'Employee Ideas');assert.equal(record.employee__idea,'idea-one');
    Object.assign(item,record);return item;
}
async function vote() { __ACTION__ }
(async()=>{
    await vote();
    assert.deepEqual(operations,['relate']);assert.equal(membership.has('user-one'),true);
    assert.equal(item.vote__count,1);assert.equal(state.colVotes.length,1);
    assert.equal(state.colVoteCounter[0].app_offset,1);assert.equal(contexts.locBlockUserInput,false);
    await vote();
    assert.deepEqual(operations,['relate','unrelate']);assert.equal(membership.size,0);
    assert.equal(item.vote__count,0);assert.equal(state.colVotes.length,0);
    assert.equal(state.colVoteCounter[1].app_offset,-1);assert.equal(contexts.locBlockUserInput,false);
    console.log('cast/withdraw pass');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('__ACTION__',result.js)
    run=subprocess.run(['node','-e',program],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert run.stdout.strip()=='cast/withdraw pass'


def test_changed_source_and_generic_opposing_actions_are_not_silently_repaired():
    assert {source['formulaSha256'] for source in FORMULAS}==EMPLOYEE_VOTE_HASHES
    result=converted(FORMULAS[0]['raw']+'\n// locally modified')
    assert not result.source_repairs
    assert any('different branches' in note for note in result.approximations)
    result=converted('Concurrent(Relate(gblRecordCampaignIdea.Users,gblUserRecord),'
                     'Unrelate(gblRecordCampaignIdea.Users,gblUserRecord))')
    assert not result.source_repairs
    assert any('different branches' in note for note in result.approximations)


def test_known_repair_fails_visibly_if_parser_shape_changes():
    raw=FORMULAS[0]['raw']
    statements=parse_formula(raw)
    concurrent=next(node for node in statements if node.value=='Concurrent')
    concurrent.children[1].children.reverse()
    with pytest.raises(FxSyntaxError,match='relationship branches'):
        apply_source_repairs(raw,statements,True)


def test_source_repair_retains_original_formula_and_cannot_be_hidden(tmp_path):
    raw=FORMULAS[0]['raw']
    ir=analyze(AppIR(name='RepairLedger',start_screen='Main',screens=[ScreenNode(name='Main',controls=[
        ControlNode(name='Vote',type='Button',properties={'OnSelect':FxExpr(raw=raw,kind='behavior')})])]))
    out=synthesize(ir,tmp_path)
    assert validate_project(out)['ok']
    ledger=json.loads((out/'conversion-ledger.json').read_text())
    row=ledger['formulas'][0]
    assert row['formula']==raw and row['emission']=='approximated'
    assert 'Intentional source repair' in row['note'] and len(row['sourceRepairs'])==1
    # Erasing the deviation in both artifacts and recomputing the hash must
    # still fail: the original fingerprint requires the repair disclosure.
    inventory=json.loads((out/'source-inventory.json').read_text())
    inventory['screens'][0]['controls'][0]['properties']['OnSelect']['source_repairs']=[]
    text=json.dumps(inventory)
    (out/'source-inventory.json').write_text(text)
    ledger['sourceInventorySha256']=hashlib.sha256(text.encode()).hexdigest()
    row['sourceRepairs']=[]
    (out/'conversion-ledger.json').write_text(json.dumps(ledger))
    validation=validate_project(out)
    assert any('source repair metadata' in problem for problem in validation['problems'])
