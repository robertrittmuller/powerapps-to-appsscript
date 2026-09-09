"""AST -> JavaScript emitter. Layers:
1. literals/arithmetic/scoping (rules)
2. function map (rules -> fx-stdlib.js calls)
3. pattern rewrites (control refs, ThisItem, galleries)
Anything the map misses becomes a ledger 'unmapped' entry handled upstream.
"""
from __future__ import annotations

import re
import json
from dataclasses import dataclass

from . import lexer as lx
from .function_map import FUNCTION_MAP
from .naming import snake as _snake


class TranspileResult:
    def __init__(self) -> None:
        self.js: str | None = None
        self.unmapped: list[str] = []
        self.approximations: list[str] = []
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
              "BorderStyle", "TextRole", "TextMode", "Live", "DateTimeFormat", "Layout"}

MATCH_PATTERNS = {"Any": ".", "Comma": ",", "Digit": r"\d", "Hyphen": r"\-",
                  "LeftParen": r"\(", "RightParen": r"\)", "Period": r"\.", "Tab": r"\t",
                  "MultipleDigits": r"\d+", "OptionalDigits": r"\d*", "Space": r"\s",
                  "MultipleSpaces": r"\s+", "OptionalSpaces": r"\s*", "NonSpace": r"\S",
                  "MultipleNonSpaces": r"\S+", "OptionalNonSpaces": r"\S*"}
MATCH_OPTIONS = {"BeginsWith", "Complete", "Contains", "EndsWith", "IgnoreCase", "Multiline", "NumberedSubMatches"}

# Legacy component exports sometimes serialize Color.White/Color.Black as
# bare reserved names. Treat the Power Apps constants as colors rather than
# app-state variables.
NAMED_COLORS = {
    "Black", "White", "Red", "Green", "Blue", "Yellow", "Gray", "Grey",
    "Orange", "Purple", "Brown", "Pink", "Transparent",
}


@dataclass(frozen=True)
class RecordScope:
    variable: str
    table: str | None = None
    alias: str | None = None


