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


@pytest.mark.parametrize("js", [
    "let x = 1;", "state.x = 1; state.y = 2;", "1); state.x = 2; (1",
    "(() => {state.x++; return state.x;})()", "state.x = 1", "state.x++",
    "FX.imaginaryHelper(state.x)", "FXRuntime.imaginaryHelper()",
    "fetch('https://example.test/')", "Function('return 1')()",
    "({}).constructor.constructor('return 1')()",
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
    assert '"gateVersion": 2' in log
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
