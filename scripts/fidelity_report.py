"""Measure conversion fidelity across sample apps.

Usage: uv run python scripts/fidelity_report.py [glob or dir]
Prints a gap analysis: control types, properties, and functions found in the
input vs what the converter actually handles.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

from pfx2gas.analyze import analyze
from pfx2gas.fx import transpile
from pfx2gas.fx.emitter import LAMBDA_FNS  # noqa: F401
from pfx2gas.fx.function_map import FUNCTION_MAP
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack

# What synthesis actually consumes today
HANDLED_PROPS = {
    "X", "Y", "Width", "Height", "ZIndex",                       # static position
    "Text", "Default", "Items", "Visible",                        # content/behavior
    "OnSelect", "OnChange", "OnVisible", "OnHidden", "OnStart",   # behavior
    "Fill", "Color", "FontColor", "Size", "FontSize",             # reactive style
    # auto-layout (flexbox) + cosmetics
    "LayoutDirection", "LayoutAlignItems", "LayoutJustifyContent", "LayoutWrap",
    "LayoutGap", "LayoutMinWidth", "LayoutMinHeight", "FillPortions",
    "PaddingLeft", "PaddingRight", "PaddingTop", "PaddingBottom",
    "RadiusTopLeft", "RadiusTopRight", "RadiusBottomLeft", "RadiusBottomRight",
    "BorderColor", "BorderThickness", "DropShadow",
    "Font", "Weight", "Align", "VerticalAlign",
    "HoverFill", "HoverColor", "HoverBorderColor",
    "PressedFill", "PressedColor", "PressedBorderColor", "DisabledFill",
    "Image", "Icon", "Content", "HtmlText",   # static content attributes
}
KNOWN_CTRL_TYPES = {"Button", "Label", "TextInput", "TextArea", "Dropdown",
                    "ComboBox", "CheckBox", "DatePicker", "Gallery", "Image",
                    "Icon", "HtmlText", "Form", "Screen", "AppHost",
                    "GroupContainer", "VerticalContainer", "HorizontalContainer",
                    "Header", "Timer", "Text", "DropDown", "Rectangle", "Chart",
                    "Legend", "InfoButton", "DataCard", "DataTable",
                    "GalleryTemplate", "Slider", "CanvasComponent"}

SPECIAL_FNS = {"Set", "UpdateContext", "Navigate", "Back", "Patch", "Remove",
               "RemoveIf", "Collect", "ClearCollect", "Refresh", "SubmitForm",
               "Reset", "Notify", "Select", "Launch", "NewForm", "EditForm",
               "ViewForm", "Defaults"}


def props_handled(prop: str) -> bool:
    style_props = {"Fill", "Color", "Size", "FontSize", "FontWeight", "Align"}
    return prop in HANDLED_PROPS or prop in style_props


def main(paths: list[Path]) -> None:
    ctrl_counts: collections.Counter = collections.Counter()
    prop_counts: collections.Counter = collections.Counter()
    fn_unmapped: collections.Counter = collections.Counter()
    formula_total = 0
    formula_ok = 0
    screens_by_app: dict[str, list[str]] = {}

    for path in paths:
        app = unpack(path)
        ir = analyze(parse(app))
        screens_by_app[app.app_name] = [s.name for s in ir.screens]
        for screen in ir.screens:
            for ctrl in screen.walk_controls():
                ctrl_counts[ctrl.type] += 1
                for pname, expr in ctrl.properties.items():
                    prop_counts[pname] += 1
                    if not expr.raw:
                        continue
                    formula_total += 1
                    try:
                        res = transpile(expr.raw, behavior=(expr.kind == "behavior"))
                    except Exception:
                        continue
                    if res.js and "FX.unsupported" not in res.js and not res.unmapped:
                        formula_ok += 1
                    for fn in res.unmapped:
                        fn_unmapped[fn] += 1

    total_ctrls = sum(ctrl_counts.values())
    unknown_ctrls = {t: n for t, n in ctrl_counts.items() if t not in KNOWN_CTRL_TYPES}
    ignored_props = [(p, n) for p, n in prop_counts.most_common() if not props_handled(p)]
    ignored_total = sum(n for _, n in ignored_props)
    prop_total = sum(prop_counts.values())
    fn_total = sum(fn_unmapped.values())

    print("# Fidelity report (sample corpus)\n")
    print("## Screens parsed (check for mis-parsed components)\n")
    for name, screens in screens_by_app.items():
        print(f"- **{name}**: {', '.join(screens)}")

    print(f"\n## Formulas: {formula_ok}/{formula_total} fully transpiled "
          f"({100 * formula_ok / max(formula_total, 1):.1f}%)\n")
    if fn_unmapped:
        print("Unmapped functions (call sites):")
        for fn, n in fn_unmapped.most_common(15):
            print(f"- {fn}() x{n}")

    print(f"\n## Control types: {total_ctrls} total")
    print("\nHandled:")
    for t, n in ctrl_counts.most_common():
        if t in KNOWN_CTRL_TYPES:
            print(f"- {t} x{n}")
    print("\nNOT modeled (fall back to generic <div>):")
    for t, n in ctrl_counts.most_common():
        if t not in KNOWN_CTRL_TYPES:
            print(f"- {t} x{n}")

    print(f"\n## Properties: {prop_total} instances; "
          f"{ignored_total} ignored ({100 * ignored_total / max(prop_total, 1):.1f}%)\n")
    print("Most frequent ignored properties (visual/behavioral parity losses):")
    for p, n in ignored_props[:25]:
        print(f"- {p} x{n}")

    print(f"\n## Function coverage: {len(FUNCTION_MAP) + len(SPECIAL_FNS)} mapped, "
          f"{len(fn_unmapped)} distinct unmapped in corpus")


if __name__ == "__main__":
    args = sys.argv[1:]
    base = Path(args[0]) if args else Path("samples/real")
    files = sorted(base.glob("*.msapp")) if base.is_dir() else [base]
    main(files)
