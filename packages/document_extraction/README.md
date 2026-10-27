# document_extraction

Step 2 of the pipeline: pulls every line of text out of each source PDF, with its page number and position on the page, so every rule can point to the exact spot its quote comes from. Plain code, no AI: the same PDF always gives the same file.

```bash
python -m document_extraction           # (re)write regulations/jurisdictions/*/*/2_extracted_text/*.jsonl
python -m document_extraction --check   # fail if any saved file differs from a fresh extraction (CI runs this)
                                        # any other argument is rejected, so a typo can't overwrite files
pytest packages/document_extraction
```

## Output

One `.jsonl` file per PDF listed in `sources.yaml` (one JSON object per line):

```
{"file": "zoning_charts_2026-04.pdf", "sha256": "042a…", "pages": 17, "extractor": "pdfplumber 0.11.10 + pdfminer.six 20260107 (dedupe_chars, level text only, extract_text_lines, footnotes as [fnN])", "rotated_chars_skipped": 0}
{"page": 3, "line": 42, "text": "Rear (minimum, % of depth or feet, 25%/ 25%/ 25% …", "x0": 106.4, "top": 877.2, "x1": 738.8, "bottom": 888.2}
```

- The header names the exact PDF version (its fingerprint). `rule_format` rejects extracted text whose fingerprint doesn't match `sources.yaml`.
- Positions are in PDF points (1/72 inch) from the page's top-left corner.
- Footnote markers (characters smaller than the page's normal text **and** raised above the line) are written as a sealed token: `3/2 [fn11]` is the value 3/2 with footnote 11. Quotes are matched as whole tokens, so a footnote can never be quoted or read as a value. Raised letters right after a number ("19th") stay plain.
- Documents whose text isn't reliable yet are marked `quotable: false` in `sources.yaml` with a `not_quotable_because` reason; the inspector refuses quotes from them, and rejects any `sources.yaml` entry with an unknown field, a non-true/false `quotable`, or a missing reason.
- Steeply tilted text (more than 5° from level: most map street labels, angled or vertical diagram labels) is left out; the header's `rotated_chars_skipped` says how many characters. Text within 5° of level is kept, including some slightly tilted map labels. The angle comes from each character's own orientation in the PDF.
- PDFs whose fingerprint doesn't match `sources.yaml` are refused, not extracted.

## Decisions

- **pdfplumber**, pinned to an exact version together with pdfminer.six, because a different version could read text differently and break reproducibility. Upgrading is a deliberate change: re-extract, review the diff.
- **De-duplicated characters:** some PDFs draw text twice, slightly offset, to look bold. Without this, the charts read "RREESSIIDDEENNTTIIAALL" and "12 5 f t".
- **Lines, not tables:** this step only records text and where it is. Reading tables (the zoning charts) is a later step that uses these positions.
