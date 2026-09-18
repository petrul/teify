"""Composable normalization stages; conversion does not guess bibliographical fields."""
from .document import ODFDocument, NS, STYLE, OUTLINE, qn, plain_text
from .styles import StyleResolver, FormattingAnnotator
from .references import ReferenceNormalizer

FODTDocument = ODFDocument


class HeadingStyleResolver(StyleResolver):
    resolve = StyleResolver.heading_level


class TableNormalizer:
    """Remove wholly covered layout rows, adjusting spans across those rows.

    TEI rows require a real cell; inventing placeholder cells would shift the
    columns. Covered rows contain no independent cells or text to preserve.
    """
    def normalize(self, document):
        for table in document.body.xpath('.//table:table', namespaces=NS):
            rows = [r for r in table.xpath('.//table:table-row', namespaces=NS)
                    if r.xpath('ancestor::table:table[1]', namespaces=NS)[0] is table]
            covered = {i for i,r in enumerate(rows) if len(r) and
                       all(c.tag == qn('table','covered-table-cell') and not len(c) and not (c.text or '').strip() for c in r)}
            if not covered:
                continue
            if any(int(r.get(qn('table','number-rows-repeated'),'1')) != 1 for r in rows):
                raise ValueError('Repeated covered table rows require manual markup')
            for i,row in enumerate(rows):
                for cell in row.findall('table:table-cell',NS):
                    attribute = qn('table','number-rows-spanned')
                    span = int(cell.get(attribute,'1'))
                    adjusted = span - sum(i < j < i+span for j in covered)
                    if adjusted != span:
                        cell.set(attribute,str(adjusted))
            for i in sorted(covered,reverse=True):
                rows[i].getparent().remove(rows[i])
            document.warnings.append(f'Collapsed {len(covered)} fully covered table row(s); merged-cell spans adjusted, review table layout')


class HeadingNormalizer:
    """Use an ancestor stack to repair missing levels without empty divisions."""
    EXCLUDED_STYLES = {'PGFrontMatter', 'PGBoundaryMarker', 'Title', 'Author'}

    def heading_level(self, paragraph, resolver):
        if paragraph.get(STYLE) in self.EXCLUDED_STYLES:
            return None
        value = paragraph.get(OUTLINE)
        if paragraph.tag == qn('text', 'h') and value:
            level = int(value)
            if level < 1:
                raise ValueError('Heading outline levels must be positive')
            return level
        return resolver.heading_level(paragraph.get(STYLE))

    def normalize(self, document):
        resolver = StyleResolver(document)
        stack = []
        for paragraph in document.flow_paragraphs():
            original = self.heading_level(paragraph, resolver)
            if original is None:
                continue
            if not plain_text(paragraph).strip():
                # Empty styled lines are layout, not section ancestors. Keep
                # their contents/identity but do not nest subsequent chapters.
                paragraph.tag = qn('text', 'p')
                paragraph.attrib.pop(OUTLINE, None)
                document.heading_changes.append({'text': '', 'original': original, 'normalized': None})
                continue
            while stack and stack[-1] >= original:
                stack.pop()
            stack.append(original)
            normalized = len(stack)
            paragraph.tag = qn('text', 'h')
            paragraph.set(OUTLINE, str(normalized))
            paragraph.set(qn('pg', 'original-level'), str(original))
            if normalized != original:
                document.heading_changes.append({'text': ''.join(paragraph.itertext())[:160], 'original': original, 'normalized': normalized})


class FODTNormalizer:
    """Compose replaceable stages for an ODT or FODT document."""
    def __init__(self, input_path, stages=None):
        self.document = ODFDocument(input_path)
        self.stages = stages if stages is not None else (TableNormalizer(), HeadingNormalizer(), FormattingAnnotator(), ReferenceNormalizer())

    def normalize(self):
        for stage in self.stages:
            stage.normalize(self.document)
        return self

    def save(self, output_path):
        self.document.save(output_path)
