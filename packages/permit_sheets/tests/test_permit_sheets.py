"""The permit sheets (packages/permit_sheets): a print-out of the egress check, never a second check.

What is pinned here (each test fails when the rule it names is undone):
- every printed result is the check's own status, word for word; NEEDS REVIEW and WAITING never print as complying;
- a window's or a room's line is never kinder than its worst row, and no rows at all is NEEDS REVIEW;
- the check's own items with no row (the interior's problems, windows marked but not checked) are printed;
- the sheets stop, printing nothing, when the result contradicts itself, its counts don't add up, the interior isn't
  the one checked, or the rules changed since the check;
- every row traces to the check (rule id, part, values, citation, quote) and the title block carries the
  disclaimer, the date and the fingerprints;
- values are never rounded toward compliance; what wasn't read is said on the plan, never drawn as none;
- the golden sheets of every test house match a fresh build.
"""

import csv
import io
import json
from functools import lru_cache

import pdfplumber
import pytest

from design_checker import present
from design_checker.check import check_site
from permit_sheets import build, draw, goldens, sheets, source, tables, words
from permit_sheets.words import Refused

ORANGETOWN = "orangetown_ny_80_south_william"


@lru_cache(maxsize=None)
def _result(name: str, mutate: str = "") -> str:
    """check_site's result for a golden house (JSON text, so each test gets its own copy)."""
    house = _house(name, mutate)
    return json.dumps(check_site(goldens.site(), goldens.facts_of(name), name=name, today=goldens.DATE,
                                 interior=house))


def _house(name: str, mutate: str = ""):
    house = goldens.interior_of(name)
    if mutate == "no_window_bed1":                      # the ranch's Bedroom 1 with its escape window unmarked
        for o in house["openings"]:
            if o["room"] == "bed1":
                o["escape"] = False
    return house


def result(name: str, mutate: str = "") -> dict:
    return json.loads(_result(name, mutate))


def about() -> dict:
    return {"rulebook": source.fingerprints_now(), "worker_fingerprint": "test"}


def got(name: str, mutate: str = "") -> dict:
    return source.gather(result(name, mutate), about(), _house(name, mutate))


def law_items(r: dict) -> list[dict]:
    return [i for i in r["view"]["items"] if i["group"] == present.LAW_GROUP]


def pdf_pages(name: str) -> list[str]:
    with pdfplumber.open(goldens.GOLDENS / name / "permit_sheets.pdf") as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def csv_rows(name: str, file: str) -> list[dict]:
    text = (goldens.GOLDENS / name / file).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


# ---- every result is the check's ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["2_two_story_small_window", ORANGETOWN, "0_no_rooms_yet"])
def test_every_printed_result_is_the_checks_own_status(name):
    r = result(name)
    rows = tables.code_rows(got(name))
    items = law_items(r)
    assert [x["Item id"] for x in rows] == [i["id"] for i in items]
    for row, item in zip(rows, items):
        assert row["Result"] == words.result_words(item["status"], item.get("waiting"))
        assert row["Rule id"] == (item["rule"] or "")
        assert row["Citation"] == item["detail"]["citation"]
        assert row["Code's words"] == ((item.get("code") or {}).get("quote") or "")
    # the committed golden CSV says the same, row for row
    assert [x["Result"] for x in csv_rows(name, "code_analysis.csv")] == [x["Result"] for x in rows]


def test_result_words_are_exact_and_unknown_ones_are_refused():
    assert words.result_words(present.REVIEW) == "NEEDS REVIEW"
    assert words.result_words(present.FAILS) == "DOES NOT COMPLY"
    assert words.result_words(present.COMPLIES) == "COMPLIES"
    assert words.result_words(present.NOT_CHECKED, "no rooms drawn yet") == "WAITING: NO ROOMS DRAWN YET"
    for bad in ("pass", "ok", "", None):
        with pytest.raises(Refused):
            words.result_words(bad)
    with pytest.raises(Refused):                      # "not checked" without the check's waiting words
        words.result_words(present.NOT_CHECKED)


