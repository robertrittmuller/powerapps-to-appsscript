import json

from pfx2gas.ir import AppIR, ScreenNode, ControlNode, FxExpr
from pfx2gas.review import review_behavioral_equivalence, review_candidates
from test_llm import _client_with


def test_review_ranks_startup_values_and_mutations_across_all_screens(tmp_path):
    labels = [ControlNode(name=f'Label{i}',type='Label',properties={'Text':FxExpr(raw='1',js='1')}) for i in range(50)]
    labels.append(ControlNode(name='Save',type='Button',properties={'OnSelect':FxExpr(raw='Patch(Rows, row, {x:1})',js='save()',kind='behavior')}))
    ir = AppIR(name='Review',on_start=FxExpr(raw='Set(user, User())',js='start()',kind='behavior'),
               screens=[ScreenNode(name='Main',controls=labels)])
    candidates = review_candidates(ir)
    assert candidates[0]['context']=='App.App.OnStart'
    assert candidates[1]['context']=='Main.Save.OnSelect'
    response = {'verdicts':[{'context':candidates[0]['context'],'risk':'high','reason':'Check identity','suggestion':'Exercise two users'},
                            {'context':'invented','risk':'low','reason':'ok','suggestion':'none'}]}
    coverage = {}
    results = review_behavioral_equivalence(ir,_client_with(json.dumps(response),tmp_path),max_pairs=2,coverage=coverage)
    assert len(results)==1 and coverage['eligible']==52
    assert len(coverage['unreviewed'])==51 and coverage['errors']
    assert coverage['status']=='partial'


def test_duplicate_model_verdicts_cannot_inflate_review_coverage(tmp_path):
    ir = AppIR(name='Review',on_start=FxExpr(raw='Set(x,1)',js='start()',kind='behavior'))
    verdict = {'context':'App.App.OnStart','risk':'low','reason':'test','suggestion':'test'}
    coverage = {}
    results = review_behavioral_equivalence(ir,_client_with(json.dumps({'verdicts':[verdict,verdict]}),tmp_path),coverage=coverage)
    assert len(results)==1 and len(coverage['reviewed'])==1 and coverage['status']=='partial'


def test_untranslated_formulas_remain_in_the_review_census():
    ir=AppIR(name='Review',on_start=FxExpr(raw='Untranslated()',js=None,kind='behavior',translation_status='stubbed'))
    candidates=review_candidates(ir)
    assert len(candidates)==1 and candidates[0]['js'] is None and candidates[0]['priority']>=60
