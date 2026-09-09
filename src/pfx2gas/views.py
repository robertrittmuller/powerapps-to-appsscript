"""Resolve Dataverse saved views from exported solution metadata, never names.

Canvas exports normally include view IDs but omit their FetchXML. The optional
solution supplies that contract. Unsupported queries remain explicit failures.
"""
from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .data_contract import _document
from .fx.naming import snake

MAX_XML_BYTES = 32 * 1024 * 1024


def _xml(payload):
    data = payload.encode() if isinstance(payload, str) else payload
    if len(data) > MAX_XML_BYTES or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported solution XML size or entity declaration')
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError('Invalid solution/view XML: ' + str(error)) from error


def load_solution_views(path: str | Path) -> tuple[dict, str]:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix.lower() == '.xml':
        payload = path.read_bytes()
    else:
        if not zipfile.is_zipfile(path):
            raise ValueError('Solution is not a ZIP archive')
        with zipfile.ZipFile(path) as archive:
            matches = [entry for entry in archive.infolist()
                       if entry.filename.replace('\\', '/').lower() == 'customizations.xml']
            if len(matches) != 1 or matches[0].file_size > MAX_XML_BYTES:
                raise ValueError('Solution must contain one bounded customizations.xml')
            payload = archive.read(matches[0])
    root = _xml(payload)
    if root.tag != 'ImportExportXml':
        raise ValueError('Expected a Power Platform solution customizations.xml')
    views = {}
    for query in root.iter('savedquery'):
        view_id = (query.findtext('savedqueryid') or '').strip().strip('{}').lower()
        wrapper = query.find('fetchxml')
        fetch = wrapper.find('fetch') if wrapper is not None else None
        if fetch is None and wrapper is not None and wrapper.text and wrapper.text.strip():
            fetch = _xml(wrapper.text)
        if not view_id or fetch is None:
            continue
        text = ET.tostring(fetch, encoding='unicode')
        if view_id in views and views[view_id] != text:
            raise ValueError('Conflicting saved view ID: ' + view_id)
        views[view_id] = text
    return views, digest


def compile_view(text: str, source) -> dict:
    root = _xml(text)
    if root.tag != 'fetch' or root.get('aggregate', 'false') != 'false' or root.get('distinct', 'false') != 'false':
        raise ValueError('aggregate/distinct FetchXML is unsupported')
    if set(root.attrib) - {'version', 'output-format', 'mapping', 'distinct', 'aggregate', 'useraworderby'}:
        raise ValueError('unsupported FetchXML paging/limit/query option')
    if root.get('useraworderby', 'false') not in {'true', 'false'}:
        raise ValueError('invalid FetchXML useraworderby option')
    if len(root) != 1 or root[0].tag != 'entity' or root[0].get('name') != source.logical_name:
        raise ValueError('saved view entity does not match its data source')
    entity = root[0]
    if set(entity.attrib) != {'name'} or any(child.tag not in {'attribute', 'all-attributes', 'filter', 'order'} for child in entity):
        raise ValueError('joined or extended FetchXML entities are unsupported')
    fields = {field.logical_name or field.name: field for field in source.fields}
    limitations = set()
    def field_contract(name, identity=False):
        if name not in fields:
            raise ValueError('unknown saved view field: ' + str(name))
        field = fields[name]
        if identity and field.type not in {'text', 'lookup'}:
            raise ValueError('current-user comparison requires an identifier or lookup field')
        if field.type not in {'text', 'number', 'bool', 'choice', 'date'} and not (identity and field.type == 'lookup'):
            raise ValueError('unsupported saved view field type: ' + field.type)
        if field.type == 'text' and not identity:
            limitations.add('Saved-view text comparison uses case-insensitive Unicode ordering; tenant collation is not reproduced')
        return {'field': snake(field.name), 'type': field.type}
    def condition(node):
        if node.tag == 'filter':
            if set(node.attrib) - {'type'} or node.get('type', 'and') not in {'and', 'or'}:
                raise ValueError('unsupported FetchXML filter option')
            return {'op': node.get('type', 'and'), 'args': [condition(child) for child in node]}
        if node.tag != 'condition' or set(node.attrib) - {'attribute', 'operator', 'value'}:
            raise ValueError('unsupported FetchXML condition or related-column comparison')
        op = node.get('operator')
        if op not in {'eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in', 'not-in', 'null', 'not-null', 'eq-userid', 'ne-userid'}:
            raise ValueError('unsupported FetchXML operator: ' + str(op))
        result = {**field_contract(node.get('attribute'), op in {'eq-userid','ne-userid'}), 'op': op}
        if any(child.tag != 'value' or child.attrib or len(child) for child in node):
            raise ValueError('unsupported FetchXML condition values')
        values = [node.get('value')] if 'value' in node.attrib else [child.text or '' for child in node]
        expected = 0 if op in {'null', 'not-null', 'eq-userid', 'ne-userid'} else None if op in {'in', 'not-in'} else 1
        if (expected is not None and len(values) != expected) or (expected is None and not values) or ('value' in node.attrib and len(node)):
            raise ValueError('wrong number of FetchXML condition values')
        if result['type'] in {'number', 'choice'}:
            values = [float(value) for value in values]
            if any(not math.isfinite(value) for value in values):
                raise ValueError('nonfinite FetchXML number')
        elif result['type'] == 'bool':
            if any(value not in {'0', '1'} for value in values):
                raise ValueError('invalid FetchXML boolean')
            values = [value == '1' for value in values]
        elif result['type'] == 'date':
            # Relative dates and caller-timezone conversion require a separate
            # contract. Accept only absolute instants with an explicit zone.
            from datetime import datetime
            for value in values:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    raise ValueError('view date comparison requires an explicit timezone')
        result['values'] = values
        return result
    order = []
    for node in entity.findall('order'):
        if set(node.attrib) - {'attribute', 'descending'} or node.get('descending', 'false') not in {'true', 'false'}:
            raise ValueError('unsupported FetchXML order option')
        contract = field_contract(node.get('attribute'))
        if contract['type'] == 'choice' and root.get('useraworderby') != 'true':
            raise ValueError('localized choice-label ordering requires a target language contract')
        order.append({**contract, 'descending': node.get('descending') == 'true'})
    for node in entity.findall('attribute'):
        if set(node.attrib) != {'name'} or len(node) or node.get('name') not in fields:
            raise ValueError('unsupported FetchXML projection')
    if any(node.attrib or len(node) for node in entity.findall('all-attributes')):
        raise ValueError('unsupported FetchXML all-attributes projection')
    predicate = {'op': 'and', 'args': [condition(node) for node in entity.findall('filter')]}
    if not order:
        limitations.add('Saved view without explicit order retains migrated row order; Dataverse implicit primary-key ordering is not reproduced')
    return {'source': source.name, 'filter': predicate, 'order': order, 'limitations': sorted(limitations)}


