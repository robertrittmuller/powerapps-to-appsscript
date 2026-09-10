"""App.Formulas declarations, kept separate from behavioral assignments.

Canvas semantics: https://learn.microsoft.com/power-platform/power-fx/reference/object-app
Token positions retain literal text/comments; a comparison inside a declaration
is part of its value, and quoted semicolons never split declarations.
"""
from .fx import lexer as lx


def declarations(source: str) -> dict[str, str]:
    tokens = lx.tokenize(source)
    result, seen, group, stack = {}, set(), [], []
    pairs = {')': '(', ']': '[', '}': '{'}
    for token in tokens:
        if token.kind == 'eof' or (token.kind == 'punct' and token.value == ';' and not stack):
            if group:
                first = group[0]
                if (first.kind != 'ident' or len(lx.reference_parts(first.value)) != 1
                        or len(group) < 3 or group[1].kind != 'op' or group[1].value != '='):
                    raise lx.FxSyntaxError('App.Formulas requires Name = expression; user-defined functions/types are unsupported')
                name = lx.reference_parts(first.value)[0]
                if name.casefold() in seen:
                    raise lx.FxSyntaxError('Duplicate named formula: ' + name)
                if not name or name.startswith('__') or name.casefold() in {'app', 'parent', 'self', 'thisitem', 'thisrecord'}:
                    raise lx.FxSyntaxError('Named formula uses a reserved runtime name: ' + name)
                seen.add(name.casefold())
                result[name] = source[group[1].pos + 1:token.pos].strip()
                group = []
            if token.kind == 'eof' and stack:
                raise lx.FxSyntaxError('Unclosed delimiter in App.Formulas')
            continue
        if token.kind == 'punct':
            if token.value in '([{':
                stack.append(token.value)
            elif token.value in pairs:
                if not stack or stack.pop() != pairs[token.value]:
                    raise lx.FxSyntaxError('Mismatched delimiter in App.Formulas')
        group.append(token)
    return result


# These functions cannot be reevaluated as declarative values. Unknown functions
# still go through the ordinary unsupported-operation gate; no model fallback
# may erase a declaration/purity failure.
BEHAVIOR_FUNCTIONS = {name.casefold() for name in (
    'Set UpdateContext Navigate Back Notify Exit Launch Select SetFocus Reset '
    'ResetForm NewForm EditForm ViewForm SubmitForm Collect Clear ClearCollect '
    'Patch Remove RemoveIf Update UpdateIf Relate Unrelate Refresh SaveData '
    'LoadData ClearData Concurrent Download Print Trace'.split()
)}
VOLATILE_FUNCTIONS = {'rand', 'randbetween', 'now', 'today', 'guid'}


def validate_value(source: str, context: str = 'Named formulas', allow_volatile: bool = False) -> None:
    roots = lx.parse_formula(source)
    if len(roots) != 1:
        raise lx.FxSyntaxError(context + ' must have one value expression')
    def visit(node):
        if node.kind == 'chain':
            raise lx.FxSyntaxError(context + ' cannot contain a behavior chain')
        if node.kind == 'call':
            name = str(node.value).casefold()
            if name in BEHAVIOR_FUNCTIONS:
                raise lx.FxSyntaxError(context + ' cannot call behavior function ' + str(node.value))
            if not allow_volatile and name in VOLATILE_FUNCTIONS:
                raise lx.FxSyntaxError('Volatile named formula needs dependency-aware caching: ' + str(node.value))
        for child in node.children:
            visit(child)
        if node.kind == 'record':
            for _name, value in node.value:
                visit(value)
    visit(roots[0])
