# Commercial egress for Maine: which books, which copies, and what blocks the rules (2026-11-20)

**Purpose:** why Gordium's first commercial egress law is the 2009 IBC and NFPA 101 (2012) for Maine, where their text lives, how it is read, and what is open for Ben.\
**For:** engineers bringing in a building or life-safety code; Ben (copies to buy, the edition questions).\
**Kept current by:** the engineer who brings in more of these books or changes how a two-column book is read.

Follows the New York precedent ([building code text](2026-11-12_building_code_text.md)): code cache outside the
repo, short quotes only, a sections file, every number read twice and comparison words a third way, definitions by
the book's own rule, the book's own errors named.

## Decisions

1. **Editions: the ones the architect's sheet cites**, so the sheet is a fair answer key. The life-safety sheet for
   the first project (LS1.0, Children's Odyssey, 19 Libby Street, Portland, October 2016) cites the **2009
   International Building Code** and **NFPA 101 section numbers of the 2012 edition**. Which editions Maine enforced
   on that permit date is open (below); the books are what the sheet was checked against.
2. **Copies:** Public.Resource.Org's on the Internet Archive (`gov.law.icc.ibc.2009`, `gov.law.nfpa.101.bis.2012`),
   never ICC's or NFPA's online viewers (their terms forbid automated reading). Everything is **verified against this
   copy only; check against a purchased copy**. Fingerprints, links and terms: `regulations/jurisdictions/maine/
   maine_state/1_source_documents/sources.yaml`.
3. **Folder:** `regulations/jurisdictions/maine/maine_state/` (a state law folder: `state.yaml`, both books). No
   Portland place folder: the registry doesn't need one (a state folder stands on its own), and a second place would
   stop the Rhino plugin until it has a place picker (adding_a_place.md).
4. **A new layout, `two_column`** (`document_extraction/columns.py`, `columns_sections.py`): both books print two
   columns, which the ICC extractor reads straight across. Columns by the page's gutter, words by letter gaps,
   stacked and glyph fractions in digits, NFPA's licence-number stamp read last. Headings: NFPA's are bold; the IBC
   copy has no bold, so a heading must be next in order with a capitalized title, and anything else that looks like
   one is a problem unless named. Tables are pieces of their own, their lines named in `sources.yaml` (`tables`).
   Definitions: the IBC by its italics (its preface: "Selected terms set forth in Chapter 2 ... are italicized"),
   matched by their letters so the OCR's run-together words still name them; NFPA marks none, so every Chapter 3
   term a piece prints (3.1). The OCR's misreads are put right by line, by name (`brought_in.misread`), never in the
   cached text. The cached text's key covers `columns.py`, so the cache stays the same for every branch.
5. **Multiple books per state folder:** one `text_verification.<book>.yaml` per book (`rulebook.verification_files`);
   New York's single `text_verification.yaml` is unchanged.

## What was found, and what is blocked

- **The IBC "scan" is not a scan of ICC's book.** Its PDF holds no page images: every page is text drawn in fonts
  from ABBYY's OCR. The 600 dpi page images in the item (`icc.ibc.2009_jp2.zip`) show the same thing, with the OCR's
  errors printed: Table 1015.1 reads "H-4, H-5, 1-1, 1-3, 1-4, R" in the image itself (p.266), where ICC's book
  prints I-1, I-3, I-4. So **no page image in this copy is independent of the OCR**: a second reading from it would
  share the OCR's errors (a "1-hour" read as "I-hour", an I-4 read as 1-4). The precedent's second reading cannot be
  done honestly from this copy, so `text_verification.icc.ibc.2009.yaml` records each piece's numbers only, with a
  top-level `not_verified` saying why (`rule_format/state_law.py` accepts it explicitly: no second-reading field
  allowed in it). **Looked for an independent copy (2026-11-20):** the Internet Archive's other 2009 IBC
  postings are Public.Resource.Org's Washington Building Code 2009 (`gov.wa.building.2009`: the same OCR-made pages,
  page for page, e.g. its p.419 is this copy's p.266, same characters and fonts), and an individual's upload
  (`2009InternationalBuildingCode`, 2017, "community" collection, no Public.Resource.Org posting and no stated licence),
  which is not used: its provenance is unknown. So **every IBC number is "read from an OCR copy only: not verified"**
  (`text_verification.icc.ibc.2009.yaml`, `not_verified`), and every IBC requirement is drafted as a flag: its check
  formula is kept, but it always needs review, never passes, until the numbers are checked against a purchased ICC copy.
  The one open item: **buy ICC's 2009 IBC.**
- **NFPA 101 (2012) is NFPA's own PDF** (real text in its fonts, one licensed copy), so its second reading from the
  page images can go ahead as in New York.
- **Done since (2026-11-20, step 2):** labels for every piece of both books, definitions, `parts.yaml` kinds (story,
  space, corridor, means-of-egress door, each measure defined in words), 60 rules (every IBC requirement a flag that
  keeps its check as the drafted test, proved by each example's `drafted_check`; NFPA rules on the second reading) and
  the coverage report (nothing left unchecked). On the sheet's own numbers every rule gives the sheet's result
  (`rule_format/tests/test_maine_egress.py`, against
  `test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml`). The folder's README has the details.

## Open questions for Ben

1. **Copies to buy:** ICC's 2009 IBC (the one item that keeps IBC rules from passing) and NFPA 101 2012 (to confirm
   this copy).
2. **Two Maine rules, two books.** The building code is MUBEC (10 M.R.S. ch. 1103), whose rules are **16-642 CMR**
   (Technical Building Codes and Standards Board; filed October 2010). The Life Safety Code is adopted by the State Fire
   Marshal's own rule, **16-219 CMR ch. 20** (Fire Safety in Buildings and Structures), with Maine's exclusions and
   modifications.
3. **The 2016 editions are open.** Found: today's MUBEC uses the 2021 I-codes (since 2025-04-07), before that the 2015
   I-codes; the rules filed in 2010 adopted the 2009 I-codes; no rule text was found online saying which IBC edition
   Portland enforced in October 2016 (the sheet says the 2009 IBC). Today's 16-219 CMR ch. 20 names the 2018 NFPA 101
   (amended 2021-01-25); in 2016 it named an earlier edition (2009, as Ben has it, and a Maine Municipal Association
   note says the same); the sheet's section numbers match the 2012 edition. Sources: law.cornell.edu (16-219 CMR ch.
   20), maine.gov Fire Marshal rules page and MUBEC Ch 1, read 2026-11-20.
4. **Maine's dead-end limit would fail the sheet.** Today's 16-219 CMR ch. 20 modifies the dead-end corridor limit to
   20 ft. The sheet's dead end is 21'-6": it passes the 2009 IBC only by 1018.4 exception 3 (less than 2.5 x its 10-ft
   width = 25 ft) and NFPA 2012's 50 ft in a sprinklered building, but **fails a flat 20-ft limit**. Whether the 2016
   rule had that modification, and for day care, is part of question 3.

## Alternatives rejected

- **Use the item's HTML** (cleaner words): it is the same OCR, edited by an unknown hand, with no pages or lines.
- **Read the 2009 IBC numbers from this copy's page images anyway:** they print the OCR's errors, so two readings
  would agree on them; a false agreement is exactly what the second reading exists to prevent.
