"""Prototype data for the UI polish proposal (feat/ui-polish-proposal): reads two real checker answers and writes
screens.json, which the WPF prototype (Program.cs) draws. Not shipping code: nothing here is loaded by Revit.

Every count is a count of the checker's own rows (view.items): a row is counted under each action it waits on, and the
totals are by the row's status as the checker gave it. Nothing here makes or changes a verdict.

The proposed wording (headlines, "why" lines, action names) is the proposal's; where the checker would have to send
something new for the add-in to say it (a cause's fact, a section's chapter, a chapter's title), the comment says so and
changes.md lists it under "checker changes".

    python make_screens.py            # writes screens.json beside this file
"""

import json
import re
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).parent
ADDIN = HERE.parent.parent
APARTMENT = HERE / "data" / "apartment_answer_words2.json"   # Ben's 11:42 request, checked on fix/plain-checker-words
HOUSE = ADDIN / "tests" / "Gordium.Revit.Reading.Tests" / "answers" / "ithaca_106_house_check_answer.json"


def view(path):
    return json.loads(path.read_text(encoding="utf-8"))["result"]["view"]


STATUS = {"does_not_comply": "fail", "needs_review": "review", "complies": "pass", "not_applicable": "na",
          "not_checked": "notyet"}


def totals(items):
    t = {"fail": 0, "review": 0, "pass": 0, "na": 0, "notyet": 0}
    for i in items:
        t[STATUS.get(i["status"], "review")] += 1      # an unknown word is read as needs review, never as a pass
    return t


# ---- "What to fix": needs-review rows grouped by what the architect can do --------------------------------------
# Each action names the rows waiting on it (a row may wait on several, so the actions' counts overlap; the header's
# totals never do). Matching is on the checker's cause keys and fields; where the checker gives only a sentence today
# (a decide cause whose words hold three asks), the clause is matched, and changes.md asks the checker for one cause
# per clause with its fact.

def has_cause(i, pred):
    return any(pred(c) for c in (i.get("causes") or []))


def reason(i):
    return " ".join([i.get("reason") or ""] + [c.get("words", "") for c in (i.get("causes") or [])])


APARTMENT_FACTS = [
    # (label, what Revit field it sets, the short ask, the "why" on demand, match)
    ("Occupancy group", "Gordium: Occupancy groups", "Which occupancy groups is the building? (e.g. R-2)",
     "The Building Code's egress limits change with the group. Today the checker asks “is it I-4?” "
     "(occupancy_group_i4), which the Occupancy groups field answers.",
     lambda i: has_cause(i, lambda c: c["key"] in ("fact:occupancy_group_i4", "fact:other_occupancy_present"))),
    ("Sprinkler system", "Gordium: Sprinkler system", "Is the building sprinklered throughout? Which system?",
     "Travel distance, common path and exit separation are longer with sprinklers (BCNYS 903.3.1.1, 903.3.1.2).",
     lambda i: has_cause(i, lambda c: c["key"].startswith("fact:sprinklered_"))),
    ("Corner lot", "Gordium: Corner lot", "Is the lot on two streets?",
     "A corner lot has two front yards and different side and rear yards (§325-19C).",
     lambda i: "corner lot" in reason(i)),
    ("Accessory dwelling unit", "Gordium: Accessory dwelling unit", "Is there an ADU on the lot?",
     "Six ADU rules apply only if there is one (§325-28).",
     lambda i: has_cause(i, lambda c: c["key"] == "facts:accessory_dwelling_unit")),
    ("Dwelling units", "Gordium: Dwelling units", "How many dwelling units? Any rooms let? A conversion?",
     "The lot area the district asks for grows with the units (§325-8, chart).",
     lambda i: has_cause(i, lambda c: "dwelling_units" in c["key"])),
    ("Main buildings on the lot", "no field yet", "How many main buildings are on the lot?",
     "Each main building needs its own lot area, and yards can't be shared (§325-7B, §325-8B).",
     lambda i: has_cause(i, lambda c: c["key"].startswith("facts:primary_buildings"))),
    ("Stream nearby", "no field yet", "Is a stream or inlet within 20 ft of the lot?",
     "New structures stay 20 ft from a stream bank or inlet wall (§325-26).",
     lambda i: has_cause(i, lambda c: "stream" in c["key"])),
    ("Next to R-1 land", "no field yet", "Does the lot touch or face R-1a or R-1b land?",
     "Stricter limits apply next to R-1 districts (§325-19E).",
     lambda i: has_cause(i, lambda c: "abuts_r1" in c["key"])),
    ("Home occupation", "Gordium: Home occupation", "Is a home business planned?",
     "A home occupation has its own size limit (§325-3B).",
     lambda i: has_cause(i, lambda c: c["key"].startswith("facts:home_occupation"))),
]


