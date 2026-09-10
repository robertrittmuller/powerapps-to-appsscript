"""Execute the bounded SVG text repair and preserve unrelated EncodeUrl semantics."""
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote
from xml.etree import ElementTree

import pytest

from pfx2gas.fx import transpile

REPO = Path(__file__).resolve().parent.parent
OPEN = "<svg xmlns='http://www.w3.org/2000/svg'><text>"
CLOSE = '</text></svg>'


def quote(text):
    return '"' + text.replace('"', '""') + '"'


def formula(before=OPEN, value='Input.Text', after=CLOSE):
    return 'EncodeUrl(' + quote(before) + ' & ' + value + ' & ' + quote(after) + ')'


@pytest.mark.parametrize('value', ['Hello World', 'Café 東京', 'R&D <teams> "ready"', "'yes'", '',
                                 '&amp;', '<tspan fill="red">markup</tspan>', ']]>', None])
def test_svg_text_is_literal_decodable_and_ledgered(value):
    result = transpile(formula(), control_names={'Input'})
    assert not result.unmapped and len(result.approximations) == 1
    assert 'SVG literal text repair' in result.approximations[0]
    script = ('const FX=require("./static/fx-stdlib.js"); const val=()=>({text:' + json.dumps(value) + '});'
              'process.stdout.write(' + result.js + ');')
    run = subprocess.run(['node', '-e', script], cwd=REPO, capture_output=True, text=True, timeout=10, check=True)
    root = ElementTree.fromstring(unquote(run.stdout))
    assert ''.join(root.itertext()) == (value or '')
    assert len(list(root.iter())) == 2  # markup-shaped input must not create SVG elements


def test_svg_text_handles_quoted_control_aliases_nested_tspans_and_repeated_references():
    raw = formula(OPEN + '<tspan>', "'Input caption'.Text", '</tspan> / ')[:-1]
    raw += ' & Input.Text & ' + quote(CLOSE) + ')'
    result = transpile(raw, control_names={'Input'}, control_aliases={'Input caption':'Input'})
    assert result.js.count('FX.xmlText(') == 2
    assert len(result.approximations) == 1


def test_svg_repair_does_not_escape_attribute_or_cdata_reference_beside_literal_text():
    raw = ('EncodeUrl(' + quote("<svg xmlns='http://www.w3.org/2000/svg' data-note='") + ' & Input.Text & '
           + quote("'><text><![CDATA[") + ' & Input.Text & ' + quote(']]>') + ' & Input.Text & ' + quote(CLOSE) + ')')
    result = transpile(raw, control_names={'Input'})
    assert result.js.count('FX.xmlText(') == 1
    assert result.js.count("val('Input').text") == 3


@pytest.mark.parametrize('raw,controls', [
    ('EncodeUrl("https://example.test/?q=" & Input.Text)', {'Input'}),
    ('EncodeUrl(svgTemplate)', {'Input'}),
    (formula(value='Concat(Items, Name)'), {'Input'}),
    (formula(value='Unknown.Text'), {'Input'}),
    (formula(), set()),
    (formula(OPEN+'<![CDATA[', after=']]>'+CLOSE), {'Input'}),
    (formula("<svg xmlns='http://www.w3.org/2000/svg'><text data-note='", after="'>static"+CLOSE), {'Input'}),
    (formula("<svg xmlns='http://www.w3.org/2000/svg'><style>", after='</style></svg>'), {'Input'}),
    (formula('<html><text>', after='</text></html>'), {'Input'}),
    (formula('<svg><text>'), {'Input'}),
    (formula('<!DOCTYPE svg [<!ENTITY value "expanded">]>'+OPEN), {'Input'}),
    (formula(OPEN, after='</missing></svg>'), {'Input'}),
    ('With({Text:"local"} As Input, '+formula()+')', {'Input'}),
])
def test_svg_repair_does_not_rewrite_other_encodeurl_expressions(raw,controls):
    result = transpile(raw, control_names=controls)
    assert 'FX.xmlText' not in result.js
    assert not any('SVG literal text repair' in note for note in result.approximations)
