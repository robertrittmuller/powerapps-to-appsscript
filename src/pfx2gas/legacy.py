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
    "togglecontrol": "CheckBox",
    "toggleswitch": "CheckBox",
    "datepicker": "DatePicker",
    "datepickercontrol": "DatePicker",
    "gallery": "Gallery",
    "verticalgallery": "Gallery",
    "horizontgallery": "Gallery",
    "gallerytemplate": "GalleryTemplate",
    "image": "Image",
    "imagecontrol": "Image",
    "icon": "Icon",
    "form": "Form",
    "htmltext": "HtmlText",
    "htmlviewer": "HtmlText",
    "groupcontainer": "GroupContainer",
    "container": "GroupContainer",
    "verticalcontainer": "GroupContainer",
    "horizontalcontainer": "GroupContainer",
    "group": "GroupContainer",
    "div": "GroupContainer",
    "rectangle": "Rectangle",
    "rectanglecontrol": "Rectangle",
    "visualizer": "Rectangle",
    "timer": "Timer",
    "slider": "Slider",
    "slidercontrol": "Slider",
    "badge": "Label",
    "header": "Header",
    "chartcontrol": "Chart",
    "piechart": "Chart",
    "barchart": "Chart",
    "linechart": "Chart",
    "legend": "Legend",
    "infobutton": "InfoButton",
    "typeddatacard": "DataCard",
    "datacard": "DataCard",
    "datatable": "DataTable",
    "datatablecolumn": "DataCard",
    "dropdowndatafield": "DataCard",
    # GUID-named component instances/definitions: keep stable, render generic
    "canvascomponent": "CanvasComponent",
}


def _normalize_template(t: dict | str | None) -> str:
    name = t.get("Name", "") if isinstance(t, dict) else str(t or "")
    return TEMPLATE_ALIASES.get(name.lower(), name or "Unknown")


# Properties that only exist on legacy ``text`` controls that are actually
# text inputs. Legacy template names conflate labels and inputs; the
# ``label`` template is the true static text control, so a ``text`` control
# carrying any of these properties is an editable input.
_TEXT_INPUT_PROPS = {"Mode", "Default", "HintText", "Format", "DelayOutput"}


def _normalize_template_for(node: dict) -> str:
    """Template-name normalization with input/label disambiguation.

    Legacy exports use template ``text`` for both static labels and text
    inputs. When input-only properties (Mode/Default/HintText/...) are
    present, the control is a TextInput (single-line) or TextArea
    (``Mode: TextMode.MultiLine``); otherwise it renders as a Label.
    """
    name = node.get("Template", {}).get("Name", "") if isinstance(node.get("Template"), dict) else ""
    base = TEMPLATE_ALIASES.get(name.lower(), name or "Unknown")
    if name.lower() == "text":
        props = _rules_to_properties(node.get("Rules") or [])
        if _TEXT_INPUT_PROPS & props.keys():
            mode = props.get("Mode", "")
            return "TextArea" if "MultiLine" in mode else "TextInput"
    return base


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
        "Control": _normalize_template_for(node),
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

    # Type letters in the schema string: *[Field:s, ...]
    _SCHEMA_TYPES = {"s": "text", "n": "number", "d": "date", "b": "bool", "i": "text", "h": "text"}

    def parse_schema(schema: str | None) -> list[dict]:
        if not schema or not schema.startswith("*[") or not schema.endswith("]"):
            return []
        out = []
        for part in schema[2:-1].split(","):
            if ":" not in part:
                continue
            fname, _, ftype = part.strip().partition(":")
            out.append({"name": fname.strip(),
                        "type": _SCHEMA_TYPES.get(ftype.strip().lower(), "text")})
        return out

    out = []
    for ds in items or []:
        if not (isinstance(ds, dict) and ds.get("Name")):
            continue
        # A Power Apps collection is client-side state, not an external table.
        is_collection = ds.get("Type") == "CollectionDataSourceInfo"
        entry: dict = {"Name": ds["Name"],
                       "Type": ds.get("Type", "LegacyDataSource"),
                       "DataSourceInfo": ds.get("DataSourceInfo", ""),
                       "IsCollection": is_collection}
        if not is_collection:
            entry["Fields"] = parse_schema(ds.get("Schema"))
            sample = ds.get("Data")
            if isinstance(sample, str):
                # the Data payload is a JSON document embedded as a string
                try:
                    sample = json.loads(sample)
                except (json.JSONDecodeError, ValueError):
                    sample = None
            if isinstance(sample, list) and sample:
                entry["SampleData"] = sample
        out.append(entry)
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
        screen_index: list[tuple[int, str]] = []
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
                idx = top.get("Index")
                order = int(idx) if isinstance(idx, (int, float)) else len(screen_index)
                screen_index.append((order, name))
        screen_index.sort()
        screen_order = [name for _, name in screen_index]

        data_sources = _data_sources_from(zf, names)

    if not screens and not app_yaml:
        raise ValueError("legacy archive contained no screens or app rules")
    return {
        "app_name": str(app_name),
        "app_yaml": app_yaml,
        "screens": screens,
        "data_sources": data_sources,
        "screen_order": screen_order,
        "warnings": ["legacy binary-JSON .msapp converted via legacy adapter"],
    }
