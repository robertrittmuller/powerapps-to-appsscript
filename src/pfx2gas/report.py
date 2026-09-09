"""Stage 6: generate conversion-report.md from the IR + support matrix."""
from __future__ import annotations

from collections import Counter

from .controls import EXPLICITLY_UNSUPPORTED_INPUTS
from .fidelity import iter_expressions
from .ir import AppIR


def _status(expr) -> str:
    if expr.emission_status == "unsupported" or expr.translation_status == "stubbed":
        return "unsupported"
    if expr.emission_status == "ignored":
        return "ignored"
    if expr.emission_status == "approximated" or expr.translation_status == "llm":
        return "partial"
    if expr.emission_status == "emitted":
        return "emitted"
    return "unassessed"


def _screen_table(ir: AppIR) -> str:
    lines = ["| Screen | Control | Property | Translation | Runtime wiring | Original formula |",
             "|---|---|---|---|---|---|"]
    for screen, control, pname, expr in iter_expressions(ir):
        raw = expr.raw.replace("|", "\\|").replace("\n", " ")[:70]
        lines.append(
            f"| {screen} | {control} | {pname} | {expr.translation_status} | "
            f"{_status(expr)} | `{raw}` |"
        )
    return "\n".join(lines) if len(lines) > 2 else "_No formulas found._"


def _risk_section(review_rows: list[dict]) -> str:
    if not review_rows:
        return ("_Behavioral review not run_ (LLM not configured or `--no-review` / "
                "`--no-llm` used). Every converted formula should still be smoke-tested.\n")
    lines = ["| Risk | Where | Why | What to do |", "|---|---|---|---|"]
    order = {"high": 0, "medium": 1, "low": 2}
    for row in sorted(review_rows, key=lambda r: order.get(r["risk"], 3)):
        reason = row["reason"].replace("|", "\\|")[:120]
        suggestion = row["suggestion"].replace("|", "\\|")[:120]
        lines.append(f"| **{row['risk']}** | {row['context']} | {reason} | {suggestion} |")
    return "\n".join(lines) + "\n"


def _qa_section(qa_scenarios: list[dict]) -> str:
    if not qa_scenarios:
        return ("_No QA scenarios generated_ (LLM not configured or review disabled).\n")
    parts = []
    for i, s in enumerate(qa_scenarios, 1):
        steps = "\n".join(f"   {n}. {step}" for n, step in enumerate(s.get("steps", []), 1))
        parts.append(
            f"### {i}. {s.get('title', 'Scenario')}\n"
            f"Covers: {s.get('covers', '—')}\n\n"
            f"1. Steps:\n{steps}\n"
            f"1. **Expected:** {s.get('expected', '—')}\n"
        )
    return "\n".join(parts)


def _data_table(ir: AppIR) -> str:
    if not ir.data_sources:
        return "_No external data sources._"
    lines = ["| Data source | Kind | Origin | Fields | Storage in converted app |",
             "|---|---|---|---|---|"]
    for ds in ir.data_sources:
        if ds.origin == "collection":
            kind, storage = "collection", "client-side state array (not persisted)"
        elif ds.origin == "option_set":
            kind, storage = "enumeration", "exported choice codes in client state; no Sheet tab"
        elif ds.origin in {"service", "view"}:
            kind, storage = ds.origin, "source metadata retained; target adapter required"
        else:
            kind, storage = "table", f"Google Sheet tab `{ds.name}`"
            if ds.primary_key:
                storage += f"; source primary key `{ds.primary_key}`"
        fields = ", ".join(f"{f.name} ({f.type})" for f in ds.fields) or "_none inferred_"
        lines.append(f"| {ds.name} | {kind} | {ds.origin} | {fields} | {storage} |")
    if any(ds.origin == "dataverse" for ds in ir.data_sources):
        lines.append("\n`data-contract.json` retains exported Dataverse attributes, logical/display names, "
                     "choices, keys, relationships and views. Lookup records are stored snapshots. Relationship traversal, defaults, calculated fields, "
                     "Dataverse permissions and implicit localized choice-to-text coercion still require adapters.")
    return "\n".join(lines)


