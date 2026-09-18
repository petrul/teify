"""Map ODF bookmark/reference names to stable XML identifiers."""
import hashlib
import json
from urllib.parse import unquote

from .document import NS, qn


class ReferenceNormalizer:
    def normalize(self, document):
        targets = {}
        for node in document.body.iter():
            if node.tag in {qn('text', name) for name in (
                'bookmark', 'bookmark-start', 'reference-mark', 'reference-mark-start') }:
                name = node.get(qn('text', 'name'), '')
                key = ('bookmark' if 'bookmark' in node.tag else 'reference', name)
            elif node.tag in {qn('text', 'alphabetical-index-mark'), qn('text', 'alphabetical-index-mark-start'), qn('text', 'toc-mark'), qn('text', 'toc-mark-start'), qn('text', 'user-index-mark'), qn('text', 'user-index-mark-start')}:
                name = node.get(qn('text', 'id'), '')
                key = ('index', name)
                node.set(qn('pg', 'index-metadata'), json.dumps(dict(node.attrib), ensure_ascii=False, sort_keys=True))
            else:
                continue
            identifier = 'odf-a' + hashlib.sha256(repr(key).encode()).hexdigest()[:20]
            # Repeated anonymous index markers and duplicate named anchors
            # retain separate positions; links resolve to the first occurrence.
            occurrence = targets.get(key, [])
            if occurrence:
                identifier += '-' + str(len(occurrence)+1)
            node.set(qn('pg', 'anchor'), identifier)
            targets.setdefault(key, []).append(identifier)

        for node in document.body.iter():
            local = node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else ''
            key = None
            if local in {'bookmark-ref', 'bookmark-end'}:
                key = ('bookmark', node.get(qn('text', 'ref-name')) or node.get(qn('text', 'name')))
            elif local in {'reference-ref', 'reference-mark-end'}:
                key = ('reference', node.get(qn('text', 'ref-name')) or node.get(qn('text', 'name')))
            elif local in {'alphabetical-index-mark-end', 'toc-mark-end', 'user-index-mark-end'}:
                key = ('index', node.get(qn('text', 'id')))
            elif node.tag == qn('text', 'a') and node.get(qn('xlink', 'href'), '').startswith('#'):
                name = unquote(node.get(qn('xlink', 'href'))[1:])
                key = next((k for k in [('bookmark',name), ('reference',name)] if k in targets), None)
            if key in targets:
                node.set(qn('pg', 'target'), '#' + targets[key][0])
