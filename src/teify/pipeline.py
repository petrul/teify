"""Coordinate parsing, source profiles, conversion, validation, and publication."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from lxml import etree
from .converter import TEIConverter
from .document import xml_parser
from .graphics import GraphicsExporter
from .metadata import MetadataExtractor
from .naming import OutputPaths
from .normalizer import FODTNormalizer
from .tei import TEIFinalizer
from .validation import ConversionValidator


@dataclass
class DocumentPipeline:
    converter: TEIConverter | None = None
    schema: Path | None = None
    metadata_overrides: dict | None = None

    def sources(self, source):
        source = Path(source)
        if not source.exists():
            raise ValueError(f'Input does not exist: {source}')
        paths = sorted(p for p in source.rglob('*') if p.suffix.lower() in {'.odt','.fodt'} and p.is_file()) if source.is_dir() else [source]
        if not paths:
            raise ValueError(f'No ODT/FODT files found in {source}')
        if any(p.suffix.lower() not in {'.odt','.fodt'} for p in paths):
            raise ValueError('Currently supported inputs: ODT and FODT')
        return paths

    def run(self, source: Path, destination: Path) -> list[Path]:
        paths = self.sources(source)
        if self.converter:
            self.converter.check_available()
        if len(paths) > 1 and self.metadata_overrides:
            raise ValueError('--metadata applies to one document at a time')
        results = []
        for path in paths:
            if self.converter:
                results.append(self.convert_one(path, destination))
            else:
                target = destination / path.with_suffix('.fodt').name if source.is_dir() else destination
                if target.exists():
                    raise ValueError(f'Output already exists: {target}')
                normalizer = FODTNormalizer(path).normalize()
                target.parent.mkdir(parents=True, exist_ok=True)
                normalizer.save(target)
                results.append(target)
        return results

    def convert_one(self, source, destination):
        normalizer = FODTNormalizer(source)
        document = normalizer.document
        metadata = MetadataExtractor().extract(document, self.metadata_overrides)
        output = OutputPaths.for_book(destination, metadata)
        for target in (output.xml, output.figures, output.report):
            if target.exists():
                raise ValueError(f'Output already exists: {target}')
        normalizer.normalize()
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        revision = self.converter.revision()
        destination.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.teify-', dir=destination) as temporary:
            temporary = Path(temporary)
            graphics = GraphicsExporter().export(document, temporary / output.figures.name, output.figures.name)
            normalized = temporary / 'normalized.fodt'
            raw = temporary / 'converted.xml'
            normalizer.save(normalized)
            messages = self.converter.convert(normalized, raw)
            tree = etree.parse(str(raw), xml_parser())
            TEIFinalizer().finalize(tree, metadata, source.name, source_hash, revision)
            validation = ConversionValidator(self.schema).validate(document, tree, temporary)
            report = {
                'source': str(source.resolve()), 'source_sha256': source_hash,
                'output': output.xml.name, 'converter_revision': revision,
                'metadata': metadata.to_dict(), 'heading_changes': document.heading_changes,
                'graphics': graphics, 'validation': validation,
                'warnings': metadata.warnings + document.warnings,
                'converter_messages': messages,
            }
            # A failed conversion leaves an audit report, never a success-looking TEI.
            output.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            if not validation['passed']:
                raise ValueError(f'Validation failed; see {output.report}: ' + '; '.join(validation['errors'][:3]))
            final = temporary / output.xml.name
            tree.write(str(final), encoding='utf-8', xml_declaration=True)
            shutil.move(str(temporary / output.figures.name), output.figures)
            final.rename(output.xml)
        return output.xml
