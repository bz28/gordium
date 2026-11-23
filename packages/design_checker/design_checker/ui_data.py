"""What the rebuilt results pane reads beyond today's fields (the UI polish design Ben approved on 2026-11-23,
changes C1 to C9; docs/revit/checker_ui_data.md says each field). Presentation only, plain code, no AI.

Nothing here reads or changes a status, a verdict or a figure: every field is new, set beside the old ones (so the
add-in on main reads exactly what it read before), and each is worked out from what the answer already says (the
row's causes, its reason, its rule's sources, the law's contents list), never guessed. Where something can't be told,
the field is left out or says so, never filled in.

New fields on an item:

  asks        (C1, C2, C3, C5) on a row in review: one entry per thing it asks of the architect, in order, each
              {kind, key, headline, why, elements, field?, fields?, measure?, rooms?, questions?}.
              kind: "mark" (state a fact or set a mark: `field` names the description's field that answers it, so a
              host names its own mark; a field starting "facts." or "building." is a project question), "fix_model"
              (the model, as `why` says: `elements` the element ids to show), "survey" (the lot needs a survey),
              "measure" (Gordium doesn't read or measure this yet: a person works it out by hand), "decide" (a person
              decides: a flag rule, a reading to confirm, the law's own review condition), "open_question" (the law
              reads more than one way and the readings disagree). headline: what to do, in a few words; why: the
              checker's words for it (today's cause words, or the reason's own clause). key: rows sharing a key ask
              the same thing.
  in_code     (C6) on a row of a rule: where it is in its document, {document, file, chapter, chapter_title, section,
              section_title, piece, piece_title}: the chapter (an ICC book) or article (the zoning chapter), the
              section as the book's contents list it ("1006", "§325-8"), and the part the rule's first quote is in
              ("1006.2.1", "Table 1006.2.1", "§325-8A"). A part not known is null.
  rule_name   (C8) on a row of a rule: the rule's name without its part and without the law and section in it
              ("Two exits over 10 occupants or a 75-ft common path, I-4"; the section is in in_code).
  limit_words (C9) on a row whose limit isn't worked out yet ("—"): "Limit depends on dwelling units", naming the
              facts or measures the limit reads that the row has no value for.

New field on the view:

  contents    (C7) one entry per law in the answer (zoning first): {key, document, file, title, chapters: [{number,
              title, coverage, sections: [{number, title, coverage, pieces: [{id, title, coverage, rules}]}]}]}, every
              chapter (article) and section of the document from its contents list (2_extracted_text/*.contents.jsonl),
              with Gordium's coverage: "rules" (rules check it), "flag" (flag rules raise it for a person), "not_checked_yet"
              (labeled rule or flag, no rules yet), "not_for_checking" (brought in, nothing in it to check: a definition,
              a reference) or "not_brought_in" (not extracted: Gordium hasn't read it).
"""

import ast
import re

from rule_format import formula

from design_checker import code_scope, present

MARK, FIX_MODEL, SURVEY, DECIDE, MEASURE, OPEN_QUESTION = ("mark", "fix_model", "survey", "decide", "measure",
                                                         "open_question")
KINDS = (MARK, FIX_MODEL, SURVEY, DECIDE, MEASURE, OPEN_QUESTION)

# the headline of a project question, by the field that answers it
FIELD_HEADLINES = {
    "building.occupancy_groups": "Set the occupancy group",
    "building.sprinkler_system": "Set the sprinkler system",
    "building.egress_balcony_increase_taken": "Say whether the design takes the egress balcony travel increase",
    "building.building_has_atrium": "Say whether the building has an atrium",
    "facts.corner_lot": "Is the lot on two streets? (Corner lot, §325-19C)",
    "facts.lot_surveyed": "Say whether the lot outline is from a survey",
    "facts.ground_is_flat": "Say whether the ground is flat",
    "facts.accessory_dwelling_unit": "Is there an ADU on the lot?",
    "facts.home_occupation": "Is a home business planned? (§325-3B)",
    "facts.abuts_r1_district": "Does the lot abut R-1a or R-1b land? (§325-19E)",
    "facts.stream_near_lot": "Is a stream or inlet within 20 ft of the lot? (§325-26)",
    "facts.adu_detached": "Is the ADU detached (its own building)?",
    "facts.adu_existing_building": "Is the detached ADU in an accessory building that already exists?",
    "facts.conversion": "Is it made by converting an existing building? (§325-3B)",
    "facts.primary_buildings_same_use": "Does every primary building hold the lot's use?",
}
# the facts the site's own questions answer, by the measuring's stop that asks for them (model_measurement/stops.py)
SITE_STOPS = {"corner_unknown": ["corner_lot"], "two_streets": ["corner_lot"], "one_street_or_two": ["corner_lot"],
              "survey_unknown": ["lot_surveyed"], "ground_unknown": ["ground_is_flat"]}
