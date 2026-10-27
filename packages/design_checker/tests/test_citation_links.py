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


def test_every_chart_link_finds_its_words_in_the_pdf():
    """Review round 1 (the link fix): a chart link's search is words the PDF page really holds in that order, so a
    viewer lands on it: never a neighbouring cell's wrapped words ("1 space 1 space" for Dormitory parking), never
    words on both sides of a footnote's superscript."""
    import urllib.parse
    docs = present._documents(J)
    missing = []
    for path in sorted((J / "5_zoning_rules").glob("*.yaml")):
        for rule in load(path)["rules"]:
            for s in rule.get("sources") or []:
                if not s["file"].startswith("zoning_charts"):
                    continue
                link = present.link(s, J, docs)
                words = urllib.parse.unquote(link.split("&search=")[1]).strip('"') if "&search=" in link else ""
                if "".join(words.split()) not in _pdf_text(s["file"], s["page"]):
                    missing.append((rule["id"], s["page"], words))
    assert not missing, sorted(set(missing))[:20]
