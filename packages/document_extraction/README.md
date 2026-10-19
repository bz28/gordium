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
- **Tables from what the PDF draws:** the chart reader uses the cell rectangles and borders the PDF draws, not guesses from where text happens to sit. Where the drawing doesn't settle it, the cell is reported as unresolved.

## Chart cells

For a document with `chart_pages` in `sources.yaml` (the zoning charts: pp. 2, 3 and 14, the residential districts), the same command also writes `<pdf name>.cells.jsonl`: every value in each chart table, with its row, its district column and the lines it comes from. `--check` re-reads it too.

```
{"page": 3, "section": "Yard Dimensions", "row": "Front (minimum)", "heading": false, "row_lines": [37],
 "column": "R-1B", "value": "25 ft", "lines": [37], "spans": ["R-1B"], "x0": 310.0, "top": 789.4, ...}
```

How it reads a table (`charts.py`), plain code with no judgment:

1. **Columns:** the header rectangles whose text is a district name (R-1A … R-3B, RU) with no other district name under them ("R-1" is a group over R-1A and R-1B). Other header columns beside them ("Additional Regulations") are kept too. The row label is the space to their left.
2. **Rows:** the chart shades every other row with drawn rectangles; a white row is the gap between two shaded rows. After the last shaded row, the next lines that are close together and fit the columns are the last row. Lines there that don't fit (the notes under a chart run across the columns) are reported as unresolved, not dropped.
3. **Cells:** in each row, a drawn rectangle or the gap between drawn vertical borders is one cell. One that covers several columns is a merged cell and applies to each of them (`spans`): p.14's "1 space per dwelling unit" covers all nine districts. Elsewhere each column is its own cell.
4. **Values:** each word goes in the cell that contains it, top line first, so multi-line cells read in order ("35%/40% /50% [fn12]"). Footnote markers are the extractor's (`[fn12]`), and line numbers are the extracted text's, so a cited line leads to its cells.
5. **Headings:** a row whose cells are all empty ("Yard Dimensions") names the `section` of the rows below; it tells apart rows with the same label ("One-family dwelling, detached" under both lot size and lot width). After an unresolved row, the rows below get no `section` (the unread row may have been a heading), and two rows with the same label under one section are both reported unresolved ("same row label twice under one section"), since a rule couldn't tell them apart.
6. **Never guessed:** a word across a cell edge, a drawn cell reaching from the label into the columns (a whole-row stripe, an outer border), a cell covering part of a column, a label area that isn't exactly one cell, a column left without a cell or covered by two, values with no row label, or a row that looks like two rows makes the **whole row** unresolved (every row read is one label and one cell per column) (`{"unresolved": why, ...}`), with none of its values written, so a half-read row can't pass as a full one. District names at different heights (a body cell that reads "RU"), any drawn rectangle or border dividing the label area (a column left of the districts, named or not), or a table with no drawn body rows makes the **page** unresolved. The district-name pattern (`DISTRICT` in `charts.py`) is Ithaca's residential one and grows with each chart page added. On the residential charts the only one is p.2's notes.

How we know it's right: `tests/test_r1b_matches_chart.py` compares the reader's R-1B cells with the R-1b rules drafted by reading (two independent readings must agree): for every cited row, the rule passes exactly at the chart's value and fails just past it (starting from the rule's own passing example, so the number limits the right measurement in the right direction), every numbered R-1B cell is cited by a rule, and the allowed and special-permit uses match the chart's • and SP marks. `tests/test_cells_match_lines.py` cross-checks every district: for each chart row on one line, the plain extracted line must be exactly the row's label and its cells' values in column order (56 rows agree). The 6 rows whose label or values wrap onto other lines (rear yard, lot coverage, other side yard, first parking band, dormitory, tower) are listed by name with the reason; every column of each is asserted against a value read by hand from the PDF (word positions against the drawn column edges, cited by page and line), and an order-free check confirms their lines' words, less the label, are exactly their cells' words. `tests/test_charts.py` checks other districts' cells, that every line of a table lands in exactly one row and every word in its label or one cell, and each safeguard on small built pages.
