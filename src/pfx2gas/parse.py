"""Stage 2: parse unpacked pa.yaml sources into the AppIR."""
from __future__ import annotations

from .fx.naming import snake as _snake
from .ir import AppIR, ControlNode, DataSource, FieldDef, FxExpr, ScreenNode
from .unpack import UnpackedApp

BEHAVIOR_PROPS = {"OnSelect", "OnChange", "OnVisible", "OnHidden", "OnStart", "OnSuccess", "OnFailure",
                  "OnTimerStart", "OnTimerEnd"}

# Control types that can hold child item templates in a gallery.
GALLERY_TYPES = {"Gallery", "VerticalGallery", "HorizontalGallery", "GalleryTemplate"}


def _make_expr(prop_value: str, prop_name: str) -> FxExpr:
    raw = str(prop_value).strip()
    if raw.startswith("="):
        raw = raw[1:].strip()
    kind = "behavior" if prop_name in BEHAVIOR_PROPS else "value"
    return FxExpr(raw=raw, kind=kind)


# Modern control names normalize onto classic equivalents (case-insensitive).
_CONTROL_ALIASES = {
    "dropdown": "Dropdown",
    "text": "Label",          # modern 'Text' control is a text block
    "textlabel": "Label",
    "badge": "Label",
    "moderncard": "GroupContainer",
    "dropdowndatafield": "Dropdown",
    "moderntablecontrol": "DataTable",
}


def _control_type(raw: object) -> str:
    """Normalize 'Classic/TextInput@2.3.2' -> 'TextInput', 'Label@2.5.1' -> 'Label'."""
    s = str(raw or "Unknown")
    if "/" in s:
        s = s.split("/")[-1]
    if "@" in s:
        s = s.split("@")[0]
    return _CONTROL_ALIASES.get(s.lower(), s)


def _parse_control(name: str, node: dict) -> ControlNode:
    node = node if isinstance(node, dict) else {}
    ctrl_type = _control_type(node.get("Control"))
    variant = node.get("Variant")
    props = node.get("Properties") or {}
    fx_props: dict[str, FxExpr] = {}
    for prop_name, value in props.items():
        if value is None:
            continue
        # Positional/size properties stay literal; everything else is Power Fx text.
        if isinstance(value, (int, float)) and prop_name in {"X", "Y", "Width", "Height", "ZIndex"}:
            fx_props[prop_name] = FxExpr(raw=str(value), kind="value", js=str(value))
            continue
        fx_props[prop_name] = _make_expr(str(value), prop_name)

    children: list[ControlNode] = []
    for child in node.get("Children") or []:
        if not isinstance(child, dict):
            continue
        for child_name, child_node in child.items():
            children.append(_parse_control(str(child_name), child_node))
    return ControlNode(name=name, type=ctrl_type, variant=variant if isinstance(variant, str) else None,
                       component_template=(str(node["ComponentTemplate"])
                                           if node.get("ComponentTemplate") else None),
                       component_inputs=[str(p) for p in node.get("ComponentInputs", [])],
                       properties=fx_props, children=children)


def _screen_entries(screen_yaml: dict) -> list[tuple[str, dict]]:
    """Yield (screen_name, screen_node) pairs from one pa.yaml document.

    Real Studio exports wrap screens in a top-level ``Screens:`` mapping;
    older/packed layouts put the screen name at the document root.
    """
    if not screen_yaml:
        return []
    if isinstance(screen_yaml.get("Screens"), dict):
        return [(str(name), node if isinstance(node, dict) else {})
                for name, node in screen_yaml["Screens"].items()]
    name, node = next(iter(screen_yaml.items()))
    return [(str(name), node if isinstance(node, dict) else {})]


def _controls_of(screen_yaml: dict) -> list[ControlNode]:
    controls: list[ControlNode] = []
    for _, screen_node in _screen_entries(screen_yaml):
        for child in screen_node.get("Children") or []:
            if isinstance(child, dict):
                for cname, cnode in child.items():
                    controls.append(_parse_control(str(cname), cnode))
    return controls


def _screen_on_visible(screen_yaml: dict) -> FxExpr | None:
    for _, screen_node in _screen_entries(screen_yaml):
        props = (screen_node or {}).get("Properties") or {}
        ov = props.get("OnVisible")
        if ov:
            return _make_expr(str(ov), "OnVisible")
    return None


def _origin_of(ds: dict) -> str:
    """Best-effort origin classification from legacy source metadata."""
    info = str(ds.get("DataSourceInfo", "")).lower()
    if "sharepoint" in info:
        return "sharepoint"
    if "excel" in info or "onedrive" in info:
        return "excel"
    if "dataverse" in info or "crm" in info:
        return "dataverse"
    if str(ds.get("Type", "")).lower() == "staticdatasourceinfo":
        return "static"
    return "other"


def parse(unpacked: UnpackedApp) -> AppIR:
    ir = AppIR(
        name=unpacked.app_name,
        warnings=list(unpacked.warnings),
        media_resources=dict(unpacked.media_resources),
    )

    # App-level OnStart
    app_props = ((unpacked.app_yaml or {}).get("App") or {}).get("Properties") or {}
    if app_props.get("OnStart"):
        ir.on_start = _make_expr(str(app_props["OnStart"]), "OnStart")

    for screen_name in sorted(unpacked.screens):
        screen_yaml = unpacked.screens[screen_name]
        ir.screens.append(
            ScreenNode(
                name=screen_name,
                on_visible=_screen_on_visible(screen_yaml),
                controls=_controls_of(screen_yaml),
            )
        )

    for ds in unpacked.data_sources:
        # Sources arriving via the modern unpacker carry explicit markers;
        # the legacy adapter sets IsCollection itself. Anything else that is
        # not a declared collection is treated as an external table.
        is_collection = bool(ds.get("IsCollection")) or "collection" in str(ds.get("Type", "")).lower()
        origin = "collection" if is_collection else _origin_of(ds)
        fields = [FieldDef(name=f.get("name", ""), type=f.get("type", "text"))
                  for f in ds.get("Fields", []) if f.get("name")]
        sample = ds.get("SampleData") if isinstance(ds.get("SampleData"), list) else []
        sample = [{_snake(str(k)): v for k, v in row.items()} if isinstance(row, dict) else row
                  for row in sample]
        source = DataSource(name=str(ds.get("Name", "DataSource")), origin=origin,
                            fields=fields, sample_data=sample)
        from .data_contract import apply_source_contract
        apply_source_contract(source, ds)
        ir.data_sources.append(source)

    # Power Apps shows the first screen in screen order; reproduce that.
    ir.screens.sort(key=lambda s: unpacked.screen_order.index(s.name)
                    if s.name in unpacked.screen_order else len(unpacked.screen_order))
    if ir.screens:
        ir.start_screen = ir.screens[0].name
    return ir