def test_needs_review_never_prints_as_complying_anywhere():
    for name in goldens.names():
        for row in csv_rows(name, "code_analysis.csv"):
            assert row["Result"] in ("COMPLIES", "DOES NOT COMPLY", "NEEDS REVIEW", "WAITING: NO ROOMS DRAWN YET",
                                     "NOT APPLICABLE")
        statuses = {i["id"]: i["status"] for i in law_items(result(name))}
        for row in csv_rows(name, "code_analysis.csv"):
            if statuses[row["Item id"]] != present.COMPLIES:
                assert row["Result"] != "COMPLIES"
            # not applicable only for what the house description says it has none of (has_none), with the source
            assert (row["Result"] == "NOT APPLICABLE") == (statuses[row["Item id"]] == present.NOT_APPLICABLE)


def test_waiting_prints_waiting_on_all_three_sheets():
    pages = pdf_pages("0_no_rooms_yet")
    assert len(pages) == 3
    for text in pages:
        assert "WAITING: NO ROOMS DRAWN YET" in text
        # (the plan's legend lists the four words; nothing else on a waiting sheet may say complies)
        assert "COMPLIES" not in text.replace("DOES NOT COMPLY", "").replace("Results: COMPLIES", "")
    # the words are the check's own: another reason a law waits prints as it is
    r = result("0_no_rooms_yet")
    for i in r["view"]["items"]:
        if i.get("waiting"):
            i["waiting"] = "no floor plan yet"
    g = source.gather(r, about(), None)
    texts = [t for _, _, p in sheets.sheets(g, goldens.project_of("0_no_rooms_yet")) for t in p.texts()]
    assert any("WAITING: NO FLOOR PLAN YET" in t for t in texts)


# ---- never kinder than the worst row ----------------------------------------------------------------------------------

def test_a_windows_line_is_the_most_cautious_of_its_rows():
    g = got("2_two_story_small_window")
    sched, _ = tables.schedule_rows(g)
    for line in sched:
        statuses = [x["status"] for law in g["laws"] for x in law["items"]
                    if (x["item"].get("part") or {}).get("id") == line["Part id"]]
        assert line["status"] == words.worst(statuses)
    w5 = next(s for s in sched if s["Part id"] == "w5")
    assert w5["Result"] == "DOES NOT COMPLY" and w5["cell_status"]["Net clear area"] == present.FAILS
    # Window 6 complies on all four sizes but other rules need review: its line needs review, never complies
    w6 = next(s for s in sched if s["Part id"] == "w6")
    assert set(w6["cell_status"].values()) == {present.COMPLIES} and w6["Result"] == "NEEDS REVIEW"


def test_one_failing_row_makes_the_window_fail():
    r = result("2_two_story_small_window")
    for i in r["view"]["items"]:                      # Window 6's "opens to a yard" row, made to fail (item and row)
        if i.get("rule") == "general.r319_1_escape_opening_opens_to_public_way_or_yard" and (i["part"] or {}).get("id") == "w6":
            i["status"] = present.FAILS
    for row in r["egress"]["rows"]:
        if row["rule"] == "general.r319_1_escape_opening_opens_to_public_way_or_yard" and row["id"] == "w6":
            row["outcome"] = "fail"
    for s in r["sections"]:
        if s["key"] != "zoning":
            s["state"], s["summary"] = present.FAILS, present._law_summary(law_items(r))
    g = source.gather(r, about(), _house("2_two_story_small_window"))
    w6 = next(s for s in tables.schedule_rows(g)[0] if s["Part id"] == "w6")
    assert w6["Result"] == "DOES NOT COMPLY"


def test_no_rows_is_needs_review_never_complies():
    assert words.worst([]) == present.REVIEW


def test_windows_marked_but_not_checked_need_review():
    sched, _ = tables.schedule_rows(got(ORANGETOWN))
    by = {s["Part id"]: s for s in sched}
    for pid in ("x1", "x2", "bsw1", "bsw2"):
        assert by[pid]["Result"] == "NEEDS REVIEW"
        assert "isn't checked" in by[pid]["Why"]


def test_a_bedroom_with_no_escape_window_prints_its_rows_result():
    g = got("1_ranch_compliant", "no_window_bed1")
    sched, _ = tables.schedule_rows(g)
    bed1 = next(s for s in sched if s["Room id"] == "bed1")
    assert bed1["Opening"] == "none marked" and bed1["Result"] == "DOES NOT COMPLY"


