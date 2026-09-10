"""Execute overloaded date operators with independent calendar expectations."""
import json
import os
import subprocess
import pytest
from pfx2gas.fx import transpile


@pytest.mark.parametrize('zone',['UTC','America/New_York','Europe/Berlin','Asia/Kolkata'])
def test_generated_weekly_dates_preserve_civil_days_and_original_operand(zone):
    formula=('ForAll([1, 2, 3], With({base: Date(2026, 3, 1)}, With({target: base + (Value - 1) * 7}, '
            '{Day: Day(target), Hour: Hour(target), Difference: target - base, Original: Day(base), '
            'Added: Day(DateAdd(base, 7)), StillOriginal: Day(base)})))')
    result=transpile(formula,control_names=set())
    assert not result.unmapped
    script="const FX=require('./static/fx-stdlib.js');const state={};process.stdout.write(JSON.stringify("+result.js+"));"
    run=subprocess.run(['node','-e',script],env={**os.environ,'TZ':zone},text=True,capture_output=True,check=True)
    assert json.loads(run.stdout)==[{'day':day,'hour':0,'difference':delta,'original':1,'added':8,'still_original':1}
                                   for day,delta in [(1,0),(8,7),(15,14)]]


def test_parse_fluent_date_picker_in_modern_and_legacy_exports():
    from pfx2gas.parse import _parse_control
    from pfx2gas.legacy import _normalize_template_for
    template='Microsoft_CoreControls_DatePicker'
    assert _parse_control('Due',{'Control':template+'@1.0.0','Properties':{'Value':'=Today()'}}).type=='FluentDatePicker'
    legacy=_normalize_template_for({'Template':{'Name':template}})
    assert _parse_control('Due',{'Control':legacy,'Properties':{'Value':'=Today()'}}).type=='FluentDatePicker'


def test_generated_date_picker_retains_native_calendar_review_note(tmp_path):
    from pathlib import Path
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.unpack import unpack
    from pfx2gas.synth.build import synthesize
    from pfx2gas.fidelity import ledger_rows
    ir=analyze(parse(unpack(Path('tests/fixtures/fixtureFluentDates.msapp'))))
    synthesize(ir,tmp_path/'dates')
    values=[row for row in ledger_rows(ir) if row['control'] in {'CalendarBase','DueDate'} and row['property']=='Value']
    assert len(values)==2
    assert all(row['emission']=='approximated' and 'local midnight' in row['note'] for row in values)


@pytest.mark.parametrize('screen',['Main',"'About Screen'"])
def test_source_screen_size_switch_accepts_legacy_enum_members_without_changing_variables(screen):
    formula=f'Switch({screen}.Size, Small, 10, Medium, 20, Large, 30, ExtraLarge, 40)'
    result=transpile(formula,screen_names={'Main','About Screen'},control_names=set())
    script="const FX=require('./static/fx-stdlib.js');const val=()=>({size:3});process.stdout.write(JSON.stringify("+result.js+"));"
    assert subprocess.run(['node','-e',script],text=True,capture_output=True,check=True).stdout=='30'
    declared=transpile('Switch(Main.Size, Small, 10, 0)',screen_names={'Main'},global_names={'Small'},control_names=set())
    assert 'state.Small' in declared.js
    local=transpile(formula,screen_names={'Main','About Screen'},screen_name='About Screen',control_names=set())
    script=("const FX=require('./static/fx-stdlib.js');const val=()=>({size:3});"
            "const FXRuntime={variable:(screen,key,fallback)=>key==='Small'?3:fallback()};"
            "process.stdout.write(JSON.stringify("+local.js+"));")
    assert subprocess.run(['node','-e',script],text=True,capture_output=True,check=True).stdout=='10'
