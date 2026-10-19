# document_extraction

Step 2 of the pipeline: pulls every line of text out of each source PDF, with its page number and position on the page, so every rule can point to the exact spot its quote comes from. Plain code, no AI: the same PDF always gives the same file.

```bash
python -m document_extraction           # (re)write regulations/jurisdictions/*/*/2_extracted_text/*.jsonl
python -m document_extraction --check   # fail if any saved file differs from a fresh extraction (CI runs this)
pytest packages/document_extraction
```

## Output

One `.jsonl` file per PDF listed in `sources.yaml` (one JSON object per line):

```
{"file": "zoning_charts_2026-04.pdf", "sha256": "042a…", "pages": 17, "extractor": "pdfplumber 0.11.10 (…)"}
{"page": 3, "line": 42, "text": "Rear (minimum, % of depth or feet, 25%/ 25%/ …", "x0": 36.0, "top": 590.1, "x1": 571.2, "bottom": 600.3}
```

- The header names the exact PDF version (its fingerprint). `rule_format` rejects extracted text whose fingerprint doesn't match `sources.yaml`.
- Positions are in PDF points (1/72 inch) from the page's top-left corner.
- PDFs whose fingerprint doesn't match `sources.yaml` are refused, not extracted.

## Decisions

- **pdfplumber**, pinned to an exact version together with pdfminer.six, because a different version could read text differently and break reproducibility. Upgrading is a deliberate change: re-extract, review the diff.
- **De-duplicated characters:** some PDFs draw text twice, slightly offset, to look bold. Without this, the charts read "RREESSIIDDEENNTTIIAALL" and "12 5 f t".
- **Lines, not tables:** this step only records text and where it is. Reading tables (the zoning charts) is a later step that uses these positions.