def test_the_checks_own_items_are_printed():
    rows = tables.code_rows(got(ORANGETOWN))
    ids = {x["Item id"] for x in rows}
    assert "egress.interior#1" in ids and {f"egress.skipped#{n}" for n in range(1, 5)} <= ids
    assert all(x["Result"] == "NEEDS REVIEW" for x in rows if x["Item id"].startswith("egress.skipped#"))


# ---- refused, nothing printed -----------------------------------------------------------------------------------------

def test_an_item_that_disagrees_with_its_row_is_refused():
    r = result("2_two_story_small_window")
    item = next(i for i in law_items(r) if i["status"] == present.REVIEW and i["part"])
    item["status"] = present.COMPLIES
    with pytest.raises(Refused, match="contradicts itself"):
        source.gather(r, about(), _house("2_two_story_small_window"))


def test_a_row_missing_from_the_panel_is_refused():
    r = result("2_two_story_small_window")
    r["view"]["items"] = [i for i in r["view"]["items"] if not (i.get("part") and i["status"] == present.FAILS)]
    with pytest.raises(Refused):
        source.gather(r, about(), _house("2_two_story_small_window"))


def test_counts_that_dont_match_the_section_are_refused():
    r = result("2_two_story_small_window")
    for s in r["sections"]:
        if s["key"] != "zoning":
            s["summary"] = "10 comply"
    with pytest.raises(Refused, match="isn't whole"):
        source.gather(r, about(), _house("2_two_story_small_window"))


def test_a_different_interior_is_refused():
    house = _house("2_two_story_small_window")
    house["rooms"][0]["name"] = "Bedroom 3 (edited)"
    with pytest.raises(Refused, match="isn't the one the check worked from"):
        source.gather(result("2_two_story_small_window"), about(), house)


def test_rules_changed_since_the_check_are_refused(monkeypatch):
    r, house = result("2_two_story_small_window"), _house("2_two_story_small_window")
    stale = {k: "0" * 64 for k in source.fingerprints_now()}
    with pytest.raises(Refused, match="rules changed"):
        source.gather(r, {"rulebook": stale}, house)
    with pytest.raises(Refused, match="doesn't say which rules"):
        source.gather(r, {}, house)
    # ... and while the check ran: the fingerprint read after the check differs from the one before
    seen = iter([{"new_york/ithaca_city": "a"}, {"new_york/ithaca_city": "b"}])
    monkeypatch.setattr(source, "fingerprints_now", lambda: next(seen))
    monkeypatch.setattr(source, "gather", lambda *a, **k: {})
    with pytest.raises(Refused, match="changed while the check ran"):
        source.checked(lambda: r, house)


def test_a_rule_whose_words_changed_is_refused():
    r = result("2_two_story_small_window")
    item = next(i for i in law_items(r) if (i.get("code") or {}).get("quote"))
    item["code"]["quote"] += " (edited)"
    with pytest.raises(Refused, match="aren't the ones the check quoted"):
        source.gather(r, about(), _house("2_two_story_small_window"))


# ---- traced, and said plainly -----------------------------------------------------------------------------------------

def test_every_row_traces_to_the_checks_row():
    r = result("2_two_story_small_window")
    rows = tables.code_rows(got("2_two_story_small_window"))
    raw = {(x["rule"], x["id"]): x for x in r["egress"]["rows"]}
    for x in rows:
        if x["Part kind"] and x["Part id"]:
            assert json.loads(x["Measures (as checked)"]) == raw[(x["Rule id"], x["Part id"])]["values"]
    w5 = next(x for x in rows if x["Rule id"] == "general.r319_2_1_escape_opening_min_net_clear_area"
              and x["Part id"] == "w5")
    assert (w5["Required"], w5["Proposed"], w5["Result"], w5["Code section"]) == \
        ("5.7 sq ft min", "5.12 sq ft", "DOES NOT COMPLY", "R319.2.1")


def test_title_block_on_every_sheet():
    g = got("2_two_story_small_window")
    pages = sheets.sheets(g, goldens.project_of("2_two_story_small_window"))
    law = g["laws"][0]
    for number, _, page in pages:
        text = " ".join(page.texts())
        assert "Prepared with Gordium: draft rules, verify before submission" in text, number
        assert goldens.DATE in text and "status: draft" in text
        assert law["rulebook_sha256"][:20] in text.replace(" ", "")
        assert g["interior_sha256"][:20] in text.replace(" ", "")
        assert number in text


