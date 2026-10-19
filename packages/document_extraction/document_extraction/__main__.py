"""Extract the text of every source document listed in each jurisdiction's sources.yaml.

    python -m document_extraction           # (re)write 2_extracted_text/<pdf name>.jsonl
    python -m document_extraction --check   # exit 1 if any saved file differs from a fresh extraction

Refuses to extract a PDF whose fingerprint doesn't match sources.yaml.
"""

import sys
from pathlib import Path

import yaml

from .extract import extract, sha256, to_jsonl

REPO = Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    failed = 0
    for jurisdiction in sorted(p for p in (REPO / "regulations/jurisdictions").glob("*/*") if p.is_dir()):
        sources = jurisdiction / "1_source_documents"
        out_dir = jurisdiction / "2_extracted_text"
        for doc in yaml.safe_load((sources / "sources.yaml").read_text())["documents"]:
            pdf, out = sources / doc["file"], out_dir / f"{Path(doc['file']).stem}.jsonl"
            label = out.relative_to(REPO)
            if sha256(pdf) != doc["sha256"]:
                print(f"✗ {pdf.relative_to(REPO)}: fingerprint doesn't match sources.yaml; not extracted")
                failed += 1
                continue
            fresh = to_jsonl(extract(pdf))
            if check:
                same = out.exists() and out.read_text() == fresh
                print(f"{'✓' if same else '✗'} {label}{'' if same else ': differs from a fresh extraction'}")
                failed += not same
            else:
                out_dir.mkdir(exist_ok=True)
                out.write_text(fresh)
                print(f"wrote {label} ({fresh.count(chr(10)) - 1} lines)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
