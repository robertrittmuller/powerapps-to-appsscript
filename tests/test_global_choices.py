import json
import subprocess

import pytest

from pfx2gas.analyze import analyze
from pfx2gas.fx import transpile
from pfx2gas.fx.lexer import FxSyntaxError
from pfx2gas.ir import AppIR, DataSource, ScreenNode, ControlNode, FxExpr
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.validate import validate_project

OPTIONS = [{'name':'Inspection','value':299600000}, {'name':'Audit','value':299600001}]


def execute(formula):
    expression=transpile(formula,option_sets={'Work types':OPTIONS},control_names=set()).js
    program="const FX=require('./static/fx-stdlib.js');console.log(JSON.stringify("+expression+'));'
    return json.loads(subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout)


def test_global_choices_keep_labels_for_text_and_codes_for_writes_and_comparison():
    assert execute("Concat(Choices('Work types'), Text(Value), \", \")") == 'Inspection, Audit'
    assert execute("LookUp(Choices('Work types'), Text(Value) = \"Audit\").Value") == 299600001
    assert execute("First(Choices('Work types')).Value = First(Choices('Work types')).Value") is True
    assert execute("First(Choices('Work types')).Value = 299600000") is True


def test_global_choices_are_registered_for_exported_display_aliases(tmp_path):
    ir=analyze(AppIR(name='GlobalChoices',start_screen='Main',data_sources=[
        DataSource(name='work_types',origin='option_set',aliases=['Work types'],option_values=OPTIONS)],
        screens=[ScreenNode(name='Main',controls=[ControlNode(name='Caption',type='Label',properties={
            'Text':FxExpr(raw="Concat(Choices('Work types'), Text(Value), \" / \")")})])]))
    out=synthesize(ir,tmp_path)
    assert validate_project(out)['ok']
    evidence=simulate_project(out,[{'id':'choice-labels','steps':[{
        'action':'expectText','control':'Caption','equals':'Inspection / Audit'}]}])
    assert not evidence['allConsoleErrors']
    assert evidence['journeyResults'][0]['status']=='pass'


def test_missing_option_metadata_and_boolean_overload_remain_explicit():
    assert transpile("Choices('Missing')").unmapped == ['Choices']
    with pytest.raises(FxSyntaxError,match='integer choices'):
        transpile("Choices('Boolean choices')",option_sets={'Boolean choices':[{'name':'Yes','value':True}]})
    with pytest.raises(FxSyntaxError,match='integer choices'):
        transpile("Choices('Missing choices')",option_sets={'Missing choices':[]})


def test_exported_labels_cannot_terminate_the_generated_script_block():
    result=transpile("Choices('Labels')",option_sets={'Labels':[{'name':'</script>','value':0}]})
    assert '</script>' not in result.js
    program="const FX=require('./static/fx-stdlib.js');console.log(FX.text(("+result.js+")[0].value));"
    assert subprocess.run(['node','-e',program],capture_output=True,text=True,check=True).stdout.strip()=='</script>'
