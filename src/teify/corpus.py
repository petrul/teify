"""Resumable conversion of an extracted corpus, isolating failures per file."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .converter import TEIConverter
from .pipeline import DocumentPipeline


def engine_version(stylesheets):
    digest = hashlib.sha256(TEIConverter(stylesheets).revision().encode())
    root = Path(__file__).parent
    for path in sorted(root.rglob('*')):
        if path.suffix in {'.py', '.xsl', '.rng'}:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def convert_file(source, destination, stylesheets):
    started = time.monotonic()
    try:
        output = DocumentPipeline(TEIConverter(Path(stylesheets))).run(Path(source), Path(destination))[0]
        report_path = output.with_name(output.name.removesuffix('.tei.xml') + '.report.json')
        report = json.loads(report_path.read_text())
        warnings = report['warnings'] + report['validation']['warnings']
        return dict(status='review' if warnings else 'converted', output=str(output),
                    report=str(report_path), profile=report['metadata']['profile'],
                    warnings=warnings, seconds=round(time.monotonic()-started, 2))
    except Exception as error:
        return dict(status='failed', error=f'{type(error).__name__}: {error}',
                    reports=[str(p) for p in Path(destination).glob('*.report.json')],
                    seconds=round(time.monotonic()-started, 2))


class CorpusRunner:
    def __init__(self, source, output, stylesheets, jobs=4, limit=None, retry_failed=False):
        self.source = Path(source).resolve()
        self.output = Path(output).resolve()
        self.stylesheets = Path(stylesheets).resolve()
        if not self.source.is_dir():
            raise ValueError(f'Corpus directory does not exist: {self.source}')
        if self.output == self.source or self.source in self.output.parents:
            raise ValueError('Corpus output must be outside the source directory')
        if jobs < 1 or (limit is not None and limit < 1):
            raise ValueError('jobs and limit must be positive')
        TEIConverter(self.stylesheets).check_available()
        self.jobs, self.limit, self.retry_failed = jobs, limit, retry_failed

    def run(self):
        version = engine_version(self.stylesheets)
        run_dir = self.output / version
        run_dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(run_dir / 'ledger.sqlite3')
        db.execute('CREATE TABLE IF NOT EXISTS documents (source TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, result TEXT)')
        counts = Counter()
        pending = {}
        submitted = 0
        scanned = 0

        def summary(state):
            result = dict(state=state, engine=version, source=str(self.source),
                          scanned=scanned, submitted=submitted, in_flight=len(pending), counts=dict(counts))
            temporary = self.output / 'status.tmp'
            temporary.write_text(json.dumps(result, indent=2)+'\n')
            temporary.replace(self.output / 'status.json')
            return result

        def collect():
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                path, stat = pending.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = dict(status='failed', error=str(error))
                counts[result['status']] += 1
                db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?)',
                           (str(path), stat.st_size, stat.st_mtime_ns, json.dumps(result, ensure_ascii=False)))
                db.commit()
                print(json.dumps(dict(source=str(path), **result), ensure_ascii=False), flush=True)
            summary('running')

        try:
            with ProcessPoolExecutor(max_workers=self.jobs) as pool:
                for path in sorted(self.source.rglob('*')):
                    if not path.is_file() or path.name.endswith('.extracting'):
                        continue
                    scanned += 1
                    stat = path.stat()
                    previous = db.execute('SELECT size, mtime_ns, result FROM documents WHERE source=?', (str(path),)).fetchone()
                    if previous and previous[:2] == (stat.st_size, stat.st_mtime_ns):
                        result = json.loads(previous[2])
                        valid = result['status'] == 'unsupported' or (result['status'] == 'failed' and not self.retry_failed)
                        if result['status'] in {'converted','review'}:
                            valid = Path(result['output']).is_file() and Path(result['report']).is_file()
                        if valid:
                            counts[result['status']] += 1
                            continue
                    if path.suffix.lower() not in {'.odt', '.fodt'}:
                        result = dict(status='unsupported', format=path.suffix.lower())
                        db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?)',
                                   (str(path),stat.st_size,stat.st_mtime_ns,json.dumps(result)))
                        db.commit()
                        counts['unsupported'] += 1
                        continue
                    while len(pending) >= self.jobs * 2:
                        collect()
                    relative = path.relative_to(self.source)
                    # Hash the entire relative name, including extension, to
                    # avoid collisions between editions and ODT/FODT pairs.
                    key = hashlib.sha256(str(relative).encode()).hexdigest()[:20]
                    destination = run_dir / 'books' / key
                    attempt = destination
                    index = 1
                    while attempt.exists():
                        attempt = destination.with_name(f'{key}-retry-{index}')
                        index += 1
                    future = pool.submit(convert_file, str(path), str(attempt), str(self.stylesheets))
                    pending[future] = path, stat
                    submitted += 1
                    summary('running')
                    if self.limit and submitted >= self.limit:
                        break
                while pending:
                    collect()
            result = summary('limited' if self.limit and submitted >= self.limit else 'complete')
            (run_dir / 'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            return result
        finally:
            db.close()
