"""Measure conversion fidelity across sample apps.

Run inside the project container with an optional sample directory or `.msapp`.
Prints a gap analysis: control types, properties, and functions found in the
input vs what the converter actually handles.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

from pfx2gas.analyze import analyze
from pfx2gas.fidelity import iter_expressions
from pfx2gas.fx.function_map import FUNCTION_MAP
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack
from pfx2gas.synth.build import assess_fidelity

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
def main(paths: list[Path]) -> None:
    ctrl_counts: collections.Counter = collections.Counter()
    prop_counts: collections.Counter = collections.Counter()
    ignored_props: collections.Counter = collections.Counter()
    fn_unmapped: collections.Counter = collections.Counter()
    formula_total = 0
    formula_translated = 0
    formula_emitted = 0
    formula_partial = 0
    screens_by_app: dict[str, list[str]] = {}

    for path in paths:
        app = unpack(path)
        ir = assess_fidelity(analyze(parse(app)))
        screens_by_app[app.app_name] = [s.name for s in ir.screens]
        for screen in ir.screens:
            for ctrl in screen.walk_controls():
                ctrl_counts[ctrl.type] += 1
                for pname, expr in ctrl.properties.items():
                    prop_counts[pname] += 1
        for _screen, _control, pname, expr in iter_expressions(ir):
            formula_total += 1
            if expr.translation_status in {"rule", "llm"}:
                formula_translated += 1
            if expr.emission_status == "emitted":
                formula_emitted += 1
            elif expr.emission_status == "approximated":
                formula_partial += 1
            if expr.emission_status in {"ignored", "unsupported"}:
                ignored_props[pname] += 1
        for entry in ir.support_matrix:
            if entry.status == "unmapped" and entry.subject.startswith("function "):
                fn_unmapped[entry.subject.removeprefix("function ").removesuffix("()") ] += 1

    total_ctrls = sum(ctrl_counts.values())
    ignored_rows = ignored_props.most_common()
    ignored_total = sum(ignored_props.values())
    prop_total = sum(prop_counts.values())
    print("# Fidelity report (sample corpus)\n")
    print("## Screens parsed (check for mis-parsed components)\n")
    for name, screens in screens_by_app.items():
        print(f"- **{name}**: {', '.join(screens)}")

    print(f"\n## Formula translation: {formula_translated}/{formula_total} translated "
          f"({100 * formula_translated / max(formula_total, 1):.1f}%)")
    print(f"## Runtime wiring: {formula_emitted}/{formula_total} emitted "
          f"({100 * formula_emitted / max(formula_total, 1):.1f}%); "
          f"{formula_partial} approximated\n")
    if fn_unmapped:
        print("Unmapped functions (call sites):")
        for fn, n in fn_unmapped.most_common(15):
            print(f"- {fn}() x{n}")

    print(f"\n## Control types: {total_ctrls} total")
    print("\nRecognized control types:")
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
    for p, n in ignored_rows[:25]:
        print(f"- {p} x{n}")

    print(f"\n## Function coverage: {len(FUNCTION_MAP) + len(SPECIAL_FNS)} mapped, "
          f"{len(fn_unmapped)} distinct unmapped in corpus")


if __name__ == "__main__":
    args = sys.argv[1:]
    base = Path(args[0]) if args else Path("samples/real")
    files = sorted(base.glob("*.msapp")) if base.is_dir() else [base]
    main(files)
