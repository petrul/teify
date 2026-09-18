"""Check TEI schema, source text coverage, structure, and local graphics."""
from functools import lru_cache
from importlib.resources import files
import re
from pathlib import Path
from lxml import etree
from .document import NS, XML_ID, plain_text, qn


def compact(value):
    return re.sub(r'\s+', '', value)


@lru_cache(maxsize=2)
def schema_at(path):
    return etree.RelaxNG(etree.parse(str(path)))


class ConversionValidator:
    def __init__(self, schema=None):
        self.schema = Path(schema) if schema else Path(str(files('teify').joinpath('resources/tei_all.rng')))

    def validate(self, document, tree, output_directory):
        root = tree.getroot()
        errors = []
        warnings = []
        schema = schema_at(str(self.schema))
        schema_valid = schema.validate(tree)
        if not schema_valid:
            errors.extend(str(item) for item in list(schema.error_log)[:30])
        by_id = {node.get(XML_ID): node for node in root.xpath('//*[@xml:id]')}
        mismatches = []
        for source in document.paragraphs():
            identifier = source.get(qn('pg', 'id'))
            target = by_id.get(identifier)
            expected = compact(plain_text(source, omit_citations=True))
            actual = compact(''.join(target.itertext())) if target is not None else None
            if actual != expected:
                mismatches.append({'id':identifier, 'expected':expected[:160], 'actual':actual[:160] if actual is not None else None})
        expected_order = [node.get(qn('pg', 'id')) for node in document.paragraphs()]
        expected_ids = set(expected_order)
        actual_order = [node.get(XML_ID) for node in root.xpath('//tei:body//*[@xml:id]', namespaces=NS) if node.get(XML_ID) in expected_ids]
        if actual_order != expected_order:
            errors.append('Source paragraph order changed or identifiers were duplicated/lost')
        if mismatches:
            errors.append(f'{len(mismatches)} source paragraphs/headings failed text preservation')
        counts = {}
        for name, source_xpath, target_xpath in [
            ('headings', './/text:h[not(ancestor::text:note-body or ancestor::table:table or ancestor::draw:text-box or ancestor::text:table-of-content or ancestor::text:alphabetical-index or ancestor::text:user-index)]', '//tei:head'),
            ('notes', './/text:note', '//tei:body//tei:note'),
            ('tables', './/table:table', '//tei:body//tei:table'),
            ('graphics', './/draw:image', '//tei:body//tei:graphic'),
        ]:
            source_count = len(document.body.xpath(source_xpath, namespaces=NS))
            target_count = len(root.xpath(target_xpath, namespaces=NS))
            counts[name] = {'source':source_count, 'tei':target_count}
            if source_count != target_count:
                errors.append(f'{name}: source={source_count}, TEI={target_count}')
        source_speakers = len(document.body.xpath('.//*[@pg:drama="speaker"]', namespaces=NS))
        target_speakers = len(root.xpath('//tei:body//tei:sp/tei:speaker', namespaces=NS))
        counts['speakers'] = {'source': source_speakers, 'tei': target_speakers}
        if source_speakers != target_speakers:
            errors.append(f'Speaker mismatch: source={source_speakers}, TEI={target_speakers}')
        stanza_count = len(root.xpath('//tei:lg[@type="stanza"]', namespaces=NS))
        line_count = len(root.xpath('//tei:lg[@type="stanza"]/tei:l', namespaces=NS))
        source_breaks = len(document.body.xpath('.//text:line-break', namespaces=NS))
        target_breaks = len(root.xpath('//tei:body//tei:lb', namespaces=NS)) + line_count - stanza_count
        counts['line_breaks'] = {'source':source_breaks, 'tei':target_breaks}
        if source_breaks != target_breaks:
            errors.append(f'Line break mismatch: source={source_breaks}, TEI={target_breaks}')
        for image in root.xpath('//tei:graphic', namespaces=NS):
            path = Path(output_directory) / image.get('url', '')
            if not path.is_file():
                errors.append(f'Missing external graphic: {image.get("url")}')
        if root.xpath('//tei:HEAD', namespaces=NS):
            errors.append('Unconverted heading markers remain')
        if '[[[UNTRANSLATED' in ''.join(root.itertext()):
            errors.append('Upstream converter left untranslated ODF elements')
        for reference in root.xpath('//tei:ref[starts-with(@target,"#")]', namespaces=NS):
            if reference.get('target')[1:] not in by_id:
                warnings.append(f'Unresolved source link: {reference.get("target")}')
        return {
            'passed': not errors, 'schema_valid': schema_valid,
            'source_paragraphs_checked': len(document.paragraphs()),
            'text_mismatches': mismatches, 'counts': counts,
            'speeches': target_speakers, 'stage_directions': len(root.xpath('//tei:body//tei:stage', namespaces=NS)),
            'stanzas': stanza_count, 'verse_lines': line_count,
            'max_div_depth': max((len(node.xpath('ancestor-or-self::tei:div', namespaces=NS)) for node in root.xpath('//tei:body//tei:div', namespaces=NS)), default=0),
            'errors': errors, 'warnings': sorted(set(warnings)),
        }
