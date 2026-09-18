"""Tiny generated fixtures for bugs found in 49 books; no extra book copies."""
import json
from pathlib import Path

from lxml import etree
import pytest

from teify.document import NS, qn, ODFDocument
from teify.drawings import EnhancedPath, render
from teify.metadata import MetadataExtractor
from teify.naming import OutputPaths
from teify.pipeline import DocumentPipeline
from teify.styles import StyleResolver
from test_conversion import converter


def document(tmp_path, content):
    root = etree.Element(qn('office','document'), nsmap=NS)
    body = etree.SubElement(etree.SubElement(root,qn('office','body')),qn('office','text'))
    fragment = etree.fromstring(('<root ' + ' '.join(f'xmlns:{k}="{v}"' for k,v in NS.items()) + '>' + content + '</root>').encode())
    body.extend(fragment)
    source = tmp_path / 'regression.fodt'
    etree.ElementTree(root).write(str(source),encoding='utf-8')
    return source


@pytest.mark.parametrize('author', ['Writer, Ada', ''])
def test_late_multiline_credits_and_explicitly_blank_author(tmp_path, author):
    source = document(tmp_path, '<text:p>cover fragment</text:p>' * 530 + f'''
      <text:p>www.liberliber.it</text:p>
      <text:p>TITOLO: A title<text:line-break/>continued on another line</text:p>
      <text:p>AUTORE: {author}</text:p>
      <text:p>LICENZA: Example fixture licence</text:p>
    ''')
    metadata = MetadataExtractor().extract(ODFDocument(source))
    assert metadata.title == 'A title\ncontinued on another line'
    assert metadata.authors == ([author] if author else [])
    assert metadata.profile == 'liberliber'
    if not author:
        assert any('explicitly blank' in warning for warning in metadata.warnings)
        assert OutputPaths.for_book(tmp_path,metadata).xml.name.startswith('unattributed-')


