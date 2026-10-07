"""Source-backed capability inventory; missing contracts are never invented."""
from __future__ import annotations

from .controls import EXPLICITLY_UNSUPPORTED_INPUTS
from .fidelity import iter_expressions
from .fx import lexer as lx
from .ir import AppIR
from .services import service_contracts


def capabilities(ir: AppIR) -> list[dict]:
    from .synth.client import ELEMENT_MAP, CHART_TYPES
    from .synth.composites import PROPERTIES
    rows = []
    def add(kind, subject, status, classification, detail):
        rows.append(dict(id=f'{kind}:{subject}', kind=kind, subject=subject, status=status,
                         classification=classification, detail=detail))
    for screen in ir.screens:
        for control in screen.walk_controls():
            subject = f'{screen.name}.{control.name}'
            if control.type in EXPLICITLY_UNSUPPORTED_INPUTS:
                add('control', subject, 'unsupported', 'converter-gap', f'{control.type} capture/upload is not implemented')
            elif control.component_error or (control.type == 'CanvasComponent' and not control.children):
                add('control', subject, 'unsupported', 'source-incomplete', control.component_error or 'Component definition is missing')
            elif control.type not in ELEMENT_MAP and control.type not in CHART_TYPES and control.type not in PROPERTIES:
                add('control', subject, 'unsupported', 'converter-gap', f'{control.type} uses a generic container')
            elif control.type in {'CanvasComponent', 'ComboBox', 'DataTable', 'FluentDatePicker'} or control.type in CHART_TYPES or control.type in PROPERTIES:
                add('control', subject, 'approximated', 'converter-gap', f'{control.type} has a bounded renderer; native interaction/appearance requires source comparison')
            else:
                add('control', subject, 'supported', 'implemented', f'{control.type} renderer is available; workflow verification is separate')
    adapters = service_contracts(ir)
    for source in ir.data_sources:
        if source.origin == 'service':
            adapter = adapters.get(source.name)
            add('connector', source.name, 'approximated' if adapter else 'unsupported', 'converter-gap',
                '; '.join(adapter['limitations']) if adapter else 'No deterministic target adapter')
            if adapter:
                add('migration', source.name, 'unverified', 'migration-required', 'Source IDs, Google users/resources and live authorization must be verified')
        elif source.origin not in {'collection', 'view', 'option_set'}:
            if not source.fields:
                add('schema', source.name, 'unsupported', 'source-incomplete', 'Exported field contract is missing')
            if source.origin != 'static':
                add('migration', source.name, 'unverified', 'migration-required',
                    'Embedded seed rows are not proof of complete tenant data; reconcile counts, keys and relationships after import')
            if source.origin == 'dataverse':
                add('permissions', source.name, 'unsupported', 'converter-gap',
                    'Dataverse row/field privileges and business-unit security are not implemented by Sheets ownership fields')
                for field in source.fields:
                    subject = f'{source.name}.{field.name}'
                    if field.calculated:
                        add('calculation', subject, 'unsupported', 'converter-gap', 'Source formula/rollup calculation requires an adapter; writes are read-only')
                    if field.type == 'unsupported':
                        add('field', subject, 'unsupported', 'converter-gap', f'Unsupported source field type: {field.source_type}')
                    if field.type == 'lookup':
                        add('lookup', subject, 'approximated', 'converter-gap', 'Lookup values are stored snapshots; live lookup propagation and cascade behavior require verification')
                    if field.date_behavior and field.date_behavior != 'UserLocal':
                        add('date', subject, 'unsupported', 'converter-gap', f'{field.date_behavior} storage semantics require an explicit adapter')
                    if field.required_level == 'SystemRequired' and field.writable_create is False and not field.has_default and field.name != source.primary_key:
                        add('default', subject, 'unsupported', 'converter-gap', 'System-required read-only field has no implemented generated default')
    known = {source.name for source in ir.data_sources} | set(ir.global_vars)
    for screen, control, prop, expr in iter_expressions(ir):
        try:
            pending = list(lx.parse_formula(expr.raw))
        except lx.FxSyntaxError:
            continue
        while pending:
            node = pending.pop()
            if node.kind == 'call' and node.value in {'Choices', 'Defaults', 'Patch', 'Refresh', 'Remove', 'RemoveIf'} and node.children:
                target = node.children[0]
                if target.kind == 'member':
                    target = target.children[0]
                if target.kind == 'ident':
                    name = lx.reference_parts(str(target.value))[0]
                    if name not in known:
                        add('dependency', f'{screen}.{control}.{prop}:{name}', 'unverified', 'source-incomplete',
                            'Referenced data source or record contract is undeclared; supply a complete export or verify the record-valued expression')
            pending.extend(node.children)
            if node.kind == 'record':
                pending.extend(value for _, value in node.value)
    return list({row['id']: row for row in rows}.values())


def assess(ir: AppIR) -> dict:
    rows = capabilities(ir)
    issues = [row for row in rows if row['status'] != 'supported']
    formula_gaps = [dict(context=f'{screen}.{control}.{prop}', translation=expr.translation_status,
                        emission=expr.emission_status, detail=expr.fidelity_note)
                    for screen,control,prop,expr in iter_expressions(ir)
                    if expr.translation_status != 'rule' or expr.emission_status in {'unsupported','ignored','approximated'}]
    return {'schemaVersion': 1, 'app': ir.name, 'status': 'needs-attention' if issues or formula_gaps else 'ready-for-verification',
            'capabilities': rows, 'issues': issues, 'sourceWarnings': getattr(ir, 'warnings', []),
            'formulaGaps': formula_gaps, 'sourceMetadata': getattr(ir, 'source_metadata', {}),
            'verification': {stage: 'unassessed' for stage in ('startup', 'workflows', 'sourceComparison', 'liveGoogle')}}
