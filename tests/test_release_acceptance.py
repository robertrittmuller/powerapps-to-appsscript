import copy
import json
from pathlib import Path

import pytest

from pfx2gas.acceptance import assess_manifest, sha256, load_manifest
from pfx2gas.benchmark import converter_fingerprint
from pfx2gas.comparison import compare_captures, validate_comparison_evidence


def test_release_manifest_contains_exact_ten_required_apps_and_concrete_setup():
    manifest = load_manifest(Path('benchmark/acceptance.json'))
    assert {app['id'] for app in manifest['apps']} == {'expandable-nav','modern-card','svg-app','sentiment-feedback',
        'milestones','employee-ideas','employee-ideas-manager','inspection','inspection-manager','review-inspections'}
    assert all(app['dataSetup'] and app['journeys'] for app in manifest['apps'])


def make_manifest(root):
    (root/'app.msapp').write_text('source fingerprint fixture')
    (root/'runner.py').write_text('# runner fingerprint fixture')
    manifest = {'schemaVersion':1,'apps':[{'id':'app','source':'app.msapp','journeys':['save-reload'],
        'runner':['runner.py'],'result':'result.json','dataSetup':'explicit source records'}]}
    path = root/'manifest.json'; path.write_text(json.dumps(manifest))
    result = {'sourceAppId':'app','inputSha256':sha256(root/'app.msapp'),'converterSourceSha256':converter_fingerprint(),
              'assessmentScriptSha256':sha256(root/'runner.py'),'status':'pass','completeUsability':'pass',
              'criticalJourneyCoverage':'complete','criticalJourneys':[{'id':'save-reload','status':'pass'}],
              'steps':[{'id':'reload','status':'pass'}]}
    (root/'result.json').write_text(json.dumps(result))
    return path,result


@pytest.mark.parametrize('failure',['missing-evidence','partial','missing-journey','stale-converter','stale-source','missing-runner','failed-step'])
def test_required_release_evidence_fails_closed(tmp_path,failure):
    path,result = make_manifest(tmp_path)
    assert assess_manifest(tmp_path,path)['status']=='pass'
    if failure=='partial': result['completeUsability']='unassessed'
    if failure=='missing-journey': result['criticalJourneys']=[]
    if failure=='stale-converter': result['converterSourceSha256']='old'
    if failure=='stale-source': result['inputSha256']='old'
    if failure=='failed-step': result['steps'][0]['status']='fail'
    (tmp_path/'result.json').write_text(json.dumps(result))
    if failure=='missing-evidence': (tmp_path/'result.json').unlink()
    if failure=='missing-runner':
        manifest=json.loads(path.read_text()); manifest['apps'][0]['runner']=None; path.write_text(json.dumps(manifest))
    assert assess_manifest(tmp_path,path)['status']=='fail'


def captures():
    source={'side':'source','status':'pass','url':'https://source.test','inputSha256':'input','converterSourceSha256':'converter','capturePlanSha256':'plan',
            'context':{'locale':'en-US','timezone':'UTC','viewport':{'width':1000,'height':700},
                       'dataSnapshotSha256':'data','launchParameters':{},'roles':['member','manager']},
            'journeys':['save-reload'],'observations':[{'id':'title','journey':'save-reload','value':'Saved','expected':'Saved','status':'pass','tolerance':0}]}
    target=copy.deepcopy(source); target.update(side='target',url='https://target.test')
    return source,target


@pytest.mark.parametrize('failure',['value','locale','timezone','data','missing-observation','duplicate','expected','role','wrong-source'])
def test_source_target_comparison_rejects_mismatched_state_and_results(failure):
    source,target=captures()
    assert compare_captures(source,target)['status']=='pass'
    if failure=='value': target['observations'][0]['value']='Lost'
    if failure in {'locale','timezone'}: target['context'][failure]='different'
    if failure=='data': target['context']['dataSnapshotSha256']='different'
    if failure=='missing-observation': target['observations']=[]
    if failure=='duplicate': target['observations']*=2
    if failure=='expected': target['observations'][0]['expected']='different'
    if failure=='role': target['context']['roles']=['anonymous']
    if failure=='wrong-source': target['inputSha256']='different'
    assert compare_captures(source,target)['status']=='fail'


