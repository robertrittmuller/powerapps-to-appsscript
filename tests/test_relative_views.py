"""Calendar-boundary and fail-closed gates for relative saved-view filters.

These pin the target's documented approximation, not live Dataverse parity.
"""
import json
import os
from pathlib import Path
import subprocess

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack
from pfx2gas.views import compile_view, RELATIVE_DAY_OPERATORS

FIXTURES = Path(__file__).parent / 'fixtures'


def source_contract():
    ir = parse(unpack(FIXTURES / 'fixtureRelativeViews.msapp'))
    return next(source for source in ir.data_sources if source.name == 'Projects')


def query(op='last-seven-days', value=None, source=None):
    value = '' if value is None else f' value="{value}"'
    return compile_view(f'<fetch><entity name="msft_project"><filter><condition '
        f'attribute="msft_start" operator="{op}"{value}/></filter>'
        '<order attribute="msft_start"/></entity></fetch>', source or source_contract())


def execute(q, timestamps, context=None, expected_error=None, tz='UTC'):
    code = """const FX=require('./static/fx-stdlib.js'),fs=require('fs');
const [q,dates,context]=JSON.parse(fs.readFileSync(0,'utf8'));
try {console.log(JSON.stringify(FX.applyView(dates.map((date,id)=>({id,start__date:date})),q,null,context).map(r=>r.id)));}
catch(e) {console.error(e.message);process.exit(1);} """
    run = subprocess.run(['node','-e',code],input=json.dumps([q,timestamps,context]),
                         capture_output=True,text=True,env={**os.environ,'TZ':tz})
    if expected_error:
        assert run.returncode == 1 and expected_error in run.stderr, run
    else:
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


@pytest.mark.parametrize('now,zone,before,start', [
    ('2026-03-08T16:00:00Z','America/New_York','2026-03-01T04:59:59.999Z','2026-03-01T05:00:00Z'),
    ('2026-11-01T17:00:00Z','America/New_York','2026-10-25T03:59:59.999Z','2026-10-25T04:00:00Z'),
    ('2026-01-01T01:00:00Z','America/Los_Angeles','2025-12-24T07:59:59.999Z','2025-12-24T08:00:00Z'),
    ('2026-01-01T01:00:00Z','Asia/Kolkata','2025-12-24T18:29:59.999Z','2025-12-24T18:30:00Z'),
])
def test_recent_days_include_local_midnight_exclude_now_future_and_blank(now,zone,before,start):
    times = [before,start,now,None,'2099-01-01T00:00:00Z']
    assert execute(query(),times,{'now':now,'timeZone':zone}) == [1]
    assert execute(query('last-x-days',7),times,{'now':now,'timeZone':zone}) == [1]
    # An omitted timezone must use the viewer environment, not the container's
    # UTC offset or the generated Apps Script manifest timezone.
    assert execute(query(),times,{'now':now},tz=zone) == [1]


@pytest.mark.parametrize('days,start,before', [
    (1,'2026-03-07T05:00:00Z','2026-03-07T04:59:59.999Z'),
    (30,'2026-02-06T05:00:00Z','2026-02-06T04:59:59.999Z'),
    (60,'2026-01-07T05:00:00Z','2026-01-07T04:59:59.999Z'),
])
def test_inspection_thirty_sixty_and_one_day_ranges(days,start,before):
    assert execute(query('last-x-days',days),[before,start,'2026-03-08T15:59:59.999Z'],
        {'now':'2026-03-08T16:00:00Z','timeZone':'America/New_York'}) == [1,2]


@pytest.mark.parametrize('op,expected',[('yesterday',[0]),('today',[1,2]),('tomorrow',[3])])
def test_calendar_days_span_spring_dst_and_include_later_today(op,expected):
    times = ['2026-03-08T04:59:59.999Z','2026-03-08T05:00:00Z',
             '2026-03-09T03:59:59.999Z','2026-03-09T04:00:00Z']
    assert execute(query(op),times,{'now':'2026-03-08T16:00:00Z','timeZone':'America/New_York'}) == expected


@pytest.mark.parametrize('value',['0','-1','1.5','NaN','Infinity','2147483648','1e3','١'])
def test_invalid_day_counts_fail_at_conversion(value):
    with pytest.raises(ValueError,match='positive 32-bit integer'):
        query('last-x-days',value)


@pytest.mark.parametrize('behavior',[None,'DateOnly','TimeZoneIndependent','Unknown'])
def test_missing_or_other_storage_behavior_is_not_inferred_from_display_format(behavior):
    source = source_contract()
    attr = next(a for a in source.metadata['attributes'] if a['LogicalName']=='msft_start')
    attr.update(DateTimeBehavior={'Value':behavior},Format='DateOnly')
    with pytest.raises(ValueError,match='exported UserLocal'):
        query(source=source)
    attr['DateTimeBehavior']={'Value':'UserLocal'}
    assert query(source=source)['filter']['args'][0]['args'][0]['dateBehavior']=='UserLocal'


@pytest.mark.parametrize('timestamp',['2026-03-08','2026-03-08T12:00:00','2026-02-30T12:00:00Z',
                                      '2026-03-08T24:00:00Z','bad',0,True,{}])
def test_ambiguous_or_invalid_source_timestamps_cannot_silently_match(timestamp):
    execute(query(),[timestamp],{'now':'2026-03-08T16:00:00Z'},expected_error='date')


def test_all_compiled_relative_operators_have_runtime_support_even_for_empty_tables():
    # Compiler/runtime operator drift is a bug-class gate, not just a string
    # assertion that the new op appeared in generated code.
    for op in RELATIVE_DAY_OPERATORS:
        q = query(op,30 if op=='last-x-days' else None)
        assert execute(q,[],{'now':'2026-03-08T16:00:00Z','timeZone':'UTC'}) == []
        execute(q,[],{'now':'2026-03-08T16:00:00Z','timeZone':'Invalid/Zone'},expected_error='time zone')
        execute(q,[],{'now':'invalid'},expected_error='date')
    q['filter']['args'][0]['args'][0]['op']='last-fiscal-period'
    execute(q,[],expected_error='Unsupported Dataverse view operator')


def test_multiple_relative_conditions_share_one_clock_and_accept_date_objects():
    q=query('today')
    q['filter']['args'].append(query()['filter'])
    code="""const FX=require('./static/fx-stdlib.js'),fs=require('fs'),q=JSON.parse(fs.readFileSync(0,'utf8'));
let reads=0;Date.now=()=>{reads++;return Date.parse('2026-03-08T16:00:00Z')};
const result=FX.applyView([{start__date:new Date('2026-03-08T15:00:00Z')}],q,null,{timeZone:'America/New_York'});
console.log(JSON.stringify([result.length,reads]));"""
    run=subprocess.run(['node','-e',code],input=json.dumps(q),capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)==[1,1]


def test_generated_relative_view_boot_and_fidelity_ledger(tmp_path):
    from pfx2gas.fidelity import iter_expressions
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    ir=analyze(parse(unpack(FIXTURES/'fixtureRelativeViews.msapp')),solution=FIXTURES/'fixtureRelativeViews.solution.zip')
    project=synthesize(ir,tmp_path/'relative')
    # Runtime evidence with the real clock. Fixed-date membership, write and
    # reload assertions run in Chromium with the DST-transition clock.
    verdict=simulate_project(project)
    assert not verdict['allConsoleErrors'],verdict
    expr=next(expr for _s,c,p,expr in iter_expressions(ir) if c=='ViewRows' and p=='Text')
    assert expr.emission_status=='approximated'
    assert 'browser clock and timezone' in expr.fidelity_note
