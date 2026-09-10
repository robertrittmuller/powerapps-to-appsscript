from pathlib import Path

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.ir import AppIR, FxExpr, ScreenNode, DataSource, FieldDef
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.validate import validate_project


def app(start='Details',on_start='Set(initialized, true)',named=None):
    ir=AppIR(name='StartScreen',start_screen='First',
        properties={'StartScreen':FxExpr(raw=start)},
        on_start=FxExpr(raw=on_start,kind='behavior'),
        screens=[ScreenNode(name=name,on_visible=FxExpr(raw='Set(entered, "'+name+'"); Set(sawInit, initialized)',kind='behavior')) for name in ['First','Details','Recovery']],
        data_sources=[DataSource(name='Routes',origin='static',fields=[FieldDef(name='Enabled',type='boolean')],sample_data=[{'enabled':True}])])
    if named:
        ir.properties['Formulas']=FxExpr(raw=named)
        from pfx2gas.named_formulas import declarations
        ir.named_formulas={name:FxExpr(raw=raw) for name,raw in declarations(named).items()}
    return ir


def boot(tmp_path,ir,expected,errors=False):
    ir=analyze(ir)
    project=synthesize(ir,tmp_path/'App')
    assert validate_project(project)['ok']
    result=simulate_project(project,[{'id':'destination','steps':[
        {'action':'expectScreen','screen':expected},
        {'action':'expectState','key':'initialized','equals':True},
        {'action':'expectState','key':'entered','equals':expected},
    ]}])
    assert result['visible']==[expected] and bool(result['consoleErrors'])==errors,result
    assert result['journeyResults'][0]['status']=='pass',result
    return ir,result


@pytest.mark.parametrize('start,expected', [('Details','Details'),("'Details'",'Details'),('Blank()','First'),
    ('If(CountRows(Routes) = 1 && First(Routes).Enabled, Details, First)','Details'),
    ('If(IsBlank(User().Email), Recovery, Details)','Recovery')])
def test_start_screen_overrides_order_with_loaded_data_and_user(tmp_path,start,expected):
    ir,_=boot(tmp_path,app(start),expected)
    assert ir.properties['StartScreen'].emission_status=='approximated'


def test_start_screen_can_read_named_formulas_before_onstart(tmp_path):
    boot(tmp_path,app('Destination',named='Destination = If(First(Routes).Enabled, Details, First);'),'Details')


@pytest.mark.parametrize('start,named', [('later',None),('Destination','Destination = later;'),('CountRows(Drafts)',None)])
def test_start_screen_cannot_read_onstart_globals_or_collections(tmp_path,start,named):
    ir=app(start,on_start='Set(initialized, true); Set(later, Details); ClearCollect(Drafts, {ID:1})',named=named)
    ir.data_sources.append(DataSource(name='Drafts',origin='collection'))
    _,result=boot(tmp_path,ir,'First',errors=True)
    assert any('cannot read global variable or collection' in error for error in result['consoleErrors'])


def test_record_local_names_can_shadow_onstart_globals(tmp_path):
    boot(tmp_path,app('With({later: Details}, later)',on_start='Set(initialized, true); Set(later, First)'),'Details')


@pytest.mark.parametrize('start', ['Set(changed, 1); Details','Navigate(Details)','Collect(Drafts, {ID:1})'])
def test_start_screen_rejects_behavior_before_it_can_execute(tmp_path,start):
    ir,result=boot(tmp_path,app(start),'First',errors=True)
    assert ir.properties['StartScreen'].emission_status=='unsupported'
    assert ir.properties['StartScreen'].blocked_dependencies


def test_unknown_start_destination_falls_back_and_retains_error(tmp_path):
    _,result=boot(tmp_path,app('"Missing"'),'First',errors=True)
    assert any('unknown screen' in error for error in result['consoleErrors'])


def test_retired_onstart_navigate_is_retained_and_runs_onvisible(tmp_path):
    boot(tmp_path,app('Details',on_start='Set(initialized, true); Navigate(Recovery)'),'Recovery')


def test_onstart_failure_still_reveals_resolved_start_screen(tmp_path):
    ir=analyze(app('Details',on_start='UnsupportedInitialization()'))
    result=simulate_project(synthesize(ir,tmp_path/'FailedOnStart'))
    assert result['visible']==['Details'] and result['consoleErrors'],result


def test_soak_start_expectation_uses_source_or_explicit_catalog_not_observed_output(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    from soak_check import expected_start_screen
    assert expected_start_screen(app('Details'),{})=='Details'
    assert expected_start_screen(app('Blank()'),{})=='First'
    dynamic=app('If(Param("route")="detail", Details, First)')
    assert expected_start_screen(dynamic,{}) is None
    assert expected_start_screen(dynamic,{'startupExpectedScreen':'Details'})=='Details'
    with pytest.raises(ValueError):expected_start_screen(dynamic,{'startupExpectedScreen':'Missing'})
