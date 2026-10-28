"""Every citation link in every rulebook points at one place: two sources share a link only if they point at the same
line of the same page (a quote, or a chart cell's own row line). Found on #20: a chart cell's link searched its row
label alone, and "One-family dwelling, detached" is a row of both the lot-size and the lot-width sections of chart
p.3, so the two rows' citations opened the same search and were named two ways in one check."""

from rule_format.rulebook import REPO, load

from design_checker import present

J = REPO / "regulations/jurisdictions/new_york/ithaca_city"


def _where(source):
    """(file, page, first line) the source points at: a quote's own first line, a cell's row line."""
    if source.get("lines"):
        return source["file"], source["page"], source["lines"][0]
    want = source.get("cell") or {}
    cell = next((c for c in present._chart_cells(J) if c.get("file") == source["file"] and c["page"] == source["page"]
                 and c.get("section") == want.get("section") and str(c["row"]).strip() == str(want.get("row")).strip()),
                None)
    assert cell and cell.get("row_lines"), source
    lines = present._page_lines(J, source["file"])
    label = " ".join(str(want.get("row")).split())
    own = [n for n in cell["row_lines"] if " ".join((lines.get((source["page"], n)) or "").split()).startswith(label)]
    return source["file"], source["page"], (own or cell["row_lines"])[0]     # the label's own line


def test_no_two_places_share_a_citation_link():
    docs = present._documents(J)
    places = {}
    for path in sorted((J / "5_zoning_rules").glob("*.yaml")):
        for rule in load(path)["rules"]:
            for s in rule.get("sources") or []:
                places.setdefault(present.link(s, J, docs), set()).add(_where(s))
    shared = {link: sorted(p) for link, p in places.items() if len(p) > 1}
    assert not shared, shared


def test_a_cell_links_to_its_own_row_not_the_label_alone():
    docs = present._documents(J)
    size = {"file": "zoning_charts_2026-04.pdf", "page": 3,
            "cell": {"section": "Minimum Lot Size [fn3]", "row": "One-family dwelling, detached", "column": "R-1A"}}
    width = {"file": "zoning_charts_2026-04.pdf", "page": 3,
             "cell": {"section": "Minimum Lot Width", "row": "One-family dwelling, detached", "column": "R-1A"}}
    assert present.link(size, J, docs) != present.link(width, J, docs)
    assert present.anchor_text(size, J).startswith("One-family dwelling, detached 10,000 sf")


def _pdf_text(file, page, cache={}):
    """The page's characters in the order the PDF stores them (what a viewer's search runs over), spaces removed."""
    import pdfplumber
    if (file, page) not in cache:
        with pdfplumber.open(J / "1_source_documents" / file) as pdf:
            cache[(file, page)] = "".join("".join(c["text"] for c in pdf.pages[page - 1].chars).split())
    return cache[(file, page)]


def test_every_link_finds_its_words_in_the_pdf():
    """Review round 1 (the link fix): a link's search is words the PDF page really holds in that order, so a viewer
    lands on it: never a neighbouring cell's wrapped words ("1 space 1 space" for Dormitory parking), never words on
    both sides of a footnote's superscript. Round 2: law quotes (chapter 325) are checked the same way as chart cells,
    not skipped."""
    import urllib.parse
    docs = present._documents(J)
    missing, checked = [], {"law": 0, "chart": 0}
    for path in sorted((J / "5_zoning_rules").glob("*.yaml")):
        for rule in load(path)["rules"]:
            for s in rule.get("sources") or []:
                if not s["file"].endswith(".pdf"):
                    continue
                link = present.link(s, J, docs)
                assert "&search=" in link, (rule["id"], link)
                words = urllib.parse.unquote(link.split("&search=")[1]).strip('"')
                checked["chart" if s["file"].startswith("zoning_charts") else "law"] += 1
                if "".join(words.split()) not in _pdf_text(s["file"], s["page"]):
                    missing.append((rule["id"], s["page"], words))
    assert checked["law"] and checked["chart"], checked      # both kinds are really checked
    assert not missing, sorted(set(missing))[:20]


def test_a_numbered_definition_links_without_its_list_number():
    """Review round 3: chapter 325 p.7 lists the one-family configurations as "(1) ONE-FAMILY DETACHED DWELLING — ..."
    but the PDF stores the list numbers apart from the words, so a search beginning "(1)" lands nowhere (R-2c's
    lot-area quotes, on #24)."""
    import urllib.parse
    quote = {"file": "chapter_325_zoning_2026-10.pdf", "page": 7, "lines": [42, 42],
             "quote": "(1) ONE-FAMILY DETACHED DWELLING — A building containing not more than one"}
    link = present.link(quote, J, present._documents(J))
    words = urllib.parse.unquote(link.split("&search=")[1]).strip('"')
    assert words.startswith("ONE-FAMILY DETACHED DWELLING")
    assert "".join(words.split()) in _pdf_text(quote["file"], 7)


def test_list_numbers_and_footnote_markers_never_split_a_search():
    """Review round 4 (seen on #38's rulebooks): a quote that begins with a list number and then a footnote marker
    ("(6) [fn3]In R-1 and R-2 ...", p.26) had no search left at all; a list number after the term ("HOME OCCUPATION —
    (1) A", p.12) split the search. Each now searches only words the PDF holds in one run."""
    import urllib.parse
    docs = present._documents(J)
    for page, quote, start in [
            (26, "(6) [fn3]In R-1 and R-2 Districts, minor dependent children in the care of a parent or relative",
             "In R-1 and R-2 Districts"),
            (12, "HOME OCCUPATION — (1) A subordinate use of a nonresidential nature which is conducted", "HOME OCCUPATION")]:
        link = present.link({"file": "chapter_325_zoning_2026-10.pdf", "page": page, "quote": quote}, J, docs)
        assert "&search=" in link, link
        words = urllib.parse.unquote(link.split("&search=")[1]).strip('"')
        assert words.startswith(start) and "(1)" not in words, words
        assert "".join(words.split()) in _pdf_text("chapter_325_zoning_2026-10.pdf", page), words


def test_a_documents_lines_are_read_again_after_a_re_extraction(tmp_path):
    """The page lines a citation link searches are kept by the file's content, never by folder name, as the chart cells
    are (#50): after a re-extraction in a long Rhino session the link searches the new text. Found carrying merge 2:
    #20's folder-keyed cache met main's #50, which had taken away the import it used, so present.py no longer loaded."""
    (tmp_path / "2_extracted_text").mkdir()
    f = tmp_path / "2_extracted_text" / "code.jsonl"
    f.write_text('{"file": "code.pdf"}\n{"page": 3, "line": 7, "text": "Lot width 50 ft"}\n', encoding="utf-8")
    assert present._page_lines(tmp_path, "code.pdf") == {(3, 7): "Lot width 50 ft"}
    f.write_text('{"file": "code.pdf"}\n{"page": 3, "line": 7, "text": "Lot width 60 ft"}\n', encoding="utf-8")
    assert present._page_lines(tmp_path, "code.pdf") == {(3, 7): "Lot width 60 ft"}
    assert present._page_lines(tmp_path, "missing.pdf") == {}