def test_references_indexes_lists_and_drawings_preserve_content(tmp_path, converter):
    source = document(tmp_path, '''
      <text:p>Title: Regression anthology</text:p><text:p>Author: Writer, Ada</text:p>
      <text:p>*** START OF THE PROJECT GUTENBERG EBOOK TEST ***</text:p>
      <text:p><text:bookmark-start text:name="A B"/>First<text:bookmark-end text:name="A B"/>
        <text:bookmark text:name="A_B"/>Second
        <text:reference-mark text:name="3 author's note"/>Third
        <text:reference-mark-start text:name="range"/>Range<text:reference-mark-end text:name="range"/>
      </text:p>
      <text:p><text:a xlink:href="#A%20B">Bookmark</text:a>
        <text:bookmark-ref text:ref-name="A_B">Other bookmark</text:bookmark-ref>
        <text:reference-ref text:ref-name="3 author's note">Reference</text:reference-ref>
        <text:reference-ref text:ref-name="range">Range reference</text:reference-ref>
        <text:alphabetical-index-mark text:string-value="HIDDEN INDEX TERM"/>
        <text:user-index-mark text:index-name="corrections" text:string-value="HIDDEN CORRECTION"/>
        <text:alphabetical-index-mark-start text:id="index range"/>Indexed words<text:alphabetical-index-mark-end text:id="index range"/>
      </text:p>
      <text:list><text:list-header><text:h text:outline-level="1">Part one</text:h></text:list-header></text:list>
      <text:p>Body one.</text:p>
      <text:list><text:list-header><text:h text:outline-level="1">Part two</text:h></text:list-header>
        <text:list-item><text:h text:outline-level="2">Chapter</text:h><text:p>Body two.</text:p></text:list-item>
      </text:list>
      <text:list><text:list-header><text:p>List preamble</text:p></text:list-header><text:list-item><text:p>A real list item</text:p></text:list-item></text:list>
      <text:alphabetical-index><text:index-body>
        <text:index-title><text:p>Printed index</text:p></text:index-title>
        <text:p>Apple<text:tab/>7</text:p>
      </text:index-body></text:alphabetical-index>
      <text:p>Before <draw:rect><text:p/></draw:rect> after.</text:p>
      <text:p>Before line <draw:line xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" svg:x1="1cm" svg:y1="2cm" svg:x2="3cm" svg:y2="2cm"><text:p/></draw:line> after line.</text:p>
      <table:table table:name="merged">
        <table:table-row><table:table-cell table:number-rows-spanned="3"><text:p>Spanning cell</text:p></table:table-cell><table:table-cell table:number-rows-spanned="2"><text:p>Second column</text:p></table:table-cell></table:table-row>
        <table:table-row><table:covered-table-cell/><table:covered-table-cell/></table:table-row>
        <table:table-row><table:covered-table-cell/><table:table-cell><text:p>Last row</text:p></table:table-cell></table:table-row>
      </table:table>
      <text:p><draw:custom-shape><text:p/>
        <draw:enhanced-geometry draw:type="right-brace" draw:modifiers="10 20" draw:enhanced-path="M 0 0 C 5 0 10 ?f0 10 ?f1 L 10 $1 N">
          <draw:equation draw:name="f0" draw:formula="$0 / 2"/>
          <draw:equation draw:name="f1" draw:formula="?f0 + 5"/>
        </draw:enhanced-geometry>
      </draw:custom-shape></text:p>
    ''')
    original = source.read_bytes()
    output = DocumentPipeline(converter).run(source,tmp_path/'out')[0]
    assert source.read_bytes() == original
    tree = etree.parse(str(output))
    report = json.loads(next(output.parent.glob('*.report.json')).read_text())
    assert report['validation']['passed']
    assert report['validation']['text_mismatches'] == []
    assert report['validation']['warnings'] == []
    ids = tree.xpath('//@xml:id')
    assert len(ids) == len(set(ids))
    for target in tree.xpath('//tei:ref/@target | //tei:ptr/@target',namespaces=NS):
        assert target[1:] in ids
    visible = tree.xpath('string(//tei:body)',namespaces=NS)
    assert 'HIDDEN' not in visible
    assert tree.xpath('//tei:anchor[contains(@n,"HIDDEN CORRECTION")]',namespaces=NS)
    assert tree.xpath('//tei:body/tei:div/tei:head/text()',namespaces=NS) == ['Part one','Part two']
    assert tree.xpath('//tei:div[tei:head="Part two"]/tei:div/tei:head/text()',namespaces=NS) == ['Chapter']
    assert tree.xpath('//tei:list/tei:item/tei:p[text()="A real list item"]',namespaces=NS)
    drawings = list(output.parent.rglob('drawing-*.svg'))
    assert len(drawings) == 3
    paths = [n.get('d') for p in drawings for n in etree.parse(str(p)).xpath('//*[local-name()="path"]')]
    assert paths == ['M 0 0 C 5 0 10 5 10 10 L 10 20']
    lines = [n for p in drawings for n in etree.parse(str(p)).xpath('//*[local-name()="line"]')]
    assert len(lines) == 1
    assert [lines[0].get(key) for key in ('x1','y1','x2','y2')] == ['10','20','30','20']
    assert tree.xpath('//tei:list[@type="index"]/tei:item/tei:p/text()',namespaces=NS) == ['Printed index','Apple','7']
    assert len(tree.xpath('//tei:table/tei:row',namespaces=NS)) == 2
    assert tree.xpath('//tei:table/tei:row[1]/tei:cell/@rows',namespaces=NS) == ['2','1']
    assert any('fully covered' in warning for warning in report['warnings'])


@pytest.mark.parametrize('formula', ['?f0 + 1', '__import__("os")', '1 / 0'])
def test_unsupported_drawing_equations_fail_instead_of_guessing(formula):
    geometry = etree.Element(qn('draw','enhanced-geometry'))
    etree.SubElement(geometry,qn('draw','equation'),{qn('draw','name'):'f0',qn('draw','formula'):formula})
    with pytest.raises((ValueError,ZeroDivisionError)):
        EnhancedPath(geometry).convert('M 0 0 L ?f0 10 N')


def test_missing_image_and_transformed_drawing_require_source_review(tmp_path):
    from teify.graphics import GraphicsExporter
    source = document(tmp_path, '<text:p><draw:frame><draw:image xlink:href="data:"/></draw:frame></text:p>')
    with pytest.raises(ValueError,match='local source'):
        GraphicsExporter().export(ODFDocument(source),tmp_path/'figures','figures')
    source = document(tmp_path, '<text:p><draw:custom-shape draw:transform="rotate(-1.57)"/></text:p>')
    doc = ODFDocument(source)
    shape = doc.body.find('.//draw:custom-shape',NS)
    with pytest.raises(ValueError,match='manual rendering'):
        render(shape,StyleResolver(doc))
