"""AST -> JavaScript emitter. Layers:
1. literals/arithmetic/scoping (rules)
2. function map (rules -> fx-stdlib.js calls)
3. pattern rewrites (control refs, ThisItem, galleries)
Anything the map misses becomes a ledger 'unmapped' entry handled upstream.
"""
from __future__ import annotations

from . import lexer as lx
from .function_map import FUNCTION_MAP
from .naming import snake as _snake


class TranspileResult:
    def __init__(self) -> None:
        self.js: str | None = None
        self.unmapped: list[str] = []
        self.statement_count = 0


def _q(s: str) -> str:
    """JS-escape a string literal."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


# Functions whose later arguments are evaluated per-row (lambda context):
# bare identifiers matching known data-source fields resolve to `item.field`.
LAMBDA_FNS = {"Filter", "ForAll", "LookUp", "CountIf", "Concat", "Distinct",
              "Sort", "Sum", "Average", "RemoveIf", "AddColumns"}

# Enum types whose members are emitted as string literals (Color.Red -> 'Red').
ENUM_TYPES = {"Color", "Icon", "Font", "FontWeight", "Align", "Image",
              "LayoutSize", "DisplayMode", "FormStatus", "SortOrder",
              "LayoutDirection", "LayoutAlignItems", "LayoutJustifyContent",
              "LayoutWrap", "VerticalAlign", "FillPortions", "Overflow",
              "ImagePosition", "TextPosition", "FontWeight2"}


class Emitter:
    def __init__(self, res: TranspileResult, behavior: bool, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None, collections: set[str] | None = None):
        self.res = res
        self.behavior = behavior
        self.row_fields = row_fields or set()
        self.control_names = control_names or set()
        # Data-source names that are Power Apps collections (client-side
        # state arrays); data calls against them run locally, not server-side.
        self.collections = collections or set()
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
        if name in ("ThisItem", "ThisRecord"):
            return "item"
        if name == "Parent":
            return "parent"
        if name == "Self":
            return "selfRef"
        if "'" in name:
            base, _, member = name.partition(".")
            member = member.strip("'\"")
            if base == "ThisItem":
                return f"item.{_snake(member)}"
            if base in ENUM_TYPES:
                return _q(member)
            # control-scoped quoted member or generic quoted access
            if base[0:1].isupper():
                return f"val({_q(base)}).{_snake(member)}"
            return f"item.{_snake(member)}"
        if "." in name:
            base, rest = name.split(".", 1)
            if base == "ThisItem":
                return f"item.{_snake(rest)}"
            if base == "Parent":
                return f"parent.{_snake(rest)}"
            if base == "Self":
                return f"selfRef.{_snake(rest)}"
            if base in ENUM_TYPES:
                return _q(rest)
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
        if name == "Clear":
            target = args[0]
            if target.kind != "ident":
                raise lx.FxSyntaxError("Clear target must be an identifier")
            return f"state.{target.value} = []"
        if name in {"SubmitForm", "Reset", "Select"}:
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            fn = "selectControl" if name == "Select" else "submitForm"
            return f"{fn}({_q(ctrl)})"
        if name == "Search":
            # Search(t, needle, col1, col2, ...) -> rows where any col contains needle
            js_args = [self.expr(a) for a in args]
            table = js_args[0] if js_args else "[]"
            needle = js_args[1] if len(js_args) > 1 else "''"
            cols = ", ".join(self._col_literal(a) for a in args[2:])
            return f"FX.search({table}, {needle}, [{cols}])"
        if name == "Table":
            # Table(record1, record2, ...) -> array of records
            js_args = [self.expr(a) for a in args]
            return "[" + ", ".join(js_args) + "]"
        if name == "Exit":
            return "exitApp()"
        if name == "Choices":
            # Choices('Data Source'.Field) -> await apiChoices('DS', 'Field')
            arg = args[0] if args else None
            ds_name = field = None
            if arg is not None and arg.kind == "ident" and "." in str(arg.value):
                ds_name, field = str(arg.value).split(".", 1)
            elif arg is not None and arg.kind == "member" and arg.children \
                    and arg.children[0].kind == "str":
                ds_name, field = str(arg.children[0].value), str(arg.value)
            if ds_name and field:
                return f"await apiChoices({_q(ds_name)}, {_q(field)})"
            self.res.unmapped.append("Choices")
            return "FX.unsupported('Choices')"
        if name in {"NewForm", "EditForm", "ViewForm"}:
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            mode = {"NewForm": "new", "EditForm": "edit", "ViewForm": "view"}[name]
            return f"setFormMode({_q(ctrl)}, {_q(mode)})"
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
        has_await = False
        for i, a in enumerate(args):
            self.in_row = i >= 1 and name != "AddColumns" or (name == "AddColumns" and i >= 2)
            js_args.append(self.expr(a))
            if i >= 1 and "await " in js_args[-1]:
                has_await = True
        self.in_row = saved
        tmpl = spec.js
        if has_await and "({it}) =>" in tmpl:
            tmpl = tmpl.replace("({it}) =>", "async ({it}) =>")
        return self._fill(tmpl, js_args)

    def mapped_call(self, name: str, args: list, spec) -> str:
        js_args = [self.expr(a) for a in args]
        return self._fill(spec.js, js_args)

    def _fill(self, tmpl: str, js_args: list[str]) -> str:
        out = tmpl
        if "{rest}" in out:
            rest = ", ".join(js_args[1:])
            out = out.replace("[{rest}]", "[" + rest + "]")
            out = out.replace("{rest}", rest)
        for idx, a in enumerate(js_args):
            out = out.replace("{a%d}" % idx, a)
        out = out.replace("{args}", ", ".join(js_args))
        out = out.replace("{it}", "item")
        return out

    def _col_literal(self, node) -> str:
        """Column-name argument of Search(): bare ident or string -> quoted name."""
        if node.kind == "ident":
            return _q(str(node.value))
        return self.expr(node)

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

        # Power Apps collections are client-side state: mutate the local
        # array synchronously (powerapps_collect fires the binding update)
        # instead of round-tripping through the Sheet API.
        if ds in self.collections:
            return self.collection_call(name, ds, node, ex)

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
            # async IIFE so ClearCollect is valid in expression position
            # (e.g. inside Concurrent(...)) as well as a statement
            return (f"(async () => {{ state.{ds} = []; "
                    f"await apiCreate({_q(ds)}, {rec}); return refreshData({_q(ds)}); }})()")
        if name == "Refresh":
            return f"await refreshData({_q(ds)})"
        return f"FX.unsupported({_q(name)})"

    def collection_call(self, name: str, ds: str, node, ex) -> str:
        """Transpile a data call against a collection (client-side array)."""
        args = node.children
        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"FX.collections.patchCollection(state, {ds!r}, {base}, {rec})"
        if name == "Remove":
            return f"powerapps_remove(state, {ds!r}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            return f"powerapps_removeIf(state, {ds!r}, (item) => ({ex(1, row_ctx=True) if len(args) > 1 else 'true'}))"
        if name == "Collect":
            return f"powerapps_collect(state, {ds!r}, {ex(1) if len(args) > 1 else '{}'})"
        if name == "ClearCollect":
            rec = ex(1) if len(args) > 1 else "{}"
            return f"powerapps_clearCollect(state, {ds!r}, {rec})"
        if name == "Refresh":
            return f"FX.collections.refreshCollection(state, {ds!r})"
        return f"FX.unsupported({_q(name)})"


def emit_formula(stmts: list, behavior: bool, res: TranspileResult, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None) -> str:
    return Emitter(res, behavior, row_fields, control_names).emit(stmts)