def actions_apartment(items):
    review = [i for i in items if i["status"] == "needs_review"]
    out = []

    facts = []
    rows = set()
    for label, field, ask, why, match in APARTMENT_FACTS:
        ids = {i["id"] for i in review if match(i)}
        if ids:
            facts.append({"label": label, "field": field, "ask": ask, "why": why, "count": len(ids)})
            rows |= ids
    facts.sort(key=lambda f: -f["count"])
    out.append({"kind": "facts", "title": "Answer {n} questions about the project".format(n=len(facts)),
                "sub": "Set on Project Information. Nothing is saved until you click Save.",
                "count": len(rows), "entries": facts, "button": "Answer here"})

    closed = {i["id"] for i in review if "isn't a closed solid" in reason(i)}
    if closed:
        m = re.search(r"isn't a closed solid: ([^;\"]+\"?)", " ".join(reason(i) for i in review if i["id"] in closed))
        name = m.group(1).strip() if m else "an element"
        # the checker names the wall type only ("a building isn't a closed solid: LS New 6\"", a wall type in
        # this model's request); changes.md asks it to name the walls themselves, so Show selects them
        out.append({"kind": "drawing", "title": f"Fix the “{name}” walls",
                    "sub": f"A wall of type “{name}” isn't a closed solid, so the footprint, height and yards "
                           "can't be measured.",
                    "why": "Walls are measured as closed solids. Look for a wall with an open end, an in-place "
                           "edit or a sweep that leaves a gap.",
                    "count": len(closed), "entries": [], "button": "Show in model"})

    survey = {i["id"] for i in review if "isn't from a survey" in reason(i)}
    if survey:
        out.append({"kind": "survey", "title": "Get a survey for the lot area",
                    "sub": "The property line is traced from the tax map (±2 ft). Lot area and coverage need a "
                           "surveyed line.",
                    "why": "Set “Property line from: Survey” once it is drawn from a survey.",
                    "count": len(survey), "entries": [], "button": None})

    hand = {}
    for i in review:
        for c in i.get("causes") or []:
            if c["kind"] == "measure_by_hand" or c["key"] == "mark:space:space_occupant_load":
                k = {"gap:space:space_egress_through_locked_room": "Egress through a room that can be locked",
                     "gap:space:space_egress_through_other_room": "Egress through kitchens, storage or other rooms",
                     "gap:space:space_egress_through_electrically_locked_lobby": "Egress through a locked lobby",
                     "mark:space:space_occupant_load": "Occupant load of each space"}.get(c["key"], c["words"])
                hand.setdefault(k, set()).add(i["id"])
    if hand:
        ids = set().union(*hand.values())
        out.append({"kind": "byhand", "title": "Measure by hand (Gordium doesn't yet)",
                    "sub": "Gordium can't read these from the drawing yet. Check each against the code's words.",
                    "count": len(ids),
                    "entries": [{"label": k, "count": len(v)} for k, v in sorted(hand.items(), key=lambda x: -len(x[1]))],
                    "button": None})

    judge = {i["id"] for i in review if (i.get("reason") or "").startswith(("A person checks this", "A judgment call"))}
    if judge:
        out.append({"kind": "judgment", "title": f"{len(judge)} code questions for you to decide",
                    "sub": "The code leaves these to judgment. Gordium shows the words; you decide.",
                    "count": len(judge), "entries": [], "button": None})

    question = {i["id"] for i in review if has_cause(i, lambda c: c["key"].startswith("question:"))}
    if question:
        out.append({"kind": "question", "title": "1 open question about how to measure",
                    "sub": "Is a storage room's area measured inside its walls or to their outer faces? "
                           "Either way, this result can't pass yet.",
                    "count": len(question), "entries": [], "button": None})

    notyet = [i for i in items if i["status"] == "not_checked"]
    out.append({"kind": "notyet", "title": "Not checked yet by Gordium",
                "sub": "Overlays and 7 zoning sections. Check these by hand.",
                "count": len(notyet), "entries": [], "button": None})
    return out


