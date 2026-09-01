"""LLM review seams: post-generation behavioral review + QA scenario authoring.

Both seams are REVIEW-ONLY: they read the IR/generated code and produce report
sections. Neither can modify generated files, preserving the determinism
guarantee of the synthesis pipeline.
"""
from __future__ import annotations

import json
import time

REVIEW_SYSTEM = """You are reviewing a converted app for BEHAVIORAL EQUIVALENCE.
The original Power Apps canvas app was transpiled to JavaScript for a Google
Apps Script web app. You will receive pairs of (context, original Power Fx
formula, generated JavaScript). For each pair, judge whether the generated JS
preserves the ORIGINAL BEHAVIOR, not just syntax.

Flag when behavior could differ:
- blank/empty-string/null handling (Power Fx Blank vs JS null vs '')
- number coercion (Power Fx Value() vs JS parseFloat quirks)
- ForAll/Filter ordering or short-circuit assumptions
- Patch semantics: Power Fx Patch MERGES with the base record; naive JS
  rewrites may overwrite or duplicate
- UpdateContext (screen-local) vs Set (global) scope differences
- stale control values: generated bindings re-evaluate only on state changes
- delegation: Power Fx may filter server-side; converted code filters
  client-side over a capped table read

Respond ONLY with JSON: {"verdicts": [{"context": "...", "risk": "low|medium|high",
"reason": "one sentence", "suggestion": "how to fix or verify, one sentence"}]}
One verdict per pair, same order as given. Be specific, not generic.
"""

SCENARIO_SYSTEM = """You author QA test scenarios for a converted app. You will receive
a summary of an app's screens, controls, and behavior formulas (original Power
Fx). Write manual test scenarios that verify the converted Google Apps Script
web app behaves like the original Power Apps app.

Respond ONLY with JSON: {"scenarios": [{"title": "...", "steps": ["..."],
"expected": "...", "covers": "context of the formula(s) exercised"}]}
6-12 scenarios, prioritizing data mutations (Patch/Collect/Remove), navigation,
conditional visibility, and any formula flagged as risky. Steps must reference
actual control names from the summary.
"""


def review_behavioral_equivalence(ir, client, max_pairs: int = 40) -> list[dict]:
    """Return [{'context','risk','reason','suggestion'}] for behavior formulas."""
    from .fx.emitter import _snake  # noqa: F401

    pairs = []
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            for pname, expr in ctrl.properties.items():
                if expr.kind != "behavior" or not expr.raw or not expr.js:
                    continue
                if "FX.unsupported" in expr.js:
                    continue
                pairs.append({"context": f"{screen.name}.{ctrl.name}.{pname}",
                              "fx": expr.raw, "js": expr.js})
    if not pairs:
        return []

    results: list[dict] = []
    batch = pairs[:max_pairs]
    prompt = REVIEW_SYSTEM
    user = json.dumps(batch, indent=1)
    t0 = time.time()
    try:
        resp = client._get_client().chat.completions.create(
            model=client.model,
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        data = json.loads(content)
        verdicts = data.get("verdicts", [])
    except Exception as exc:  # network/parse errors — skip review, keep conversion
        client._log("review_batch", {"error": str(exc), "pairs": len(batch)}, t0)
        return []

    for v in verdicts:
        if isinstance(v, dict) and v.get("risk") in {"low", "medium", "high"}:
            results.append({"context": v.get("context", "?"),
                            "risk": v["risk"],
                            "reason": v.get("reason", ""),
                            "suggestion": v.get("suggestion", "")})
    client._log("review_batch", {"pairs": len(batch), "verdicts": len(results)}, t0)
    return results


def author_qa_scenarios(ir, client, max_scenarios: int = 12) -> list[dict]:
    """Return [{'title','steps','expected','covers'}] manual QA scenarios."""
    summary = []
    for screen in ir.screens:
        ctrl_summ = []
        for ctrl in screen.walk_controls():
            props = []
            for pname, expr in ctrl.properties.items():
                if expr.raw and expr.kind == "behavior":
                    props.append(f"{pname}: {expr.raw[:90]}")
            ctrl_summ.append({"name": ctrl.name, "type": ctrl.type, "formulas": props})
        summary.append({"screen": screen.name, "controls": ctrl_summ})

    user = json.dumps(summary, indent=1)[:14000]
    t0 = time.time()
    try:
        resp = client._get_client().chat.completions.create(
            model=client.model,
            messages=[{"role": "system", "content": SCENARIO_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        scenarios = [s for s in data.get("scenarios", []) if isinstance(s, dict)]
    except Exception as exc:
        client._log("qa_scenarios", {"error": str(exc)}, t0)
        return []
    client._log("qa_scenarios", {"scenarios": len(scenarios)}, t0)
    return scenarios[:max_scenarios]
