"""Extract the text of every source document listed in each jurisdiction's sources.yaml.

    python -m document_extraction           # (re)write 2_extracted_text/<pdf name>.jsonl, and
                                            # <pdf name>.cells.jsonl for documents with chart_pages
    python -m document_extraction --check   # exit 1 if any saved file differs from a fresh extraction

Refuses to extract a PDF whose fingerprint doesn't match sources.yaml. A document with
`layout: ecode360` is also cut into sections: 2_extracted_text/<pdf name>.sections.jsonl.

A document kept outside the repo (`kept_outside_repo: true`: a copyrighted code book, such as New York's Residential
Code, `layout: icc`) is read from the code cache (rule_format.rulebook.code_cache). The cache keeps the text of
every page, once per extractor version (book_text.py), so it is the same for every branch; each branch's brought-in
pages (`brought_in`) are read afresh, must be the cached text's (or the whole book is read again into the cache),
and are cut into its sections file (section numbers, titles, line counts and fingerprints: no words of the book),
the only part that comes to 2_extracted_text/. --check writes nothing: the brought-in pages read afresh must be the
cached text's, byte for byte. Where the cache doesn't have the book (CI), it is skipped, and the run says so.
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

from rule_format.place import place
from rule_format.rulebook import cached, cached_text, law_folders, read_jsonl, utf8_console

from . import book_text, icc_sections, sections
from .charts import read_charts
from .extract import extract, sha256, to_jsonl
from .icc import extract_icc, read_book

REPO = Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m document_extraction")
    parser.add_argument("--check", action="store_true", help="compare with a fresh extraction; write nothing")
    check = parser.parse_args(argv).check  # unknown arguments stop here, so a typo can't overwrite files
    failed = 0
    for jurisdiction in law_folders(REPO):
        sources = jurisdiction / "1_source_documents"
        out_dir = jurisdiction / "2_extracted_text"
        for doc in yaml.safe_load((sources / "sources.yaml").read_text(encoding="utf-8"))["documents"]:
            if doc.get("kept_outside_repo") is True:
                failed += not _kept_outside(jurisdiction, doc, check)
                continue
            pdf, out = sources / doc["file"], out_dir / f"{Path(doc['file']).stem}.jsonl"
            if sha256(pdf) != doc["sha256"]:
                print(f"✗ {pdf.relative_to(REPO)}: fingerprint doesn't match sources.yaml; not extracted")
                failed += 1
                continue
            rows = extract(pdf)
            outputs = {out: to_jsonl(rows)}
            if doc.get("layout") == "ecode360":
                outputs[out_dir / f"{Path(doc['file']).stem}.sections.jsonl"] = sections.to_jsonl(sections.split(rows), rows[0])
            if doc.get("chart_pages"):   # tables read into cells, from the same lines
                outputs[out_dir / f"{Path(doc['file']).stem}.cells.jsonl"] = to_jsonl(read_charts(
                    pdf, doc["chart_pages"], place(jurisdiction).district_column))
            for path, fresh in outputs.items():
                failed += not _write_or_check(path, fresh, check)
    return 1 if failed else 0


def _kept_outside(jurisdiction: Path, doc: dict, check: bool) -> bool:
    """A book kept outside the repo: its brought-in pages read afresh from the cached book, and required to be the
    cached text's (the cached text is the whole book, for every branch; written again, all of it, when it isn't
    there or doesn't match); the sections file cut from them, to the repo. Skipped (not failed) where the cache
    doesn't have the book. True when fine."""
    pdf, text = cached(doc), cached_text(doc)
    label = (jurisdiction / "1_source_documents" / doc["file"]).relative_to(REPO)
    if not pdf.exists():
        print(f"– {label}: kept outside the repo and not in the code cache here; not extracted or checked "
              "(checked where the cache exists)")
        return True
    if sha256(pdf) != doc["sha256"]:
        print(f"✗ {label}: the cached copy's fingerprint doesn't match sources.yaml; not extracted")
        return False
    if doc.get("layout") != "icc" or not isinstance(doc.get("brought_in"), dict):
        print(f"✗ {label}: a book kept outside the repo needs layout: icc and brought_in (pages, sections)")
        return False
    pages = icc_sections.parse_pages(doc["brought_in"]["pages"])
    rows = extract_icc(pdf, pages)
    cut = jurisdiction / "2_extracted_text" / f"{Path(doc['file']).stem}.sections.jsonl"
    ok = _same_as_cached(pdf, text, pages, rows, check)
    return all([ok, _write_or_check(cut, icc_sections.to_jsonl(icc_sections.split(rows, doc["brought_in"]), rows[0]),
                                    check)])


def _same_as_cached(pdf: Path, text: Path, pages: list[int], fresh: list[dict], check: bool) -> bool:
    """Whether the cached whole-book text, at `pages`, is `fresh` (those pages just read), byte for byte, header
    included. Not checking: where it isn't, the whole book is read again and written (atomically, so a branch reading
    the cache at the same time never sees half a file)."""
    label = f"<code cache>/{text.parent.name[:12]}…/{text.name} ({len(pages)} brought-in pages of the whole book)"
    try:
        same = to_jsonl(book_text.select(read_jsonl(text), pages)) == to_jsonl(fresh)
    except (OSError, ValueError, KeyError):
        same = False
    if check or same:
        print(f"{'✓' if same else '✗'} {label}{'' if same else ': differs from a fresh extraction'}")
        return same
    print(f"reading every page of {pdf.name} into the code cache (once per book and extractor version)")
    book = read_book(pdf)
    if to_jsonl(book_text.select(book, pages)) != to_jsonl(fresh):     # never: each page is read on its own
        print(f"✗ {label}: the whole book's pages are not the pages read alone")
        return False
    part = text.with_name(f"{text.name}.part{os.getpid()}")
    part.write_text(to_jsonl(book), encoding="utf-8", newline="\n")
    os.replace(part, text)
    print(f"wrote {label}: {len(book) - 1} lines")
    return True


def _write_or_check(path: Path, fresh: str, check: bool) -> bool:
    label = path.relative_to(REPO) if path.is_relative_to(REPO) else f"<code cache>/{path.parent.name[:12]}…/{path.name}"
    if check:
        same = path.exists() and path.read_text(encoding="utf-8") == fresh
        print(f"{'✓' if same else '✗'} {label}{'' if same else ': differs from a fresh extraction'}")
        return same
    path.parent.mkdir(exist_ok=True)
    path.write_text(fresh, encoding="utf-8", newline="\n")
    print(f"wrote {label} ({fresh.count(chr(10)) - 1} lines)")
    return True


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