class Emitter:
    def __init__(self, res: TranspileResult, behavior: bool, row_fields: set[str] | None = None,
                 control_names: set[str] | None = None, collections: set[str] | None = None,
                 screen_names: set[str] | None = None, global_names: set[str] | None = None,
                 media_resources: dict[str, str] | None = None,
                 row_alias: str | None = None, screen_name: str | None = None,
                 control_screens: dict[str, str] | None = None, view_sets: dict | None = None):
        self.res = res
        self.behavior = behavior
        self.view_sets = view_sets or {}
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
        self.scopes: list[RecordScope] = []
        self.row_alias = row_alias
        self.scope_sequence = 0
        self.screen_name = screen_name
        self.control_screens = control_screens or {}

    def new_scope(self) -> str:
        self.scope_sequence += 1
        return f"__scope{self.scope_sequence}"

    @staticmethod
    def state_ref(name: str) -> str:
        return f"state.{name}" if re.fullmatch(r"[A-Za-z_]\w*", name) else f"state[{_q(name)}]"

    @staticmethod
    def source_name(node) -> str | None:
        if node.kind in {"ident", "global"}:
            parts = lx.reference_parts(str(node.value))
            if len(parts) == 1:
                return parts[0]
        return None

    def scoped_source(self, node, variable: str):
        alias = str(node.value) if node.kind == "alias" else None
        source = node.children[0] if alias else node
        return source, RecordScope(variable, self.source_name(source), alias)

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
        if k == "global":
            return self.ident(node.value, global_only=True)
        if k == "alias":
            return self.expr(node.children[0])
        if k == "disambiguate":
            table = self.source_name(node.children[0])
            for scope in reversed(self.scopes):
                if table is not None and scope.table == table:
                    return f"FX.field({scope.variable}, {_q(_snake(str(node.value)))})"
            raise lx.FxSyntaxError(f"no active record scope for {table or 'expression'}[@{node.value}]")
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

    def ident(self, name: str, global_only: bool = False) -> str:
        base, *members = lx.reference_parts(name)
        if base in self.view_sets:
            reason = f'Dataverse view {name}: must be a direct Filter argument'
            self.res.unmapped.append(reason)
            return 'FX.applyView([], ' + json.dumps({'error': reason}) + ')'
        alias = next((scope.variable for scope in reversed(self.scopes) if scope.alias == base), None)
        if alias is None and base == self.row_alias:
            alias = "item"
        control = False
        if not members and base in {"Ascending", "Descending"}:
            return _q(base)
        if base == "ScreenSize" and len(members) == 1 and members[0] in {"Small", "Medium", "Large", "ExtraLarge"}:
            return str({"Small": 1, "Medium": 2, "Large": 3, "ExtraLarge": 4}[members[0]])
        if base in ENUM_TYPES and members:
            return _q(".".join(members))
        if alias is not None and not global_only:
            access = alias
        elif base == "ThisItem" and not global_only:
            access = "item"  # gallery item is not shadowed by nested With/Filter
        elif base == "ThisRecord" and not global_only:
            access = self.scopes[-1].variable if self.scopes else "item"
        elif base in {"Parent", "Self"}:
            access = "parentRef" if base == "Parent" else "selfRef"
            control = True
        elif base == "App":
            access = "val('App')"
            control = True
            if members[:1] == ["ActiveScreen"] and len(members) > 1:
                access = "val(val('App').active_screen)"
                members = members[1:]
        elif self.screen_names is not None and base in self.screen_names:
            access = f"val({_q(base)})" if members else _q(base)
            control = bool(members)
        elif base in self.media_resources:
            access = _q(self.media_resources[base])
        elif base in self.control_names or (members and not self.known_controls
                                           and base not in self.global_names and base[:1].isupper()):
            access = f"val({_q(base)})"
            control = True
        else:
            fallback = _q(base.lower()) if base in NAMED_COLORS else self.state_ref(base)
            if self.screen_name is not None and not global_only and base not in NAMED_COLORS:
                fallback = f"FXRuntime.variable({_q(self.screen_name)}, {_q(base)}, () => {fallback})"
            if self.scopes and not global_only:
                access = (f"FX.scopeValue([{', '.join(scope.variable for scope in reversed(self.scopes))}], "
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
        if op in {"in", "exactin"}:
            return f"FX.contains({l}, {r}, {'true' if op == 'exactin' else 'false'})"
        return f"({l} {op} {r})"

    def record(self, node) -> str:
        parts = [f"{_snake(str(name))}: {self.expr(v)}" for name, v in node.value]
        return "{" + ", ".join(parts) + "}"

    # ---- calls -------------------------------------------------------------

    def call(self, node) -> str:
        name = str(node.value)
        args = node.children
        if name in {"IsMatch", "Match", "MatchAll"}:
            if len(args) not in {2, 3}:
                raise lx.FxSyntaxError(f"{name} requires text, a constant pattern, and optional match options")
            pattern = self.match_constant(args[1], False)
            options = self.match_constant(args[2], True) if len(args) == 3 else ""
            fn = {"IsMatch": "isMatch", "Match": "match", "MatchAll": "matchAll"}[name]
            return f"FX.{fn}({self.expr(args[0])}, {_q(pattern)}, {_q(options)})"
        if name in {"IsBlankOrError", "IsError"}:
            if len(args) != 1:
                raise lx.FxSyntaxError(name + " requires one expression")
            value = self.expr(args[0])
            prefix = "async " if "await " in value else ""
            helper = 'isError' if name == 'IsError' else 'isBlankOrError'
            call = f"FX.{helper}({prefix}() => ({value}))"
            return f"await {call}" if prefix else call
        if name == "Set":
            return self.set_call(node)
        if name == "UpdateContext":
            if not args or args[0].kind != "record":
                raise lx.FxSyntaxError("UpdateContext requires a record")
            fields = ", ".join(
                f"{_q(str(field))}: {self.expr(value)}" for field, value in args[0].value
            )
            owner = _q(self.screen_name) if self.screen_name is not None else "null"
            return f"FXRuntime.updateContext({owner}, {{{fields}}})"
        if name == "Navigate":
            if not 1 <= len(args) <= 3:
                raise lx.FxSyntaxError("Navigate requires a destination, optional transition and context record")
            target = args[0]
            if self.source_name(target) in self.control_screens:
                destination = _q(self.control_screens[self.source_name(target)])
            elif target.kind == "ident" and self.screen_names is None \
                    and "." not in str(target.value):
                destination = _q(str(target.value))
            else:
                destination = self.expr(target)
            context = ""
            if len(args) == 3:
                if args[2].kind != "record":
                    raise lx.FxSyntaxError("Navigate context must be a record with named variables")
                # Context variable names are symbols, not data-source columns.
                fields = ", ".join(f"{_q(str(key))}: {self.expr(value)}" for key, value in args[2].value)
                context = f", {{{fields}}}"
            return f"go({destination}{context})"
        if name == "Back":
            return "goBack()"
        if name == "Notify":
            return f"toast(String({self.expr(args[0])}))"
        if name == "Defaults":
            return "null"
        if name == "If":
            if len(args) < 2:
                raise lx.FxSyntaxError("If requires a condition and a result")
            # Each condition and selected result is evaluated at most once.
            # Preserve all condition/result pairs and the optional fallback;
            # a fixed three-argument map silently discards later branches.
            pairs = [(args[i], args[i + 1]) for i in range(0, len(args) - 1, 2)]
            result = self.expr(args[-1]) if len(args) % 2 else "null"
            for condition, value in reversed(pairs):
                result = f"({self.expr(condition)} ? ({self.expr(value)}) : ({result}))"
            return result
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
        if name in {"SaveData", "LoadData"}:
            if len(args) not in ({2} if name == "SaveData" else {2, 3}):
                raise lx.FxSyntaxError(f"{name} requires a collection and a storage name")
            collection = self.source_name(args[0])
            if collection is None or collection not in self.collections:
                raise lx.FxSyntaxError(f"{name} target must be a local collection")
            storage_name = self.expr(args[1])
            if name == "SaveData":
                return f"FXRuntime.saveData({self.state_ref(collection)}, {storage_name})"
            ignore_missing = self.expr(args[2]) if len(args) == 3 else "false"
            return f"FXRuntime.loadData({_q(collection)}, {storage_name}, {ignore_missing})"
        if name == "ClearData":
            if len(args) > 1:
                raise lx.FxSyntaxError("ClearData accepts at most one storage name")
            return f"FXRuntime.clearData({self.expr(args[0]) if args else ''})"
        if name in {"Patch", "Remove", "RemoveIf", "UpdateIf", "Collect", "ClearCollect", "Refresh"}:
            return self.data_call(name, node)
        if name == "Clear":
            target = args[0]
            source = self.source_name(target)
            if source is None:
                raise lx.FxSyntaxError("Clear target must be an identifier")
            return f"FXRuntime.setState({{{_q(source)}: []}})"
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
        if name == "GroupBy":
            if len(args) < 3:
                raise lx.FxSyntaxError("GroupBy requires a table, grouping columns, and a group column")
            return f"FX.groupBy({self.expr(args[0])}, [{', '.join(self._col_literal(a) for a in args[1:-1])}], {self._col_literal(args[-1])})"
        if name == "Ungroup":
            if len(args) != 2:
                raise lx.FxSyntaxError("Ungroup requires a table and a group column")
            return f"FX.ungroup({self.expr(args[0])}, {self._col_literal(args[1])})"
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
        source, binding = self.scoped_source(args[0], scope)
        def view_reference(node):
            if node.kind in {'ident', 'global'}:
                return lx.reference_parts(str(node.value))
            if node.kind == 'member':
                return [*view_reference(node.children[0]), str(node.value)]
            return []
        view_args = {}
        if name == 'Filter':
            for index, arg in enumerate(args[1:], 1):
                parts = view_reference(arg)
                if len(parts) == 2 and parts[0] in self.view_sets:
                    query = dict(self.view_sets[parts[0]].get(_snake(parts[1]),
                        {'error': f'Dataverse view {parts[0]}.{parts[1]}: missing saved view metadata'}))
                    if not query.get('error') and query['source'] != self.source_name(source):
                        query['error'] = 'Dataverse view source does not match the Filter data source'
                    view_args[index] = query
            if len(view_args) > 1:
                for query in view_args.values():
                    query['error'] = 'Dataverse view: only one view per Filter is supported'
        js_args: list[str] = []
        has_await = False
        for i, a in enumerate(args):
            if i in view_args:
                query = view_args[i]
                if query.get('error'):
                    self.res.unmapped.append(query['error'])
                self.res.approximations.extend(query.get('limitations', []))
                identity = query.get('identity') if not query.get('error') else None
                user_id = (f", FX.userId({self.state_ref(identity['source'])}, FX.field(FXUser(), 'email'), "
                           f"{_q(identity['key'])}, {_q(identity['emailField'])})") if identity else ''
                js_args[0] = 'FX.applyView(' + js_args[0] + ', ' + json.dumps(query).replace('<', '\\u003c') + user_id + ')'
                js_args.append('true')
                continue
            scoped = i >= 1 if name == "Filter" else (i in {1, 2} if name == "LookUp" else i == 1)
            if name == "AddColumns":
                scoped = i >= 2 and i % 2 == 0
            if scoped:
                self.scopes.append(binding)
            try:
                js_args.append(self.expr(source if i == 0 else a) if not (name == "AddColumns" and i % 2 == 1)
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

    def match_constant(self, node, options: bool) -> str:
        if node.kind == "str":
            return str(node.value)
        if node.kind == "binary" and node.value == "&":
            return "".join(self.match_constant(child, options) for child in node.children)
        if node.kind == "ident":
            parts = lx.reference_parts(str(node.value))
            if options and ((len(parts) == 2 and parts[0] == "MatchOptions") or len(parts) == 1) and parts[-1] in MATCH_OPTIONS:
                return parts[-1] + "|"
            if not options and len(parts) == 2 and parts[0] == "Match" and parts[1] in MATCH_PATTERNS:
                return MATCH_PATTERNS[parts[1]]
        raise lx.FxSyntaxError("matching requires a constant supported canvas pattern/options; unsupported Match enums need an explicit mapping")

    def switch_call(self, node) -> str:
        subject = self.expr(node.children[0])
        value = self.new_scope()
        rest = node.children[1:]
        pairs = [(rest[i], rest[i + 1]) for i in range(0, len(rest) - 1, 2)]
        default = rest[-1] if len(rest) % 2 == 1 else None
        js = "null" if default is None else self.expr(default)
        for cond, result in reversed(pairs):
            js = f"((FX.eq({value}, {self.expr(cond)})) ? ({self.expr(result)}) : ({js}))"
        async_prefix = "async " if "await " in js else ""
        call = f"({async_prefix}({value}) => ({js}))({subject})"
        return f"await {call}" if async_prefix else call

    def with_call(self, node) -> str:
        scope = self.new_scope()
        source, binding = self.scoped_source(node.children[0], scope)
        record = self.expr(source)  # evaluated in the enclosing scope
        self.scopes.append(binding)
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
        name = self.source_name(target)
        if name is None:
            raise lx.FxSyntaxError("Set target must be an identifier")
        key = name if re.fullmatch(r"[A-Za-z_]\w*", name) else _q(name)
        return f"FXRuntime.setState({{{key}: {value}}})"

    def data_call(self, name: str, node) -> str:
        args = node.children
        if not args:
            raise lx.FxSyntaxError(f"{name} requires a data source")
        row_scope = self.new_scope() if name in {"RemoveIf", "UpdateIf"} else "item"
        source, binding = self.scoped_source(args[0], row_scope)
        ds = self.source_name(source)
        if ds is None:
            raise lx.FxSyntaxError(f"{name} target requires a named data source")

        def ex(i: int, row_ctx: bool = False) -> str:
            if row_ctx:
                self.scopes.append(binding)
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

        if name == 'UpdateIf':
            self.res.unmapped.append('UpdateIf against an external data source')
            return "FX.unsupported('UpdateIf against an external data source')"

        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"await apiPatch({_q(ds)}, {base}, {rec})"
        if name == "Remove":
            return f"await apiRemove({_q(ds)}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            conditions = " && ".join(f"({ex(i, row_ctx=True)})" for i in range(1, len(args))) or "true"
            return f"await apiRemoveIf({_q(ds)}, ({row_scope}) => ({conditions}))"
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
        if name == 'UpdateIf':
            if not self.behavior or len(args) < 3 or len(args) % 2 != 1:
                raise lx.FxSyntaxError('UpdateIf requires condition/change pairs in a behavior formula')
            pairs = []
            for index in range(1, len(args), 2):
                condition, changes = ex(index, row_ctx=True), ex(index + 1, row_ctx=True)
                if 'await ' in condition or 'await ' in changes:
                    raise lx.FxSyntaxError('UpdateIf conditions and change records must be synchronous')
                pairs.append(f'{{condition: ({row_scope}) => ({condition}), changes: ({row_scope}) => ({changes})}}')
            return f"FX.collections.updateIf(state, {ds!r}, [{', '.join(pairs)}])"
        if name == "Patch":
            base = ex(1) if len(args) >= 3 else "null"
            rec = ex(2) if len(args) >= 3 else (ex(1) if len(args) == 2 else "{}")
            return f"FX.collections.patchCollection(state, {ds!r}, {base}, {rec})"
        if name == "Remove":
            return f"powerapps_remove(state, {ds!r}, {ex(1) if len(args) > 1 else 'item'})"
        if name == "RemoveIf":
            conditions = " && ".join(f"({ex(i, row_ctx=True)})" for i in range(1, len(args))) or "true"
            return f"powerapps_removeIf(state, {ds!r}, ({row_scope}) => ({conditions}))"
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
