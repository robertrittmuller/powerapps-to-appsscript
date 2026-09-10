"""Recover omitted modern defaults from the same export's native controls.

YAML remains authoritative. Only an existing control in the corresponding
screen/component is supplemented; native actions, resources and control trees
are never substituted for modern source. Every recovered formula is ledgered.
"""
import json


LAYOUT_PROPERTIES = {
    'X','Y','Width','Height','ZIndex','FillPortions','AlignInContainer',
    'LayoutMinWidth','LayoutMinHeight','LayoutMaxWidth','LayoutMaxHeight',
    'LayoutMode','LayoutDirection','LayoutAlignItems','LayoutJustifyContent',
    'LayoutGap','LayoutOverflowX','LayoutOverflowY','LayoutWrap',
    'PaddingLeft','PaddingRight','PaddingTop','PaddingBottom',
    'TemplateSize','TemplatePadding','WrapCount',
}


def restore_layout_defaults(app, entries):
    from .unpack import UnpackError
    from .template_defaults import selection_defaults

    try:
        selection=selection_defaults(entries)
    except ValueError as error:
        raise UnpackError(str(error)) from error

    sources = {}
    for filename, text in entries.items():
        normalized = filename.lower()
        if not normalized.endswith('.json') or not normalized.startswith(('controls/','components/')):
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            app.warnings.append('unparseable native layout defaults: ' + filename)
            continue
        root = doc.get('TopParent') if isinstance(doc,dict) else None
        if not isinstance(root,dict) or not isinstance(root.get('Name'),str):
            continue
        kind = 'component' if normalized.startswith('components/') else 'screen'
        key = (kind, root['Name'].casefold())
        if key in sources:
            raise UnpackError('ambiguous native layout root: ' + root['Name'])
        sources[key] = (filename,root)

    recovered = []
    recovered_selection = []
    def restore(kind, name, modern):
        pair = sources.get((kind,name.casefold()))
        if not pair or not isinstance(modern,dict):
            return
        filename,native = pair
        indexed = {}
        def index(node):
            if not isinstance(node,dict): return
            if isinstance(node.get('Name'),str):
                indexed.setdefault(node['Name'].casefold(),[]).append(node)
            for child in node.get('Children') or []: index(child)
        index(native)

        def visit(control_name, node):
            if not isinstance(node,dict): return
            matches = indexed.get(str(control_name).casefold(),[])
            if len(matches) > 1:
                raise UnpackError('ambiguous native layout control: ' + str(control_name))
            if matches:
                match = matches[0]
                template = match.get('Template') or {}
                modern_version = str(node.get('Control','')).partition('@')[2]
                if modern_version and template.get('Version') and modern_version != template['Version']:
                    app.warnings.append('native layout version differs from YAML: ' + str(control_name))
                else:
                    rules = [(rule,'Rules') for rule in match.get('Rules') or []]
                    rules.extend((prop.get('Rule'),'DynamicProperties') for prop in match.get('DynamicProperties') or []
                                 if isinstance(prop,dict))
                    defaults = {}
                    for rule,origin in rules:
                        if not isinstance(rule,dict): continue
                        prop,script = rule.get('Property'),rule.get('InvariantScript')
                        if prop not in LAYOUT_PROPERTIES | {'SelectMultiple'}: continue
                        if not isinstance(script,str):
                            if prop=='SelectMultiple':
                                raise UnpackError('invalid native selection property: ' + str(control_name))
                            continue
                        if not script.strip() and prop!='SelectMultiple': continue
                        if prop in defaults and defaults[prop][0] != script:
                            raise UnpackError('conflicting native layout property: ' + str(control_name) + '.' + prop)
                        defaults[prop] = (script,origin)
                    factory=selection.get((template.get('Name'),template.get('Version')))
                    if factory and 'SelectMultiple' not in defaults:
                        defaults['SelectMultiple']=(factory['value'],'Template.defaultValue')
                    props = node.setdefault('Properties',{})
                    if props is None:
                        props = node['Properties'] = {}
                    if not isinstance(props,dict):
                        raise UnpackError('invalid modern control Properties: ' + str(control_name))
                    declared = {str(prop).casefold() for prop in props}
                    for prop,(script,origin) in defaults.items():
                        if prop.casefold() in declared: continue
                        props[prop] = script if script.startswith('=') else '=' + script
                        evidence={'scope':kind,'root':name,'control':control_name,
                                  'property':prop,'archiveEntry':filename,'nativeField':origin}
                        if prop=='SelectMultiple':
                            if origin=='Template.defaultValue':
                                evidence.update(templateName=template['Name'],templateVersion=template['Version'],**factory)
                            recovered_selection.append(evidence)
                        else:
                            recovered.append(evidence)
            for child in node.get('Children') or []:
                if isinstance(child,dict):
                    for child_name,child_node in child.items(): visit(child_name,child_node)
        visit(name,modern)

    for name,document in app.screens.items():
        nodes = document.get('Screens',document)
        if isinstance(nodes,dict): restore('screen',name,nodes.get(name))
    for name,definition in app.component_definitions.items():
        restore('component',name,definition)
    if recovered:
        app.source_metadata['nativeLayoutDefaults'] = recovered
    if recovered_selection:
        app.source_metadata['nativeSelectionDefaults'] = recovered_selection
