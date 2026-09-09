"""Carry exported column aliases through explicit collection/table lineage."""
from . import fx
from .analyze import behavior_formulas, named_target, walk_formula
from .data_contract import field_aliases
from .fx.naming import snake


def infer_collection_contracts(ir):
    sources = {source.name:source for source in ir.data_sources}
    lineage = {name:set() for name,source in sources.items() if source.origin == 'collection'}
    def source_of(node):
        if node.kind == 'alias':
            return source_of(node.children[0])
        if node.kind == 'call' and node.value in {'Filter','Search','Sort','SortByColumns','FirstN','LastN','AddColumns'} and node.children:
            return source_of(node.children[0])
        return named_target(node)
    for expr in behavior_formulas(ir):
        try:
            roots = fx.lexer.parse_formula(expr.raw)
        except fx.lexer.FxSyntaxError:
            continue
        for node in (node for root in roots for node in walk_formula(root)):
            if node.kind != 'call' or node.value not in {'Collect','ClearCollect'} or not node.children:
                continue
            target = named_target(node.children[0])
            if target in lineage:
                lineage[target].update(name for arg in node.children[1:]
                    if (name := source_of(arg)) in sources and name != target)
    for _ in range(len(lineage)):
        changed = False
        for names in lineage.values():
            inherited = set().union(*(lineage.get(name,set()) for name in names)) if names else set()
            if not inherited <= names:
                names.update(inherited)
                changed = True
        if not changed:
            break
    for name, names in lineage.items():
        tables = sorted(table for table in names if sources[table].origin != 'collection')
        aliases, errors = {}, []
        for table in tables:
            for field in sources[table].fields:
                if not field.aliases:
                    continue
                canonical = snake(field.name)
                for alias in sorted(field_aliases(field)):
                    if alias in aliases and aliases[alias] != canonical:
                        errors.append(alias)
                    aliases[alias] = canonical
        if aliases:
            sources[name].metadata['collectionSourceTables'] = tables
            sources[name].metadata['columnAliases'] = aliases
        if errors:
            message = 'Collection contract ' + name + ': conflicting exported column aliases: ' + ', '.join(sorted(set(errors)))
            sources[name].metadata['collectionContractError'] = message
            ir.warnings.append(message)