def resolve_views(ir, solution: str | Path | None = None) -> None:
    definitions, digest = load_solution_views(solution) if solution else ({}, None)
    if digest:
        ir.source_metadata['solutionSha256'] = digest
    sources = {source.name: source for source in ir.data_sources}
    ir.view_sets = {}
    for view_source in ir.data_sources:
        if view_source.origin != 'view':
            continue
        source = sources.get(view_source.metadata.get('RelatedEntityName'))
        mapping = view_source.metadata.get('ViewInfoNameMapping', {})
        resolved = {}
        for view_id, name in mapping.items():
            view_id = str(view_id).strip('{}').lower()
            query = {'id': view_id, 'name': str(name), 'source': source.name if source else None}
            try:
                if source is None:
                    raise ValueError('saved view data source is missing')
                text = definitions.get(view_id)
                if not text:
                    # Some source formats carry FetchXML directly in Views.
                    exported = _document(source.metadata.get('views') or {}, 'saved views')
                    text = next((row.get('fetchxml') for row in exported.get('value', [])
                                 if str(row.get('savedqueryid', '')).strip('{}').lower() == view_id), None)
                if not text:
                    raise ValueError('FetchXML is missing; supply the exported solution with --solution')
                query.update(compile_view(text, source))
                def needs_identity(node):
                    return node['op'] in {'eq-userid','ne-userid'} or any(needs_identity(child) for child in node.get('args', []))
                if needs_identity(query['filter']):
                    users = [table for table in ir.data_sources if table.logical_name == 'systemuser']
                    if len(users) != 1 or not users[0].primary_key:
                        raise ValueError('current-user view requires the exported systemuser table and an identity mapping')
                    email = next((field for field in users[0].fields if field.logical_name == 'internalemailaddress'), None)
                    if email is None:
                        raise ValueError('systemuser email mapping is missing')
                    query['identity'] = {'source': users[0].name, 'key': snake(users[0].primary_key), 'emailField': snake(email.name)}
            except (ValueError, ET.ParseError) as error:
                query['error'] = f'Dataverse view {name}: {error}'
            key = snake(str(name))
            if key in resolved:
                raise ValueError('Ambiguous saved view name: ' + str(name))
            resolved[key] = query
        for name in [view_source.name, *view_source.aliases]:
            ir.view_sets[name] = resolved
