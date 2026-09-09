"""Tests for the LLM seam: prompt building, JS acceptance gate, mocked client."""
import json
import pytest

from pfx2gas.llm import LlmClient, _js_acceptable, build_system_prompt


def test_build_system_prompt_has_no_format_collisions():
    prompt = build_system_prompt()
    assert "{fx_api}" not in prompt
    assert "FX.filter" in prompt  # coverage table embedded
    assert "getTimezoneOffset" in prompt  # plain-JS guidance present


def test_js_acceptable_value_expression():
    assert _js_acceptable("new Date().getTimezoneOffset()", behavior=False)
    assert _js_acceptable("state.x = 1; state.y = 2;", behavior=True)
    assert _js_acceptable("await apiPatch('Tasks', item, {status: 'Done'});", behavior=True)
    assert _js_acceptable("({value: 1, name: 'Ready'})", behavior=False)
    assert _js_acceptable("FXRuntime.language()", behavior=False)
    assert _js_acceptable("FX.sort(state.rows, item => item.amount, 'Ascending')", behavior=False)
    assert _js_acceptable("FXRuntime.variable('Details', 'selected', () => state.selected)", behavior=False)
    assert _js_acceptable("FXRuntime.updateContext('Details', {selected: null});", behavior=True)


@pytest.mark.parametrize("js", [
    "let x = 1;", "state.x = 1; state.y = 2;", "1); state.x = 2; (1",
    "(() => {state.x++; return state.x;})()", "state.x = 1", "state.x++",
    "FX.imaginaryHelper(state.x)", "FXRuntime.imaginaryHelper()",
    "fetch('https://example.test/')", "Function('return 1')()",
    "({}).constructor.constructor('return 1')()",
    "FXRuntime.updateContext('Details', {selected: null})", "FXRuntime.setState({x: 1})",
    "FXRuntime.configureContexts({Details: []})", "FXRuntime.saveData([], 'draft')",
    "go('Details')", "(0, FXRuntime.setState)({x: 1})", "state.rows.push(1)",
    "FX.collections.clear(state, 'Rows')", "window.localStorage.setItem('x', '1')",
    "new Date().setFullYear(2020)",
    "window['go']('Details')",
    "FX.concurrent([() => 1, () => 2])", "FX['concurrent']([() => 1, () => 2])",
])
def test_value_fallback_rejects_statement_escape_mutation_and_unknown_helpers(js):
    assert not _js_acceptable(js, behavior=False)


def test_behavior_fallback_cannot_escape_its_handler():
    assert not _js_acceptable("}\nstate.x = 1;\nasync function another() {", behavior=True)


def test_js_acceptable_rejects_broken_js():
    assert not _js_acceptable("this is not (( valid js", behavior=False)
    assert not _js_acceptable("", behavior=True)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content
        self.calls = []

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


def _client_with(content: str, tmp_path) -> LlmClient:
    client = LlmClient(base_url="http://mock", api_key="test", log_dir=tmp_path / ".runs")
    from openai import OpenAI

    client._client = OpenAI(base_url="http://localhost:9", api_key="x")
    client._client.chat = type("C", (), {"completions": _FakeCompletions(content)})()
    return client


def test_translate_formula_accepts_good_js(tmp_path):
    import json

    payload = json.dumps({"js": "new Date().getTimezoneOffset()", "notes": "ok",
                          "confidence": 0.9})
    client = _client_with(payload, tmp_path)
    result = client.translate_formula("TimeZoneOffset()", "Test.Control", behavior=False)
    assert result is not None
    assert "getTimezoneOffset" in result["js"]
    assert result["confidence"] == 0.9
    # call log written
    log = (tmp_path / ".runs" / "llm-calls.jsonl").read_text()
    assert "TimeZoneOffset" in log
    assert '"gateVersion": 4' in log
    assert '"formulaSha256"' in log
    assert "Formula kind: value" in client._client.chat.completions.last_kwargs["messages"][1]["content"]


@pytest.mark.parametrize("data", [[], "text", {"js": 42}, {"js": []},
    {"js": "1", "confidence": 2}, {"js": "1", "confidence": -0.1},
    {"js": "1", "confidence": "0.9"}, {"js": "1", "confidence": float('nan')},
    {"js": "1", "notes": []}, {"js": "1", "confidence": True}])
def test_formula_response_schema_is_checked_without_coercion(data, tmp_path):
    assert _client_with(json.dumps(data), tmp_path).translate_formula("Unknown()", "Test") is None


