"""Extract the text of every source document listed in each jurisdiction's sources.yaml.

    python -m document_extraction           # (re)write 2_extracted_text/<pdf name>.jsonl, and
                                            # <pdf name>.cells.jsonl for documents with chart_pages
    python -m document_extraction --check   # exit 1 if any saved file differs from a fresh extraction

Refuses to extract a PDF whose fingerprint doesn't match sources.yaml.
"""

import argparse
import sys
from pathlib import Path

import yaml

from rule_format.rulebook import jurisdictions

from .charts import read_charts
from .extract import extract, sha256, to_jsonl

REPO = Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m document_extraction")
    parser.add_argument("--check", action="store_true", help="compare with a fresh extraction; write nothing")
    check = parser.parse_args(argv).check  # unknown arguments stop here, so a typo can't overwrite files
    failed = 0
    for jurisdiction in jurisdictions(REPO):
        sources = jurisdiction / "1_source_documents"
        out_dir = jurisdiction / "2_extracted_text"
        for doc in yaml.safe_load((sources / "sources.yaml").read_text())["documents"]:
            pdf, out = sources / doc["file"], out_dir / f"{Path(doc['file']).stem}.jsonl"
            if sha256(pdf) != doc["sha256"]:
                print(f"✗ {pdf.relative_to(REPO)}: fingerprint doesn't match sources.yaml; not extracted")
                failed += 1
                continue
            outputs = [(out, to_jsonl(extract(pdf)))]
            if doc.get("chart_pages"):   # tables read into cells, from the same lines
                outputs.append((out_dir / f"{Path(doc['file']).stem}.cells.jsonl",
                                to_jsonl(read_charts(pdf, doc["chart_pages"]))))
            for path, fresh in outputs:
                label = path.relative_to(REPO)
                if check:
                    same = path.exists() and path.read_text(encoding="utf-8") == fresh
                    print(f"{'✓' if same else '✗'} {label}{'' if same else ': differs from a fresh extraction'}")
                    failed += not same
                else:
                    out_dir.mkdir(exist_ok=True)
                    path.write_text(fresh, encoding="utf-8", newline="\n")
                    print(f"wrote {label} ({fresh.count(chr(10)) - 1} records)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
