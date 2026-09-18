"""Stable author/title filenames; bibliographical values stay unchanged."""
from dataclasses import dataclass
from pathlib import Path
import re
import hashlib
import unicodedata


def words(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.findall(r"[a-z0-9]+(?:['’][a-z0-9]+)*", value)


def slug(value):
    return '_'.join(word.replace("'", '') for word in words(value))


@dataclass(frozen=True)
class OutputPaths:
    xml: Path
    figures: Path
    report: Path

    @classmethod
    def for_book(cls, directory, metadata):
        # This is a filename label only, never an invented TEI author.
        author = metadata.authors[0] if metadata.authors else 'unattributed'
        if ',' in author:
            surname, given = author.split(',', 1)
        else:
            parts = author.split()
            surname, given = parts[-1], ' '.join(parts[:-1])
        author_slug = slug(surname) + (',' + slug(given) if given.strip() else '')
        title_slug = slug(metadata.title)
        if not author_slug or not title_slug:
            raise ValueError('Cannot form a filename; provide romanized title/author metadata')
        stem = f'{author_slug}-{title_slug}'
        if len(stem) > 200:
            digest = hashlib.sha256(stem.encode()).hexdigest()[:10]
            stem = stem[:189].rstrip('_') + '-' + digest
        directory = Path(directory)
        return cls(directory / f'{stem}.tei.xml', directory / f'{stem}-figs.d', directory / f'{stem}.report.json')
