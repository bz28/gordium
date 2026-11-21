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
  done honestly from this copy, so `text_verification.icc.ibc.2009.yaml` is not written, and `python -m rule_format`
  fails on it, on purpose. **Ben decides:** buy ICC's 2009 IBC (PDF), or name another copy that is a true scan.
- **NFPA 101 (2012) is NFPA's own PDF** (real text in its fonts, one licensed copy), so its second reading from the
  page images can go ahead as in New York.
- **Not done yet:** labels, definitions, rules, `parts.yaml` measures and the coverage report (they depend on the
  verified text). The answer key from the sheet is recorded:
  `test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml`.

## Open questions for Ben

1. **Copies to buy:** ICC 2009 IBC (blocking, above) and NFPA 101 2012 (to confirm this copy).
2. **NFPA edition:** the sheet's numbers match the 2012 edition; Maine's Fire Marshal rule (16-219 CMR ch. 20)
   adopted an earlier edition in 2016 (2009, as Ben has it) and today names the 2018 edition with Maine's own
   modifications, one of them the dead-end corridor limit (20 ft). Which edition and modifications applied on the
   permit date decides the dead-end result (21'-6": passes the IBC by its exception 3 and NFPA 2012's 50 ft when
   sprinklered; fails a flat 20 ft).
3. **IBC edition:** MUBEC's rules are 16-642 CMR (filed October 2010); that the 2009 IBC was in force in Portland in
   October 2016 is the sheet's word, not yet the rule text's.

## Alternatives rejected

- **Use the item's HTML** (cleaner words): it is the same OCR, edited by an unknown hand, with no pages or lines.
- **Read the 2009 IBC numbers from this copy's page images anyway:** they print the OCR's errors, so two readings
  would agree on them; a false agreement is exactly what the second reading exists to prevent.
