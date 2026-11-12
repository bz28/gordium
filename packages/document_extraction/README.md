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

## A code book kept outside the repo (layout: icc)

A copyrighted code book (the 2025 Residential Code of New York State) is marked `kept_outside_repo: true` and `layout: icc` in `sources.yaml`. It is read from the code cache (`$GORDIUM_CODE_CACHE`, else `~/Documents/gordium_archive/code_cache/<sha256>/`). The cache keeps the text of every page, once per book and extractor version (`book_text.py`), so it is the same for every branch; each branch reads its brought-in pages (`brought_in: pages`) from it, and `--check` re-extracts those pages and requires them to be the cached text's, byte for byte. Only the sections file comes to the repo. Where the cache is missing (CI), it is skipped, and the run says so. Why: [docs/decisions/2026-11-12_building_code_text.md](../../docs/decisions/2026-11-12_building_code_text.md).

- **Stacked fractions** (`icc.py`): ICC prints 8 1/4 as a full-size 8, a small raised 1, a full-size slash and a small lowered 4. The extractor puts each back on its line as one word, "8 1/4" (a space between the whole number and the fraction, so it can never read as 81/4). A small raised digit that is no numerator stays a sealed footnote marker (`m[fn2]`, m²). Each line also records its `italic` and `bold` runs ([start, end] offsets into its text).
- **Cutting** (`icc_sections.py`): a piece starts at a line that starts in bold: `SECTION R318—...`, a numbered part (`[NY] R318.7.5.1 Risers.`), or a defined term in capitals in a section titled DEFINITIONS (Section R202, or an appendix's own, such as BO103). Appendix sections (`BO105.10`) are cut like the code's. Numbered parts must come in order, and a brought-in part must end on the pages read; anything else is a problem in the header, unless `sources.yaml` names the line as the book's own misnumbering (`printed_out_of_order`) or a term New York's rules amend (`amended_by_law`), each with why. An appendix's own definitions apply in that appendix only. `brought_in: alone` brings in a part without the parts under it. Brought in: the `brought_in: sections`, and every R202 definition they use (by the book's italics, R201.1), then the definitions those use; a definition whose term a section prints in roman type too, with the definitions it uses. A kept piece that uses a definition not kept is a problem. Every other line of the pages read is furniture, or is listed in the header's `outside` with the part it belongs to.
- **Numbers** (`numbers.py`): every number of a piece with its limit words and unit ("not more than 8 1/4 inch"), so the text can be compared with a second reading of the page images (the state folder's `text_verification.yaml`).

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
