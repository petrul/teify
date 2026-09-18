"""Small original fixtures exercise edge cases without distributing book files."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import pytest
from teify.converter import TEIConverter
from teify.document import NS, qn
from teify.pipeline import DocumentPipeline
from teify.tei import VerseNormalizer

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


@pytest.fixture
def converter():
    result = TEIConverter(ROOT / 'vendor/tei-stylesheets')
    if not (result.stylesheets / 'lib/saxon9he.jar').is_file():
        pytest.skip('Run scripts/setup-converter.sh for real stylesheet integration tests')
    return result


def fixture_document(marker='THE'):
    xml = f'''<office:document xmlns:office="{NS['office']}" xmlns:text="{NS['text']}" xmlns:style="{NS['style']}" xmlns:fo="{NS['fo']}" xmlns:draw="{NS['draw']}" xmlns:xlink="{NS['xlink']}">
    <office:styles>
      <style:style style:name="stanza" style:family="paragraph"><style:paragraph-properties fo:margin-left="1cm"/></style:style>
      <style:style style:name="emphasis" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>
      <style:style style:name="bold" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>
    </office:styles>
    <office:body><office:text>
      <text:p>Title: A Little Test Book</text:p>
      <text:p>Author: Writer, Ada</text:p>
      <text:p>Translator: Reader, Bea</text:p>
      <text:p>Editor: Editor, Celia</text:p>
      <text:p>Language: English</text:p>
      <text:p>This test is distributed under the Example Licence at https://example.org/license.</text:p>
      <text:p>*** START OF {marker} PROJECT GUTENBERG EBOOK TEST ***</text:p>
      <text:h text:outline-level="3">Part one</text:h>
      <text:p>Some <text:span text:style-name="emphasis">italic text</text:span> and<text:s text:c="3"/>spaces<text:tab/>after.</text:p>
      <text:h text:outline-level="5">A chapter</text:h>
      <text:p text:style-name="stanza">First <text:span text:style-name="bold">bold line<text:line-break/>Second bold</text:span> line<text:line-break/>Third line.</text:p>
      <text:p>A note<text:note text:id="note1" text:note-class="footnote"><text:note-citation>1</text:note-citation><text:note-body><text:p>Note content.</text:p></text:note-body></text:note></text:p>
      <text:p><draw:frame><draw:image xlink:href="Pictures/pixel.png"/></draw:frame></text:p>
      <text:h text:outline-level="4">Sibling chapter</text:h>
      <text:p>Final body paragraph.</text:p>
      <text:p>*** END OF THE PROJECT GUTENBERG EBOOK TEST ***</text:p>
      <text:p>Example Licence: permission for this synthetic fixture only.</text:p>
    </office:text></office:body></office:document>'''
    return etree.fromstring(xml.encode())


@pytest.mark.parametrize('kind', ['odt','fodt'])
@pytest.mark.parametrize('marker', ['THE','THIS'])
def test_full_conversion_metadata_structure_formatting_and_images(tmp_path, converter, kind, marker):
    root = fixture_document(marker)
    source = tmp_path / f'source.{kind}'
    if kind == 'odt':
        with ZipFile(source, 'w') as archive:
            content = etree.Element(qn('office','document-content'), nsmap=NS)
            content.append(deepcopy(root.find('office:body',NS)))
            styles = etree.Element(qn('office','document-styles'), nsmap=NS)
            styles.append(deepcopy(root.find('office:styles',NS)))
            archive.writestr('content.xml', etree.tostring(content))
            archive.writestr('styles.xml', etree.tostring(styles))
            archive.writestr('Pictures/pixel.png', PNG)
    else:
        image = root.find('.//draw:image',NS)
        image.attrib.clear()
        etree.SubElement(image,qn('office','binary-data')).text = base64.b64encode(PNG).decode()
        etree.ElementTree(root).write(str(source))
    original = source.read_bytes()
    output = DocumentPipeline(converter).run(source, tmp_path / 'output')[0]
    assert source.read_bytes() == original
    assert output.name == 'writer,ada-a_little_test_book.tei.xml'
    tree = etree.parse(str(output))
    def query(expression):
        return tree.xpath(expression,namespaces=NS)
    assert query('string(//tei:titleStmt/tei:title)') == 'A Little Test Book'
    assert query('string(//tei:titleStmt/tei:author)') == 'Writer, Ada'
    assert query('string(//tei:titleStmt/tei:respStmt/tei:name[@role="translator"])') == 'Reader, Bea'
    assert query('string(//tei:titleStmt/tei:editor)') == 'Editor, Celia'
    assert query('//tei:availability/tei:licence[@target="https://example.org/license"]')
    assert 'Example Licence: permission' in query('string(//tei:availability)')
    assert query('//tei:body/tei:div[tei:head="Part one"]/tei:div/tei:head/text()') == ['A chapter','Sibling chapter']
    assert not query('//tei:body//tei:div[not(node())]')
    assert query('//tei:hi[@style="font-style: italic"]/text()') == ['italic text']
    assert query('//tei:lg/tei:l/tei:hi[@style="font-weight: bold"]/text()') == ['bold line','Second bold']
    assert [''.join(line.itertext()) for line in query('//tei:lg/tei:l')] == ['First bold line','Second bold line','Third line.']
    assert query('//tei:lg[contains(@style,"margin-left: 1cm")]')
    assert query('//tei:space[@type="tab"]')
    assert 'and   spaces' in query('string(//tei:p[tei:space])')
    assert query('//tei:note[@n="1"]')
    image = query('//tei:graphic')[0]
    assert image.get('url') == 'writer,ada-a_little_test_book-figs.d/image-0001.png'
    assert (output.parent / image.get('url')).read_bytes() == PNG
    report = json.loads(next(output.parent.glob('*.report.json')).read_text())
    assert report['validation']['passed']
    assert report['validation']['text_mismatches'] == []
    with pytest.raises(ValueError, match='already exists'):
        DocumentPipeline(converter).run(source, output.parent)


def test_verse_breaks_inside_note_do_not_split_stanza():
    root = etree.fromstring(b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><p type="verse-stanza" xml:id="stanza">Line<note>note<lb/>continued</note><lb/>Next</p></TEI>')
    VerseNormalizer().normalize(root)
    assert len(root.xpath('//tei:lg/tei:l',namespaces=NS)) == 2
    assert len(root.xpath('//tei:note/tei:lb',namespaces=NS)) == 1
