"""Stage 3: derive global vars, data-source fields, and per-control verdicts."""
from __future__ import annotations

import re

from .fx import lexer as lx
from .fx import transpile
from .fx.emitter import LAMBDA_FNS
from .fx.naming import snake as _snake
from .ir import AppIR, ControlNode, DataSource, FieldDef, FxExpr, SupportEntry

from .parse import BEHAVIOR_PROPS as BEHAVIOR
NON_LOGIC_PROPS = {"X", "Y", "Width", "Height", "ZIndex", "Text", "Default", "Items",
                   "Visible", "Fill", "Color", "FontSize", "FontWeight", "Align",
                   "AccessibleLabel", "Tooltip", "Placeholder", "ItemsOrder"}


def behavior_formulas(ir: AppIR):
    if ir.on_start:
        yield ir.on_start
    yield from (expr for expr in ir.properties.values() if expr.kind == "behavior")
    for screen in ir.screens:
        if screen.on_visible:
            yield screen.on_visible
        yield from (expr for expr in screen.properties.values() if expr.kind == "behavior")
        for ctrl in screen.walk_controls():
            yield from (expr for expr in ctrl.properties.values() if expr.kind == "behavior")


def walk_formula(node):
    yield node
    for child in node.children:
        yield from walk_formula(child)
    if node.kind == "record":
        for _key, value in node.value:
            yield from walk_formula(value)


def named_target(node) -> str | None:
    if node.kind == "alias":
        node = node.children[0]
    if node.kind in {"ident", "global"}:
        parts = lx.reference_parts(str(node.value))
        if len(parts) == 1:
            return parts[0]
    return None


def scoped_target(expr: FxExpr, node) -> str | None:
    from .fx.naming import component_symbol
    name = named_target(node)
    return component_symbol(expr.component_owner, name) if name is not None and expr.component_owner and expr.component_private else name


def collect_global_vars(ir: AppIR) -> list[str]:
    """App-wide identifiers assigned via Set/Collect, excluding screen locals."""
    names: set[str] = set()

    def add_from(formula: FxExpr) -> None:
        if not formula.raw:
            return
        try:
            stmts = lx.parse_formula(formula.raw)
        except lx.FxSyntaxError:
            return
        for st in (node for root in stmts for node in walk_formula(root)):
            if st.kind == "call" and st.value in {"Set", "Collect", "ClearCollect"}:
                t = st.children[0] if st.children else None
                name = scoped_target(formula, t) if t is not None else None
                if name is not None:
                    names.add(name)

    for expr in behavior_formulas(ir):
        add_from(expr)
    return sorted(names)


def collect_context_vars(ir: AppIR, control_screens: dict[str, str]) -> None:
    """Declare local symbols even before their first assignment (initial Blank)."""
    by_name = {screen.name: screen for screen in ir.screens}
    names = {name: set() for name in by_name}
    def scan(expr, owner):
        if not expr or not expr.raw or expr.component_owner:
            return
        try:
            roots = lx.parse_formula(expr.raw)
        except lx.FxSyntaxError:
            return
        for node in (node for root in roots for node in walk_formula(root)):
            if node.kind != 'call':
                continue
            record, destination = None, owner
            if node.value == 'UpdateContext' and node.children:
                record = node.children[0]
            elif node.value == 'Navigate' and len(node.children) == 3:
                target = named_target(node.children[0])
                destination = target if target in by_name else control_screens.get(target)
                record = node.children[2]
                if destination is None:
                    warning = 'Dynamic Navigate context declarations are deferred until the destination is known at runtime'
                    if warning not in ir.warnings:
                        ir.warnings.append(warning)
            if destination in names and record is not None and record.kind == 'record':
                names[destination].update(str(key) for key, _value in record.value)
    scan(ir.on_start, None)
    for expr in ir.properties.values():
        scan(expr, None)
    for screen in ir.screens:
        scan(screen.on_visible, screen.name)
        for expr in screen.properties.values():
            scan(expr, screen.name)
        for control in screen.walk_controls():
            for expr in control.properties.values():
                scan(expr, screen.name)
    for name, screen in by_name.items():
        screen.context_vars = sorted(names[name])


def infer_local_collections(ir: AppIR) -> None:
    """Collections can be created by formulas without exported source metadata.

    Existing external sources retain their origin: Collect can also append to
    an external table. Only a previously undeclared target creates a collection.
    """
    known = {ds.name for ds in ir.data_sources}
    for expr in behavior_formulas(ir):
        try:
            roots = lx.parse_formula(expr.raw)
        except lx.FxSyntaxError:
            continue
        for node in (node for root in roots for node in walk_formula(root)):
            if node.kind != "call" or node.value not in {"Collect", "ClearCollect"} or not node.children:
                continue
            target = node.children[0]
            name = scoped_target(expr, target)
            if name is not None and name not in known:
                ir.data_sources.append(DataSource(name=name, origin="collection"))
                known.add(name)


