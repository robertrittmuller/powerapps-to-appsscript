"""AST -> JavaScript emitter. Layers:
1. literals/arithmetic/scoping (rules)
2. function map (rules -> fx-stdlib.js calls)
3. pattern rewrites (control refs, ThisItem, galleries)
Anything the map misses becomes a ledger 'unmapped' entry handled upstream.
"""
from __future__ import annotations

import re

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
    return ("'" + s.replace("\\", "\\\\").replace("'", "\\'")
            .replace("\r", "\\r").replace("\n", "\\n") + "'")


# Functions with per-row predicate/projection arguments (record scope).
LAMBDA_FNS = {"Filter", "ForAll", "LookUp", "CountIf", "Concat", "Distinct",
              "Sort", "Sum", "Average", "RemoveIf", "AddColumns"}

# Enum types whose members are emitted as string literals (Color.Red -> 'Red').
ENUM_TYPES = {"Color", "Icon", "Font", "FontWeight", "Align", "Image",
              "LayoutSize", "DisplayMode", "FormMode", "FormStatus", "SortOrder",
              "LayoutDirection", "LayoutAlignItems", "LayoutJustifyContent",
              "LayoutWrap", "VerticalAlign", "FillPortions", "Overflow",
              "ImagePosition", "ImageRotation", "TextPosition", "FontWeight2",
              "BorderStyle", "TextRole", "Live"}

# Legacy component exports sometimes serialize Color.White/Color.Black as
# bare reserved names. Treat the Power Apps constants as colors rather than
# app-state variables.
NAMED_COLORS = {
    "Black", "White", "Red", "Green", "Blue", "Yellow", "Gray", "Grey",
    "Orange", "Purple", "Brown", "Pink", "Transparent",
}


