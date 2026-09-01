"""Tests for the Power Fx lexer/parser."""
import pytest

from pfx2gas.fx import lexer as lx


def test_tokenize_ident_dotted():
    toks = lx.tokenize("ThisItem.Name")
    assert [t.value for t in toks if t.kind != "eof"] == ["ThisItem.Name"]


def test_tokenize_ops():
    toks = lx.tokenize("a && b || !c")
    values = [t.value for t in toks if t.kind != "eof"]
    assert "&&" in values and "||" in values


def test_parse_binary_precedence():
    ast = lx.parse_formula('Amount > 100 && Status = "Open"')
    assert ast[0].kind == "binary"


def test_parse_call_with_lambda_arg():
    ast = lx.parse_formula("Filter(Tasks, Amount > 100)")
    call = ast[0]
    assert call.kind == "call" and call.value == "Filter"
    assert call.children[1].kind == "binary"


def test_parse_record():
    ast = lx.parse_formula('{Name: TextInput1.Text, Amount: Value(TextInputAmount.Text)}')
    rec = ast[0]
    assert rec.kind == "record"
    names = [n for n, _ in rec.value]
    assert names == ["Name", "Amount"]


def test_parse_chain_statements():
    stmts = lx.parse_formula('Set(counter, counter + 1); Navigate(Screen2)')
    assert len(stmts) == 2
    assert stmts[0].kind == "call"
    assert stmts[1].kind == "call"


def test_parse_member_chain():
    ast = lx.parse_formula("LookUp(Tasks, Id = 5).Name")
    node = ast[0]
    assert node.kind == "member"
    assert node.value == "Name"


def test_syntax_error_raises():
    with pytest.raises(lx.FxSyntaxError):
        lx.parse_formula("Filter(Tasks, Amount > )")
