"""The single teify command-line interface."""
import argparse
import json
from pathlib import Path
import sys
from zipfile import BadZipFile
from lxml import etree
from .pipeline import DocumentPipeline
from .converter import TEIConverter


def main(argv=None):
    parser = argparse.ArgumentParser(description='Convert ODT/FODT books to audited TEI XML')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('normalize', 'convert'):
        command = commands.add_parser(name)
        command.add_argument('input', type=Path, help='ODT/FODT file or directory (recursive)')
        command.add_argument('output', type=Path, help='Output directory for convert; file or directory for normalize')
        if name == 'convert':
            command.add_argument('--stylesheets', type=Path, default=Path(__file__).resolve().parents[2] / 'vendor/tei-stylesheets')
            command.add_argument('--java', default='java')
            command.add_argument('--schema', type=Path, help='Override bundled TEI All Relax NG schema')
            command.add_argument('--metadata', type=Path, help='JSON metadata overrides for a single input file')
    archive = commands.add_parser('archive', help='Stream and convert a tar.bz2 archive with a resumable ledger')
    archive.add_argument('input', type=Path)
    archive.add_argument('output', type=Path)
    archive.add_argument('--jobs', type=int, default=4)
    archive.add_argument('--follow', action='store_true', help='Wait for an incomplete archive to grow')
    archive.add_argument('--limit', type=int, help='Limit documents for a trial run')
    archive.add_argument('--stylesheets', type=Path, default=Path(__file__).resolve().parents[2] / 'vendor/tei-stylesheets')
    corpus = commands.add_parser('corpus', help='Convert an extracted corpus with per-document reports and a resumable ledger')
    corpus.add_argument('input', type=Path)
    corpus.add_argument('output', type=Path)
    corpus.add_argument('--jobs', type=int, default=4)
    corpus.add_argument('--limit', type=int)
    corpus.add_argument('--retry-failed', action='store_true')
    corpus.add_argument('--stylesheets', type=Path, default=Path(__file__).resolve().parents[2] / 'vendor/tei-stylesheets')
    args = parser.parse_args(argv)
    try:
        if args.command == 'corpus':
            from .corpus import CorpusRunner
            result = CorpusRunner(args.input, args.output, args.stylesheets, args.jobs, args.limit, args.retry_failed).run()
            print(json.dumps(result, indent=2))
            return 0 if result['state'] == 'complete' and not result['counts'].get('failed') and not result['counts'].get('unsupported') else 1
        if args.command == 'archive':
            from .archive import ArchiveRunner
            result = ArchiveRunner(args.input,args.output,args.stylesheets,args.jobs,args.follow,args.limit).run()
            print(json.dumps(result,indent=2))
            return 0 if result['state'] == 'complete' and not result['counts'].get('failed') else 1
        if args.command == 'convert':
            overrides = json.loads(args.metadata.read_text()) if args.metadata else None
            if overrides is not None and not isinstance(overrides, dict):
                raise ValueError('Metadata override must be a JSON object')
            pipeline = DocumentPipeline(TEIConverter(args.stylesheets, args.java), args.schema, overrides)
        else:
            pipeline = DocumentPipeline()
        for output in pipeline.run(args.input, args.output):
            print(f'Saved {output}')
    except (OSError, ValueError, etree.LxmlError, BadZipFile, KeyError) as error:
        print(f'teify: {error}', file=sys.stderr)
        return 1
    return 0
