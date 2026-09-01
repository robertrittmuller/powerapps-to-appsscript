"""Power Fx lexer -> AST. Covers the subset needed by canvas app properties."""
from __future__ import annotations

from dataclasses import dataclass, field


class FxSyntaxError(Exception):
    pass


# --- Tokens ---------------------------------------------------------------

@dataclass
class Tok:
    kind: str  # ident number string op punct keyword
    value: str
    pos: int


IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IDENT_CHARS = IDENT_START | set("0123456789")
KEYWORDS = {"true", "false", "in", "and", "or", "not", "As"}


def tokenize(src: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c in IDENT_START:
            j = i
            while j < n and src[j] in IDENT_CHARS:
                j += 1
            word = src[i:j]
            # Power Fx allows dotted identifiers (control names, ThisItem.field)
            # and quoted enum members like Font.'Open Sans'
            while j < n - 1 and src[j] == "." and (src[j + 1] in IDENT_START or src[j + 1] in "\"'"):
                k = j + 1
                if src[k] in "\"'":
                    quote = src[k]
                    k += 1
                    while k < n and src[k] != quote:
                        k += 1
                    if k < n:
                        k += 1  # include closing quote
                    word += src[j:k]
                    j = k
                else:
                    while k < n and src[k] in IDENT_CHARS:
                        k += 1
                    word += src[j:k]
                    j = k
            toks.append(Tok("keyword" if word in KEYWORDS else "ident", word, i))
            i = j
            continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            seen_dot = False
            while j < n and (src[j].isdigit() or (src[j] == "." and not seen_dot)):
                if src[j] == ".":
                    seen_dot = True
                j += 1
            if j < n and src[j] == "%":  # percent literal: 20% == 0.2
                j += 1
                toks.append(Tok("number", src[i:j], i))
                i = j
                continue
            toks.append(Tok("number", src[i:j], i))
            i = j
            continue
        if src.startswith("//", i):  # Power Fx line comment
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c in "\"'":
            quote = c
            j = i + 1
            buf = []
            while j < n:
                if src[j] == quote:
                    if j + 1 < n and src[j + 1] == quote:  # doubled quote escape
                        buf.append(quote)
                        j += 2
                        continue
                    break
                if src[j] == "&" and j + 1 < n and src[j + 1] == "{":
                    # interpolation start &{ ... } — treat as op, close parsing at }
                    break
                buf.append(src[j])
                j += 1
            if j >= n:
                raise FxSyntaxError(f"unterminated string at {i}")
            toks.append(Tok("string", "".join(buf), i))
            i = j + 1
            continue
        if src.startswith("<>", i) or src.startswith("<=", i) or src.startswith(">=", i) \
                or src.startswith("&&", i) or src.startswith("||", i):
            toks.append(Tok("op", src[i:i + 2], i))
            i += 2
            continue
        if c in "+-*/=<>&!|":
            toks.append(Tok("op", c, i))
            i += 1
            continue
        if c == ".":
            # member access after an expression (e.g. LookUp(...).Name);
            # dotted identifiers were already merged during ident scanning
            toks.append(Tok("punct", c, i))
            i += 1
            continue
        if c in "()[],{}:;":
            toks.append(Tok("punct", c, i))
            i += 1
            continue
        if c == "%":
            # percent literal (Power Fx uses % as postfix in some locales) — treat as op
            toks.append(Tok("op", c, i))
            i += 1
            continue
        raise FxSyntaxError(f"unexpected character {c!r} at position {i}")
    toks.append(Tok("eof", "", n))
    return toks


# --- AST ------------------------------------------------------------------

@dataclass
class Node:
    kind: str
    value: object = None
    children: list["Node"] = field(default_factory=list)


BINARY_PRECEDENCE = {
    "in": 1, "or": 1, "||": 1,
    "and": 2, "&&": 2,
    "=": 3, "<>": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "+": 4, "-": 4, "&": 4,
    "*": 5, "/": 5, "%": 5,
}
RIGHT_ASSOC = {"^"}


class Parser:
    def __init__(self, toks: list[Tok]):
        self.toks = toks
        self.i = 0

    def peek(self) -> Tok:
        return self.toks[self.i]

    def next(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind: str, value: str | None = None) -> Tok:
        t = self.peek()
        if t.kind != kind or (value is not None and t.value != value):
            raise FxSyntaxError(f"expected {value or kind}, got {t.value!r} at {t.pos}")
        return self.next()

    def parse(self) -> Node:
        node = self.parse_expr(0)
        if self.peek().kind != "eof":
            # formula chains (a; b; c) are handled by the caller (parse_formula)
            raise FxSyntaxError(f"unexpected token {self.peek().value!r} at {self.peek().pos}")
        return node

    def parse_expr(self, min_prec: int) -> Node:
        left = self.parse_unary()
        while True:
            t = self.peek()
            op = None
            if t.kind == "op" and t.value in BINARY_PRECEDENCE:
                op = t.value
            elif t.kind == "keyword" and t.value in {"in", "and", "or"}:
                op = t.value
            if op is None or BINARY_PRECEDENCE[op] < min_prec:
                return left
            self.next()
            right = self.parse_expr(BINARY_PRECEDENCE[op] + 1)
            left = Node("binary", op, [left, right])

    def parse_unary(self) -> Node:
        t = self.peek()
        if t.kind == "op" and t.value in {"-", "!", "not"}:
            self.next()
            operand = self.parse_unary()
            return Node("unary", "not" if t.value in {"!", "not"} else "neg", [operand])
        return self.parse_postfix()

    def parse_postfix(self) -> Node:
        node = self.parse_primary()
        while True:
            t = self.peek()
            if t.kind == "punct" and t.value == ".":
                self.next()
                name = self.next()
                if name.kind not in {"ident", "keyword"}:
                    raise FxSyntaxError(f"expected identifier after '.', got {name.value!r}")
                node = Node("member", name.value, [node])
            elif t.kind == "punct" and t.value == "(":
                if node.kind != "ident":
                    raise FxSyntaxError(f"cannot call non-identifier at {t.pos}")
                self.next()
                args: list[Node] = []
                if not (self.peek().kind == "punct" and self.peek().value == ")"):
                    args.append(self.parse_expr(0))
                    while self.peek().kind == "punct" and self.peek().value == ",":
                        self.next()
                        args.append(self.parse_expr(0))
                self.expect("punct", ")")
                node = Node("call", node.value, args)
            else:
                return node

    def parse_primary(self) -> Node:
        t = self.peek()
        if t.kind == "number":
            self.next()
            if str(t.value).endswith("%"):
                return Node("num", float(t.value[:-1]) / 100.0)
            return Node("num", float(t.value) if "." in t.value else int(t.value))
        if t.kind == "string":
            self.next()
            return Node("str", t.value)
        if t.kind == "keyword" and t.value in {"true", "false"}:
            self.next()
            return Node("bool", t.value == "true")
        if t.kind == "keyword" and t.value == "not":
            self.next()
            return Node("unary", "not", [self.parse_unary()])
        if t.kind == "ident":
            self.next()
            return Node("ident", t.value)
        if t.kind == "punct" and t.value == "(":
            self.next()
            inner = self.parse_expr(0)
            self.expect("punct", ")")
            return inner
        if t.kind == "punct" and t.value == "[":
            return self.parse_table()
        if t.kind == "punct" and t.value == "{":
            return self.parse_record()
        raise FxSyntaxError(f"unexpected token {t.value!r} at {t.pos}")

    def parse_table(self) -> Node:
        self.expect("punct", "[")
        items: list[Node] = []
        if not (self.peek().kind == "punct" and self.peek().value == "]"):
            items.append(self.parse_expr(0))
            while self.peek().kind == "punct" and self.peek().value == ",":
                self.next()
                items.append(self.parse_expr(0))
        self.expect("punct", "]")
        return Node("table", None, items)

    def parse_record(self) -> Node:
        self.expect("punct", "{")
        fields: list[tuple[str, Node]] = []
        if not (self.peek().kind == "punct" and self.peek().value == "}"):
            while True:
                name = self.next()
                if name.kind not in {"ident", "keyword"}:
                    raise FxSyntaxError(f"expected field name, got {name.value!r}")
                self.expect("punct", ":")
                fields.append((name.value, self.parse_expr(0)))
                if self.peek().kind == "punct" and self.peek().value == ",":
                    self.next()
                    continue
                break
        self.expect("punct", "}")
        return Node("record", fields)


def parse_formula(src: str) -> list[Node]:
    """Parse a formula, returning a list of expression nodes chained by ';'."""
    toks = tokenize(src)
    statements: list[Node] = []
    p = Parser(toks)
    while p.peek().kind != "eof":
        statements.append(p.parse_expr(0))
        if p.peek().kind == "punct" and p.peek().value == ";":
            p.next()
        elif p.peek().kind != "eof":
            raise FxSyntaxError(f"unexpected token {p.peek().value!r}")
    return statements or [Node("blank")]
