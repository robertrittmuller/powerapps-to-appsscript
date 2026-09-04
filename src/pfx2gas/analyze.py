"""Stage 3: derive global vars, data-source fields, and per-control verdicts."""
from __future__ import annotations

import re

from .fx import lexer as lx
from .fx import transpile
from .fx.emitter import LAMBDA_FNS
from .ir import AppIR, ControlNode, FieldDef, FxExpr, SupportEntry

BEHAVIOR = {"OnSelect", "OnChange", "OnVisible", "OnHidden", "OnStart", "OnSuccess", "OnFailure"}
NON_LOGIC_PROPS = {"X", "Y", "Width", "Height", "ZIndex", "Text", "Default", "Items",
                   "Visible", "Fill", "Color", "FontSize", "FontWeight", "Align",
                   "AccessibleLabel", "Tooltip", "Placeholder", "ItemsOrder"}


def collect_global_vars(ir: AppIR) -> list[str]:
    """All identifiers assigned via Set/UpdateContext/Collect in behavior formulas."""
    names: set[str] = set()
    targets: list[str] = []

    def add_from(formula: FxExpr) -> None:
        if not formula.raw:
            return
        try:
            stmts = lx.parse_formula(formula.raw)
        except lx.FxSyntaxError:
            return
        for st in stmts:
            if st.kind == "call" and st.value == "UpdateContext" and st.children:
                record = st.children[0]
                if record.kind == "record":
                    names.update(str(name) for name, _value in record.value)
            elif st.kind == "call" and st.value in {"Set", "Collect", "ClearCollect"}:
                t = st.children[0] if st.children else None
                if t is not None and t.kind == "ident":
                    names.add(str(t.value))

    if ir.on_start:
        add_from(ir.on_start)
    for screen in ir.screens:
        if screen.on_visible:
            add_from(screen.on_visible)
        for ctrl in screen.walk_controls():
            for prop in ctrl.properties.values():
                if prop.kind == "behavior":
                    add_from(prop)
    return sorted(names)


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
    """Infer field names/types for each data source from Patch/Collect and dotted refs."""
    by_name = {ds.name: ds for ds in ir.data_sources}

    def record_fields_from(record_node) -> list[str]:
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

    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            for expr in ctrl.properties.values():
                if expr.kind != "behavior":
                    continue
                try:
                    stmts = lx.parse_formula(expr.raw)
                except lx.FxSyntaxError:
                    continue
                for st in stmts:
                    if st.kind != "call" or not st.children:
                        continue
                    if st.value in {"Patch", "Collect", "ClearCollect"} and st.children[0].kind == "ident":
                        ds_name = str(st.children[0].value)
                        rec = st.children[-1] if st.value == "Patch" else (st.children[1] if len(st.children) > 1 else None)
                        ds = by_name.get(ds_name)
                        if ds is not None and rec is not None:
                            known = {f.name for f in ds.fields}
                            for fname, ftype in record_fields_from(rec):
                                if fname not in known:
                                    ds.fields.append(FieldDef(name=fname, type=ftype))
                                    known.add(fname)
                    elif st.value in {"Remove", "RemoveIf", "Refresh"} and st.children[0].kind == "ident":
                        ds_name = str(st.children[0].value)
                        if ds_name in by_name and not by_name[ds_name].fields:
                            by_name[ds_name].fields.append(FieldDef(name="id", type="number"))

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
                        if ds is not None and field_name and all(f.name != field_name for f in ds.fields):
                            ds.fields.append(FieldDef(name=field_name, type="text"))


def verdict_for_property(prop: FxExpr, control_names: set[str], row_fields: set[str]) -> SupportEntry:
    if prop.js is not None:
        status = "full"
        detail = ""
    else:
        status = "stubbed"
        detail = f"could not transpile: {prop.raw}"
    return SupportEntry(subject=prop.raw[:80], status=status, detail=detail)


def analyze(ir: AppIR, uncovered: list[dict] | None = None) -> AppIR:
    ir.global_vars = collect_global_vars(ir)
    infer_data_source_fields(ir)

    control_names = {c.name for s in ir.screens for c in s.walk_controls()}
    screen_names = {s.name for s in ir.screens}
    row_fields = collect_row_fields(ir)
    collections = {ds.name for ds in ir.data_sources if ds.origin == "collection"}

    def convert_formula(expr: FxExpr) -> None:
        if not expr.raw:
            return
        try:
            res = transpile(expr.raw, behavior=(expr.kind == "behavior"),
                            row_fields=row_fields, control_names=control_names,
                            collections=collections, screen_names=screen_names)
            expr.js = res.js
            expr.translation_status = "stubbed" if res.unmapped else "rule"
            if res.unmapped:
                for fn in res.unmapped:
                    ir.support_matrix.append(SupportEntry(
                        subject=f"function {fn}()", status="unmapped",
                        detail=f"in formula: {expr.raw[:60]}",
                    ))
        except Exception as exc:  # TranspileError or unexpected
            expr.js = None
            expr.translation_status = "stubbed"
            ir.support_matrix.append(SupportEntry(
                subject=expr.raw[:80], status="stubbed",
                detail=f"transpile failed: {exc}",
            ))

    if ir.on_start:
        convert_formula(ir.on_start)
    for screen in ir.screens:
        if screen.on_visible:
            convert_formula(screen.on_visible)
        for ctrl in screen.walk_controls():
            for prop in ctrl.properties.values():
                convert_formula(prop)

    # Collect Choices('DS'.Field) references for the generated Choices table.
    choice_refs: set[str] = set()

    def find_choices(expr: FxExpr | None) -> None:
        if not expr or not expr.raw:
            return
        for m in re.finditer(r"Choices\(\s*'([^'.]+)'\s*\.\s*([^')]+?)\s*\)", expr.raw):
            choice_refs.add(f"{m.group(1)}.{m.group(2)}")

    find_choices(ir.on_start)
    for screen in ir.screens:
        find_choices(screen.on_visible)
        for ctrl in screen.walk_controls():
            for prop in ctrl.properties.values():
                find_choices(prop)
    ir.choice_fields = sorted(choice_refs)

    return ir
