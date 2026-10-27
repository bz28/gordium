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

## Sections (for labeling)

A document marked `layout: ecode360` in `sources.yaml` (a city code chapter in eCode360's layout, like Chapter 325) is also cut into pieces at its own headings, saved as `<document>.sections.jsonl` and checked by `--check` like the text:

```
{"file": "chapter_325_zoning_2026-10.pdf", "sha256": "5ceb…", "splitter": "document_extraction.sections v2", "pieces": 626, "problems": [], "furniture": [[1, 1], …]}
{"id": "325-16C", "title": "Height and open space", "kind": "subsection", "lines": [[47, 6, 14]]}
```

- Pieces: the front matter (table of contents, history); each section (`§ 325-16`), with an article heading attached to the section after it; each lettered subsection (`325-16C`); each defined term in a Definitions section (`325-3B:height_of_building`); each editor's note.
- Guards against false headings: a heading starts at the headings' margin (measured from the document; text inside a subsection is indented further), section numbers must increase, subsection letters must come in order (A, B, C), a subsection heading must be followed by an indented line or another heading (a section's own text wraps at the margin, so a margin line "A. ..." followed by more margin text is that text, and is reported), and a defined term is mostly capitals before its dash, inside a Definitions section. A line at the margin that looks like a heading but breaks the order is reported, never silently skipped, and every section in the document's own table of contents must be found (and no other). Any of these goes in the header's `problems` and fails CI.
- Every line is in exactly one piece, or is page furniture (the repeated first line, the running header, the download footer). The coverage report checks this from the text itself.
- Chapter 325: 626 pieces (83 sections, 275 subsections, 219 definitions, 48 editor's notes, the front matter), no problems; every section in the law's own table of contents is a piece.

## Decisions

- **pdfplumber**, pinned to an exact version together with pdfminer.six, because a different version could read text differently and break reproducibility. Upgrading is a deliberate change: re-extract, review the diff.
- **De-duplicated characters:** some PDFs draw text twice, slightly offset, to look bold. Without this, the charts read "RREESSIIDDEENNTTIIAALL" and "12 5 f t".
- **Lines, not tables:** this step only records text and where it is. Reading tables (the zoning charts) is a later step that uses these positions.
