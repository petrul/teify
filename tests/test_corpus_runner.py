from pathlib import Path

from lxml import etree

from teify.corpus import CorpusRunner
from test_conversion import converter, fixture_document


def test_corpus_isolates_failures_and_resumes_without_overwriting(tmp_path, converter):
    source = tmp_path / 'input'
    source.mkdir()
    for name in ('a', 'b'):
        folder = source / name
        folder.mkdir()
        # No pictures in this fixture: focus on corpus orchestration.
        root = fixture_document()
        from teify.document import NS
        frame = root.find('.//draw:frame', NS)
        frame.getparent().remove(frame)
        etree.ElementTree(root).write(str(folder / 'same.fodt'))
    (source / 'broken.odt').write_bytes(b'not a zip')
    (source / 'unsupported.pdf').write_bytes(b'not converted')
    output = tmp_path / 'output'
    runner = CorpusRunner(source, output, converter.stylesheets, jobs=2)
    first = runner.run()
    assert first['state'] == 'complete'
    assert first['counts'] == {'converted': 2, 'failed': 1, 'unsupported': 1}
    files = list(output.rglob('*.tei.xml'))
    assert len(files) == 2
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    second = runner.run()
    assert second['submitted'] == 0
    assert second['counts'] == first['counts']
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    files[0].unlink()
    third = runner.run()
    assert third['submitted'] == 1
    assert third['counts'] == first['counts']
    assert len(list(output.rglob('*.tei.xml'))) == 2
