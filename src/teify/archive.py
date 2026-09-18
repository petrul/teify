"""Bounded, resumable conversion of a possibly still-growing tar.bz2 archive."""
import bz2
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile
import time

from .converter import TEIConverter
from .pipeline import DocumentPipeline


def now():
    return datetime.now(timezone.utc).isoformat()


class GrowingBZ2Reader:
    """Wait at the current physical EOF, without mistaking it for bzip2 EOF."""
    def __init__(self, path, follow=False, idle_timeout=600):
        self.file = open(path, 'rb')
        self.decoder = bz2.BZ2Decompressor()
        self.pending = b''
        self.follow = follow
        self.idle_timeout = idle_timeout
        self.last_data = time.monotonic()
        self.bytes_read = 0
        self.finished = False

    def read(self, size):
        output = bytearray()
        while len(output) < size and not self.finished:
            if self.decoder.eof:
                # A valid archive can contain concatenated bzip2 streams.
                self.pending = self.decoder.unused_data + self.file.read(256 * 1024)
                self.bytes_read = self.file.tell()
                if not self.pending:
                    self.finished = True
                    break
                self.decoder = bz2.BZ2Decompressor()
            if self.decoder.needs_input:
                chunk = self.pending or self.file.read(256 * 1024)
                self.pending = b''
                self.bytes_read = self.file.tell()
                if not chunk:
                    if not self.follow or time.monotonic() - self.last_data > self.idle_timeout:
                        raise EOFError('Compressed archive is incomplete; rerun with --follow when more data arrives')
                    time.sleep(1)
                    continue
                self.last_data = time.monotonic()
            else:
                chunk = b''
            output.extend(self.decoder.decompress(chunk, size - len(output)))
        return bytes(output)

    def close(self):
        self.file.close()


def convert_member(source, destination, stylesheets, member_name):
    """Worker owns a single temporary source; results survive in the ledger."""
    source = Path(source)
    try:
        output = DocumentPipeline(TEIConverter(Path(stylesheets))).run(source, Path(destination))[0]
        report_path = output.with_name(output.name.removesuffix('.tei.xml') + '.report.json')
        report = json.loads(report_path.read_text())
        report['archive_member'] = member_name
        report['source'] = member_name
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        validation = report['validation']
        warnings = report['warnings'] + validation['warnings']
        return {'status': 'review' if warnings else 'converted', 'output':str(output),
                'report':str(report_path), 'validation':validation, 'warnings':warnings}
    except Exception as error:
        return {'status':'failed', 'error':f'{type(error).__name__}: {error}'}
    finally:
        shutil.rmtree(source.parent)


class ArchiveRunner:
    def __init__(self, archive, output, stylesheets, jobs=4, follow=False, limit=None):
        self.archive = Path(archive).resolve()
        self.output = Path(output).resolve()
        self.stylesheets = Path(stylesheets).resolve()
        self.jobs = jobs
        self.follow = follow
        self.limit = limit
        if jobs < 1:
            raise ValueError('jobs must be positive')
        converter = TEIConverter(self.stylesheets)
        converter.check_available()
        digest = hashlib.sha256(converter.revision().encode())
        for path in sorted(Path(__file__).parent.rglob('*')):
            if path.suffix in {'.py','.xsl','.rng'}:
                digest.update(path.read_bytes())
        self.version = digest.hexdigest()[:12]
        self.run_dir = self.output / self.version
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.run_dir / 'ledger.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS documents (member TEXT PRIMARY KEY, size INTEGER, status TEXT, result TEXT, updated TEXT)')
        self.pending = {}
        self.scanned = 0
        self.reader = None

    def record(self, member, size, result):
        self.db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?)', (member,size,result['status'],json.dumps(result,ensure_ascii=False),now()))
        self.db.commit()
        print(json.dumps({'member':member, **{key:result[key] for key in ('status','output','error') if key in result}},ensure_ascii=False), flush=True)

    def summary(self, state):
        counts = dict(self.db.execute('SELECT status, COUNT(*) FROM documents GROUP BY status'))
        result = {'archive':str(self.archive), 'archive_bytes_now':self.archive.stat().st_size,
                  'compressed_bytes_read':self.reader.bytes_read if self.reader else 0,
                  'engine':self.version, 'state':state, 'updated':now(), 'pid':os.getpid(),
                  'scanned_members':self.scanned, 'in_flight':len(self.pending), 'counts':counts}
        path = self.output / 'status.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(result,indent=2) + '\n')
        temporary.replace(path)
        return result

    def collect(self, block=True):
        if not self.pending:
            return
        done, _ = wait(self.pending, timeout=10 if block else 0, return_when=FIRST_COMPLETED)
        for future in done:
            member, size = self.pending.pop(future)
            try:
                result = future.result()
            except Exception as error:
                result = {'status':'failed','error':str(error)}
            self.record(member,size,result)
        self.summary('running')

    def run(self):
        self.reader = GrowingBZ2Reader(self.archive,self.follow)
        state = 'complete'
        submitted = 0
        scratch_root = self.output / '.scratch'
        scratch_root.mkdir(exist_ok=True)
        self.summary('running')
        try:
            with ProcessPoolExecutor(max_workers=self.jobs) as pool:
                try:
                    with tarfile.open(fileobj=self.reader,mode='r|') as archive:
                        for member in archive:
                            self.scanned += 1
                            if not member.isfile():
                                continue
                            relative = PurePosixPath(member.name)
                            if relative.is_absolute() or '..' in relative.parts:
                                self.record(member.name,member.size,{'status':'rejected','error':'Unsafe archive member path'})
                                continue
                            previous = self.db.execute('SELECT size, status, result FROM documents WHERE member=?',(member.name,)).fetchone()
                            if previous and previous[0] == member.size:
                                result = json.loads(previous[2])
                                if previous[1] in {'unsupported','rejected'} or (previous[1] in {'converted','review'} and Path(result['output']).is_file()):
                                    continue
                            if relative.suffix.lower() not in {'.odt','.fodt'}:
                                self.record(member.name,member.size,{'status':'unsupported','format':relative.suffix.lower() or '(none)'})
                                continue
                            if member.size > 512 * 1024 * 1024:
                                self.record(member.name,member.size,{'status':'rejected','error':'Document exceeds 512 MiB extraction limit'})
                                continue
                            while len(self.pending) >= self.jobs * 2:
                                self.collect()
                            # Each member gets an isolated output namespace; editions cannot overwrite one another.
                            destination = self.run_dir / 'books' / relative.with_suffix('')
                            attempt = destination
                            retry = 1
                            while attempt.exists():
                                attempt = destination.with_name(destination.name + f'-retry-{retry}')
                                retry += 1
                            temporary = Path(tempfile.mkdtemp(prefix='document-',dir=scratch_root))
                            source = temporary / relative.name
                            with archive.extractfile(member) as input_file, source.open('wb') as output_file:
                                shutil.copyfileobj(input_file,output_file,1024*1024)
                            future = pool.submit(convert_member,str(source),str(attempt),str(self.stylesheets),member.name)
                            self.pending[future] = (member.name,member.size)
                            submitted += 1
                            self.collect(block=False)
                            if self.limit and submitted >= self.limit:
                                state = 'limited'
                                break
                except (EOFError, tarfile.ReadError, OSError) as error:
                    state = 'incomplete'
                    print(json.dumps({'state':state,'error':str(error)}),flush=True)
                finally:
                    while self.pending:
                        self.collect()
            result = self.summary(state)
            (self.run_dir / 'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            return result
        finally:
            self.reader.close()
            self.db.close()
