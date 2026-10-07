"""LLM review seams: post-generation behavioral review + QA scenario authoring.

Both seams are REVIEW-ONLY: they read the IR/generated code and produce report
sections. Neither can modify generated files, preserving the determinism
guarantee of the synthesis pipeline.
"""
from __future__ import annotations

import json
import time
import re

from .fidelity import iter_expressions


def review_candidates(ir) -> list[dict]:
    """Rank the entire app, retaining startup and value-formula dependencies."""
    candidates = []
    for screen, control, prop, expr in iter_expressions(ir):
        if not expr.raw:
            continue
        writes = bool(re.search(r'\b(Patch|Collect|ClearCollect|Remove|RemoveIf|UpdateIf|SubmitForm|Relate|Unrelate)\s*\(', expr.raw))
        score = (100 if writes else 0) + (80 if prop in {'OnStart','OnVisible','StartScreen'} else 0)
        score += 60 if not expr.js or expr.translation_status in {'llm','stubbed'} or expr.approximations else 0
        score += 50 if prop in {'Visible','DisplayMode','Required','Valid','Update','Items','Item','Default','DefaultSelectedItems'} else 0
        score += 30 if re.search(r'\b(Value|DateDiff|IfError|User|LookUp|Filter|Sum|Average)\s*\(',expr.raw) else 0
        score += 20 if expr.kind == 'behavior' else 0
        candidates.append({'context':f'{screen}.{control}.{prop}', 'fx':expr.raw, 'js':expr.js,
                           'priority':score, 'kind':expr.kind, 'translation':expr.translation_status,
                           'limitations':expr.approximations})
    return sorted(candidates,key=lambda item:(-item['priority'],item['context']))

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
a summary of an app's startup, screen, control and value formulas (original Power
Fx). Write manual test scenarios that verify the converted Google Apps Script
web app behaves like the original Power Apps app.

Respond ONLY with JSON: {"scenarios": [{"title": "...", "steps": ["..."],
"expected": "...", "covers": "one exact context from the supplied formulas"}]}
6-12 scenarios, prioritizing data mutations (Patch/Collect/Remove), navigation,
conditional visibility, and any formula flagged as risky. Steps must reference
actual control names from the summary.
"""


def review_behavioral_equivalence(ir, client, max_pairs: int = 40, *, coverage: dict | None = None) -> list[dict]:
    """Review the highest-risk formulas across the whole app within a fixed budget."""
    pairs = review_candidates(ir)
    coverage = coverage if coverage is not None else {}
    coverage.update(eligible=len(pairs), budget=max_pairs, selected=[], reviewed=[],
                    unreviewed=[pair['context'] for pair in pairs], errors=[], status='unassessed')
    if not pairs:
        return []

    results: list[dict] = []
    batch = pairs[:max_pairs]
    coverage['selected'] = [pair['context'] for pair in batch]
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
        coverage['errors'].append(str(exc))
        return []

    if not isinstance(verdicts,list):
        coverage['errors'].append('Review response verdicts must be a list')
        return []
    allowed = set(coverage['selected'])
    seen = set()
    for v in verdicts:
        if (isinstance(v, dict) and v.get('context') in allowed and v['context'] not in seen
                and v.get("risk") in {"low", "medium", "high"}
                and all(isinstance(v.get(key),str) for key in ('reason','suggestion'))):
            seen.add(v['context'])
            results.append({"context": v.get("context", "?"),
                            "risk": v["risk"],
                            "reason": v.get("reason", ""),
                            "suggestion": v.get("suggestion", "")})
        else:
            coverage['errors'].append('Rejected duplicate, unknown or malformed review verdict')
    coverage['reviewed'] = [result['context'] for result in results]
    coverage['unreviewed'] = [pair['context'] for pair in pairs if pair['context'] not in seen]
    coverage['status'] = 'complete' if not coverage['unreviewed'] and not coverage['errors'] else 'partial'
    client._log("review_batch", {"pairs": len(batch), "verdicts": len(results)}, t0)
    return results


def author_qa_scenarios(ir, client, max_scenarios: int = 12) -> list[dict]:
    """Return [{'title','steps','expected','covers'}] manual QA scenarios."""
    summary = []
    for candidate in review_candidates(ir):
        item = {key:candidate[key] for key in ('context','fx','kind','limitations')}
        if len(json.dumps(summary + [item])) <= 14000:
            summary.append(item)
    user = json.dumps(summary, indent=1)
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
        contexts = {item['context'] for item in summary}
        scenarios = [s for s in data.get("scenarios", []) if isinstance(s, dict)
                     and s.get('covers') in contexts and isinstance(s.get('title'),str)
                     and isinstance(s.get('expected'),str) and isinstance(s.get('steps'),list)
                     and s['steps'] and all(isinstance(step,str) for step in s['steps'])]
    except Exception as exc:
        client._log("qa_scenarios", {"error": str(exc)}, t0)
        return []
    client._log("qa_scenarios", {"scenarios": len(scenarios)}, t0)
    return scenarios[:max_scenarios]
