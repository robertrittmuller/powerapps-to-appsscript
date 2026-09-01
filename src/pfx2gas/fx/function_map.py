"""Function coverage table: Power Fx -> JS (fx-stdlib) mapping.

This is the single source of truth for what the rule-based transpiler
supports. The LLM fallback prompt embeds this table at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FnSpec:
    js: str  # JS emission template; {args} = joined arg list, {a0}/{a1} = positional
    note: str = ""


# {args} is replaced with the comma-joined argument expressions.
FUNCTION_MAP: dict[str, FnSpec] = {
    # logic
    "If": FnSpec("({a0} ? ({a1}) : ({a2}))"),
    "Switch": FnSpec("FX.switch({a0}, [[{rest}]]", "special-cased in emitter"),
    "IfError": FnSpec("FX.ifError(() => ({a0}), () => ({a1}))"),
    "IsBlank": FnSpec("FX.isBlank({a0})"),
    "IsBlankOrError": FnSpec("FX.isBlankOrError({a0})"),
    "IsEmpty": FnSpec("FX.isEmpty({a0})"),
    "IsNumeric": FnSpec("FX.isNumeric({a0})"),
    "Coalesce": FnSpec("FX.coalesce([{args}])"),
    # math
    "Abs": FnSpec("Math.abs({a0})"),
    "Int": FnSpec("Math.floor({a0})"),
    "Round": FnSpec("FX.round({a0}, {a1})"),
    "RoundUp": FnSpec("FX.roundUp({a0}, {a1})"),
    "RoundDown": FnSpec("FX.roundDown({a0}, {a1})"),
    "Mod": FnSpec("FX.mod({a0}, {a1})"),
    "Sqrt": FnSpec("Math.sqrt({a0})"),
    "Power": FnSpec("Math.pow({a0}, {a1})"),
    "Min": FnSpec("FX.min({args})"),
    "Max": FnSpec("FX.max({args})"),
    "Sum": FnSpec("FX.sum({a0}, ({it}) => {a1})"),
    "Average": FnSpec("FX.average({a0}, ({it}) => {a1})"),
    "Value": FnSpec("FX.value({a0})"),
    "Rand": FnSpec("Math.random()"),
    # text
    "Concatenate": FnSpec("[{args}].join('')"),
    "Upper": FnSpec("String({a0}).toUpperCase()"),
    "Lower": FnSpec("String({a0}).toLowerCase()"),
    "Trim": FnSpec("FX.trim({a0})"),
    "TrimEnds": FnSpec("String({a0}).trim()"),
    "Left": FnSpec("String({a0}).slice(0, {a1})"),
    "Right": FnSpec("FX.right({a0}, {a1})"),
    "Mid": FnSpec("String({a0}).slice({a1} - 1, {a1} - 1 + {a2})"),
    "Len": FnSpec("String({a0}).length"),
    "Find": FnSpec("(String({a2 ?? a1}).indexOf(String({a1 ?? a0})) + 1)"),
    "Proper": FnSpec("FX.proper({a0})"),
    "Substitute": FnSpec("FX.substitute({a0}, {a1}, {a2})"),
    "Replace": FnSpec("FX.replace({a0}, {a1}, {a2}, {a3})"),
    "Text": FnSpec("FX.text({a0}, {a1})"),
    "Char": FnSpec("String.fromCharCode({a0})"),
    "Unicode": FnSpec("String({a0}).charCodeAt(0)"),
    "GUID": FnSpec("(crypto.randomUUID ? crypto.randomUUID() : FX.guid())"),
    "RGBA": FnSpec("FX.rgba({args})"),
    "ColorFade": FnSpec("FX.colorFade({args})"),
    "EncodeUrl": FnSpec("encodeURIComponent({a0})"),
    "PlainText": FnSpec("FX.plainText({a0})"),
    "Select": FnSpec("selectControl({a0})"),
    "Launch": FnSpec("window.open({a0}, '_blank')"),
    "Sequence": FnSpec("FX.sequence({args})"),
    "Split": FnSpec("FX.split({a0}, {a1})"),
    "ShowColumns": FnSpec("FX.showColumns({a0}, [{a1}])"),
    "DropColumns": FnSpec("FX.dropColumns({a0}, [{a1}])"),
    "RenameColumns": FnSpec("FX.renameColumns({a0}, [{a1}])"),
    "Search": FnSpec("FX.search({a0}, {a1}, [{rest}])", "special-cased in emitter"),
    "ColorValue": FnSpec("FX.colorValue({a0})"),
    "And": FnSpec("FX.allOf([{args}])"),
    "Or": FnSpec("FX.anyOf([{args}])"),
    "Not": FnSpec("!({a0})"),
    "User": FnSpec("FXUser()"),
    # date/time
    "Today": FnSpec("FX.today()"),
    "Now": FnSpec("FX.now()"),
    "Year": FnSpec("FX.year({a0})"),
    "Month": FnSpec("FX.month({a0})"),
    "Day": FnSpec("FX.day({a0})"),
    "Hour": FnSpec("FX.hour({a0})"),
    "Minute": FnSpec("FX.minute({a0})"),
    "Weekday": FnSpec("FX.weekday({a0})"),
    "DateAdd": FnSpec("FX.dateAdd({a0}, {a1}, {a2})"),
    "DateDiff": FnSpec("FX.dateDiff({a0}, {a1}, {a2})"),
    "Date": FnSpec("FX.date({a0}, {a1}, {a2})"),
    "Time": FnSpec("FX.time({a0}, {a1}, {a2})"),
    # tables
    "Filter": FnSpec("FX.filter({a0}, ({it}) => {a1})"),
    "ForAll": FnSpec("FX.forAll({a0}, ({it}) => {a1})"),
    "LookUp": FnSpec("FX.lookUp({a0}, ({it}) => {a1})"),
    "CountRows": FnSpec("FX.countRows({a0})"),
    "CountA": FnSpec("FX.countRows({a0})"),
    "CountIf": FnSpec("FX.countIf({a0}, ({it}) => {a1})"),
    "Concat": FnSpec("FX.concat({a0}, ({it}) => {a1}, {a2})"),
    "First": FnSpec("FX.first({a0})"),
    "Last": FnSpec("FX.last({a0})"),
    "Sort": FnSpec("FX.sort({a0}, ({it}) => {a1}, {a2})"),
    "SortByColumns": FnSpec("FX.sortByColumns({a0}, [{a1}], {a2})"),
    "Distinct": FnSpec("FX.distinct({a0}, ({it}) => ({a1}))"),
    "AddColumns": FnSpec("FX.addColumns({a0}, [{rest}])", "special-cased in emitter"),
    "Summarize": FnSpec("FX.unsupported('Summarize')"),
    # records / misc
    "JSON": FnSpec("JSON.stringify({a0})"),
    "Blank": FnSpec("null"),
    "With": FnSpec("(({{...{a0}}}) )", "special-cased in emitter"),
}


def js_for(name: str, argc: int) -> FnSpec | None:
    """Return the spec for a known function, or None if unmapped."""
    return FUNCTION_MAP.get(name)


UNMAPPED_WARNING = "function not in coverage map; requires LLM fallback or stub"
