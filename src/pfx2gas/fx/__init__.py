"""Public transpile API: Power Fx string -> JS string + coverage info."""
from __future__ import annotations

from . import lexer as lx
from .emitter import Emitter, TranspileResult


class TranspileError(Exception):
    pass


def transpile(fx: str, behavior: bool = False, row_fields: set[str] | None = None,
              control_names: set[str] | None = None,
              collections: set[str] | None = None,
              screen_names: set[str] | None = None,
              global_names: set[str] | None = None,
              media_resources: dict[str, str] | None = None,
              row_alias: str | None = None) -> TranspileResult:
    """Transpile one Power Fx formula (may contain ;-chained statements)."""
    res = TranspileResult()
    try:
        stmts = lx.parse_formula(fx)
    except lx.FxSyntaxError as exc:
        raise TranspileError(f"cannot parse formula: {fx!r}: {exc}") from exc
    em = Emitter(res, behavior, row_fields, control_names, collections, screen_names, global_names, media_resources, row_alias)
    res.js = em.emit(stmts)
    return res
