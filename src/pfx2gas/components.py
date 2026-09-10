"""Expand modern CanvasComponent definitions without editing Power Fx text.

Schema: microsoft/PowerApps-Tooling/schemas/pa-yaml/v3.0/pa.schema.yaml
Instance overrides retain their host scope; defaults/children retain the
definition scope. Nested definitions have independent control namespaces.
"""
from .ir import AppIR, ControlNode


def expand_components(ir: AppIR, definitions: dict) -> None:
    from .parse import _parse_control, _make_expr

    lookup = {name.casefold(): (name, node) for name, node in definitions.items()}
    occupied = {ctrl.name.casefold() for screen in ir.screens for ctrl in screen.walk_controls()}
    evidence = []

    def expand(ctrl: ControlNode, stack=(), in_row=False):
        if ctrl.type != 'CanvasComponent' or not ctrl.component_name:
            for child in ctrl.children:
                expand(child, stack, in_row or ctrl.type in {'Gallery', 'Form', 'DataTable'})
            return
        name = ctrl.component_name
        record = {'instance': ctrl.name, 'definition': name, 'status': 'unsupported'}
        evidence.append(record)
        try:
            if in_row:
                raise ValueError('components inside gallery/form templates are unsupported')
            if name.casefold() in stack:
                raise ValueError('circular component definition: ' + ' -> '.join((*stack, name)))
            if name.casefold() not in lookup:
                raise ValueError('component definition was not exported: ' + name)
            original, definition = lookup[name.casefold()]
            if not isinstance(definition, dict) or definition.get('DefinitionType') != 'CanvasComponent':
                raise ValueError('unsupported component definition type: ' + name)
            access = definition.get('AccessAppScope', False)
            if type(access) is not bool:
                raise ValueError('AccessAppScope must be boolean')
            if ctrl.component_library and access:
                raise ValueError('a library component cannot access app scope')
            custom = definition.get('CustomProperties') or {}
            if not isinstance(custom, dict):
                raise ValueError('invalid component CustomProperties')
            for prop, contract in custom.items():
                if not isinstance(contract, dict) or contract.get('PropertyKind') not in {'Input', 'Output'}:
                    raise ValueError('unsupported component custom property: ' + prop)
                if contract.get('PropertyKind') == 'Output' and prop in ctrl.properties:
                    raise ValueError('a component output cannot be overridden: ' + prop)
            template = _parse_control(original, {'Control': 'CanvasComponent',
                                                'Properties': definition.get('Properties'),
                                                'Children': definition.get('Children')})
            for prop, contract in custom.items():
                if prop not in template.properties and contract.get('Default') is not None:
                    template.properties[prop] = _make_expr(contract['Default'], prop)
            names = {original: ctrl.name}
            local_names = {original.casefold()}
            for child in template.walk():
                if child is template:
                    continue
                if child.name.casefold() in local_names:
                    raise ValueError('duplicate component child: ' + child.name)
                local_names.add(child.name.casefold())
                qualified = ctrl.name + '__' + child.name
                if qualified.casefold() in occupied:
                    raise ValueError('expanded component name collides with an app control: ' + qualified)
                names[child.name] = qualified
            for child in template.walk():
                child.name = names[child.name]
                for expr in child.properties.values():
                    expr.control_aliases = dict(names)
                    expr.component_owner = ctrl.name
                    expr.component_private = not access
            # Host-authored overrides already carry the correct outer scope,
            # including when this instance lives within another component.
            template.properties.update(ctrl.properties)
            ctrl.properties = template.properties
            ctrl.children = template.children
            ctrl.component_template = original
            ctrl.component_inputs = list(custom)
            occupied.update(value.casefold() for value in names.values())
            record.update(status='expanded', accessAppScope=access,
                          customProperties={key: value['PropertyKind'] for key, value in custom.items()})
            for child in ctrl.children:
                expand(child, (*stack, name.casefold()))
        except (ValueError, TypeError) as error:
            ctrl.component_error = str(error)
            ctrl.children = []
            record['error'] = str(error)
            ir.warnings.append('Canvas component ' + ctrl.name + ': ' + str(error))

    for screen in ir.screens:
        for ctrl in screen.controls:
            expand(ctrl)
    if evidence:
        ir.source_metadata['canvasComponents'] = evidence
