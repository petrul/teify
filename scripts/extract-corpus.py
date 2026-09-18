#!/usr/bin/env python3
"""Extract a corpus once, recording a complete inventory and progress.

Use --decompressor /path/to/lbzip2 for parallel bzip2 decompression.
Sources are published with atomic renames so concurrent readers see whole files.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--decompressor', default='bzip2')
    parser.add_argument('--jobs', type=int, default=6)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    inventory = args.destination / 'inventory.jsonl'
    if inventory.exists():
        raise SystemExit(f'Inventory already exists: {inventory}; use a fresh destination')
    command = [args.decompressor, '-dc']
    if 'lbzip2' in Path(args.decompressor).name:
        command += ['-n', str(args.jobs)]
    command.append(str(args.archive))
    started = time.time()
    counts = Counter()
    total = 0
    files = 0
    last_status = 0
    state = 'extracting'

    def status(error=None):
        result = dict(state=state, files=files, bytes=total, formats=dict(counts),
                      elapsed_seconds=round(time.time()-started), error=error)
        target = args.destination / 'extraction-status.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2)+'\n')
        temporary.replace(target)
        print(json.dumps(result), flush=True)

    status()
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        with inventory.open('x') as log, tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                # Python's data filter rejects traversal, devices, unsafe links,
                # and strips privileged metadata before extraction.
                checked = tarfile.data_filter(member, str(args.destination))
                if checked is None:
                    raise ValueError(f'Rejected archive member: {member.name}')
                target = args.destination / checked.name
                if checked.isfile():
                    if shutil.disk_usage(args.destination).free < checked.size + 10 * 1024**3:
                        raise OSError('Less than 10 GiB would remain; extraction stopped')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise ValueError(f'Duplicate/existing archive target: {target}')
                    temporary = target.with_name(target.name + '.extracting')
                    with archive.extractfile(member) as source, temporary.open('xb') as output:
                        shutil.copyfileobj(source, output, 1024*1024)
                    if temporary.stat().st_size != checked.size:
                        raise ValueError(f'Incomplete member: {member.name}')
                    temporary.rename(target)
                    total += checked.size
                    files += 1
                    counts[target.suffix.lower() or '(none)'] += 1
                else:
                    archive.extract(checked, args.destination, filter='data')
                log.write(json.dumps(dict(path=member.name, size=member.size,
                                          type=member.type.decode('ascii')), ensure_ascii=False)+'\n')
                log.flush()
                if time.time() - last_status > 15:
                    status()
                    last_status = time.time()
            # Drain to verify the bzip2 checksum and physical end of stream.
            while process.stdout.read(1024*1024):
                pass
        if process.wait() != 0:
            raise ValueError('bzip2 decompression/checksum verification failed')
        state = 'complete'
        status()
    except BaseException as error:
        state = 'failed'
        status(str(error))
        process.terminate()
        process.wait()
        raise
    finally:
        process.stdout.close()


if __name__ == '__main__':
    main()