# ---- "By code": the documents' own order ---------------------------------------------------------------------------
# Zoning rows carry only a citation string today ("§325-8, District Regulations Chart, ..."); egress rows carry
# code.section ("1006.2.1"). The section's chapter (or article) and their titles are the prototype's, from the
# documents' contents pages; changes.md asks the checker to send them with each row (code.document, code.chapter,
# code.section, code.section_title) and one contents list per law (every chapter and section, with Gordium's
# coverage), so nothing here is hand-kept in the add-in.

ZONING_ARTICLES = [  # City of Ithaca Code Ch. 325, contents (p.1-2)
    ("I", "General Provisions", (1, 3)),
    ("II", "Zoning Districts", (4, 8)),
    ("III", "Special Permits and Related Special Conditions", (9, 10)),
    ("IV", "Cluster Subdivision, Floating Zones and Planned Unit Development Zones", (11, 13)),
    ("V", "Supplementary Regulations", (14, 29)),
]
ZONING_SECTIONS = {  # titles from 6_coverage_report/chapter_325_zoning_2026-10.md
    "325-7": "Application of regulations", "325-8": "District regulations (the chart)",
    "325-16": "Height regulations", "325-17": "Area regulations", "325-18": "Yard regulations",
    "325-19": "Transition regulations", "325-20": "Off-street parking", "325-21": "Off-street loading",
    "325-25": "Location of accessory structures", "325-26": "New structures along streams or inlets",
    "325-28": "Accessory Dwelling Units (ADUs)", "325-3": "Definitions and word usage",
}
BC_CHAPTERS = {  # 2025 Building Code of New York State, contents; checked chapters first
    3: "Occupancy Classification and Use", 5: "General Building Heights and Areas", 10: "Means of Egress",
}
BC_OTHER_CHAPTERS = 33 - 3       # chapters 1-35 less reserved ones; the real count comes from the book's contents
BC_SECTIONS = {
    "308": "Institutional Group I", "508": "Mixed Use and Occupancy",
    "1006": "Number of Exits and Exit Access Doorways", "1007": "Exit and Exit Access Doorway Configuration",
    "1016": "Exit Access", "1017": "Exit Access Travel Distance", "1020": "Corridors",
}
BC_CH10_ALL = 31                  # sections 1001-1031


def zoning_section(i):
    cit = (i.get("detail") or {}).get("citation") or ""
    m = re.findall(r"§(325-\d+)", cit)
    if not m:
        return None
    # a chart rule cites the chart first (its home is §325-8); a rule of its own cites its section first: its home
    # is the first section cited that isn't the definitions
    if cit.startswith("§325-8, District Regulations Chart"):
        return "325-8"
    own = [s for s in m if s != "325-3"]
    return own[0] if own else m[0]


def bc_section(i):
    code = i.get("code") if isinstance(i.get("code"), dict) else None
    s = (code or {}).get("section") or ""
    m = re.search(r"(\d{3,4})", s)
    return m.group(1) if m else None


def rule_key(i):
    return i.get("rule") or i["id"]


def worst(states):
    """A group's state: fails if any fails, review if any needs review or isn't checked; complies only if every
    one complies (never green over a needs review)."""
    s = set(states)
    if "fail" in s:
        return "fail"
    if s == {"notyet"}:
        return "notyet"
    if s & {"review", "notyet"}:
        return "review"
    if s and s <= {"pass", "na"}:
        return "pass" if "pass" in s else "na"
    return "notyet"