def test_never_rounded_toward_compliance():
    sill = {"id": "x", "for_each": "emergency_escape_opening", "check": "opening_sill_height <= 44"}
    assert words.required_and_proposed(sill, {"opening_sill_height": 44.06}) == ("3'-8\" max", "3'-8 1/8\"")
    area = {"id": "x", "for_each": "emergency_escape_opening",
            "check": "opening_net_clear_area >= (5.0 if opening_at_grade else 5.7)"}
    assert words.required_and_proposed(area, {"opening_net_clear_area": 5.699, "opening_at_grade": False}) == \
        ("5.7 sq ft min", "5.69 sq ft")
    assert words.length(19.99, "down") == "1'-7 7/8\"" and words.length(7.5) == "7 1/2\""


def test_not_read_is_said_on_the_plan_never_drawn_as_none():
    texts = " ".join(t for _, _, p in sheets.sheets(got(ORANGETOWN), goldens.project_of(ORANGETOWN))
                     if _.startswith("Life") for t in p.texts())
    assert "Stairs: not read from the drawing: NEEDS REVIEW" in texts
    assert "Unfinished basement: not drawn" in texts and "BSW1" in texts
    texts3 = " ".join(t for n, _, p in sheets.sheets(got("3_tall_riser"), goldens.project_of("3_tall_riser"))
                      if n.startswith("LS") for t in p.texts())
    assert "Exit door: not read from the drawing: NEEDS REVIEW" in texts3
    assert "WAY OUT (SCHEMATIC, NOT CHECKED BY GORDIUM)" in texts3


def test_bad_project_files_are_refused():
    assert build.project_problems({"title": "x", "date": "2026-11-15"}) == []
    assert build.project_problems({"title": "x", "date": "15/11/2026"})
    assert build.project_problems({"date": "2026-11-15", "colour": "red"})


# ---- the goldens --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", goldens.names())
def test_golden_sheets_match_a_fresh_build(name):
    assert goldens.differences(name) == []


def test_svg_and_pdf_carry_the_same_words():
    g = got("2_two_story_small_window")
    pages = sheets.sheets(g, goldens.project_of("2_two_story_small_window"))
    out = build.files(g, goldens.project_of("2_two_story_small_window"))
    with pdfplumber.open(io.BytesIO(out["permit_sheets.pdf"])) as pdf:
        assert len(pdf.pages) == len(pages)
        for (number, _, page), p in zip(pages, pdf.pages):
            words_pdf = set((p.extract_text() or "").split())
            svg = out[f"{number}.svg"].decode("utf-8")
            for t in page.texts():
                assert all(w in words_pdf for w in t.split()), (number, t)
                assert draw._esc_xml(t) in svg



def test_the_command_checks_a_model_and_writes_every_file(tmp_path):
    from permit_sheets.__main__ import main
    site = goldens.REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
    (tmp_path / "project.yaml").write_text('title: 106 Ithaca Rd\ndate: "2026-11-15"\n', encoding="utf-8")
    house = goldens.REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml"
    assert main([str(house), "--model", str(site / "model.3dm"), "--facts", str(site / "model_facts.yaml"),
                 "--project", str(tmp_path / "project.yaml"), "--out", str(tmp_path / "out")]) == 0
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"G-001.svg", "LS-101.svg", "A-601.svg", "permit_sheets.pdf", "code_analysis.csv",
            "escape_window_schedule.csv", "permit_sheets.xlsx"} <= names
    (tmp_path / "bad.yaml").write_text("title: x\ndate: tomorrow\n", encoding="utf-8")
    assert main([str(house), "--model", str(site / "model.3dm"), "--facts", str(site / "model_facts.yaml"),
                 "--project", str(tmp_path / "bad.yaml"), "--out", str(tmp_path / "out2")]) == 1
    assert not (tmp_path / "out2").exists()


# ---- review round 1 -------------------------------------------------------------------------------------------------

