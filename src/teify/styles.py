"""Resolve inherited ODF styles and preserve representable formatting as CSS."""
import re
from .document import NS, STYLE, qn


class StyleResolver:
    def __init__(self, document):
        self.styles = {}
        self.defaults = {}
        for node in document.root.xpath('//style:style', namespaces=NS):
            self.styles[(node.get(qn('style', 'family')), node.get(qn('style', 'name')))] = node
        for node in document.root.xpath('//style:default-style', namespaces=NS):
            self.defaults[node.get(qn('style', 'family'))] = node

    @staticmethod
    def decode(name):
        return re.sub(r'_([0-9a-fA-F]{2})_', lambda m: chr(int(m[1], 16)), name or '')

    def chain(self, name, family='paragraph'):
        seen = set()
        while name and name not in seen:
            seen.add(name)
            yield name
            node = self.styles.get((family, name))
            name = node.get(qn('style', 'parent-style-name')) if node is not None else None

    def properties(self, name, family='paragraph'):
        nodes = [self.styles.get((family, key)) for key in self.chain(name, family)]
        nodes.append(self.defaults.get(family))
        properties = {}
        for node in reversed(nodes):
            if node is not None:
                for child in node:
                    if child.tag in (qn('style', 'text-properties'), qn('style', 'paragraph-properties')):
                        properties.update(child.attrib)
        return properties

    def css(self, name, family='paragraph'):
        properties = self.properties(name, family)
        allowed = {'font-style', 'font-weight', 'font-size', 'font-family', 'font-variant', 'color', 'background-color', 'text-align', 'text-indent', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'line-height', 'keep-with-next', 'break-before', 'break-after'}
        result = {etree_name(key): value for key, value in properties.items() if key.startswith('{'+NS['fo']+'}') and etree_name(key) in allowed}
        if properties.get(qn('style', 'text-underline-style'), 'none') != 'none':
            result['text-decoration'] = 'underline'
        if properties.get(qn('style', 'text-line-through-style'), 'none') != 'none':
            result['text-decoration'] = result.get('text-decoration', '') + ' line-through'
        position = properties.get(qn('style', 'text-position'), '')
        if position.startswith(('super', 'sub')):
            result['vertical-align'] = position.split()[0]
        return '; '.join(f'{key}: {value}' for key, value in sorted(result.items()))

    def heading_level(self, name):
        for ancestor in self.chain(name):
            node = self.styles.get(('paragraph', ancestor))
            explicit = node.get(qn('style', 'default-outline-level')) if node is not None else None
            if explicit and int(explicit) > 0:
                return int(explicit)
            match = re.fullmatch(r'Heading ([1-9][0-9]*)', self.decode(ancestor), re.I)
            if match:
                return int(match[1])
        return None

    def is_verse(self, name):
        return any(re.fullmatch(r'(strofa|stanza|verse|verse line|poetry|poesia|lg|l)(\s*\d+)?', self.decode(key), re.I) for key in self.chain(name))


def etree_name(name):
    return name.rsplit('}', 1)[-1]


class FormattingAnnotator:
    def normalize(self, document):
        resolver = StyleResolver(document)
        for index, paragraph in enumerate(document.paragraphs(), 1):
            paragraph.set(qn('pg', 'id'), f'odf-p{index:06d}')
            names = {resolver.decode(name).lower() for name in resolver.chain(paragraph.get(STYLE))}
            if names & {'speaker', 'speakerfirst', 'personaggio', 'personnage'}:
                paragraph.set(qn('pg', 'drama'), 'speaker')
            elif names & {'stage', 'stage direction', 'stage directions', 'didascalia'}:
                paragraph.set(qn('pg', 'drama'), 'stage')
            if resolver.is_verse(paragraph.get(STYLE)):
                paragraph.set(qn('pg', 'verse'), 'true')
        for node in document.body.xpath('.//*[@text:style-name]', namespaces=NS):
            family = 'text' if node.tag in (qn('text', 'span'), qn('text', 'a')) else 'paragraph'
            css = resolver.css(node.get(STYLE), family)
            if css:
                node.set(qn('pg', 'css'), css)