def test_translate_formula_rejects_broken_js(tmp_path):
    import json

    payload = json.dumps({"js": "definitely (( not js", "notes": "", "confidence": 0.9})
    client = _client_with(payload, tmp_path / "x1")
    result = client.translate_formula("Foo()", "Test", behavior=True)
    assert result is None


def test_translate_formula_handles_null_js(tmp_path):
    payload = json.dumps({"js": None, "notes": "impossible", "confidence": 1.0})
    client = _client_with(payload, tmp_path)
    assert client.translate_formula("Something()", "ctx", behavior=True) is None


def test_translate_formula_handles_unparseable_response(tmp_path):
    client = _client_with("not json at all", tmp_path)
    assert client.translate_formula("X()", "ctx", behavior=True) is None


def test_unavailable_client_short_circuits(tmp_path, monkeypatch):
    for var in ("PFX2GAS_LLM_BASE_URL", "PFX2GAS_LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # keep the repo's real .env out of the lookup
    client = LlmClient(base_url=None, api_key=None, log_dir=tmp_path)
    assert not client.available
    assert client.translate_formula("X()", "ctx") is None


def test_fallback_includes_screen_properties_and_explicit_scope(tmp_path):
    from pfx2gas.analyze import analyze
    from pfx2gas.cli import _llm_fallback
    from pfx2gas.ir import AppIR, FxExpr, ScreenNode

    ir = analyze(AppIR(name='Scope', screens=[ScreenNode(name='Details', properties={
        'OnHidden': FxExpr(raw='UpdateContext({localName: "saved"}); UnknownHelper()', kind='behavior')})]))
    client = _client_with(json.dumps({'js': "FXRuntime.updateContext('Details', {localName: 'saved'});",
                                    'notes': 'requires behavioral check', 'confidence': 0.7}), tmp_path)
    _llm_fallback(ir, client)
    expr = ir.screens[0].properties['OnHidden']
    assert expr.translation_status == 'llm'
    assert 'unverified' in expr.fidelity_note
    prompt = client._client.chat.completions.last_kwargs['messages'][1]['content']
    assert 'Details.Details.OnHidden' in prompt
    assert '"definingScreen": "Details"' in prompt and '"localVariables": ["localName"]' in prompt


@pytest.mark.parametrize('sign,expected_status', [('', 'pass'), ('-', 'fail')])
def test_llm_timezone_proposal_requires_behavioral_evidence(sign, expected_status, tmp_path, monkeypatch):
    """A live model returned the wrong sign at 0.98 confidence. Syntax alone
    cannot establish equivalence; replay both candidates without provider calls.
    """
    from pfx2gas.analyze import analyze
    from pfx2gas.cli import _llm_fallback
    from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.validate import validate_project

    client = _client_with(json.dumps({'js': f'{sign}(new Date(2026, state.monthNumber - 1, 15)).getTimezoneOffset()',
                                    'notes': 'candidate', 'confidence': 0.98}), tmp_path)
    ir = analyze(AppIR(name='Timezone', on_start=FxExpr(raw='Set(monthNumber, 1)', kind='behavior'),
        start_screen='Timezone', screens=[ScreenNode(name='Timezone', controls=[
            ControlNode(name='Offset', type='Label', properties={'Text': FxExpr(raw='TimeZoneOffset(Date(2026, monthNumber, 15))')}),
            ControlNode(name='Summer', type='Button', properties={'OnSelect': FxExpr(raw='Set(monthNumber, 7)', kind='behavior')})])]))
    _llm_fallback(ir, client)
    assert ir.screens[0].controls[0].properties['Text'].translation_status == 'llm'
    project = synthesize(ir, tmp_path / 'project')
    assert validate_project(project)['ok']
    for zone, winter, summer in [('UTC', 0, 0), ('America/New_York', 300, 240),
                                 ('Europe/Berlin', -60, -120), ('Asia/Kolkata', -330, -330)]:
        monkeypatch.setenv('TZ', zone)
        verdict = simulate_project(project, [{'id': zone, 'steps': [
            {'action': 'expectText', 'control': 'Offset', 'equals': str(winter)},
            {'action': 'click', 'control': 'Summer'},
            {'action': 'expectText', 'control': 'Offset', 'equals': str(summer)},
        ]}])
        assert not verdict['allConsoleErrors']
        assert verdict['journeyResults'][0]['status'] == ('pass' if zone == 'UTC' else expected_status), verdict
