"""Externalize embedded graphics and rewrite only the working document."""
import base64
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from lxml import etree
from .styles import StyleResolver
from .document import NS, qn
from .drawings import render


class GraphicsExporter:
    def export(self, document, directory, relative_directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        exported = {}
        archive = ZipFile(document.path) if document.path.suffix.lower() == '.odt' else None
        try:
            for index, node in enumerate(document.body.xpath('.//draw:image', namespaces=NS), 1):
                href = node.get(qn('xlink', 'href'), '')
                embedded = node.find('office:binary-data', NS)
                key = href or f'embedded-{index}'
                if key in exported:
                    node.set(qn('xlink', 'href'), exported[key])
                    continue
                if embedded is not None:
                    data = base64.b64decode(''.join(embedded.itertext()))
                elif href and ':' not in href and not PurePosixPath(href).is_absolute() and '..' not in PurePosixPath(href).parts:
                    if archive:
                        data = archive.read(href.removeprefix('./'))
                    else:
                        data = (document.path.parent / href).read_bytes()
                else:
                    raise ValueError(f'Cannot externalize image without a local source: {href}')
                suffix = Path(href).suffix.lower()
                if data.startswith(b'\x89PNG'):
                    suffix = '.png'
                elif data.startswith(b'\xff\xd8'):
                    suffix = '.jpg'
                elif data.startswith((b'GIF87a', b'GIF89a')):
                    suffix = '.gif'
                elif b'<svg' in data[:1000]:
                    suffix = '.svg'
                if not suffix:
                    suffix = '.bin'
                filename = f'image-{len(exported)+1:04d}{suffix}'
                (directory / filename).write_bytes(data)
                target = f'{relative_directory}/{filename}'
                node.set(qn('xlink', 'href'), target)
                if embedded is not None:
                    node.remove(embedded)
                exported[key] = target
        finally:
            if archive:
                archive.close()
        resolver = StyleResolver(document)
        for index, shape in enumerate(document.body.xpath('.//draw:custom-shape | .//draw:rect | .//draw:line', namespaces=NS), 1):
            svg = render(shape, resolver)
            if shape.tag == qn('draw', 'custom-shape'):
                geometry = shape.find('draw:enhanced-geometry', NS)
                if geometry is not None and geometry.get(qn('draw', 'type')) != 'rectangle':
                    warning = 'Drawing converted to SVG; verify its grouping against the original page layout'
                    if warning not in document.warnings:
                        document.warnings.append(warning)
            filename = f'drawing-{index:04d}.svg'
            (directory / filename).write_bytes(etree.tostring(svg, xml_declaration=True, encoding='utf-8'))
            target = f'{relative_directory}/{filename}'
            image = etree.SubElement(shape, qn('draw', 'image'))
            image.set(qn('xlink', 'href'), target)
            exported[f'drawing-{index}'] = target
        return exported
