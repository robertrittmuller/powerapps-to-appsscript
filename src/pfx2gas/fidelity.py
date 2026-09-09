"""Shared fidelity-state helpers.

The translator proves only that Power Fx became JavaScript. These helpers let
the synthesizer separately record whether that JavaScript is actually wired to
the generated UI/runtime, approximated, ignored, or unsupported.
"""
from __future__ import annotations

from .ir import AppIR, FxExpr


def mark_emission(expr: FxExpr | None, status: str = "emitted", note: str = "") -> None:
    if expr is None or not expr.raw:
        return
    if expr.translation_status == "stubbed" or (expr.js and "FX.unsupported" in expr.js):
        expr.emission_status = "unsupported"
    elif expr.emission_status in {"pending", "ignored"}:
        expr.emission_status = status  # type: ignore[assignment]
    elif expr.emission_status == "approximated" and status == "emitted":
        expr.emission_status = "emitted"
    if note and not expr.fidelity_note:
        expr.fidelity_note = note


def iter_expressions(ir: AppIR):
    on_start = getattr(ir, "on_start", None)
    if on_start and on_start.raw:
        yield "App", "App", "OnStart", on_start
    for name, expr in getattr(ir, 'properties', {}).items():
        if expr.raw:
            yield "App", "App", name, expr
    for screen in ir.screens:
        if screen.on_visible and screen.on_visible.raw:
            yield screen.name, screen.name, "OnVisible", screen.on_visible
        for name, expr in getattr(screen, 'properties', {}).items():
            if expr.raw:
                yield screen.name, screen.name, name, expr
        for ctrl in screen.walk_controls():
            for prop_name, expr in ctrl.properties.items():
                if expr.raw:
                    yield screen.name, ctrl.name, prop_name, expr


def finalize_fidelity(ir: AppIR) -> None:
    """Close every pending ledger row after synthesis has assessed the IR."""
    for _screen, _control, prop_name, expr in iter_expressions(ir):
        if expr.translation_status == "stubbed" or (expr.js and "FX.unsupported" in expr.js):
            expr.emission_status = "unsupported"
            if not expr.fidelity_note:
                expr.fidelity_note = "formula contains an unsupported operation"
        elif expr.emission_status == "pending":
            expr.emission_status = "ignored"
            if not expr.fidelity_note:
                expr.fidelity_note = (
                    f"{prop_name} translated to JavaScript but is not consumed by synthesis"
                )


def ledger_rows(ir: AppIR) -> list[dict]:
    return [
        {
            "screen": screen,
            "control": control,
            "property": prop_name,
            "translation": expr.translation_status,
            "emission": expr.emission_status,
            "note": expr.fidelity_note,
            "formula": expr.raw,
        }
        for screen, control, prop_name, expr in iter_expressions(ir)
    ]
