"""Legacy .msapp adapter: binary-JSON format (Controls/*.json, pre-YAML).

Older Studio exports carry no src/*.pa.yaml sources; instead each
``Controls\\N.json`` file holds one top-parent control tree whose ``Rules``
array carries ``{Property, InvariantScript}`` pairs (the Power Fx). This
module converts that shape into the same dict structure the pa.yaml parser
expects, so the rest of the pipeline is format-agnostic.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

# Legacy Template.Name -> canonical control type used by the pa.yaml pipeline.
TEMPLATE_ALIASES = {
    "screen": "Screen",
    "app": "AppHost",
    "appinfo": "AppHost",
    "text": "Label",
    "textlabel": "Label",
    "label": "Label",
    "button": "Button",
    "textinput": "TextInput",
    "richtext": "TextArea",
    "textarea": "TextArea",
    "dropdown": "Dropdown",
    "combobox": "ComboBox",
    "checkbox": "CheckBox",
    "toggle": "CheckBox",
    "datepicker": "DatePicker",
    "datepickercontrol": "DatePicker",
    "gallery": "Gallery",
    "verticalgallery": "Gallery",
    "horizontgallery": "Gallery",
    "image": "Image",
    "imagecontrol": "Image",
    "icon": "Icon",
    "form": "Form",
    "htmltext": "HtmlText",
    "groupcontainer": "GroupContainer",
    "container": "GroupContainer",
    "verticalcontainer": "GroupContainer",
    "horizontalcontainer": "GroupContainer",
    "rectangle": "div",
    "timer": "Timer",
    "slider": "Slider",
    "pencontrol": "Unknown",
}


def _normalize_template(t: dict | str | None) -> str:
    name = t.get("Name", "") if isinstance(t, dict) else str(t or "")
    return TEMPLATE_ALIASES.get(name.lower(), name or "Unknown")


def _rules_to_properties(rules: list) -> dict[str, str]:
    props: dict[str, str] = {}
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        prop = rule.get("Property")
        script = rule.get("InvariantScript")
        if prop and isinstance(script, str):
            value = script if script.startswith("=") else f"={script}"
            props[prop] = value
    return props


def _control_to_yaml(node: dict) -> dict:
    """Legacy control node -> pa.yaml-style control mapping."""
    out: dict = {
        "Control": _normalize_template(node.get("Template")),
        "Properties": _rules_to_properties(node.get("Rules")),
    }
    variant = node.get("VariantName")
    if variant:
        out["Variant"] = variant
    children = [c for c in (node.get("Children") or []) if isinstance(c, dict)]
    if children:
        out["Children"] = [{c.get("Name", f"Control{i}"): _control_to_yaml(c)}
                           for i, c in enumerate(children)]
    return out


def _data_sources_from(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    raw = None
    for n in names:
        if n.lower().replace("\\\\", "\\").replace("\\", "/").endswith("references/datasources.json"):
            raw = zf.read(n)
            break
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("DataSources", data) if isinstance(data, dict) else data
    out = []
    for ds in items or []:
        if isinstance(ds, dict) and ds.get("Name"):
            out.append({"Name": ds["Name"],
                        "Type": ds.get("Type", "LegacyDataSource"),
                        "DataSourceInfo": ds.get("DataSourceInfo", "")})
    return out


def convert_legacy_msapp(msapp_path: str | Path) -> dict:
    """Return the UnpackedApp-shaped kwargs for a legacy binary .msapp."""
    path = Path(msapp_path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        control_files = sorted(n for n in names
                               if n.lower().replace("\\", "/").startswith("controls/")
                               and n.lower().endswith(".json"))
        if not control_files:
            raise ValueError("no Controls/*.json entries")

        app_name = path.stem
        for n in names:
            if n.lower().replace("\\", "/").endswith("properties.json"):
                try:
                    app_name = json.loads(zf.read(n)).get("Name") or app_name
                except (json.JSONDecodeError, AttributeError):
                    pass
                break

        app_yaml: dict = {}
        screens: dict[str, dict] = {}
        for n in control_files:
            try:
                doc = json.loads(zf.read(n))
            except json.JSONDecodeError:
                continue
            top = doc.get("TopParent")
            if not isinstance(top, dict):
                continue
            template = str(top.get("Template", {}).get("Name", "")).lower()
            name = str(top.get("Name", "Screen"))
            if template in {"appinfo", "app"}:
                props = _rules_to_properties(top.get("Rules"))
                if props:
                    app_yaml = {"App": {"Control": "AppHost", "Properties": props}}
            elif template == "screen":
                screens[name] = {"Screens": {name: _control_to_yaml(top)}}

        data_sources = _data_sources_from(zf, names)

    if not screens and not app_yaml:
        raise ValueError("legacy archive contained no screens or app rules")
    return {
        "app_name": str(app_name),
        "app_yaml": app_yaml,
        "screens": screens,
        "data_sources": data_sources,
        "warnings": ["legacy binary-JSON .msapp converted via legacy adapter"],
    }
