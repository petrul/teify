# teify

Convert ODT/FODT books to TEI XML, with source metadata, externalized graphics,
formatting, and per-document validation reports. Python 3.11+, uv, Java, and
Rake are required for the workflows below.

## Setup and verification

```bash
rake setup
rake test
rake corpus
rake trial
```

`rake test` runs portable regressions. `rake corpus` requires six local books
listed in `tests/corpus/works.json`; it fails if any are missing. Set `CORPUS`
to their directory (default: `samples/selected`). Books are not distributed
with the project.

`rake trial` converts and asserts the same books, retaining TEI files, figures,
and JSON reports in a new timestamped directory under `output/trials`.
Set `OUTPUT` to choose a fresh destination. Existing trial directories are
never overwritten.

| Fixture | Assertions beyond text preservation and TEI schema |
| --- | --- |
| Bracco, *Il perfetto amore* | 759 speeches, 435 stage directions, act/scene hierarchy |
| Zagarrio, *Poesie e liriche* | 356 stanzas, 1,797 verse lines, headings and formatting |
| Chesterton, *Il Napoleone di Notting Hill* | Translation credits, chapter hierarchy |
| Darwin, coral reefs | 178 notes, 2 tables, 28 graphics |
| Gioberti, *Del primato*, vol. 3 | Deep outline, 200 notes |
| Sabbadini, *Vita di Guarino Veronese* | Missing top heading level, SVG drawing |

All six also assert metadata, source immutability, paragraph text and order,
image bytes, local graphic references, and preserved italic formatting.

## Conversion

```bash
rake convert INPUT=book.odt OUTPUT=output/book
uv run teify normalize book.odt normalized/book.fodt
uv run teify convert book.fodt output/book --metadata metadata.json
rake batch INPUT=/path/to/extracted/textbase OUTPUT=output/corpus JOBS=4
```

Single-file conversion refuses to overwrite existing outputs. The `corpus`
command (`rake batch`) processes each ODT/FODT independently, isolates output
names, and records failures and unsupported formats in a SQLite ledger.
Rerunning skips unchanged recorded files whose successful outputs still exist;
use `RETRY_FAILED=1` to retry failures. Engine changes create a new output
version. `LIMIT=20` limits a trial batch. The command exits unsuccessfully if
any files fail, are unsupported, or the run is limited. Warning-bearing
validated documents are marked `review`, separately from `converted`.

Metadata profiles currently cover Liber Liber and Project Gutenberg, with
explicit ODF styles or JSON overrides for other sources. BNF and other source
collections still need representative corpus verification. Unknown authors
and titles are reported rather than inferred from filenames.

## Archive extraction

```bash
uv run python scripts/extract-corpus.py corpus.tar.bz2 /path/to/fresh/destination
# Optional: --decompressor /path/to/lbzip2 --jobs 6
```

Extraction preserves directory structure and records `inventory.jsonl` and
`extraction-status.json`. Completed files appear atomically; incomplete files
end in `.extracting` and are excluded from batch conversion. The decompressor
must finish successfully, including checksum verification, before extraction
is marked complete. The destination must be fresh. A 10 GiB free-space reserve
prevents filling the disk.

The archive command also supports streaming conversion with `--follow`; use
`uv run teify --help` for commands. The converter dependency is pinned by
`scripts/setup-converter.sh`. Unsupported drawings, unrecognized metadata,
invalid TEI, and text loss remain explicit failures with audit details.