class Emitter:
    def __init__(self, res: TranspileResult, behavior: bool, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None, collections: set[str] | None = None,
                 screen_names: set[str] | None = None, global_names: set[str] | None = None,
                 media_resources: dict[str, str] | None = None):
        self.res = res
        self.behavior = behavior
        self.row_fields = row_fields or set()
        self.control_names = control_names or set()
        self.known_controls = control_names is not None
        self.global_names = global_names or set()
        self.media_resources = media_resources or {}
        # Data-source names that are Power Apps collections (client-side
        # state arrays); data calls against them run locally, not server-side.
        self.collections = collections or set()
        # None preserves the standalone transpiler's historical assumption
        # that a bare Navigate target is a screen. Analysis always supplies
        # the app's concrete screen set.
        self.screen_names = screen_names
        self.scopes: list[str] = []
        self.scope_sequence = 0

    def new_scope(self) -> str:
        self.scope_sequence += 1
        return f"__scope{self.scope_sequence}"

    @staticmethod
    def state_ref(name: str) -> str:
        return f"state.{name}" if re.fullmatch(r"[A-Za-z_]\w*", name) else f"state[{_q(name)}]"

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
        if k == "chain":
            # A comma expression preserves branch-local order and the final
            # result, including awaits in the surrounding async handler.
            return "(" + ", ".join(self.expr(child) for child in node.children) + ")"
        raise RuntimeError(f"unhandled node kind {k!r}")

    def ident(self, name: str) -> str:
        base, *members = lx.reference_parts(name)
        control = False
        if not members and base in {"Ascending", "Descending"}:
            return _q(base)
        if base in ENUM_TYPES and members:
            return _q(".".join(members))
        if base == "ThisItem":
            access = "item"  # gallery item is not shadowed by nested With/Filter
        elif base == "ThisRecord":
            access = self.scopes[-1] if self.scopes else "item"
        elif base in {"Parent", "Self"}:
            access = "parentRef" if base == "Parent" else "selfRef"
            control = True
        elif self.screen_names is not None and base in self.screen_names:
            access = _q(base)
        elif base in self.media_resources:
            access = _q(self.media_resources[base])
        elif base in self.control_names or (members and not self.known_controls
                                           and base not in self.global_names and base[:1].isupper()):
            access = f"val({_q(base)})"
            control = True
        else:
            fallback = _q(base.lower()) if base in NAMED_COLORS else self.state_ref(base)
            if self.scopes:
                access = (f"FX.scopeValue([{', '.join(reversed(self.scopes))}], "
                          f"{_q(_snake(base))}, () => {fallback})")
            else:
                access = fallback
        for i, member in enumerate(members):
            key = _snake(member)
            access = f"{access}.{key}" if control and i == 0 else f"FX.field({access}, {_q(key)})"
        return access

    def member(self, node) -> str:
        target = node.children[0]
        if target.kind == "ident":
            return self.ident(f"{target.value}.{node.value}")
        access = self.expr(target)
        for member in lx.reference_parts(str(node.value)):
            access = f"FX.field({access}, {_q(_snake(member))})"
        return access

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
        if name == "Set":
            return self.set_call(node)
        if name == "UpdateContext":
            if not args or args[0].kind != "record":
                raise lx.FxSyntaxError("UpdateContext requires a record")
            fields = ", ".join(
                f"{_q(str(field))}: {self.expr(value)}" for field, value in args[0].value
            )
            return f"FXRuntime.setState({{{fields}}})"
        if name == "Navigate":
            target = args[0]
            if target.kind == "ident" and self.screen_names is None \
                    and "." not in str(target.value):
                return f"go({_q(str(target.value))})"
            return f"go({self.expr(target)})"
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
        if name == "IfError":
            if len(args) != 2:
                self.res.unmapped.append("IfError:multiple-replacements")
                return "FX.unsupported('IfError:multiple-replacements')"
            attempt, fallback = (self.expr(a) for a in args)
            is_async = "await " in attempt or "await " in fallback
            prefix = "async " if is_async else ""
            call = f"FX.ifError({prefix}() => ({attempt}), {prefix}() => ({fallback}))"
            return f"await {call}" if is_async else call
        if name in {"Patch", "Remove", "RemoveIf", "Collect", "ClearCollect", "Refresh"}:
            return self.data_call(name, node)
        if name == "Clear":
            target = args[0]
            if target.kind != "ident":
                raise lx.FxSyntaxError("Clear target must be an identifier")
            return f"FXRuntime.setState({{{_q(lx.reference_parts(target.value)[0])}: []}})"
        if name == "SubmitForm":
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            return f"await submitForm({_q(ctrl)})"
        if name == "ResetForm":
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            return f"resetForm({_q(ctrl)})"
        if name in {"Reset", "Select", "SetFocus"}:
            target = args[0]
            ctrl = str(target.value) if target.kind == "ident" else self.expr(target)
            fn = {"Select": "selectControl", "Reset": "resetControl", "SetFocus": "FXRuntime.focusControl"}[name]
            return f"{fn}({_q(ctrl)})"
        if name == "Search":
            # Search(t, needle, col1, col2, ...) -> rows where any col contains needle
            js_args = [self.expr(a) for a in args]
            table = js_args[0] if js_args else "[]"
            needle = js_args[1] if len(js_args) > 1 else "''"
            cols = ", ".join(self._col_literal(a) for a in args[2:])
            return f"FX.search({table}, {needle}, [{cols}])"
        if name == "SortByColumns":
            columns, orders = [], []
            i = 1
            while i < len(args):
                columns.append(self._col_literal(args[i]))
                i += 1
                if i < len(args) and (args[i].kind != "str" or str(args[i].value).lower().endswith(("ascending", "descending"))):
                    orders.append(self.expr(args[i]))
                    i += 1
                else:
                    orders.append("'Ascending'")
            return f"FX.sortByColumns({self.expr(args[0])}, [{', '.join(columns)}], [{', '.join(orders)}])"
        if name in {"ShowColumns", "DropColumns", "RenameColumns"}:
            fn = {"ShowColumns": "showColumns", "DropColumns": "dropColumns", "RenameColumns": "renameColumns"}[name]
            return f"FX.{fn}({self.expr(args[0])}, [{', '.join(self._col_literal(a) for a in args[1:])}])"
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
            if arg is not None and arg.kind == "ident" and len(lx.reference_parts(str(arg.value))) == 2:
                ds_name, field = lx.reference_parts(str(arg.value))
            elif arg is not None and arg.kind == "member" and arg.children \
                    and arg.children[0].kind in {"str", "ident"}:
                ds_name = lx.reference_parts(str(arg.children[0].value))[0]
                field = lx.reference_parts(str(arg.value))[0]
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
        """Only predicate/projection arguments introduce a fresh record scope."""
        scope = self.new_scope()
        js_args: list[str] = []
        has_await = False
        for i, a in enumerate(args):
            scoped = i >= 1 if name == "Filter" else (i in {1, 2} if name == "LookUp" else i == 1)
            if name == "AddColumns":
                scoped = i >= 2 and i % 2 == 0
            if scoped:
                self.scopes.append(scope)
            try:
                js_args.append(self.expr(a) if not (name == "AddColumns" and i % 2 == 1)
                               else self._col_literal(a))
            finally:
                if scoped:
                    self.scopes.pop()
            if scoped and "await " in js_args[-1]:
                has_await = True
        if name == "Filter" and len(js_args) > 2:
            js_args = [js_args[0], " && ".join(f"({arg})" for arg in js_args[1:])]
        if has_await and name != "ForAll":
            raise lx.FxSyntaxError(f"asynchronous {name} record expression needs an explicit adapter")
        if name == "LookUp" and len(js_args) > 2:
            return f"FX.lookUp({js_args[0]}, ({scope}) => {js_args[1]}, ({scope}) => {js_args[2]})"
        if name == "AddColumns":
            pairs = [js_args[0]]
            for i in range(1, len(js_args) - 1, 2):
                pairs.extend([js_args[i], f"({scope}) => ({js_args[i + 1]})"])
            return f"FX.addColumns({', '.join(pairs)})"
        tmpl = spec.js
        if has_await and "({it}) =>" in tmpl:
            tmpl = tmpl.replace("({it}) =>", "async ({it}) =>")
        call = self._fill(tmpl.replace("{it}", scope), js_args)
        return f"await Promise.all({call})" if has_await else call

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
        # A number of Power Fx functions have optional trailing arguments.
        # Never leave a template token behind as executable JavaScript.
        def optional(match):
            preferred, fallback = int(match.group(1)), int(match.group(2))
            if preferred < len(js_args):
                return js_args[preferred]
            if fallback < len(js_args):
                return js_args[fallback]
            return "null"

        out = re.sub(r"\{a(\d+) \?\? a(\d+)\}", optional, out)
        out = re.sub(r"\{a\d+\}", "null", out)
        out = out.replace("{args}", ", ".join(js_args))
        out = out.replace("{it}", "item")
        return out

    def _col_literal(self, node) -> str:
        """Column-name argument of Search(): bare ident or string -> quoted name."""
        if node.kind in {"ident", "str"}:
            value = lx.reference_parts(str(node.value))[0] if node.kind == "ident" else str(node.value)
            return _q(_snake(value))
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
        record = self.expr(node.children[0])  # evaluated in the enclosing scope
        scope = self.new_scope()
        self.scopes.append(scope)
        try:
            body = self.expr(node.children[-1])
        finally:
            self.scopes.pop()
        async_prefix = "async " if "await " in body else ""
        call = f"FX.withRow({record}, {async_prefix}({scope}) => ({body}))"
        return f"await {call}" if async_prefix else call

    def set_call(self, node) -> str:
        target = node.children[0]
        value = self.expr(node.children[1])
        if target.kind != "ident":
            raise lx.FxSyntaxError("Set target must be an identifier")
        name = lx.reference_parts(target.value)[0]
        key = name if re.fullmatch(r"[A-Za-z_]\w*", name) else _q(name)
        return f"FXRuntime.setState({{{key}: {value}}})"

    def data_call(self, name: str, node) -> str:
        args = node.children
        ds = lx.reference_parts(str(args[0].value))[0] if args and args[0].kind == "ident" else ""
        row_scope = self.new_scope() if name == "RemoveIf" else "item"

        def ex(i: int, row_ctx: bool = False) -> str:
            if row_ctx:
                self.scopes.append(row_scope)
            try:
                return self.expr(args[i])
            finally:
                if row_ctx:
                    self.scopes.pop()

        # Power Apps collections are client-side state: mutate the local
        # array synchronously (powerapps_collect fires the binding update)
        # instead of round-tripping through the Sheet API.
        if ds in self.collections:
            return self.collection_call(name, ds, node, ex, row_scope)

        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"await apiPatch({_q(ds)}, {base}, {rec})"
        if name == "Remove":
            return f"await apiRemove({_q(ds)}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            return f"await apiRemoveIf({_q(ds)}, ({row_scope}) => ({ex(1, row_ctx=True) if len(args) > 1 else 'true'}))"
        if name == "Collect":
            return f"await apiCreate({_q(ds)}, {ex(1) if len(args) > 1 else '{}'})"
        if name == "ClearCollect":
            rec = ex(1) if len(args) > 1 else "{}"
            # async IIFE so ClearCollect is valid in expression position
            # (e.g. inside Concurrent(...)) as well as a statement
            return (f"(async () => {{ {self.state_ref(ds)} = []; "
                    f"await apiCreate({_q(ds)}, {rec}); return refreshData({_q(ds)}); }})()")
        if name == "Refresh":
            return f"await refreshData({_q(ds)})"
        return f"FX.unsupported({_q(name)})"

    def collection_call(self, name: str, ds: str, node, ex, row_scope: str) -> str:
        """Transpile a data call against a collection (client-side array)."""
        args = node.children
        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"FX.collections.patchCollection(state, {ds!r}, {base}, {rec})"
        if name == "Remove":
            return f"powerapps_remove(state, {ds!r}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            return f"powerapps_removeIf(state, {ds!r}, ({row_scope}) => ({ex(1, row_ctx=True) if len(args) > 1 else 'true'}))"
        if name == "Collect":
            records = ", ".join(ex(i) for i in range(1, len(args))) or "{}"
            return f"powerapps_collect(state, {ds!r}, {records})"
        if name == "ClearCollect":
            rec = ", ".join(ex(i) for i in range(1, len(args))) or "{}"
            return f"powerapps_clearCollect(state, {ds!r}, {rec})"
        if name == "Refresh":
            return f"FX.collections.refreshCollection(state, {ds!r})"
        return f"FX.unsupported({_q(name)})"


def emit_formula(stmts: list, behavior: bool, res: TranspileResult, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None) -> str:
    return Emitter(res, behavior, row_fields, control_names).emit(stmts)