def test_visual_tolerances_are_explicit_and_missing_live_evidence_cannot_pass(tmp_path):
    source,target=captures()
    source['observations'][0].update(value={'width':100},expected={'width':100},tolerance=2)
    target['observations'][0].update(value={'width':101},expected={'width':100},tolerance=2)
    proof=compare_captures(source,target)
    validate_comparison_evidence(proof,'input','converter',required_journeys=['save-reload'])
    with pytest.raises(ValueError): validate_comparison_evidence(proof,'input','converter',live=True)
    path,_=make_manifest(tmp_path)
    assert assess_manifest(tmp_path,path,require_live=True,require_source=True)['status']=='fail'


@pytest.mark.parametrize('failure',['mocked','wrong-host','version','roles','missing-check','wrong-result','browser-error','solution','same-url'])
def test_live_and_source_evidence_require_executed_matching_assertions(failure):
    source,target=captures()
    target.update(url='https://script.google.com/macros/s/deployment/exec',solutionSha256='solution')
    target['observations']=[dict(id=check,journey='save-reload',status='pass',expected=True,value=True)
                            for check in ['authorization','persistence','failureRecovery','concurrentEdits']]
    proof=dict(schemaVersion=1,kind='live-google',status='pass',inputSha256='input',converterSourceSha256='converter',
               target=target,journeys=['save-reload'],usesMocks=False,deploymentVersion='1')
    validate_comparison_evidence(proof,'input','converter',live=True,required_journeys=['save-reload'],solution_hash='solution')
    if failure=='mocked': proof['usesMocks']=True
    if failure=='wrong-host': target['url']='https://example.test/exec'
    if failure=='version': proof['deploymentVersion']=None
    if failure=='roles': target['context']['roles']=['member']
    if failure=='missing-check': target['observations'].pop()
    if failure=='wrong-result': target['observations'][0]['value']=False
    if failure=='browser-error': target['errors']=['Uncaught error']
    if failure=='solution': target['solutionSha256']='stale'
    if failure=='same-url':
        source,target=captures(); target['url']=source['url']
        assert compare_captures(source,target)['status']=='fail'
    else:
        with pytest.raises(ValueError):
            validate_comparison_evidence(proof,'input','converter',live=True,required_journeys=['save-reload'],solution_hash='solution')


def test_malformed_steps_and_missing_solution_metadata_fail_closed(tmp_path):
    path,result=make_manifest(tmp_path)
    result['steps']=[None]
    (tmp_path/'result.json').write_text(json.dumps(result))
    assert assess_manifest(tmp_path,path)['status']=='fail'
    result['steps']=[{'status':'pass'}]
    (tmp_path/'result.json').write_text(json.dumps(result))
    (tmp_path/'solution.zip').write_bytes(b'fixture metadata')
    manifest=json.loads(path.read_text()); manifest['apps'][0]['solution']='solution.zip'
    path.write_text(json.dumps(manifest))
    assert assess_manifest(tmp_path,path)['status']=='fail'


@pytest.mark.parametrize('scope',['harness','app'])
def test_changed_harness_and_data_fixtures_invalidate_workflow_evidence(tmp_path,scope):
    path,result=make_manifest(tmp_path)
    fixture=tmp_path/'fixture.json';fixture.write_text('{"user":"original"}')
    manifest=json.loads(path.read_text())
    container=manifest if scope=='harness' else manifest['apps'][0]
    container['harnessFiles' if scope=='harness' else 'dependencies']=['fixture.json']
    path.write_text(json.dumps(manifest))
    assert assess_manifest(tmp_path,path)['status']=='fail'
    result['assessmentDependencySha256']={'fixture.json':sha256(fixture)}
    (tmp_path/'result.json').write_text(json.dumps(result))
    assert assess_manifest(tmp_path,path)['status']=='pass'
    fixture.write_text('{"user":"changed"}')
    assert assess_manifest(tmp_path,path)['status']=='fail'
