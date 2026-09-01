"""AST -> JavaScript emitter. Layers:
1. literals/arithmetic/scoping (rules)
2. function map (rules -> fx-stdlib.js calls)
3. pattern rewrites (control refs, ThisItem, galleries)
Anything the map misses becomes a ledger 'unmapped' entry handled upstream.
"""
from __future__ import annotations

from . import lexer as lx
from .function_map import FUNCTION_MAP


class TranspileResult:
    def __init__(self) -> None:
        self.js: str | None = None
        self.unmapped: list[str] = []
        self.statement_count = 0


def _q(s: str) -> str:
    """JS-escape a string literal."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


def _snake(name: str) -> str:
    """snake_case a Power Fx field name for property access."""
    out: list[str] = []
    prev_upper = False
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not prev_upper:
            out.append("_")
        out.append(ch.lower())
        prev_upper = ch.isupper()
    return "".join(out)


# Functions whose later arguments are evaluated per-row (lambda context):
# bare identifiers matching known data-source fields resolve to `item.field`.
LAMBDA_FNS = {"Filter", "ForAll", "LookUp", "CountIf", "Concat", "Distinct",
              "Sort", "Sum", "Average", "RemoveIf", "AddColumns"}


class Emitter:
    def __init__(self, res: TranspileResult, behavior: bool, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None):
        self.res = res
        self.behavior = behavior
        self.row_fields = row_fields or set()
        self.control_names = control_names or set()
        self.in_row = False

    # ---- top level ---------------------------------------------------------

    def emit(self, stmts: list) -> str:
        parts = [self.stmt(s) for s in stmts]
        self.res.statement_count = len(stmts)
        if self.behavior:
            return "\n".join(p + ";" for p in parts)
        if len(parts) == 1:
            return parts[0]
        return "(function(){ %s; return (%s); })()" % (
            "; ".join(parts[:-1]),
            parts[-1],
        )

    def stmt(self, node) -> str:
        if node.kind == "call":
            return self.call(node)
        return self.expr(node)

    # ---- expressions -------------------------------------------------------

    def expr(self, node) -> str:
        k = node.kind
        if k == "num":
            return repr(node.value)
        if k == "str":
            return _q(node.value)
        if k == "bool":
            return "true" if node.value else "false"
        if k == "blank":
            return "null"
        if k == "ident":
            return self.ident(node.value)
        if k == "member":
            return self.member(node)
        if k == "binary":
            return self.binary(node)
        if k == "unary":
            operand = self.expr(node.children[0])
            return f"!({operand})" if node.value == "not" else f"-({operand})"
        if k == "table":
            return "[" + ", ".join(self.expr(c) for c in node.children) + "]"
        if k == "record":
            return self.record(node)
        if k == "call":
            return self.call(node)
        raise RuntimeError(f"unhandled node kind {k!r}")

    def ident(self, name: str) -> str:
        if name == "ThisItem":
            return "item"
        if name == "Parent":
            return "parent"
        if "." in name:
            base, rest = name.split(".", 1)
            if base == "ThisItem":
                return f"item.{_snake(rest)}"
            if base == "Parent":
                return f"parent.{_snake(rest)}"
            if base[0].isupper():
                # Control.Property reference -> val('Ctrl').prop
                return f"val({_q(base)}).{_snake(rest)}"
            return f"state.{base}.{_snake(rest)}"
        # bare identifier: inside a per-row lambda, Capitalized names are row
        # fields (unless they reference a control); lowercase are app state.
        if self.in_row and name not in self.control_names:
            return f"item.{_snake(name)}"
        return f"state.{name}"

    def member(self, node) -> str:
        target = node.children[0]
        if target.kind == "ident":
            return self.ident(f"{target.value}.{node.value}")
        return f"{self.expr(target)}.{_snake(str(node.value))}"

    def binary(self, node) -> str:
        op = node.value
        l = self.expr(node.children[0])
        r = self.expr(node.children[1])
        if op == "&":
            return f"FX.concatStr({l}, {r})"
        if op == "=":
            return f"FX.eq({l}, {r})"
        if op == "<>":
            return f"FX.neq({l}, {r})"
        if op in ("and", "&&"):
            return f"({l} && {r})"
        if op in ("or", "||"):
            return f"({l} || {r})"
        if op == "in":
            return f"FX.contains({l}, {r})"
        return f"({l} {op} {r})"

    def record(self, node) -> str:
        parts = [f"{_snake(str(name))}: {self.expr(v)}" for name, v in node.value]
        return "{" + ", ".join(parts) + "}"

    # ---- calls -------------------------------------------------------------

    def call(self, node) -> str:
        name = str(node.value)
        args = node.children
        if name in {"Set", "UpdateContext"}:
            return self.set_call(node)
        if name == "Navigate":
            target = args[0]
            screen = target.value if target.kind == "ident" else self.expr(target)
            return f"go({_q(str(screen))})"
        if name == "Back":
            return "goBack()"
        if name == "Notify":
            return f"toast(String({self.expr(args[0])}))"
        if name == "Defaults":
            return "null"
        if name == "Switch":
            return self.switch_call(node)
        if name == "With":
            return self.with_call(node)
        if name in {"Patch", "Remove", "RemoveIf", "Collect", "ClearCollect", "Refresh"}:
            return self.data_call(name, node)
        if name in {"SubmitForm", "Reset"}:
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            return f"submitForm({_q(ctrl)})"
        spec = FUNCTION_MAP.get(name)
        if spec is None:
            self.res.unmapped.append(name)
            return f"FX.unsupported({_q(name)})"
        if name in LAMBDA_FNS:
            return self.lambda_call(name, args, spec)
        return self.mapped_call(name, args, spec)

    def lambda_call(self, name: str, args: list, spec) -> str:
        """Emit table functions, treating args[1:] as per-row expressions."""
        saved = self.in_row
        js_args: list[str] = []
        for i, a in enumerate(args):
            self.in_row = i >= 1 and name != "AddColumns" or (name == "AddColumns" and i >= 2)
            js_args.append(self.expr(a))
        self.in_row = saved
        return self._fill(spec.js, js_args)

    def mapped_call(self, name: str, args: list, spec) -> str:
        js_args = [self.expr(a) for a in args]
        return self._fill(spec.js, js_args)

    def _fill(self, tmpl: str, js_args: list[str]) -> str:
        out = tmpl
        for idx, a in enumerate(js_args):
            out = out.replace("{a%d}" % idx, a)
        out = out.replace("{args}", ", ".join(js_args))
        out = out.replace("{it}", "item")
        return out

    def switch_call(self, node) -> str:
        subject = self.expr(node.children[0])
        rest = node.children[1:]
        pairs = [(rest[i], rest[i + 1]) for i in range(0, len(rest) - 1, 2)]
        default = rest[-1] if len(rest) % 2 == 1 else None
        js = "null" if default is None else self.expr(default)
        for cond, result in reversed(pairs):
            js = f"((FX.eq({subject}, {self.expr(cond)})) ? ({self.expr(result)}) : ({js}))"
        return js

    def with_call(self, node) -> str:
        saved = self.in_row
        self.in_row = True
        body = self.expr(node.children[-1])
        self.in_row = saved
        return f"FX.withRow({self.expr(node.children[0])}, (item) => ({body}))"

    def set_call(self, node) -> str:
        target = node.children[0]
        value = self.expr(node.children[1])
        if target.kind != "ident":
            raise lx.FxSyntaxError("Set target must be an identifier")
        return f"state.{target.value} = {value}"

    def data_call(self, name: str, node) -> str:
        args = node.children
        ds = str(args[0].value) if args and args[0].kind == "ident" else ""
        saved = self.in_row

        def ex(i: int, row_ctx: bool = False) -> str:
            self.in_row = row_ctx
            try:
                return self.expr(args[i])
            finally:
                self.in_row = saved

        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"await apiPatch({_q(ds)}, {base}, {rec})"
        if name == "Remove":
            return f"await apiRemove({_q(ds)}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            return f"await apiRemoveIf({_q(ds)}, (item) => ({ex(1, row_ctx=True) if len(args) > 1 else 'true'}))"
        if name == "Collect":
            return f"await apiCreate({_q(ds)}, {ex(1) if len(args) > 1 else '{}'})"
        if name == "ClearCollect":
            rec = ex(1) if len(args) > 1 else "{}"
            return f"state.{ds} = []; await apiCreate({_q(ds)}, {rec})"
        if name == "Refresh":
            return f"await refreshData({_q(ds)})"
        return f"FX.unsupported({_q(name)})"


def emit_formula(stmts: list, behavior: bool, res: TranspileResult, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None) -> str:
    return Emitter(res, behavior, row_fields, control_names).emit(stmts)