def _followups(ir: AppIR) -> str:
    items: list[str] = []
    grouped: Counter = Counter()
    examples: dict[tuple, str] = {}
    for screen, control, prop_name, expr in iter_expressions(ir):
        status = _status(expr)
        if status not in {"emitted"}:
            key = (status, prop_name, expr.fidelity_note or "runtime wiring incomplete")
            grouped[key] += 1
            examples.setdefault(key, f"{screen}.{control}")
    for (status, prop_name, note), count in grouped.most_common():
        items.append(
            f"- [ ] **{status}** `{prop_name}` x{count} — {note} "
            f"(example: `{examples[(status, prop_name, note)]}`)"
        )

    component_names = []
    emulated_components = []
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            if ctrl.type == "CanvasComponent" or (
                len(ctrl.type) >= 24 and all(ch in "0123456789abcdefABCDEF" for ch in ctrl.type)
            ):
                if ctrl.type == "CanvasComponent" and ctrl.children:
                    emulated_components.append(f"{screen.name}.{ctrl.name}")
                else:
                    component_names.append(f"{screen.name}.{ctrl.name}")
    if component_names:
        sample = ", ".join(f"`{name}`" for name in component_names[:5])
        suffix = "…" if len(component_names) > 5 else ""
        items.append(
            f"- [ ] **unsupported controls** component instances x{len(component_names)} render "
            f"as generic containers: {sample}{suffix}"
        )
    if emulated_components:
        sample = ", ".join(f"`{name}`" for name in emulated_components[:5])
        suffix = "…" if len(emulated_components) > 5 else ""
        items.append(
            f"- [ ] **approximated controls** component templates x{len(emulated_components)} "
            f"were expanded and require visual/interaction QA: {sample}{suffix}"
        )

    unsupported_inputs = [
        f"{screen.name}.{ctrl.name} ({ctrl.type})"
        for screen in ir.screens
        for ctrl in screen.walk_controls()
        if ctrl.type in EXPLICITLY_UNSUPPORTED_INPUTS
    ]
    if unsupported_inputs:
        sample = ", ".join(f"`{name}`" for name in unsupported_inputs[:8])
        suffix = "…" if len(unsupported_inputs) > 8 else ""
        items.append(
            f"- [ ] **unsupported input controls** x{len(unsupported_inputs)} block their "
            f"capture/upload journeys and render a visible placeholder: {sample}{suffix}"
        )

    for entry in ir.support_matrix:
        if entry.status in {"stubbed", "unmapped"}:
            items.append(f"- [ ] `{entry.subject}` — {entry.detail}")
    for warning in getattr(ir, "warnings", []):
        items.append(f"- [ ] **source warning** — {warning}")
    if not items:
        items.append("_None — every formula was rule-translated and wired by synthesis._")
    return "\n".join(items)


def render_report(ir: AppIR, validation: dict | None = None,
                  review_rows: list[dict] | None = None,
                  qa_scenarios: list[dict] | None = None) -> str:
    formula_rows = list(iter_expressions(ir))
    counts = Counter(_status(expr) for _s, _c, _p, expr in formula_rows)
    translations = Counter(expr.translation_status for _s, _c, _p, expr in formula_rows)
    total_formulas = len(formula_rows)
    stub_note = ""
    if validation is not None:
        stub_note = f"\n**Validator:** {'PASS' if validation['ok'] else 'FAIL'}"
        if validation.get("problems"):
            stub_note += " — " + "; ".join(validation["problems"])
        stub_note += f" — {validation.get('stub_count', 0)} unsupported-function call sites emitted."
        stub_note += f" — {validation.get('fidelity_gap_count', 0)} fidelity gaps ledgered."

    return f"""# Conversion report — {ir.name}

Generated by pfx2gas. This report distinguishes Power Fx translation from
actual generated runtime wiring. "Emitted" means the deterministic synthesizer
consumed the formula; it is not a claim of deployed behavioral equivalence.

## Summary

- **Screens:** {len(ir.screens)} ({', '.join(s.name for s in ir.screens) or 'none'})
- **Controls:** {sum(1 for s in ir.screens for c in s.walk_controls())}
- **Formulas found:** {total_formulas}
- **Rule-translated:** {translations.get('rule', 0)}
- **LLM-translated:** {translations.get('llm', 0)}
- **Emitted into runtime:** {counts.get('emitted', 0)}
- **Partial / approximated:** {counts.get('partial', 0)}
- **Ignored / unsupported / unassessed:** {counts.get('ignored', 0) + counts.get('unsupported', 0) + counts.get('unassessed', 0)}
- **Global variables:** {', '.join(f'`{v}`' for v in ir.global_vars) or 'none'}
- **Deployment:** `{getattr(ir, 'webapp_access', 'unassessed')}` / `{getattr(ir, 'webapp_execute_as', 'unassessed')}`
{stub_note}

## Data mapping

Original data sources are mapped to tabs of one Google Sheet workbook
(created by running `setup()` from `DataInit.gs` once after deploy).

{_data_table(ir)}

## Screens & formula fidelity ledger

{_screen_table(ir)}

## Behavioral-equivalence review

{_risk_section(review_rows or [])}

## Manual QA scenarios

{_qa_section(qa_scenarios or [])}

## Manual follow-ups

{_followups(ir)}

## Capacity notes

Apps Script quotas differ from Power Apps: max 6 min per execution (30 min on
Workspace), 30 concurrent executions per script, 30 s response budget for web
app entry points, and URL Fetch 20k calls/day (consumer). The generated data
layer reads whole tabs into memory; keep tabs under ~5,000 rows or add
filtering server-side.

## Known limitations

- Power Automate flows, Dataverse-specific features, and delegated queries are
  out of scope. Legacy component definitions are expanded when their template
  trees are available; they remain approximations requiring QA. Missing
  definitions are flagged rather than silently dropped.
- Power Fx delegation semantics are not reproduced: all filtering happens
  client-side over the full tab.
"""
