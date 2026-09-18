import bz2
import io
from pathlib import Path
import tarfile
import threading
import time

from teify.archive import GrowingBZ2Reader


def test_reader_waits_for_a_growing_compressed_stream(tmp_path):
    raw = b'abcde' * 10000
    compressed = bz2.compress(raw)
    path = tmp_path / 'growing.bz2'
    cut = len(compressed) // 2
    path.write_bytes(compressed[:cut])
    def append_remainder():
        time.sleep(0.05)
        with path.open('ab') as output:
            output.write(compressed[cut:])
    thread = threading.Thread(target=append_remainder)
    thread.start()
    reader = GrowingBZ2Reader(path, follow=True, idle_timeout=5)
    try:
        assert reader.read(len(raw) + 1) == raw
    finally:
        reader.close()
        thread.join()
    assert path.read_bytes() == compressed


def test_reader_handles_concatenated_bzip_streams(tmp_path):
    path = tmp_path / 'concatenated.bz2'
    path.write_bytes(bz2.compress(b'first') + bz2.compress(b'second'))
    reader = GrowingBZ2Reader(path)
    try:
        assert reader.read(100) == b'firstsecond'
    finally:
        reader.close()