def collect_row_fields(ir: AppIR) -> set[str]:
    """Field names referenced in gallery row templates (ThisItem.X, bare fields in Items)."""
    fields: set[str] = set()

    def scan_props(ctrl: ControlNode) -> None:
        for expr in ctrl.properties.values():
            try:
                toks = lx.tokenize(expr.raw)
            except lx.FxSyntaxError:
                continue  # unlexable formulas are handled (as stubs) later
            for tok in toks:
                if tok.kind == "ident" and "." in tok.value:
                    base, field_name = tok.value.split(".", 1)
                    if base == "ThisItem":
                        fields.add(field_name)

    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            scan_props(ctrl)
    return fields


def infer_data_source_fields(ir: AppIR) -> None:
    """Infer source fields from mutations, dotted refs, and Form DataCards."""
    from .data_contract import NON_TABLE_ORIGINS, field_aliases
    by_name = {ds.name: ds for ds in ir.data_sources
               if ds.origin not in NON_TABLE_ORIGINS - {"collection"}}

    def known_fields(ds):
        return {name for field in ds.fields for name in field_aliases(field)}

    def simple_source_name(raw: str) -> str | None:
        text = raw.strip()
        if text.startswith("[@") and text.endswith("]"):
            text = text[2:-1]
        if len(text) >= 2 and text[0] == text[-1] == "'":
            text = text[1:-1]
        return text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", text) else None

    def string_literal(raw: str) -> str | None:
        try:
            nodes = lx.parse_formula(raw)
        except lx.FxSyntaxError:
            return None
        if len(nodes) == 1 and nodes[0].kind == "str":
            return str(nodes[0].value)
        return None

    def descendants(ctrl: ControlNode):
        for child in ctrl.children:
            yield child
            yield from descendants(child)

    def card_field_type(card: ControlNode) -> str:
        update = card.properties.get("Update")
        if update and re.search(r"\bValue\s*\(", update.raw, re.I):
            return "number"
        input_types = {child.type for child in descendants(card)}
        if {"DatePicker", "FluentDatePicker"} & input_types:
            return "date"
        if "CheckBox" in input_types:
            return "bool"
        return "text"

    # Form/DataCard metadata is stronger schema evidence than a generic dotted
    # reference. It also ensures real forms get a Sheet tab even when no Patch
    # formula exists in the source app.
    for screen in ir.screens:
        for form in screen.walk_controls():
            if form.type != "Form":
                continue
            source_expr = form.properties.get("DataSource")
            ds_name = simple_source_name(source_expr.raw) if source_expr else None
            ds = by_name.get(ds_name or "")
            if ds is None:
                continue
            known = known_fields(ds)
            if not ds.primary_key and "id" not in known:
                # Google Sheets has no intrinsic row identity. Every generated
                # form-backed table gets a stable converter-owned key so an
                # EditForm submission updates exactly one persisted row.
                ds.fields.insert(0, FieldDef(name="id", type="text"))
                known.add("id")
            for card in descendants(form):
                if card.type != "DataCard":
                    continue
                field_expr = card.properties.get("DataField")
                field_name = string_literal(field_expr.raw) if field_expr else None
                if field_name and _snake(field_name) not in known:
                    ds.fields.append(FieldDef(name=field_name, type=card_field_type(card)))
                    known.add(_snake(field_name))

    def record_fields_from(record_node) -> list[tuple[str, str]]:
        out = []
        if record_node.kind == "record":
            for fname, vexpr in record_node.value:
                ftype = "text"
                if vexpr.kind == "num":
                    ftype = "number"
                elif vexpr.kind == "bool":
                    ftype = "bool"
                elif vexpr.kind == "call" and vexpr.value == "Value":
                    ftype = "number"
                out.append((str(fname), ftype))
        return out

    # Mutations may live in With/IfError/If or App.OnStart, not just a
    # top-level button expression. Decode quoted source names consistently
    # with emission, or the generated server silently has no backing table.
    for expr in behavior_formulas(ir):
        try:
            stmts = lx.parse_formula(expr.raw)
        except lx.FxSyntaxError:
            continue
        for st in (node for root in stmts for node in walk_formula(root)):
            if st.kind != "call" or not st.children:
                continue
            ds_name = scoped_target(expr, st.children[0])
            ds = by_name.get(ds_name)
            if ds is None:
                continue
            if st.value in {"Patch", "Collect", "ClearCollect", "UpdateIf"}:
                records = st.children[2::2] if st.value == 'UpdateIf' else st.children[2:] if st.value == "Patch" else st.children[1:]
                known = known_fields(ds)
                for record in records:
                    for fname, ftype in record_fields_from(record):
                        if _snake(fname) not in known:
                            ds.fields.append(FieldDef(name=fname, type=ftype))
                            known.add(_snake(fname))
                if ds.origin != "collection":
                    # A partial Patch must not discard untouched fields from
                    # embedded rows, even when the export omitted its schema.
                    normalized = known_fields(ds)
                    for row in ds.sample_data:
                        for field, value in row.items():
                            if field not in normalized:
                                kind = "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "text"
                                ds.fields.append(FieldDef(name=field, type=kind))
                                normalized.add(field)
                    # Patch updates by identity, not row position. Form-backed
                    # sources already get this key; standalone Patch needs it too.
                    if not ds.primary_key and "id" not in normalized:
                        ds.fields.insert(0, FieldDef(name="id", type="text"))
            elif st.value in {"Remove", "RemoveIf", "Refresh"} and not ds.fields:
                ds.fields.append(FieldDef(name="id", type="number"))

    # dotted data-source refs from value formulas (Tasks.Status etc.)
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            for expr in ctrl.properties.values():
                try:
                    toks = lx.tokenize(expr.raw)
                except lx.FxSyntaxError:
                    continue
                for tok in toks:
                    if tok.kind == "ident" and "." in tok.value:
                        ds_name, field_name = tok.value.split(".", 1)
                        ds = by_name.get(ds_name)
                        if ds is not None and field_name and _snake(field_name) not in known_fields(ds):
                            ds.fields.append(FieldDef(name=field_name, type="text"))