SURVEY_STOPS = ("not_surveyed",)
OPEN_STOPS = ("readings_differ", "all_street", "rear_on_street", "no_side_line", "no_rear_line",
              "corner_outside_residential", "lines_unclear")
# the questions a by-hand check asks, for the measures Gordium doesn't measure yet (strings.md, Checker reasons)
BY_HAND_QUESTIONS = {
    "space_egress_through_locked_room": "Check by hand: does the path pass through a room that can be locked?",
    "space_egress_through_other_room": "Check by hand: does the path pass through another room?",
    "space_egress_through_electrically_locked_lobby":
        "Check by hand: does the path pass through an electrically locked lobby?",
    "space_egress_through_kitchen_storage":
        "Check by hand: does the path pass through a kitchen, storage room or similar space?",
    "space_egress_sleeping_through_sleeping_or_toilet":
        "Check by hand: does the path from a sleeping area pass through another sleeping area or a toilet room?",
    "story_first_above_or_below_grade": "Check by hand: is this the first story above or below grade?",
    "space_exit_remoteness_ratio": "Check by hand: are the exits far enough apart (1/2 or 1/3 of the diagonal)?",
    "exit_remoteness_ratio": "Check by hand: are the exits far enough apart (1/2 or 1/3 of the diagonal)?",
}
JUDGMENT = "The code leaves this to judgment: read the words and decide"
JUDGMENT_WORDS = "A judgment call: a person decides (this rule is a flag)."   # project_report.report's words
PERSON_CHECKS = "A person checks this (Gordium doesn't decide it): "            # egress.FLAG_WHY's start


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _clause_head(text: str) -> str:
    """A clause's words up to its first colon, as a headline ("The street side isn't given")."""
    return _cap(text.split(": ")[0].strip().rstrip("."))


# ---- asks ---------------------------------------------------------------------------------------------------

def _measure_name(measure: str, kind: str | None) -> str:
    from design_checker.each_part import _words
    return _words({"for_each": kind}, measure)


def _fact_headline(fact: str) -> str:
    from design_checker.host_core.facts import STATED_FACTS
    field = f"facts.{fact}"
    if field in FIELD_HEADLINES:
        return FIELD_HEADLINES[field]
    said = STATED_FACTS.get(fact)
    if said and said[1] == "yes_no":
        return said[0]                                  # the question as the Setup form asks it
    return "Enter " + (said[2] if said else fact.replace("_", " "))


def _fact_ask(fact: str, why: str, elements=()) -> dict:
    return {"kind": MARK, "key": f"field:facts.{fact}", "headline": _fact_headline(fact), "why": why,
            "elements": list(elements), "field": f"facts.{fact}"}


