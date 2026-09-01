"""Stage 2: parse unpacked pa.yaml sources into the AppIR."""
from __future__ import annotations

from .ir import AppIR, ControlNode, DataSource, FxExpr, ScreenNode
from .unpack import UnpackedApp

BEHAVIOR_PROPS = {"OnSelect", "OnChange", "OnVisible", "OnHidden", "OnStart", "OnSuccess", "OnFailure"}

# Control types that can hold child item templates in a gallery.
GALLERY_TYPES = {"Gallery", "VerticalGallery", "HorizontalGallery", "GalleryTemplate"}


def _make_expr(prop_value: str, prop_name: str) -> FxExpr:
    raw = str(prop_value).strip()
    if raw.startswith("="):
        raw = raw[1:].strip()
    kind = "behavior" if prop_name in BEHAVIOR_PROPS else "value"
    return FxExpr(raw=raw, kind=kind)


def _parse_control(name: str, node: dict) -> ControlNode:
    node = node if isinstance(node, dict) else {}
    ctrl_type = str(node.get("Control", "Unknown"))
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
                       properties=fx_props, children=children)


def _controls_of(screen_yaml: dict) -> list[ControlNode]:
    if not screen_yaml:
        return []
    screen_name, screen_node = next(iter(screen_yaml.items()))
    screen_node = screen_node if isinstance(screen_node, dict) else {}
    controls: list[ControlNode] = []
    for child in screen_node.get("Children") or []:
        if isinstance(child, dict):
            for cname, cnode in child.items():
                controls.append(_parse_control(str(cname), cnode))
    return controls


def _screen_on_visible(screen_yaml: dict) -> FxExpr | None:
    if not screen_yaml:
        return None
    _, screen_node = next(iter(screen_yaml.items()))
    props = (screen_node or {}).get("Properties") or {}
    ov = props.get("OnVisible")
    return _make_expr(str(ov), "OnVisible") if ov else None


def parse(unpacked: UnpackedApp) -> AppIR:
    ir = AppIR(name=unpacked.app_name)

    # App-level OnStart
    app_props = ((unpacked.app_yaml or {}).get("App") or {}).get("Properties") or {}
    if app_props.get("OnStart"):
        ir.global_vars  # (analysis happens in analyze.py; kept for IR completeness)

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
        origin = "sharepoint" if "sharepoint" in str(ds.get("DataSourceInfo", "")).lower() else "other"
        ir.data_sources.append(DataSource(name=str(ds.get("Name", "DataSource")), origin=origin))
    return ir
