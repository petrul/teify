"""Opt-in real-book regressions. Add a case to corpus/works.json for each new work."""
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import pytest
from teify.converter import TEIConverter
from teify.document import NS
from teify.pipeline import DocumentPipeline

CASES = json.loads((Path(__file__).parent / 'corpus/works.json').read_text())
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.corpus
@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_exemplary_work(case, tmp_path):
    if os.environ.get('TEIFY_CORPUS_OUTPUT'):
        tmp_path = Path(os.environ['TEIFY_CORPUS_OUTPUT']) / case['id']
        tmp_path.mkdir(parents=True, exist_ok=False)
    corpus = Path(os.environ.get('TEIFY_CORPUS', ROOT / 'samples/selected'))
    source = corpus / case['source']
    if not source.is_file():
        if os.environ.get('TEIFY_REQUIRE_CORPUS') == '1':
            pytest.fail(f'Missing required corpus file: {source}')
        pytest.skip(f'Local corpus file unavailable: {source.name}')
    converter = TEIConverter(Path(os.environ.get('TEIFY_STYLESHEETS', ROOT / 'vendor/tei-stylesheets')))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = DocumentPipeline(converter).run(source, tmp_path)[0]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert output.name == case['filename']
    tree = etree.parse(str(output))
    report = json.loads(output.with_name(output.name.removesuffix('.tei.xml') + '.report.json').read_text())
    validation = report['validation']
    assert validation['passed'] and validation['schema_valid']
    assert validation['text_mismatches'] == []
    assert validation['warnings'] == []
    assert tree.xpath('string(/tei:TEI/tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title)', namespaces=NS) == case['title']
    for key, xpath in [('authors', 'tei:author'), ('editors', 'tei:editor'), ('translators', 'tei:respStmt/tei:name[@role="translator"]')]:
        assert tree.xpath('/tei:TEI/tei:teiHeader/tei:fileDesc/tei:titleStmt/' + xpath + '/text()', namespaces=NS) == case[key]
    licenses = tree.xpath('/tei:TEI/tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:availability/tei:licence', namespaces=NS)
    assert len(licenses) == 1
    assert 'liberliber.it/' in licenses[0].get('target')
    assert ''.join(licenses[0].itertext()) == report['metadata']['fields']['LICENZA']
    assert tree.xpath('//tei:sourceDesc/tei:bibl[1]/text()', namespaces=NS) == [report['metadata']['source']]
    for key in ('headings', 'notes', 'tables', 'graphics'):
        assert validation['counts'][key]['tei'] == case[key]
    assert validation['speeches'] == case.get('speeches', 0)
    assert validation['stage_directions'] == case.get('stage_directions', 0)
    assert validation['stanzas'] == case['stanzas']
    assert validation['verse_lines'] == case['verse_lines']
    assert validation['max_div_depth'] == case['depth']
    container = tree.find('tei:text/tei:body', NS)
    for heading in case['heading_path']:
        candidates = [div for div in container.findall('tei:div', NS) if div.find('tei:head', NS) is not None and ''.join(div.find('tei:head', NS).itertext()) == heading]
        assert len(candidates) == 1, heading
        container = candidates[0]
    if 'first_heading_original_level' in case:
        first = tree.xpath('//tei:body//tei:head', namespaces=NS)[0]
        assert first.get('n') == str(case['first_heading_original_level'])
        assert len(first.xpath('ancestor::tei:div', namespaces=NS)) == 1
    assert tree.xpath('//*[contains(@style,"font-style: italic")]', namespaces=NS), 'Italic formatting was lost'
    figure_dir = tmp_path / (output.name.removesuffix('.tei.xml') + '-figs.d')
    assert figure_dir.is_dir()
    assert len(list(figure_dir.glob('drawing-*.svg'))) == case.get('svg_drawings', 0)
    with ZipFile(source) as archive:
        for original, target in report['graphics'].items():
            if not original.startswith('drawing-'):
                assert (tmp_path / target).read_bytes() == archive.read(original.removeprefix('./'))
    for graphic in tree.xpath('//tei:graphic', namespaces=NS):
        assert graphic.get('url').startswith(figure_dir.name + '/')
        assert (tmp_path / graphic.get('url')).is_file()
