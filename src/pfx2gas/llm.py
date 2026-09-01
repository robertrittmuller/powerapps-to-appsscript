"""LLM seam: fallback translation for Power Fx the rule engine can't map.

The LLM never writes files — it only returns a JS replacement for one formula,
which is syntax-validated before acceptance. All requests/responses are logged
to .runs/ for reproducibility.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .fx.function_map import FUNCTION_MAP

SYSTEM_PROMPT = """You translate Microsoft Power Fx expressions to plain JavaScript
for a Google Apps Script web app client. Rules:
- Return ONLY JSON: {"js": "...", "notes": "...", "confidence": 0.0-1.0}
- Use the FX.* helper namespace and these existing globals: state (app variables),
  go(screenName), goBack(), toast(msg), item (current row in per-row context).
- Never import libraries. Never use async/await unless calling apiPatch/apiCreate/
  apiRemove/refreshData (then the expression is used inside an async handler).
- Preserve the original semantics; if genuinely impossible, set "js" to null and
  explain in notes.

Available FX.* helpers (the only API you may use):
{fx_api}
"""


def _fx_api_reference() -> str:
    lines = []
    for name, spec in sorted(FUNCTION_MAP.items()):
        js = spec.js.replace("{a0}", "x").replace("{a1}", "y").replace("{a2}", "z").replace("{args}", "...")
        lines.append(f"- {name}(...)  ->  {js}")
    return "\n".join(lines)


class LlmClient:
    """Thin OpenAI-compatible client; provider/key come from env."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, log_dir: str | Path = ".runs"):
        self.base_url = base_url or os.environ.get("PFX2GAS_LLM_BASE_URL")
        self.api_key = api_key or os.environ.get("PFX2GAS_LLM_API_KEY", "")
        self.model = model or os.environ.get("PFX2GAS_LLM_MODEL", "gpt-4o-mini")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def translate_formula(self, fx: str, context: str) -> dict | None:
        """Return {'js': str, 'notes': str, 'confidence': float} or None on failure."""
        if not self.available:
            return None
        client = self._get_client()
        prompt = SYSTEM_PROMPT.format(fx_api=_fx_api_reference())
        user = f"Context: {context}\n\nPower Fx formula:\n{fx}"
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt},
                          {"role": "user", "content": user}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
        except Exception as exc:  # network, auth, provider errors — degrade to stub
            self._log(fx, {"error": str(exc)}, t0)
            return None
        try:
            data = json.loads(content)
            js = data.get("js")
            if js is None:
                self._log(fx, data, t0)
                return None
            from .validate import js_syntax_ok
            ok, _ = js_syntax_ok(js if js.strip().startswith(("function", "(")) or js.rstrip().endswith(";")
                                 else f"({js})")
            if not ok:
                self._log(fx, {"rejected_syntax": data}, t0)
                return None
            result = {"js": js, "notes": data.get("notes", ""),
                      "confidence": float(data.get("confidence", 0.5))}
            self._log(fx, result, t0)
            return result
        except (json.JSONDecodeError, ValueError, TypeError):
            self._log(fx, {"unparseable": content[:500]}, t0)
            return None

    def _log(self, fx: str, data: dict, t0: float) -> None:
        entry = {"ts": time.time(), "elapsed_s": round(time.time() - t0, 2), "fx": fx, **data}
        with (self.log_dir / "llm-calls.jsonl").open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
