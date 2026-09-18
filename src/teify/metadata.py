"""Source-specific metadata extraction, with explicit evidence and overrides."""
from dataclasses import dataclass, field, asdict
import re
from .document import NS, STYLE, plain_text
from .styles import StyleResolver


@dataclass
class BookMetadata:
    title: str = ''
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    editors: list[str] = field(default_factory=list)
    licences: list[str] = field(default_factory=list)
    rights: str = ''
    source: str = ''
    language: str = ''
    edition_date: str = ''
    fields: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    profile: str = 'generic'
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def require_identity(self):
        declared_without_author = self.profile == 'liberliber' and self.fields.get('AUTORE') == ''
        if not self.title or (not self.authors and not declared_without_author):
            raise ValueError('Cannot reliably identify title and author; provide --metadata with explicit title/authors')
        if not self.authors:
            self.warnings.append('Source author field is explicitly blank; authorship requires review')
        if not self.licences:
            self.warnings.append('No explicit licence was found; no rights grant has been inferred')


class LiberLiberMetadataExtractor:
    """Read labelled credits; continuation lines belong to the preceding field."""
    LABEL = re.compile(r"^([A-ZÀÈÉÌÒÙ0-9][A-ZÀÈÉÌÒÙ0-9a '\u2019-]+):\s*(.*)$", re.S)

    def matches(self, document):
        # Cover art/OCR can precede the labelled credits by hundreds of lines.
        paragraphs = document.paragraphs()
        return (any('liberliber.it' in plain_text(p).lower() for p in paragraphs)
                and any(plain_text(p).strip().startswith('TITOLO:') for p in paragraphs)
                and any(plain_text(p).strip().startswith('AUTORE:') for p in paragraphs))

    def extract(self, document):
        result = BookMetadata(profile='liberliber')
        resolver = StyleResolver(document)
        current = None
        started = False
        for paragraph in document.flow_paragraphs():
            value = plain_text(paragraph).strip()
            if value.startswith('TITOLO:'):
                started = True
            if not started:
                continue
            if value.startswith(('Informazioni sul', 'Aiuta anche tu')) or (paragraph.tag.endswith('}h') and current):
                break
            # Respect explicit metadata style boundaries after the credits.
            chain = list(resolver.chain(paragraph.get(STYLE)))
            is_info = any('LL: info' == resolver.decode(name) for name in chain)
            match = self.LABEL.match(value)
            if match:
                current, field_value = match.groups()
                current = current.replace('’', "'")
                result.fields[current] = field_value
            elif value and current and is_info:
                result.fields[current] += ('\n' if result.fields[current] else '') + value
            elif value and current and not is_info:
                # A subject may use a preformatted style in the source.
                if current == 'SOGGETTO' and not result.fields[current]:
                    result.fields[current] = value
                else:
                    break
        fields = result.fields
        result.title = fields.get('TITOLO', '')
        for label, attribute in [('AUTORE','authors'), ('TRADUTTORE','translators'), ('CURATORE','editors')]:
            if fields.get(label):
                setattr(result, attribute, [fields[label]])
        result.licences = [fields['LICENZA']] if fields.get('LICENZA') else []
        result.rights = fields.get("DIRITTI D'AUTORE", '')
        result.source = fields.get('TRATTO DA', '')
        result.edition_date = fields.get('1a EDIZIONE ELETTRONICA DEL', '')
        result.evidence = {key: f'Liber Liber labelled field: {label}' for key, label in [('title','TITOLO'), ('authors','AUTORE'), ('translators','TRADUTTORE'), ('editors','CURATORE'), ('licences','LICENZA')] if fields.get(label)}
        return result