def _from_cause(c: dict, rule_kind: str | None) -> dict:
    """One of panel_data's (or present.law_causes') causes as an ask: the same words as its why, a headline, the
    field that answers it (C1: a building measure by the fact it is worked out from)."""
    from model_measurement.routes.stops import STOPS
    key, words = str(c.get("key") or ""), str(c.get("words") or "")
    base = {"key": key, "why": words, "elements": list(c.get("elements") or [])}
    for k in ("rooms", "questions", "measure"):
        if k in c:
            base[k] = c[k]
    measure = c.get("measure")
    kind = c.get("kind")
    if kind == "mark":
        if key.startswith("fact:") and isinstance(measure, str):
            field = code_scope.field_of(measure) or c.get("field")
            name = _measure_name(measure, rule_kind)
            return {**base, "kind": MARK, "key": f"field:{field}", "field": field,
                    "headline": FIELD_HEADLINES.get(field) or f"Set the {name}"}
        stated = STOPS["stated_not_given"].split("{what}")[0]
        if key.startswith("mark:") and isinstance(measure, str) and stated in words:
            name = _measure_name(measure, rule_kind)
            return {**base, "kind": MEASURE,
                    "headline": f"Work out the {name} by hand: Gordium has no field for it yet"}
        if key.startswith("mark:") and isinstance(measure, str):
            return {**base, "kind": MARK, "headline": f"Mark the {_measure_name(measure, rule_kind)} in the model"}
        out = {**base, "kind": MARK, "headline": _clause_head(words) or "Set the mark this asks for"}
        for k in ("field", "fields"):
            if k in c:
                out[k] = c[k]
        return out
    if kind == "fix_model":
        if key.startswith("rooms:"):
            return {**base, "kind": FIX_MODEL, "headline": _clause_head(words)}
        if key.startswith("model:") and isinstance(measure, str):
            return {**base, "kind": FIX_MODEL,
                    "headline": f"Fix the model so the {_measure_name(measure, rule_kind)} can be measured"}
        return {**base, "kind": FIX_MODEL, "headline": _clause_head(words) or "Fix the model"}
    if kind == "measure_by_hand":
        if isinstance(measure, str) or key.startswith("gap:"):
            m = measure if isinstance(measure, str) else key.rsplit(":", 1)[-1]
            return {**base, "kind": MEASURE, "headline": BY_HAND_QUESTIONS.get(m) or
                    f"Measure the {_measure_name(m, rule_kind)} by hand: Gordium doesn't measure it yet"}
        return {**base, "kind": MEASURE, "headline": _clause_head(words) or "Check this by hand"}
    # a person decides
    if key == "flag":
        return {**base, "kind": DECIDE, "headline": JUDGMENT}
    if key.startswith("question:"):
        return {**base, "kind": OPEN_QUESTION, "headline": "An open question about the law decides this"}
    if key.startswith(("reading:", "has_none:")):
        return {**base, "kind": DECIDE, "headline": "Confirm the reading this depends on"}
    if key.startswith("review_when:"):
        return {**base, "kind": DECIDE, "headline": "The law asks a person to decide here"}
    if words.startswith(PERSON_CHECKS):
        return {**base, "kind": DECIDE, "headline": "Check this by hand: a person decides it"}
    if words == JUDGMENT_WORDS:
        return {**base, "kind": DECIDE, "headline": JUDGMENT}
    return {**base, "kind": DECIDE, "headline": "A person decides this: see why"}


def _clauses(reason: str) -> list[str]:
    """A reason's clauses: split at "; " outside brackets (a clause's own "(more if …; …)" stays whole)."""
    out, depth, start = [], 0, 0
    for k, ch in enumerate(reason):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0 and reason[k + 1:k + 2] == " ":
            out.append(reason[start:k].strip())
            start = k + 2
    out.append(reason[start:].strip())
    return [c for c in out if c]


def _stop_of(clause: str):
    """(stop key, its blanks) of a clause the measuring gave (model_measurement.stops.code_of), or None: words no
    stop gives (or two give alike) are no stop, never a guess. A clause with a bracket after it ("… (more if the
    §325-16C height bonus applies; …)") is read without the bracket."""
    from model_measurement.stops import code_of
    for text in (clause, re.sub(r"\s*\([^()]*\)\s*$", "", clause)):
        try:
            return code_of(text)
        except ValueError:
            continue
    return None


def _open_ids(site: dict | None, place) -> list[str]:
    """The site's building objects that aren't closed solids, by the place's own measuring (its _open_ids), else by
    the reader's own problem words."""
    from model_measurement.stops import stop
    buildings = [b for b in (site or {}).get("buildings") or [] if isinstance(b, dict) and "id" in b]
    finder = getattr(place, "_open_ids", None)
    if finder is not None:
        try:
            return [str(i) for i in finder(buildings)]
        except Exception:
            pass
    shut = stop("open_solid", what="")
    return [str(b["id"]) for b in buildings if any(str(p).startswith(shut) for p in b.get("problems") or [])]


def _named(site: dict | None, what: str, among: list[str]) -> list[str]:
    """The ids, among `among`, of the objects the measuring names `what` (its name, else its id)."""
    called = {str(b["id"]): str(b.get("name") or b["id"]) for b in (site or {}).get("buildings") or []
              if isinstance(b, dict) and "id" in b}
    return [i for i in among if called.get(i) == what]


