"""Legacy .msapp adapter: binary-JSON format (Controls/*.json, pre-YAML).

Older Studio exports carry no src/*.pa.yaml sources; instead each
``Controls\\N.json`` file holds one top-parent control tree whose ``Rules``
array carries ``{Property, InvariantScript}`` pairs (the Power Fx). This
module converts that shape into the same dict structure the pa.yaml parser
expects, so the rest of the pipeline is format-agnostic.
"""
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
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
    "piechart": "PieChart",
    "barchart": "BarChart",
    "columnchart": "ColumnChart",
    "linechart": "LineChart",
    "legend": "Legend",
    "infobutton": "InfoButton",
    "typeddatacard": "DataCard",
    "datacard": "DataCard",
    "fluidgrid": "FluidGrid",
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
            return "TextArea" if mode.removeprefix('=').strip() == "TextMode.MultiLine" else "TextInput"
    return base


def _rewrite_formula(script: str, names: dict[str, str] | None) -> str:
    """Namespace control references inside an instantiated component tree."""
    if not names:
        return script
    rewritten = script
    for old, new in sorted(names.items(), key=lambda item: len(item[0]), reverse=True):
        rewritten = re.sub(
            # A component child can have the same name as a custom property
            # (MENU.link1). Only namespace identifiers in reference position;
            # never rewrite a member/property token after a dot.
            rf"(?<![A-Za-z0-9_.]){re.escape(old)}(?![A-Za-z0-9_])",
            new,
            rewritten,
        )
    return rewritten


def _rules_to_properties(rules: list, names: dict[str, str] | None = None) -> dict[str, str]:
    props: dict[str, str] = {}
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        prop = rule.get("Property")
        script = rule.get("InvariantScript")
        if prop and isinstance(script, str):
            script = _rewrite_formula(script, names)
            value = script if script.startswith("=") else f"={script}"
            props[prop] = value
    return props


def _descendant_names(node: dict) -> list[str]:
    names: list[str] = []
    for child in node.get("Children") or []:
        if not isinstance(child, dict):
            continue
        if child.get("Name"):
            names.append(str(child["Name"]))
        names.extend(_descendant_names(child))
    return names


def _component_definitions(zf: zipfile.ZipFile, names: list[str]) -> dict[str, dict]:
    """Load legacy Components/*.json definitions keyed by template GUID."""
    display_names: dict[str, str] = {}
    metadata_name = next(
        (n for n in names if n.lower().replace("\\", "/") == "componentsmetadata.json"),
        None,
    )
    if metadata_name:
        try:
            metadata = json.loads(zf.read(metadata_name))
            for entry in metadata.get("Components", []):
                if isinstance(entry, dict) and entry.get("TemplateName"):
                    display_names[str(entry["TemplateName"])] = str(entry.get("Name") or "")
        except (json.JSONDecodeError, AttributeError):
            pass

    definitions: dict[str, dict] = {}
    for archive_name in names:
        normalized = archive_name.lower().replace("\\", "/")
        if not (normalized.startswith("components/") and normalized.endswith(".json")):
            continue
        try:
            top = json.loads(zf.read(archive_name)).get("TopParent")
        except (json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(top, dict):
            continue
        template = top.get("Template") or {}
        template_name = str(template.get("Name") or "")
        if not template_name:
            continue
        definitions[template_name] = {
            "name": display_names.get(template_name) or str(top.get("Name") or template_name),
            "root": top,
        }
    return definitions


def _primary_outputs(zf: zipfile.ZipFile, names: list[str]) -> dict[tuple[str, str], str]:
    """Read each exact exported template version's primary output contract."""
    outputs = {}
    for name in names:
        if name.lower().replace("\\", "/") != "references/templates.json":
            continue
        doc = json.loads(zf.read(name))
        for template in doc.get("UsedTemplates", []):
            raw = template.get("Template", "")
            if not raw or "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                continue
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            props = {node.get("name") for node in root.iter()
                     if any(key.lower() == "isprimaryoutputproperty" and value.lower() == "true"
                            for key, value in node.attrib.items())}
            props.discard(None)
            # Conflicting template declarations require review; never guess
            # which of several outputs is the source control's default.
            if len(props) == 1:
                outputs[(template.get("Name", ""), template.get("Version", ""))] = props.pop()
    return outputs


def _control_to_yaml(
    node: dict,
    component_defs: dict[str, dict] | None = None,
    names: dict[str, str] | None = None,
    parent_name: str | None = None,
    primary_outputs: dict[tuple[str, str], str] | None = None,
) -> dict:
    """Legacy control node -> pa.yaml-style control mapping."""
    template = node.get("Template") if isinstance(node.get("Template"), dict) else {}
    template_name = str(template.get("Name") or "")
    component = (component_defs or {}).get(template_name)
    if component and not template.get("IsComponentDefinition"):
        definition = component["root"]
        instance_name = str(node.get("Name") or component["name"])
        name_map = {str(definition.get("Name") or component["name"]): instance_name}
        for child_name in _descendant_names(definition):
            name_map[child_name] = f"{instance_name}__{child_name}"

        # Definitions provide defaults; instance rules override them.
        root_names = dict(name_map)
        root_names["Self"] = instance_name
        props = _rules_to_properties(definition.get("Rules") or [], root_names)
        props.update(_rules_to_properties(node.get("Rules") or [], root_names))
        custom = template.get("CustomProperties") or (
            (definition.get("Template") or {}).get("CustomProperties") or []
        )
        out: dict = {
            "Control": "CanvasComponent",
            "ComponentTemplate": component["name"],
            "ComponentInputs": [str(p["Name"]) for p in custom
                                if isinstance(p, dict) and p.get("Name")],
            "Properties": props,
        }
        children = [c for c in (definition.get("Children") or []) if isinstance(c, dict)]
        if children:
            out["Children"] = [
                {name_map.get(str(c.get("Name") or f"Control{i}"), str(c.get("Name") or f"Control{i}")):
                 _control_to_yaml(c, component_defs, name_map, instance_name, primary_outputs)}
                for i, c in enumerate(children)
            ]
        return out

    original_name = str(node.get("Name") or "")
    rendered_name = (names or {}).get(original_name, original_name)
    formula_names = dict(names or {})
    if names:
        formula_names["Self"] = rendered_name
        if parent_name:
            formula_names["Parent"] = parent_name
    out: dict = {
        "Control": _normalize_template_for(node),
        "Properties": _rules_to_properties(node.get("Rules"), formula_names),
    }
    primary = (primary_outputs or {}).get((template_name, template.get("Version", "")))
    if primary:
        out["PrimaryOutput"] = primary
    variant = node.get("VariantName")
    if variant:
        out["Variant"] = variant
    children = [c for c in (node.get("Children") or []) if isinstance(c, dict)]
    if children:
        out["Children"] = [{(names or {}).get(str(c.get("Name", f"Control{i}")),
                                             str(c.get("Name", f"Control{i}"))):
                            _control_to_yaml(c, component_defs, names, rendered_name, primary_outputs)}
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
    return decode_reference_sources(raw)


def decode_reference_sources(raw: str | bytes) -> list[dict]:
    """The exported References/DataSources contract is shared by both layouts."""
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
        # Keep the exported contract for parse(), including nested Dataverse
        # definitions and option-set mappings. Only sample rows are normalized.
        entry: dict = dict(ds, IsCollection=is_collection)
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
        component_defs = _component_definitions(zf, names)
        primary_outputs = _primary_outputs(zf, names)
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
                screens[name] = {"Screens": {name: _control_to_yaml(top, component_defs, primary_outputs=primary_outputs)}}
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
