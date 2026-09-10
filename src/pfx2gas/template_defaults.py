"""Read narrowly supported behavior defaults from exact exported templates.

Authoring examples such as Items/DefaultSelectedItems are deliberately excluded:
they are not a license to invent data or replace an app's own formulas.
"""
import json
import xml.etree.ElementTree as ET


def selection_defaults(entries):
    defaults = {}
    for filename,text in entries.items():
        if filename.lower().replace('\\','/') != 'references/templates.json':
            continue
        document=json.loads(text)
        for template in document.get('UsedTemplates',[]):
            raw=template.get('Template')
            if not isinstance(raw,str) or not raw:
                continue
            if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
                raise ValueError('unsafe exported control template XML')
            try:
                root=ET.fromstring(raw)
            except ET.ParseError as error:
                raise ValueError('invalid exported control template XML') from error
            key=(template.get('Name'),template.get('Version'))
            if not all(isinstance(value,str) and value for value in key):
                continue
            for prop in root.iter():
                if prop.tag.rsplit('}',1)[-1]!='property' or prop.get('name')!='SelectMultiple':
                    continue
                value=prop.get('defaultValue')
                if value is None:
                    continue  # Display-metadata property references have no default.
                value=value.strip().lower()
                if prop.get('datatype','').lower()!='boolean' or value not in {'true','false'}:
                    raise ValueError('unsupported SelectMultiple template default: '+key[0]+'@'+key[1])
                previous=defaults.get(key)
                if previous and previous['value']!=value:
                    raise ValueError('conflicting SelectMultiple template defaults: '+key[0]+'@'+key[1])
                defaults[key]={'value':value,'archiveEntry':filename}
    return defaults


def restore_native_selection(node, defaults, recovered, scope, root):
    """Supplement legacy native trees before component expansion/parsing."""
    if not isinstance(node,dict):
        return
    template=node.get('Template') or {}
    default=defaults.get((template.get('Name'),template.get('Version')))
    declared={str(rule.get('Property','')).casefold() for rule in node.get('Rules') or [] if isinstance(rule,dict)}
    dynamic=[prop.get('Rule') for prop in node.get('DynamicProperties') or [] if isinstance(prop,dict)]
    for rule in dynamic:
        if not isinstance(rule,dict) or str(rule.get('Property','')).casefold()!='selectmultiple':
            continue
        if 'selectmultiple' in declared:
            own=[entry for entry in node.get('Rules') or [] if isinstance(entry,dict)
                 and str(entry.get('Property','')).casefold()=='selectmultiple']
            if any(entry.get('InvariantScript')!=rule.get('InvariantScript') for entry in own):
                raise ValueError('conflicting native selection property: '+str(node.get('Name'))+'.SelectMultiple')
            continue
        node['Rules']=list(node.get('Rules') or [])
        node['Rules'].append(dict(rule,Property='SelectMultiple'))
        declared.add('selectmultiple')
        recovered.append({'scope':scope,'root':root,'control':node.get('Name'),
                          'property':'SelectMultiple','nativeField':'DynamicProperties'})
    if default and 'selectmultiple' not in declared:
        node['Rules']=list(node.get('Rules') or [])
        node['Rules'].append({'Property':'SelectMultiple','InvariantScript':default['value']})
        recovered.append({'scope':scope,'root':root,'control':node.get('Name'),'property':'SelectMultiple',
                          'templateName':template['Name'],'templateVersion':template['Version'],**default})
    for child in node.get('Children') or []:
        restore_native_selection(child,defaults,recovered,scope,root)