def _zoning_asks(item: dict, ctx: dict) -> list[dict]:
    """A zoning row's asks: each fact it waits on (its `needs`), then each clause of its reason the measuring gave,
    by the stop it is (a fact the site's questions answer, a survey, an open question, the model: C5 names the
    objects that aren't closed solids), then any clause no stop gives that isn't a question its facts already ask
    (a person decides it, in its own words). Nothing at all: the row's one cause, as it is."""
    from design_checker.host_core.facts import USE_DETAILS_WHEN
    out = []
    needs = [n for n in item.get("needs") or [] if isinstance(n, str)]
    reason = (item.get("reason") or "").strip()
    if reason.startswith(USE_DETAILS_WHEN + ": "):
        reason = reason[len(USE_DETAILS_WHEN) + 2:]
    clauses = _clauses(reason) if reason else []
    asked = set()
    for n in needs:
        out.append(_fact_ask(n, reason, ()))
        asked.add(n)
    place = ctx.get("place")
    ask_of = getattr(place, "ASK", None) or {}
    hint = item.get("hint")
    if hint in (present.PICK_MAIN, present.PICK_ADU):
        out.append({"kind": MARK, "key": f"pick:{hint}", "headline": hint.rstrip("…"), "why": reason,
                    "elements": [o for o in item.get("objects") or [] if isinstance(o, str)]})
    for clause in clauses:
        got = _stop_of(clause)
        key = got[0] if got else None
        facts = SITE_STOPS.get(key) or [f for f, k in ask_of.items() if k == key] if key else []
        if key and facts:
            for f in facts:
                if f not in asked:
                    asked.add(f)
                    out.append(_fact_ask(f, clause))
        elif key in SURVEY_STOPS:
            out.append({"kind": SURVEY, "key": f"stop:{key}", "headline": "The lot area needs a lot outline from a survey",
                        "why": clause, "elements": []})
        elif key in OPEN_STOPS:
            out.append({"kind": OPEN_QUESTION, "key": f"stop:{key}:{clause}",
                        "headline": "An open question about the lot decides this", "why": clause, "elements": []})
        elif key == "open_solid":
            what = got[1].get("what") or ""
            ids = _named(ctx.get("site"), what, ctx["open_ids"])
            out.append({"kind": FIX_MODEL, "key": f"stop:open_solid:{what}",
                        "headline": f"“{what}” isn't a closed solid", "why": clause, "elements": ids})
        elif key is not None:
            out.append({"kind": FIX_MODEL, "key": f"stop:{key}:{clause}", "headline": _clause_head(clause),
                        "why": clause, "elements": []})
        elif needs and re.match(r"(?i)(say whether|enter|answer)\b", clause):
            continue                    # a question the row's facts ask (its follow-ups come once it is answered)
        elif clause == JUDGMENT_WORDS:
            out.append({"kind": DECIDE, "key": "flag", "headline": JUDGMENT, "why": clause, "elements": []})
        elif not needs:
            out.append({"kind": DECIDE, "key": f"reason:{item.get('id')}:{clause}", "headline":
                        "A person decides this: see why", "why": clause, "elements": []})
    if not out:
        out = [_from_cause(c, None) for c in item.get("causes") or []]
    if item.get("id") == "scope.not_included":
        out = [{"kind": FIX_MODEL, "key": "scope.not_included", "headline": "Objects on the lot aren't in the check",
                "why": reason, "elements": [o for o in item.get("objects") or [] if isinstance(o, str)]}]
    return _deduped(out)


def _deduped(asks: list[dict]) -> list[dict]:
    """Each key once (its first), in order; the elements of a repeat added to the first."""
    out, by = [], {}
    for a in asks:
        if a["key"] in by:
            first = by[a["key"]]
            first["elements"] += [e for e in a["elements"] if e not in first["elements"]]
            continue
        by[a["key"]] = a
        out.append(a)
    return out


def asks_of(item: dict, ctx: dict) -> list[dict] | None:
    """A row's asks (the module's note), or None for a row not in review."""
    if item.get("status") != present.REVIEW:
        return None
    if item.get("group") == present.LAW_GROUP:
        kind = (ctx.get("rule_kinds") or {}).get(item.get("rule"))
        return _deduped([_from_cause(c, kind) for c in item.get("causes") or []])
    return _zoning_asks(item, ctx)


# ---- the rule's name and its limit ------------------------------------------------------------------------------

