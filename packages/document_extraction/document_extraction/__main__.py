"""Extract the text of every source document listed in each jurisdiction's sources.yaml.

    python -m document_extraction           # (re)write 2_extracted_text/<pdf name>.jsonl, and
                                            # <pdf name>.cells.jsonl for documents with chart_pages
    python -m document_extraction --check   # exit 1 if any saved file differs from a fresh extraction

Refuses to extract a PDF whose fingerprint doesn't match sources.yaml. A document with
`layout: ecode360` is also cut into sections: 2_extracted_text/<pdf name>.sections.jsonl.

A document kept outside the repo (`kept_outside_repo: true`: a copyrighted code book, such as New York's Residential
Code, `layout: icc`) is read from the code cache (rule_format.rulebook.code_cache), only its brought-in pages
(`brought_in`); its text is written to the cache, next to it, and only its sections file (section numbers, titles,
line counts and fingerprints: no words of the book) to 2_extracted_text/. Where the cache doesn't have it (CI), it
is skipped, and the run says so.
"""

import argparse
import sys
from pathlib import Path

import yaml

from rule_format.place import place
from rule_format.rulebook import cached, law_folders, utf8_console

from . import icc_sections, sections
from .charts import read_charts
from .extract import extract, sha256, to_jsonl
from .icc import extract_icc

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
    """A book kept outside the repo: its brought-in pages read from the cache, the text written back to the cache,
    the sections file to the repo. Skipped (not failed) where the cache doesn't have the book. True when fine."""
    pdf, text = cached(doc), cached(doc, ".jsonl")
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
    rows = extract_icc(pdf, icc_sections.parse_pages(doc["brought_in"]["pages"]))
    cut = icc_sections.split(rows, doc["brought_in"])
    outputs = {text: to_jsonl(rows), jurisdiction / "2_extracted_text" / f"{Path(doc['file']).stem}.sections.jsonl":
               icc_sections.to_jsonl(cut, rows[0])}
    return all([_write_or_check(path, fresh, check) for path, fresh in outputs.items()])


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
