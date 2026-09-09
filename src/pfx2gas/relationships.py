"""Export-derived relationship navigation contracts; never infer a join by label."""
from .data_contract import external_tables
from .fx.naming import snake


def relationship_contracts(ir):
    tables = external_tables(ir.data_sources)
    by_logical = {}
    schemas = {}
    one_to_many = {}
    for source in tables:
        by_logical.setdefault(source.logical_name, []).append(source)
        for raw in source.metadata.get('relationships', {}).get('ManyToManyRelationships', []):
            schemas.setdefault(raw.get('SchemaName'), set()).add((raw.get('Entity1LogicalName'), raw.get('Entity2LogicalName')))
        relationships = source.metadata.get('relationships', {})
        for raw in relationships.get('OneToManyRelationships', []) + relationships.get('ManyToOneRelationships', []):
            if raw.get('ReferencedEntityNavigationPropertyName'):
                one_to_many.setdefault(raw.get('ReferencedEntity'), []).append(raw)
    result = {}
    for source in tables:
        navigation = {}
        names = source.metadata.get('relationshipNames', {})
        def add(raw_name, spec):
            if not raw_name:
                return
            for name in dict.fromkeys([raw_name, names.get(raw_name, raw_name)]):
                key = snake(name)
                if key in navigation and navigation[key] != spec:
                    navigation[key] = {'error': 'ambiguous exported relationship: ' + source.name + '.' + name}
                else:
                    navigation[key] = spec
        relationships = source.metadata.get('relationships', {})
        for raw in relationships.get('ManyToManyRelationships', []):
            for side in (1, 2):
                if raw.get(f'Entity{side}LogicalName') != source.logical_name:
                    continue
                targets = by_logical.get(raw.get(f'Entity{3-side}LogicalName'), [])
                spec = {'schema': raw.get('SchemaName'), 'side': side, 'kind': 'many-to-many'}
                if len(targets) != 1 or not source.primary_key or not targets[0].primary_key:
                    spec['error'] = 'relationship requires both exported tables and primary keys'
                elif not spec['schema']:
                    spec['error'] = 'relationship has no exported schema name'
                elif len(schemas[spec['schema']]) != 1:
                    spec['error'] = 'conflicting exported relationship schema'
                else:
                    spec['target'] = targets[0].name
                add(raw.get(f'Entity{side}NavigationPropertyName'), spec)
        for raw in one_to_many.get(source.logical_name, []):
            spec = {'schema': raw.get('SchemaName'), 'kind': 'one-to-many'}
            targets = by_logical.get(raw.get('ReferencingEntity'), [])
            primary = next((f for f in source.fields if f.name == source.primary_key), None)
            field = next((f for f in targets[0].fields if f.logical_name == raw.get('ReferencingAttribute')), None) if len(targets) == 1 else None
            if not primary or primary.logical_name != raw.get('ReferencedAttribute') or raw.get('ReferencedEntity') != source.logical_name:
                spec['error'] = 'one-to-many relationship requires the exported parent primary key'
            elif len(targets) != 1 or not targets[0].primary_key or not field or field.type != 'lookup':
                spec['error'] = 'one-to-many relationship requires the exported child table and lookup field'
            else:
                spec.update(target=targets[0].name, lookup=snake(field.name), required=field.required_level == 'SystemRequired')
                if field.writable_update is False:
                    spec['mutationError'] = 'relationship lookup is not writable in the source contract'
            add(raw.get('ReferencedEntityNavigationPropertyName'), spec)
        primary = next((f for f in source.fields if f.name == source.primary_key), None)
        keys = sorted({snake(primary.name), *(snake(a) for a in primary.aliases)}) if primary else []
        result[source.name] = {'primaryKey': snake(source.primary_key) if source.primary_key else None,
                               'keys': keys, 'navigation': navigation}
    return result