def test_no_rooms_and_rules_refused_prints_needs_review_not_a_crash(monkeypatch):
    """No interior, and the state's rulebook refused by the rule checks: the check gives the law's needs-review item,
    no waiting item. Every sheet says NEEDS REVIEW (never complies) and nothing crashes."""
    from design_checker import egress
    real = egress.laws

    def refused(jurisdiction):
        found = real(jurisdiction)
        for law in found["laws"]:
            law["problems"], law["rules"] = ["simulated: a rule fails its checks"], []
        return found
    monkeypatch.setattr(egress, "laws", refused)
    r = check_site(goldens.site(), dict(goldens.FACTS), name="x", today=goldens.DATE, interior=None)
    g = source.gather(r, about(), None)
    out = build.files(g, goldens.project_of("0_no_rooms_yet"))
    with pdfplumber.open(io.BytesIO(out["permit_sheets.pdf"])) as pdf:
        for p in pdf.pages:
            text = p.extract_text() or ""
            assert "NEEDS REVIEW" in text
            assert "COMPLIES" not in text.replace("DOES NOT COMPLY", "").replace("Results: COMPLIES", "")
    sched = list(csv.DictReader(io.StringIO(out["escape_window_schedule.csv"].decode("utf-8"))))
    assert [s["Result"] for s in sched] == ["NEEDS REVIEW"]


def test_the_schedule_files_are_never_an_empty_table():
    out, wb, _ = goldens.build("0_no_rooms_yet")           # built fresh, not read from the committed golden
    sched = list(csv.DictReader(io.StringIO(out["escape_window_schedule.csv"].decode("utf-8"))))
    assert [s["Result"] for s in sched] == ["WAITING: NO ROOMS DRAWN YET"]
    ws = wb["Escape-window schedule"]
    assert any(c.value == "WAITING: NO ROOMS DRAWN YET" for row in ws.iter_rows() for c in row)
    # a house with no sleeping room and no escape opening: one NEEDS REVIEW line saying so
    house = goldens.interior_of("1_ranch_compliant")
    for room in house["rooms"]:
        room["sleeping"] = False
    for o in house["openings"]:
        o["escape"] = False
    r = check_site(goldens.site(), dict(goldens.FACTS), name="x", today=goldens.DATE, interior=house)
    rows, _ = tables.schedule_rows(source.gather(r, about(), house))
    assert [(x["Result"], x["Why"]) for x in rows] == [
        ("NEEDS REVIEW", "no sleeping room and no escape opening in the drawing")]


def test_every_csv_row_carries_the_project_date_and_draft_warning():
    for name in ("0_no_rooms_yet", "2_two_story_small_window"):
        out, _, _ = goldens.build(name)                       # built fresh
        for file in ("code_analysis.csv", "escape_window_schedule.csv"):
            for row in csv.DictReader(io.StringIO(out[file].decode("utf-8"))):
                assert row["Status"] == sheets.DISCLAIMER
                assert row["Date"] == goldens.DATE and row["Project"] == goldens.project_of(name)["title"]


def test_an_earlier_sets_pages_are_removed(tmp_path):
    from permit_sheets.__main__ import main
    site = goldens.REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
    (tmp_path / "project.yaml").write_text('title: 106 Ithaca Rd\ndate: "2026-11-15"\n', encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "G-009.svg").write_text("<svg/>", encoding="utf-8")        # a page from an earlier, longer set
    (out / "notes.txt").write_text("the architect's own file", encoding="utf-8")
    house = goldens.REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml"
    assert main([str(house), "--model", str(site / "model.3dm"), "--facts", str(site / "model_facts.yaml"),
                 "--project", str(tmp_path / "project.yaml"), "--out", str(out)]) == 0
    assert not (out / "G-009.svg").exists() and (out / "notes.txt").exists()


# ---- review round 2 -------------------------------------------------------------------------------------------------

def _no_rooms_key():
    house = goldens.interior_of("1_ranch_compliant")
    del house["rooms"]                                   # left out: the rooms weren't read (never "no rooms")
    g = source.checked(lambda: check_site(goldens.site(), dict(goldens.FACTS), name="x", today=goldens.DATE,
                                          interior=house), house)
    return g, sheets.sheets(g, goldens.project_of("1_ranch_compliant"))


