"""Read ODT/FODT without changing source files or invoking an office suite."""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

NS = {
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'xlink': 'http://www.w3.org/1999/xlink',
    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'pg': 'urn:teify:conversion',
    'tei': 'http://www.tei-c.org/ns/1.0',
}
STYLE = f"{{{NS['text']}}}style-name"
OUTLINE = f"{{{NS['text']}}}outline-level"
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'


def qn(prefix, name):
    return f'{{{NS[prefix]}}}{name}'


def xml_parser():
    return etree.XMLParser(remove_blank_text=False, resolve_entities=False, no_network=True)


def plain_text(node, omit_citations=False):
    """ODF spaces/breaks are elements, not text nodes."""
    if omit_citations and node.tag == qn('text', 'note-citation'):
        return ''
    if node.tag == qn('text', 's'):
        return ' ' * int(node.get(qn('text', 'c'), '1'))
    if node.tag in (qn('text', 'line-break'), qn('text', 'tab')):
        return '\n' if node.tag == qn('text', 'line-break') else '\t'
    return (node.text or '') + ''.join(plain_text(child, omit_citations) + (child.tail or '') for child in node)


class ODFDocument:
    """A flat XML representation, including named styles from an ODT package."""

    def __init__(self, input_path):
        self.path = Path(input_path)
        if self.path.suffix.lower() == '.odt':
            with ZipFile(self.path) as archive:
                content = etree.fromstring(archive.read('content.xml'), xml_parser())
                root = etree.Element(qn('office', 'document'), nsmap=NS)
                for filename in ('meta.xml', 'styles.xml'):
                    if filename in archive.namelist():
                        part = etree.fromstring(archive.read(filename), xml_parser())
                        for child in part:
                            if child.tag in (qn('office', 'meta'), qn('office', 'styles'), qn('office', 'automatic-styles'), qn('office', 'font-face-decls')):
                                root.append(deepcopy(child))
                for child in content:
                    root.append(deepcopy(child))
                self.tree = etree.ElementTree(root)
        else:
            self.tree = etree.parse(str(self.path), xml_parser())
        self.root = self.tree.getroot()
        self.body = self.root.find('office:body/office:text', NS)
        if self.body is None:
            raise ValueError(f'No OpenDocument text body: {self.path}')
        self.warnings = []
        self.heading_changes = []

    def paragraphs(self):
        return self.body.xpath('.//text:p | .//text:h', namespaces=NS)

    def flow_paragraphs(self):
        return [node for node in self.paragraphs() if not node.xpath(
            'ancestor::text:note-body | ancestor::table:table | ancestor::draw:text-box | ancestor::text:table-of-content | ancestor::text:alphabetical-index | ancestor::text:user-index', namespaces=NS)]

    def save(self, output_path):
        self.tree.write(str(output_path), encoding='utf-8', xml_declaration=True)