def verdict_for_property(prop: FxExpr, control_names: set[str], row_fields: set[str]) -> SupportEntry:
    if prop.js is not None:
        status = "full"
        detail = ""
    else:
        status = "stubbed"
        detail = f"could not transpile: {prop.raw}"
    return SupportEntry(subject=prop.raw[:80], status=status, detail=detail)


def analyze(ir: AppIR, uncovered: list[dict] | None = None, solution=None) -> AppIR:
    ir.global_vars = collect_global_vars(ir)
    collisions = {name.casefold() for name in ir.global_vars}
    collisions.update(ds.name.casefold() for ds in ir.data_sources)
    collisions.update(s.name.casefold() for s in ir.screens)
    collisions.update(c.name.casefold() for s in ir.screens for c in s.walk_controls())
    conflicting = [name for name in ir.named_formulas if name.casefold() in collisions]
    if conflicting:
        ir.named_formula_error = 'Named formulas conflict with app symbols: ' + ', '.join(conflicting)
    infer_local_collections(ir)
    infer_data_source_fields(ir)
    from .collection_contracts import infer_collection_contracts
    infer_collection_contracts(ir)
    from .views import resolve_views
    resolve_views(ir, solution)

    control_names = {c.name for s in ir.screens for c in s.walk_controls()}
    control_screens = {c.name: s.name for s in ir.screens for c in s.walk_controls()}
    collect_context_vars(ir, control_screens)
    screen_names = {s.name for s in ir.screens}
    row_fields = collect_row_fields(ir)
    collections = {ds.name for ds in ir.data_sources if ds.origin == "collection"}
    from .relationships import relationship_contracts
    relationship_keys = {key for contract in relationship_contracts(ir).values() for key in contract['navigation']}
    from .services import service_contracts
    adapters = service_contracts(ir)

    def convert_formula(expr: FxExpr, row_alias: str | None = None, screen_name: str | None = None) -> None:
        if not expr.raw:
            return
        try:
            res = transpile(expr.raw, behavior=(expr.kind == "behavior"),
                            row_fields=row_fields, control_names=set(expr.control_aliases.values()) if expr.component_private else control_names,
                            collections=collections, screen_names=set() if expr.component_private else screen_names,
                            global_names=set(ir.global_vars) | {ds.name for ds in ir.data_sources} | set(ir.named_formulas),
                            media_resources=ir.media_resources, row_alias=row_alias,
                            screen_name=None if expr.component_owner else screen_name, control_screens=control_screens, view_sets=ir.view_sets,
                            relationship_keys=relationship_keys,
                            service_adapters=adapters, power_fx_v1=ir.power_fx_v1,
                            named_formulas=set(ir.named_formulas), control_aliases=expr.control_aliases,
                            component_owner=expr.component_owner, component_private=expr.component_private)
            expr.js = res.js
            expr.translation_status = "stubbed" if res.unmapped else "rule"
            expr.blocked_dependencies = [name for name in res.unmapped if name.startswith('Dataverse view')]
            expr.approximations = sorted(set(res.approximations))
            if expr.blocked_dependencies:
                expr.fidelity_note = '; '.join(expr.blocked_dependencies)
            if res.unmapped:
                for fn in res.unmapped:
                    ir.support_matrix.append(SupportEntry(
                        subject=f"function {fn}()", status="unmapped",
                        detail=f"in formula: {expr.raw[:60]}",
                    ))
        except Exception as exc:  # TranspileError or unexpected
            expr.js = None
            expr.translation_status = "stubbed"
            if 'Named formula is read-only' in str(exc):
                expr.blocked_dependencies = [str(exc)]
                expr.fidelity_note = str(exc)
            ir.support_matrix.append(SupportEntry(
                subject=expr.raw[:80], status="stubbed",
                detail=f"transpile failed: {exc}",
            ))

    if ir.on_start:
        convert_formula(ir.on_start)
    for name, expr in ir.properties.items():
        if name != 'Formulas':
            convert_formula(expr)
        elif ir.named_formula_error:
            expr.translation_status = 'stubbed'
            expr.blocked_dependencies = [ir.named_formula_error]
            expr.fidelity_note = ir.named_formula_error
    from .named_formulas import validate_value
    for name, expr in ir.named_formulas.items():
        try:
            validate_value(expr.raw)
        except lx.FxSyntaxError as exc:
            expr.translation_status = 'stubbed'
            expr.blocked_dependencies = [str(exc)]
            expr.fidelity_note = str(exc)
            continue
        convert_formula(expr)
        if expr.js and 'await ' in expr.js:
            from .validate import js_syntax_ok
            # Literal text containing "await " is still a synchronous value.
            if not js_syntax_ok('(\n' + expr.js + '\n)')[0]:
                expr.js = None
                expr.translation_status = 'stubbed'
                expr.blocked_dependencies = ['Asynchronous named formula is unsupported']
                expr.fidelity_note = expr.blocked_dependencies[0]

    def convert_control(ctrl: ControlNode, row_alias: str | None = None, screen_name: str | None = None) -> None:
        child_alias = row_alias
        if ctrl.type in {"Gallery", "DataTable"}:
            child_alias = None
            items = ctrl.properties.get("Items")
            if items:
                try:
                    roots = lx.parse_formula(items.raw)
                    if len(roots) == 1 and roots[0].kind == "alias":
                        child_alias = str(roots[0].value)
                except lx.FxSyntaxError:
                    pass  # the normal formula conversion records the failure
        for name, prop in ctrl.properties.items():
            # Gallery OnSelect runs with its selected row; other gallery
            # properties (including Items) run outside that row's scope.
            alias = child_alias if ctrl.type == "Gallery" and name == "OnSelect" else row_alias
            convert_formula(prop, alias, screen_name)
            if (ctrl.type == 'FluentDatePicker' and name == 'Value') or (ctrl.type == 'DatePicker' and name == 'DefaultDate'):
                prop.approximations.append('Date picker uses the browser calendar and local midnight; source timezone settings, custom calendar formatting and exact Fluent appearance require review')
        for child in ctrl.children:
            convert_control(child, child_alias, screen_name)

    for screen in ir.screens:
        if screen.on_visible:
            convert_formula(screen.on_visible, screen_name=screen.name)
        for expr in screen.properties.values():
            convert_formula(expr, screen_name=screen.name)
        for ctrl in screen.controls:
            convert_control(ctrl, screen_name=screen.name)

    # Collect Choices('DS'.Field) references for the generated Choices table.
    choice_refs: set[str] = set()

    def find_choices(expr: FxExpr | None) -> None:
        if not expr or not expr.raw:
            return
        for m in re.finditer(r"Choices\(\s*'([^'.]+)'\s*\.\s*([^')]+?)\s*\)", expr.raw):
            choice_refs.add(f"{m.group(1)}.{m.group(2)}")

    find_choices(ir.on_start)
    for expr in ir.named_formulas.values():
        find_choices(expr)
    for screen in ir.screens:
        find_choices(screen.on_visible)
        for ctrl in screen.walk_controls():
            for prop in ctrl.properties.values():
                find_choices(prop)
    ir.choice_fields = sorted(choice_refs)

    return ir