def line(t):
    parts = []
    for k, w in (("fail", "fail"), ("review", "need review"), ("pass", "comply"), ("notyet", "not checked yet")):
        if t.get(k):
            word = w
            if t[k] == 1:
                word = {"fail": "fails", "need review": "needs review", "comply": "complies"}.get(w, w)
            parts.append(f"{t[k]} {word}")
    return " · ".join(parts)


def rule_rows(rows):
    """One line per rule (its parts folded: 8 spaces under "Two exits")."""
    by = OrderedDict()
    for i in rows:
        by.setdefault(rule_key(i), []).append(i)
    out = []
    for k, parts in by.items():
        first = parts[0]
        name = first["name"].split(" · ", 1)[-1] if " · " in first["name"] else first["name"]
        name = re.sub(r"^Egress · ", "", name)
        name = re.sub(r" \((BCNYS )?[\d.]+\)$", "", name)
        name = re.sub(r" \(BCNYS\)$", "", name)
        name = re.sub(r"^Table [\d.()]+'s rows for other occupancies$", "Rows for other occupancies", name)
        st = [STATUS.get(p["status"], "review") for p in parts]
        t = {k2: st.count(k2) for k2 in ("fail", "review", "pass", "notyet", "na")}
        sec = bc_section(first) or ""
        code = first.get("code") if isinstance(first.get("code"), dict) else {}
        out.append({"name": name, "state": worst(st), "parts": len(parts), "line": line(t),
                    "section": (code or {}).get("section") or "",
                    "measured": first.get("proposed") or "", "limit": ((first.get("sign") or "") + " " + (first.get("required") or "")).strip()})
    return out


def bycode_apartment(items):
    docs = []
    # zoning
    z = [i for i in items if i["id"].startswith("R-3a.") or i["id"].startswith("gap.")]
    arts = []
    for num, title, (lo, hi) in ZONING_ARTICLES:
        secs = OrderedDict()
        for i in z:
            s = zoning_section(i)
            if s and lo <= int(s.split("-")[1]) <= hi:
                secs.setdefault(s, []).append(i)
        sections = []
        for s, rows in sorted(secs.items(), key=lambda x: int(x[0].split("-")[1])):
            st = [STATUS.get(r["status"], "review") for r in rows]
            sections.append({"num": "§" + s, "title": ZONING_SECTIONS.get(s, ""), "state": worst(st),
                             "line": line({k: st.count(k) for k in ("fail", "review", "pass", "notyet")}),
                             "rules": rule_rows(rows)})
        st = [STATUS.get(r["status"], "review") for rows in secs.values() for r in rows]
        arts.append({"num": f"Art. {num}", "title": title, "state": worst(st) if st else "notyet",
                     "line": line({k: st.count(k) for k in ("fail", "review", "pass", "notyet")}) if st
                     else "Gordium doesn't check this article", "sections": sections, "greyed": not st})
    over = [i for i in items if i["id"] == "release.overlays"]
    docs.append({"title": "City of Ithaca Zoning", "sub": "Chapter 325 · R-3a · chart April 2026",
                 "chapters": arts,
                 "other": "Articles VA–XII (permits, appeals, special zones): Gordium doesn't check these",
                 "extra": [{"title": "Overlay districts (historic, gorge, flood)",
                            "line": "Not in this release · check by hand"}] if over else []})
    # building code
    e = [i for i in items if (i.get("law_key") or "").endswith("new_york_state_building") and i["id"] != "egress.code_scope"]
    chs = []
    for n, title in BC_CHAPTERS.items():
        secs = OrderedDict()
        for i in e:
            s = bc_section(i)
            if s and int(s) // 100 == n:
                secs.setdefault(s, []).append(i)
        sections = []
        for s, rows in sorted(secs.items(), key=lambda x: int(x[0])):
            st = [STATUS.get(r["status"], "review") for r in rows]
            sections.append({"num": s, "title": BC_SECTIONS.get(s, ""), "state": worst(st),
                             "line": line({k: st.count(k) for k in ("fail", "review", "pass", "notyet")}),
                             "rules": rule_rows(rows)})
        st = [STATUS.get(r["status"], "review") for rows in secs.values() for r in rows]
        t = {k: st.count(k) for k in ("fail", "review", "pass")}
        missing = (BC_CH10_ALL - len(secs)) if n == 10 else None
        chs.append({"num": f"Ch {n}", "title": title, "state": "review" if missing else worst(st),
                    "line": line(t) + (f" · {missing} sections not checked yet" if missing else ""),
                    "sections": sections, "greyed": False,
                    "notyet": f"{missing} other sections of Chapter 10 (doors, stairs, exit signs, …): not checked "
                              "yet by Gordium" if missing else None})
    docs.append({"title": "NY State Building Code 2025", "sub": "Governs this building: multiple-family use isn't a "
                 "dwelling the Residential Code covers (R101.2)", "chapters": chs,
                 "other": f"{BC_OTHER_CHAPTERS} other chapters (construction types, fire protection, accessibility, "
                          "…): not checked yet by Gordium", "extra": []})
    return docs


