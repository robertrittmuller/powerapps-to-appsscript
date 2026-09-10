"""Decode exported data contracts without querying the original tenant."""
from __future__ import annotations

import json

from .fx.naming import snake
from .ir import DataSource, FieldDef


NON_TABLE_ORIGINS = {"collection", "option_set", "service", "view"}


def external_tables(sources):
    return [ds for ds in sources if ds.origin not in NON_TABLE_ORIGINS and ds.fields]


def _document(value, label):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid exported {label} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Exported {label} must be an object")
    return value


def _label(value):
    if not isinstance(value, dict):
        return None
    local = value.get("UserLocalizedLabel")
    if isinstance(local, dict) and local.get("Label"):
        return local["Label"]
    return next((v["Label"] for v in value.get("LocalizedLabels", []) if v.get("Label")), None)


def _options(option_set, boolean=False):
    if boolean:
        return [{"name": _label(option_set[key].get("Label")) or str(value), "value": value}
                for key, value in (("FalseOption", False), ("TrueOption", True))
                if isinstance(option_set.get(key), dict)]
    return [{"name": _label(option.get("Label")) or str(option["Value"]), "value": option["Value"]}
            for option in option_set.get("Options", []) if isinstance(option, dict) and "Value" in option]


def apply_source_contract(source: DataSource, raw: dict) -> None:
    kind = raw.get("Type")
    if kind in {"ServiceInfo", "ViewInfo", "OptionSetInfo"}:
        source.origin = {"ServiceInfo": "service", "ViewInfo": "view", "OptionSetInfo": "option_set"}[kind]
        source.fields = []
        source.aliases = [str(raw["DisplayName"])] if raw.get("DisplayName") else []
        # Connections carry service operations, never table rows. Keep names
        # and view/enum references, without copying tenant connection secrets.
        source.metadata = {key: raw[key] for key in (
            "Type", "RelatedEntityName", "RelatedColumnInvariantName", "OptionSetReference",
            "OptionSetIsBooleanValued", "OptionSetIsGlobal", "ViewName", "ViewId", "ViewInfoNameMapping",
        ) if key in raw}
        if kind == "ViewInfo":
            source.metadata['ViewInfoNameMapping'] = _document(raw.get('ViewInfoNameMapping', {}), 'view name mapping')
        if kind == "OptionSetInfo":
            mapping = _document(raw.get("OptionSetInfoNameMapping", {}), "option name mapping")
            boolean = raw.get("OptionSetIsBooleanValued") is True
            for code, name in mapping.items():
                if boolean:
                    if str(code) not in {"0", "1"}:
                        raise ValueError(f"Invalid boolean option value in {source.name}: {code}")
                    value = str(code) == "1"
                else:
                    try:
                        value = int(code)
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid option value in {source.name}: {code}") from exc
                source.option_values.append({"name": str(name), "value": value})
        return
    if kind != "NativeCDSDataSourceInfo":
        return
    source.origin = "dataverse"
    definition = _document(raw.get("TableDefinition"), "Dataverse TableDefinition")
    entity = _document(definition.get("EntityMetadata"), "Dataverse EntityMetadata")
    attributes = entity.get("Attributes")
    if not isinstance(attributes, list) or not attributes:
        raise ValueError(f"Dataverse table {source.name} has no exported attribute contract")
    mapping = _document(raw.get("NativeCDSDataSourceInfoNameMapping", {}), "Dataverse field name mapping")
    source.logical_name = entity.get("LogicalName") or raw.get("LogicalName")
    choices = {}
    state_model = {"defaultState": None, "states": [], "statuses": [],
                   "enforceTransitions": entity.get("EnforceStateTransitions")}
    for category in ("Boolean", "Picklist", "MultiSelectPicklist", "State", "Status"):
        # Modern exports use JSON null when this category was not exported.
        # Keep malformed non-null values as errors and never invent choices.
        exported_options = definition.get(category + "OptionSetAttribute")
        option_attributes = {} if exported_options is None else _document(exported_options, category + " options")
        for attr in option_attributes.get("value", []):
            if attr.get("LogicalName") and isinstance(attr.get("OptionSet"), dict):
                choices[attr["LogicalName"]] = _options(attr["OptionSet"], category == "Boolean")
                options = attr["OptionSet"].get("Options", [])
                if category == "State" and attr["LogicalName"] == "statecode":
                    state_model["defaultState"] = attr.get("DefaultFormValue")
                    state_model["states"] = [{"value": option.get("Value"),
                        "defaultStatus": option.get("DefaultStatus"), "invariantName": option.get("InvariantName")}
                        for option in options]
                elif category == "Status" and attr["LogicalName"] == "statuscode":
                    state_model["statuses"] = [{"value": option.get("Value"), "state": option.get("State"),
                        "transitionData": option.get("TransitionData")} for option in options]
    types = {"String": "text", "Memo": "text", "Uniqueidentifier": "text", "EntityName": "text",
             "Integer": "number", "BigInt": "number", "Decimal": "number", "Double": "number", "Money": "number",
             "DateTime": "date", "Boolean": "bool", "Picklist": "choice", "State": "choice", "Status": "choice",
             "Lookup": "lookup", "Customer": "lookup", "Owner": "lookup", "MultiSelectPicklist": "choices"}
    source.fields = []
    used_headers = set()
    for attr in attributes:
        logical = attr.get("LogicalName")
        if not logical:
            continue
        attribute_type = attr.get("AttributeTypeName", {}).get("Value", "").removesuffix("Type")
        attribute_type = attribute_type or attr.get("AttributeType", "")
        # The export's mapping is authoritative, including lookup wire names.
        wire = "_" + logical + "_value"
        name = mapping.get(logical) or mapping.get(wire) or _label(attr.get("DisplayName")) or logical
        if snake(name) in used_headers:
            # Ambiguous display labels must not overwrite another column.
            name = logical
        if snake(name) in used_headers:
            raise ValueError(f"Dataverse table {source.name} has colliding field names: {name}")
        used_headers.add(snake(name))
        aliases = [logical]
        if wire in mapping:
            aliases.append(wire)
        source.fields.append(FieldDef(name=name, logical_name=logical,
            aliases=[a for a in aliases if snake(a) != snake(name)],
            type=types.get(attribute_type, "unsupported"), source_type=attribute_type,
            choices=choices.get(logical, []), lookup_targets=attr.get("Targets") or [],
            required_level=(attr.get("RequiredLevel") or {}).get("Value"),
            writable_create=attr.get("IsValidForCreate"), writable_update=attr.get("IsValidForUpdate")))
        if logical == entity.get("PrimaryIdAttribute"):
            source.primary_key = name
    if not source.primary_key:
        raise ValueError(f"Dataverse table {source.name} has no exported primary key attribute")
    source.metadata = {"entitySetName": entity.get("EntitySetName"), "primaryNameAttribute": entity.get("PrimaryNameAttribute"),
        "attributes": attributes,
        "relationships": {key: entity.get(key, []) for key in
                          ("ManyToOneRelationships", "OneToManyRelationships", "ManyToManyRelationships")},
        "views": definition.get("Views"), "defaultPublicView": definition.get("DefaultPublicView")}
    navigation_names = {r.get(key) for values in source.metadata['relationships'].values() for r in values
                        for key in ('ReferencedEntityNavigationPropertyName', 'ReferencingEntityNavigationPropertyName',
                                    'Entity1NavigationPropertyName', 'Entity2NavigationPropertyName') if r.get(key)}
    source.metadata['relationshipNames'] = {key: value for key, value in mapping.items() if key in navigation_names}
    if any(field.source_type in {"State", "Status"} for field in source.fields):
        source.metadata['stateModel'] = state_model


def field_aliases(field):
    return {snake(field.name), *(snake(name) for name in field.aliases)}
