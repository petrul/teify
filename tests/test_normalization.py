from pathlib import Path
from lxml import etree
import pytest
from teify.cli import main
from teify.document import NS, STYLE, OUTLINE, ODFDocument, qn
from teify.metadata import MetadataExtractor
from teify.normalizer import FODTNormalizer
from teify.naming import OutputPaths
from teify.metadata import BookMetadata
from teify.styles import StyleResolver


def make_document(tmp_path, levels=(3, 5, 4, 3, 1, 4)):
    root = etree.Element(qn('office', 'document'), nsmap=NS)
    styles = etree.SubElement(root, qn('office', 'styles'))
    for name, parent in [('CustomHeading','Heading_20_3'), ('CycleA','CycleB'), ('CycleB','CycleA')]:
        etree.SubElement(styles, qn('style','style'), {qn('style','name'):name, qn('style','family'):'paragraph', qn('style','parent-style-name'):parent})
    body = etree.SubElement(etree.SubElement(root, qn('office','body')), qn('office','text'))
    etree.SubElement(body, qn('text','p')).text = 'Source preface without a Gutenberg marker.'
    for index, level in enumerate(levels):
        heading = etree.SubElement(body, qn('text','h'), {STYLE:'CustomHeading', OUTLINE:str(level)})
        heading.text = f'Section {index}'
        etree.SubElement(body, qn('text','p')).text = 'Body text.'
    path = tmp_path / 'book.fodt'
    etree.ElementTree(root).write(str(path))
    return path


def test_heading_stack_repairs_gaps_without_inventing_parents(tmp_path):
    source = make_document(tmp_path)
    original = source.read_bytes()
    normalizer = FODTNormalizer(source).normalize()
    headings = normalizer.document.root.xpath('//text:h', namespaces=NS)
    assert [int(h.get(OUTLINE)) for h in headings] == [1,2,2,1,1,2]
    assert all(h.get(STYLE) == 'CustomHeading' for h in headings)
    assert source.read_bytes() == original
    assert normalizer.document.paragraphs()[0].get(STYLE) is None


def test_style_resolution_and_cycles(tmp_path):
    resolver = StyleResolver(ODFDocument(make_document(tmp_path)))
    assert resolver.heading_level('CustomHeading') == 3
    assert resolver.heading_level('CycleA') is None


def test_empty_heading_is_preserved_without_creating_section_ancestor(tmp_path):
    source = make_document(tmp_path, levels=(1, 2, 3))
    document = ODFDocument(source)
    document.root.find('.//text:h', NS).text = ' '
    document.save(source)
    normalized = FODTNormalizer(source).normalize().document
    assert [int(h.get(OUTLINE)) for h in normalized.body.findall('text:h', NS)] == [1, 2]
    assert len(normalized.paragraphs()) == len(document.paragraphs())
    assert normalized.paragraphs()[1].tag == qn('text', 'p')
    assert normalized.paragraphs()[1].text == ' '


def test_cli_preserves_existing_output(tmp_path):
    source = make_document(tmp_path)
    output = tmp_path / 'output.fodt'
    assert main(['normalize', str(source), str(output)]) == 0
    original = output.read_bytes()
    assert main(['normalize', str(source), str(output)]) == 1
    assert output.read_bytes() == original


def test_unknown_source_requires_explicit_author_and_title(tmp_path):
    document = ODFDocument(make_document(tmp_path))
    with pytest.raises(ValueError, match='reliably identify'):
        MetadataExtractor().extract(document)
    metadata = MetadataExtractor().extract(document, {'title':'Known title', 'authors':['Writer, A.']})
    assert metadata.title == 'Known title'
    assert metadata.licences == []
    assert metadata.warnings


def test_full_title_filename_and_long_name_collision_protection(tmp_path):
    book = BookMetadata(title='Il Napoleone di Notting Hill', authors=['Chesterton, Gilbert Keith'])
    paths = OutputPaths.for_book(tmp_path, book)
    assert paths.xml.name == 'chesterton,gilbert_keith-il_napoleone_di_notting_hill.tei.xml'
    assert paths.figures.name == 'chesterton,gilbert_keith-il_napoleone_di_notting_hill-figs.d'
    book.title = 'Long title ' * 100 + 'one'
    first = OutputPaths.for_book(tmp_path, book)
    book.title = 'Long title ' * 100 + 'two'
    second = OutputPaths.for_book(tmp_path, book)
    assert first.xml != second.xml
    assert len(first.figures.name.encode()) < 255


def test_empty_directory_fails(tmp_path):
    source = tmp_path / 'empty'
    source.mkdir()
    assert main(['normalize', str(source), str(tmp_path / 'out')]) == 1