def rule_name(item: dict, rule: dict | None) -> str | None:
    """The rule's name without the law and section in it: its title less a last bracket naming its section
    ("… (BCNYS 1006.2.1)"); a zoning row's own name. None for a row of no rule."""
    if not item.get("rule"):
        return None
    if item.get("group") != present.LAW_GROUP:
        return item.get("name")
    title = (rule or {}).get("title")
    if not isinstance(title, str):
        return None
    section = ((item.get("code") or {}).get("section") or "").strip()
    m = re.search(r"\s*\(([^()]*)\)\s*$", title)
    if m and section and section in m.group(1):
        return title[:m.start()].strip()
    return title.strip()


def limit_words(item: dict, rule: dict | None, values: dict) -> str | None:
    """"Limit depends on dwelling units" for a zoning row whose limit isn't worked out ("—"): the facts or
    measures its limit (the right side of the comparison its measure is on) reads that have no value."""
    if item.get("required") != "—" or not isinstance((rule or {}).get("check"), str):
        return None
    from design_checker.check import plain_name
    from design_checker.host_core.facts import STATED_FACTS
    try:
        compares = present._compares(rule["check"])
    except Exception:
        return None
    measure = item.get("measure")
    node = next((c for c in compares if isinstance(c.left, ast.Name) and c.left.id == measure), None) or \
        (compares[0] if compares else None)
    if node is None:
        return None
    try:
        names = sorted(formula.names(ast.unparse(node.comparators[0])))
    except Exception:
        return None
    missing = [n for n in names if values.get(n) is None]
    if not missing:
        return None
    said = [STATED_FACTS[n][2] if n in STATED_FACTS else plain_name(n) for n in missing]
    said = list(dict.fromkeys(said))
    return "Limit depends on " + (said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1])


# ---- adding them to the view ----------------------------------------------------------------------------------

def add(view: dict, *, rules_by_id: dict, laws: list[dict], site: dict | None, values: dict, place=None,
        place_folder=None, documents: dict | None = None) -> None:
    """Every new field onto the view's items, and the view's `contents` (the module's note). Never a crash: a field
    that can't be worked out is left out, the rest of the answer as it was."""
    from design_checker import contents as contents_mod
    law_rules = {(law["key"], r.get("id")): r for law in laws for r in law.get("rules") or [] if isinstance(r, dict)}
    rule_kinds = {r.get("id"): r.get("for_each") for law in laws for r in law.get("rules") or []
                  if isinstance(r, dict)}
    try:
        open_ids = _open_ids(site, place)
    except Exception:
        open_ids = []
    ctx = {"site": site, "place": place, "open_ids": open_ids, "rule_kinds": rule_kinds}
    try:
        books = contents_mod.books(laws, place_folder, documents)
    except Exception:
        books = {}
    for item in view.get("items") or []:
        law = item.get("group") == present.LAW_GROUP
        rule = law_rules.get((item.get("law_key"), item.get("rule"))) if law else rules_by_id.get(item.get("rule"))
        try:
            got = asks_of(item, ctx)
        except Exception:            # never a row in review without its asks: each cause as a person's to decide
            got = [{"kind": DECIDE, "key": str(c.get("key")), "headline": "A person decides this: see why",
                    "why": str(c.get("words") or ""), "elements": list(c.get("elements") or [])}
                   for c in item.get("causes") or []] if item.get("status") == present.REVIEW else None
        if got is not None:
            item["asks"] = got
        try:
            name = rule_name(item, rule)
            if name:
                item["rule_name"] = name
        except Exception:
            pass
        try:
            words = None if law else limit_words(item, rule, values)
            if words:
                item["limit_words"] = words
        except Exception:
            pass
        try:
            where = contents_mod.in_code(item, rule, books)
            if where:
                item["in_code"] = where
        except Exception:
            pass
    by_law = {law["key"]: law.get("rules") or [] for law in laws}
    try:
        view["contents"] = contents_mod.listing(
            books, view.get("items") or [],
            rules_for=lambda key: list(rules_by_id.values()) if key == "zoning" else by_law.get(key) or [])
    except Exception:
        view["contents"] = []


def place_documents(folder) -> dict:
    """{file: its sources.yaml entry} of a place's own documents (the zoning chapter's title, for in_code)."""
    from pathlib import Path

    from rule_format.rulebook import load
    path = Path(folder) / "1_source_documents" / "sources.yaml"
    try:
        return {d["file"]: d for d in (load(path) or {}).get("documents") or [] if isinstance(d, dict) and "file" in d}
    except Exception:
        return {}
