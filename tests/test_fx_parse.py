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


def test_comments_do_not_strip_string_contents_or_following_code():
    nodes = lx.parse_formula('/* intro ; () */ Set(url, "https://a/*literal*/"); // comment\nSet(done, true)')
    assert len(nodes) == 2
    assert nodes[0].children[1].value == 'https://a/*literal*/'
    with pytest.raises(lx.FxSyntaxError, match="unterminated block comment"):
        lx.parse_formula("Set(x, 1); /* unfinished")


def test_nested_behavior_chain_is_one_argument():
    node = lx.parse_formula("If(true, Set(x, 1); Set(y, 2), Set(x, 3))")[0]
    assert len(node.children) == 3
    assert node.children[1].kind == "chain"
    assert len(node.children[1].children) == 2