class GutenbergMetadataExtractor:
    START = re.compile(r'\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG (?:EBOOK|ETEXT)', re.I)
    END = re.compile(r'\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG (?:EBOOK|ETEXT)', re.I)
    LABEL = re.compile(r'^(Title|Author|Translator|Editor|Language|Release date|Release Date):\s*(.*)$')

    def matches(self, document):
        return any(self.START.search(plain_text(p)) for p in document.flow_paragraphs()[:200])

    def extract(self, document):
        result = BookMetadata(profile='gutenberg')
        current = None
        in_header = True
        in_footer = False
        for paragraph in document.flow_paragraphs():
            value = plain_text(paragraph).strip()
            if self.START.search(value):
                in_header = False
                continue
            if self.END.search(value):
                in_footer = True
            if in_footer:
                if value:
                    result.licences.append(value)
                continue
            if not in_header:
                continue
            for line in value.splitlines():
                match = self.LABEL.match(line.strip())
                if match:
                    current, field_value = match.groups()
                    result.fields[current] = field_value
                elif current and line.strip() and not re.match(r'^[\w ]+:', line):
                    # Only indented continuation lines, never arbitrary boilerplate.
                    if line.startswith((' ', '\t')):
                        result.fields[current] += ' ' + line.strip()
                if re.search(r'licen[sc]e|copyright|terms of use', line, re.I):
                    result.licences.append(line.strip())
        result.title = result.fields.get('Title', '')
        for label, attr in [('Author', 'authors'), ('Translator', 'translators'), ('Editor', 'editors')]:
            if result.fields.get(label):
                setattr(result, attr, [result.fields[label]])
        language = result.fields.get('Language', '')
        result.language = {'English':'en', 'Italian':'it', 'French':'fr', 'German':'de', 'Romanian':'ro'}.get(language, '')
        result.evidence = {key: f'Gutenberg labelled field: {label}' for key, label in [('title','Title'), ('authors','Author'), ('translators','Translator'), ('editors','Editor')] if result.fields.get(label)}
        return result


class GenericMetadataExtractor:
    def matches(self, document):
        return True

    def extract(self, document):
        result = BookMetadata()
        resolver = StyleResolver(document)
        for paragraph in document.flow_paragraphs():
            styles = [resolver.decode(name).lower() for name in resolver.chain(paragraph.get(STYLE))]
            value = plain_text(paragraph).strip()
            if value and 'title' in styles and not result.title:
                result.title = value
                result.evidence['title'] = 'Explicit ODF Title style'
            if value and 'author' in styles:
                result.authors.append(value)
                result.evidence['authors'] = 'Explicit ODF Author style'
        if not result.title:
            titles = document.root.xpath('./office:meta/dc:title/text()', namespaces=NS)
            if titles:
                result.title = titles[0].strip()
                result.evidence['title'] = 'ODF dc:title'
        # dc:creator/initial-creator often identify the typist, not the author.
        result.warnings.append('Unrecognized source: metadata needs explicit styles or an override')
        return result


class MetadataExtractor:
    def __init__(self):
        self.profiles = [LiberLiberMetadataExtractor(), GutenbergMetadataExtractor(), GenericMetadataExtractor()]

    def extract(self, document, overrides=None):
        result = next(profile for profile in self.profiles if profile.matches(document)).extract(document)
        if not result.language:
            languages = document.root.xpath('./office:meta/dc:language/text()', namespaces=NS)
            if languages:
                result.language = languages[0].strip()
        if not result.language:
            properties = StyleResolver(document).properties(None)
            language = properties.get('{'+NS['fo']+'}language', '')
            if language and language not in {'zxx', 'none'}:
                result.language = language
                result.evidence['language'] = 'ODF default paragraph language'
        if overrides:
            for key, value in overrides.items():
                if key not in {'title','authors','translators','editors','licences','rights','source','language','edition_date'}:
                    raise ValueError(f'Unknown metadata override: {key}')
                expected = list if key in {'authors','translators','editors','licences'} else str
                if not isinstance(value, expected) or (expected is list and not all(isinstance(item, str) for item in value)):
                    raise ValueError(f'Invalid value for metadata override: {key}')
                setattr(result, key, value)
                result.evidence[key] = 'Explicit metadata override'
        result.require_identity()
        return result