def test_rooms_not_read_is_said_on_the_plan_and_its_windows_kept():
    g, pages = _no_rooms_key()
    plan = " ".join(t for n, _, p in pages if n.startswith("LS") for t in p.texts())
    assert "Rooms not read from the drawing: NEEDS REVIEW" in plan and "No rooms drawn" not in plan
    marks = [s["Mark"] for s in tables.schedule_rows(g)[0] if not s.get("statement")]
    assert marks and all(f"{m} " in plan for m in marks)


def test_schedule_banners_say_their_result_once():
    _, pages = _no_rooms_key()
    banners = [t for n, _, p in pages if n.startswith("A-") for t in p.texts() if t.startswith("NEEDS REVIEW:")]
    assert banners and all(t.count("NEEDS REVIEW") == 1 for t in banners)
    out, _, _ = goldens.build("0_no_rooms_yet")
    texts = [t for t in out["A-601.svg"].decode("utf-8").split(">") if "WAITING" in t]
    assert any("WAITING: NO ROOMS DRAWN YET: no escape openings to schedule yet<" in t + "<" for t in texts)


# ---- review round 3 -------------------------------------------------------------------------------------------------

def _ranch_sheets(change):
    house = goldens.interior_of("1_ranch_compliant")
    change(house)
    g = source.checked(lambda: check_site(goldens.site(), dict(goldens.FACTS), name="x", today=goldens.DATE,
                                          interior=house), house)
    pages = sheets.sheets(g, goldens.project_of("1_ranch_compliant"))
    return {n[:2]: " | ".join(t for m, _, p in pages if m.startswith(n[:2]) for t in p.texts()) for n in ("LS", "A-")}


def test_malformed_rooms_are_not_read_never_no_rooms():
    texts = _ranch_sheets(lambda h: h.update(rooms="oops"))
    assert "Rooms not read from the drawing: NEEDS REVIEW" in texts["LS"] and "No rooms drawn" not in texts["LS"]


@pytest.mark.parametrize("change", [lambda h: h.pop("openings"), lambda h: h.update(openings="oops")])
def test_openings_not_read_never_say_none_marked(change):
    texts = _ranch_sheets(change)
    assert "Escape openings: not read from the drawing: NEEDS REVIEW" in texts["LS"]
    for t in texts.values():
        assert "none marked" not in t and "No escape opening marked" not in t
    assert "Escape openings not read: NEEDS REVIEW" in texts["LS"]


# ---- review round 4 -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["oops", [1]])
def test_malformed_doors_are_not_read_never_none_marked(bad):
    texts = _ranch_sheets(lambda h: h.update(doors=bad))
    assert "Exit door: not read from the drawing: NEEDS REVIEW" in texts["LS"]
    assert "none marked" not in texts["LS"]


@pytest.mark.parametrize("bad", ["oops", [1]])
def test_malformed_stairs_are_not_read_never_silent(bad):
    texts = _ranch_sheets(lambda h: h.update(stairs=bad))
    assert "Stairs: not read from the drawing: NEEDS REVIEW" in texts["LS"]
    assert "No stairs in the drawing" not in texts["LS"]


# ---- the sections Gordium doesn't check yet (design_checker/egress.py): never a set that reads as complete --------

def _not_yet(r):
    return [i for i in law_items(r) if i["id"].endswith(".not_checked_yet")]


def _fresh_text(name):
    """Every page's words of a fresh build of the house's sheets (never the committed golden)."""
    out, _, _ = goldens.build(name)
    with pdfplumber.open(io.BytesIO(out["permit_sheets.pdf"])) as pdf:
        return " ".join(" ".join((p.extract_text() or "") for p in pdf.pages).split())


@pytest.mark.parametrize("name", ["1_ranch_compliant", ORANGETOWN])
def test_the_sections_not_checked_yet_are_printed_as_needs_review(name):
    r = result(name)
    [item] = _not_yet(r)
    sections = item["detail"]["citation"].split(", ")
    assert {"R321.2.1", "R318.6", "R319.5"} <= set(sections) and len(sections) > 50
    [row] = [x for x in tables.code_rows(got(name)) if x["Item id"] == item["id"]]
    assert row["Result"] == "NEEDS REVIEW" and row["Why / what to change"] == item["reason"]    # in full, in the CSV
    flat = _fresh_text(name)
    # G-001's result lines say so, and the table's banner lists every section, under the NEEDS REVIEW line
    assert f"Not checked yet by Gordium: {len(sections)} code sections, check them by hand (code_analysis.csv line " \
           f"{row['Line']})" in flat
    assert f"NEEDS REVIEW: not checked yet by Gordium, check these {len(sections)} code sections by hand:" in flat
    # the banner lists exactly the check's sections, in its order (never a substring match)
    [banner] = [b for b in sheets.code_table(got(name)) if b[0] == "__banner__"]
    assert banner == ["__banner__", sheets.NOT_YET_BANNER.format(result="NEEDS REVIEW", n=len(sections),
                                                               sections=", ".join(sections)), present.REVIEW]