def detail_apartment(items):
    i = next(x for x in items if x["id"].startswith("general.bc_1006_2_1_two_exits"))
    q = (i.get("detail") or {}).get("quotes") or []
    return {"title": "Two exits from a space over 10 occupants",
            "where": "Apartment South L1 · BCNYS 1006.2.1",
            "position": "3 of 106",
            "headline": "Gordium needs the occupancy group, the sprinkler system and this space's occupant load.",
            "why": i.get("reason") or "",
            "steps": ["Set Occupancy group and Sprinkler system (2 project questions).",
                      "Occupant load: Gordium has no field for it yet. Work it out by hand (Table 1004.5)."],
            "quote": q[0]["text"] if q else "", "quote_where": "BCNYS 1006.2.1 · PDF p.315",
            "table": q[1]["text"] if len(q) > 1 else ""}


def main():
    apt = view(APARTMENT)["items"]
    house = view(HOUSE)["items"]
    after = {i["id"]: i for i in view(HOUSE.with_name("ithaca_106_house_after_check_answer.json"))["items"]}
    words = {"fail": "Does not comply", "review": "Needs review", "pass": "Complies", "na": "Doesn't apply",
             "notyet": "Not checked yet"}
    after_na = {r["Rule id"] for r in json.loads(HOUSE.with_name("ithaca_106_house_after_check_answer.json")
                                               .read_text(encoding="utf-8"))["result"]["not_applicable"]}
    changes = []
    for i in house:
        j = after.get(i["id"])
        a, b = STATUS.get(i["status"], "review"), STATUS.get(j["status"], "review") if j else None
        if j is None and i["id"] in after_na:
            b = "na"                    # moved to the answer's not-applicable list (no ADU on the lot)
        if b is None or a != b:
            changes.append({"name": i["name"], "before": a, "after": b or "gone",
                            "words": f"{words[a]} → {words.get(b, 'no longer checked')}"})
    gained = [j for k, j in after.items() if k not in {i["id"] for i in house}]
    out = {
        "apartment": {"title": "Four-unit apartment", "at": "14:32", "totals": totals(apt),
                      "actions": actions_apartment(apt), "bycode": bycode_apartment(apt),
                      "detail": detail_apartment(apt)},
        "house": {"title": "106 Ithaca Rd", "at": "14:32", "totals": totals(house),
                  "fails": [{"name": i["name"], "measured": i.get("proposed"), "limit": f"{i.get('sign')} {i.get('required')}",
                             "over": i.get("margin"), "cite": "§325-8 · District Regulations Chart"}
                            for i in house if i["status"] == "does_not_comply"],
                  "after_totals": totals(list(after.values())), "changes": changes, "new": len(gained)},
    }
    print("house changes", len(changes), "new", len(gained), [c["words"] for c in changes][:12])
    (HERE / "screens.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in out.items():
        print(k, v["totals"])
    for a in out["apartment"]["actions"]:
        print(f"  {a['count']:3}  {a['kind']:9} {a['title']}")
    for d in out["apartment"]["bycode"]:
        print(d["title"])
        for c in d["chapters"]:
            print("  ", c["num"], c["title"], "|", c["state"], "|", c["line"])
            for s in c["sections"]:
                print("      ", s["num"], s["title"], "|", s["state"], "|", s["line"], "|", len(s["rules"]), "rules")


if __name__ == "__main__":
    main()