def test_while_egress_waits_the_sheets_stay_waiting_and_still_list_the_sections():
    r = result("0_no_rooms_yet")
    assert _not_yet(r) == []                                       # waiting stays waiting: no needs-review line
    [waiting] = law_items(r)
    sections = waiting["detail"]["citation"].split(", ")
    assert {"R321.2.1", "R318.6"} <= set(sections)
    status, waits = source.overall(got("0_no_rooms_yet"))
    assert status == present.NOT_CHECKED and waits                 # the headline is still WAITING
    flat = _fresh_text("0_no_rooms_yet")
    assert "Egress result: WAITING: NO ROOMS DRAWN YET" in flat
    assert f"Not checked yet by Gordium: {len(sections)} code sections, check them by hand" in flat
    assert f"WAITING: NO ROOMS DRAWN YET: not checked yet by Gordium, check these {len(sections)} code sections" in flat
    assert "NEEDS REVIEW: not checked yet" not in flat


@pytest.mark.parametrize("name", ["1_ranch_compliant", "0_no_rooms_yet"])
def test_a_list_of_sections_that_cant_be_read_says_check_the_whole_law(name, monkeypatch):
    """Review round 1 (permit sheets): a check that can't tell which sections it skips had no line under the result
    and no banner, the sheet saying less than the check."""
    from design_checker import egress
    real = egress._not_checked_yet
    monkeypatch.setattr(egress, "_not_checked_yet", lambda folder, rules: ([], "no 6_coverage_report/*.rules.yaml"))
    house = _house(name)
    r = check_site(goldens.site(), goldens.facts_of(name), name=name, today=goldens.DATE, interior=house)
    g = source.gather(r, about(), house)
    banners = [b for b in sheets.code_table(g) if b[0] == "__banner__"]
    assert len(banners) == 1 and "check the whole law by hand" in banners[0][1]
    lines = [r_ for r_ in tables.code_rows(g) if sheets.not_checked_yet(r_) is None]
    assert len(lines) == 1
    # and said under the egress result, on the sheets themselves (review round 2)
    pages = sheets.sheets(g, goldens.project_of(name))
    said = sheets.UNKNOWN_LINE.format(line=lines[0]["Line"])
    words_ = _page_words(pages)
    assert said in words_[0]                                             # G-001, under the result
    assert all(said in w for (number, _, _), w in zip(pages, words_) if number in ("LS-101", "A-601"))
    monkeypatch.setattr(egress, "_not_checked_yet", real)
    status, _ = source.overall(g)
    assert status == (present.NOT_CHECKED if name == "0_no_rooms_yet" else present.REVIEW)


def _page_words(pages):
    """The words drawn on each page (its text marks), in drawing order."""
    from permit_sheets.draw import svg
    import re as _re
    import html as _html
    return [" ".join(_html.unescape(_re.sub(r"<[^>]+>", " ", svg(pg, number))).split()) for number, _, pg in pages]


def test_a_not_checked_yet_row_renamed_across_laws_still_gets_its_banner():
    """Review round 2 (permit sheets): an id made unique across laws ("egress.not_checked_yet#<law>") lost its banner."""
    row = {"Item id": "egress.not_checked_yet#new_york/other", "Citation": "R321.2.1, R318.6", "Why / what to change": ""}
    assert sheets.not_checked_yet(row) == ["R321.2.1", "R318.6"]
    assert sheets.not_checked_yet(dict(row, **{"Item id": "egress.waiting#new_york/other"})) == ["R321.2.1", "R318.6"]
    assert sheets.not_checked_yet(dict(row, Citation="")) is None


# ---- G-001 grouped as the panel groups the check (docs/decisions/2026-11-16_results_grouping.md) ----------------------

def _csv_lines_of(row) -> list[int]:
    """The CSV lines a G-001 row cites ("code_analysis.csv lines 7–10, 12")."""
    small = row[2][2] if isinstance(row[2], tuple) and len(row[2]) > 2 else ""
    text = (small or "").split("code_analysis.csv line")[-1].lstrip("s ")
    out = []
    for part in [p for p in text.split(", ") if p]:
        a, _, b = part.partition("–")
        out += list(range(int(a), int(b or a) + 1))
    return out


@pytest.mark.parametrize("name", goldens.names())
def test_every_rule_row_is_on_g001_exactly_once_and_never_kinder(name):
    g = got(name)
    every = {r["Line"]: r for r in tables.code_rows(g)}
    cited = []
    for row in sheets.code_table(g):
        if row[0] in ("__group__", "__banner__"):
            continue
        lines = _csv_lines_of(row)
        assert lines, row
        cited += lines
        printed, status = row[5]
        assert status == words.worst(every[n]["status"] for n in lines)        # the most cautious of its rules
        assert printed.startswith(words.WAITING) if status == present.NOT_CHECKED else \
            printed == words.result_words(status)
        if any(every[n]["status"] != present.COMPLIES for n in lines):
            assert printed != "COMPLIES"
    assert sorted(cited) == sorted(every)                                      # every rule's row, exactly once


@pytest.mark.parametrize("name", ["2_two_story_small_window", "5_basement_window_well", "4_loft"])
def test_every_failing_rule_has_its_own_g001_row_with_required_and_proposed(name):
    g = got(name)
    fails = [r for r in tables.code_rows(g) if r["status"] == present.FAILS]
    assert fails
    table = [row for row in sheets.code_table(g) if row[0] not in ("__group__", "__banner__")]
    for r in fails:
        [row] = [x for x in table if _csv_lines_of(x) == [r["Line"]]]
        assert row[5] == ("DOES NOT COMPLY", present.FAILS) and row[3] == r["Required"] and row[4] == r["Proposed"]
    # and they come first: no row before them needs review or complies
    first = [x[5][1] for x in table][:len(fails)]
    assert first == [present.FAILS] * len(fails)


@pytest.mark.parametrize("name", goldens.names())
def test_every_csv_row_says_where_g001_shows_it(name):
    rows = csv_rows(name, "code_analysis.csv")
    assert rows and all(r["Shown on G-001 as"] for r in rows)
    for r in rows:
        tier = r["Shown on G-001 as"].split(" › ")[0]
        # a not-applicable row is never under a heading that says only "Complies" (grouping.tier_title)
        expected = {"COMPLIES": ("Complies", "Complies or not applicable"), "DOES NOT COMPLY": ("Does not comply",),
                    "NOT APPLICABLE": ("Not applicable", "Complies or not applicable")}.get(r["Result"])
        if expected:
            assert tier in expected
        elif r["Result"] == "NEEDS REVIEW":
            assert tier in ("Needs review", "Check by hand: not read by Gordium yet")


@pytest.mark.parametrize("name", goldens.names())
def test_a_not_applicable_row_is_never_printed_under_a_complies_heading(name):
    """G-001's heading over the complies tier names what is under it: "Complies or not applicable" when a rule the
    description set aside is there, never "Complies" alone over a NOT APPLICABLE row."""
    heading, seen = None, False
    for row in sheets.code_table(got(name)):
        if row[0] == "__group__":
            heading = row[1]
        elif row[0] != "__banner__" and row[5][1] == present.NOT_APPLICABLE:
            seen = True
            assert heading in ("Not applicable", "Complies or not applicable"), (heading, row)
    if any(i["status"] == present.NOT_APPLICABLE for i in law_items(result(name))):
        assert seen


def test_orangetowns_g001_is_a_few_pages_not_a_rule_per_row():
    pages = [n for n, _, _ in sheets.sheets(got(ORANGETOWN), goldens.project_of(ORANGETOWN)) if n.startswith("G-")]
    assert len(pages) <= 4 < len(tables.code_rows(got(ORANGETOWN))) // 20     # was 17 pages, a rule per row
