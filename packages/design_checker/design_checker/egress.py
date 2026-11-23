"""Egress switched on: a place's check also runs the building-code rules of the state law it inherits (New York's
house code for Ithaca) on the parts the interior measuring gives (model_measurement.interior). Plain code, no AI.

    found = laws("regulations/jurisdictions/new_york/ithaca_city")   # the place's inherited rulebooks, checked
    got = check(found, interior, values, allowed)                    # rows, items and one section per law
    add_to_view(view, got, place_name)                               # the panel's items, groups, state, summary

One check, one result, grouped by law (Ben, 2026-11-12: zoning and egress are two separate results; the design doc
§11): the view's `sections` are "Zoning (City of Ithaca)" and "Egress (NY State Residential Code 2025)", each with
its own state. Its items join the panel's, in a group of their own, so the design's one state (present.state) is
the most cautious of both:

- **No interior read** (no interior description, or one whose `rooms` list is empty): each law is one item, "waiting, no rooms
  drawn yet", not checked. Never a pass and never a fail; the design is then needs review at best, and the summary
  says "Egress waiting: no rooms drawn yet", so it never reads as all complying while egress waits. Zoning's own
  section can still say it complies; then the headline is "Zoning complies · Egress waiting: no rooms drawn yet",
  shown in a neutral grey "waiting" style with no "?" (`waiting_only`, choice B: Ben, 2026-11-15), the state still
  needs review.
- **An interior read:** every rule's rows (design_checker/each_part.py, the same outcome() as zoning's), each item
  naming its part ("Bedroom 2 › Window 5"), the code section and the rule's exact quote, and for a fail the change
  the rule asks ("sill height 48 in, needs ≤ 44 in"). A measure the measuring left without a value, or gave a reason
  for, needs review with that reason (each_part.cautious), unless the part fails whatever it is (2026-10-21).
- **Rules that don't pass the rule checks** (`python -m rule_format`'s, as zoning's rulebook must): one item, needs
  review, naming the problem; never a row from them. Zoning is still checked.
- **Sections not checked yet** (Ben, 2026-11-15): the law's pieces labeled rule or flag that have no rules in the rulebook
  (the generated 6_coverage_report/<book>.rules.yaml's `not_checked_yet`, never a list in code) are one needs-review
  item, "Not checked yet by Gordium: window fall protection (R321.2.1), hallway width (R318.6) and 84 more: check
  these by hand", every one listed in its detail; so the law never reads as complying while whole sections were
  never checked (principle 4). A piece the list says has rules but none of them is in the rules loaded counts as not
  checked, and a list that can't be read is itself needs review. While the law waits it stays waiting: the waiting
  row's detail lists them instead.

Loading is by place: a place's `inherits` (rule_format/place.py) names the state law folders, and each one's
rulebook is building_code_rulebook's. A state folder is never checked on its own (refuse_state_alone).
Design: docs/decisions/2026-11-12_building_code_text.md (item 6), docs/interior/interior_measurements.md.
"""

import hashlib
import json
from pathlib import Path

from model_measurement.interior import measure as measure_interior
from model_measurement.interior.read import FORMAT as INTERIOR_FORMAT
from model_measurement.routes import measure as measure_routes
from rule_format import parts as part_rules
from rule_format.formula import names as formula_names
from rule_format.labels import load_pieces
from rule_format.place import place as place_of
from rule_format.rulebook import REPO, STATE_SETTINGS, Context, load, rulebook_file_problems
from rule_format.state_law import state_settings_problems

from design_checker import code_scope, each_part, present

WAITING = "waiting"                                 # a law's section state while no interior is read
WAITING_REASON = "no rooms drawn yet"              # why a law waits: its waiting item's own `waiting` (the headline's words)
WAITING_WORDS = "waiting, " + WAITING_REASON
WAITING_WHY = ("Escape windows (size and sill), stairs (risers, treads, headroom, width) and the exit door are checked "
               "once the rooms are drawn; handrails, guards and sleeping lofts aren't read from the drawing yet, so "
               "their rules will need review. Until then this is not a pass")
BAD_RULES = "The {title} rules don't pass the rule checks (python -m rule_format), so none of them was used: {why}"
NO_RULES = "No rulebook in {folder}/5_building_code_rules/: nothing of this law was checked"
INTERIOR_PROBLEM = "The interior drawing: {why}"
SKIPPED = ("{name} is marked as an escape opening but isn't checked: {why}. An escape opening may also be required in a "
           "{where} (R319.1), which {are} read from the drawing yet: check it by hand")
# the spaces R319.1 also asks for one in, unless the description says (as a settled claim) the house has none
SKIPPED_SPACES = (("basement", "basement"), ("habitable_attic", "habitable attic"),
                  ("sleeping_loft", "room a sleeping loft is open to"))
SKIPPED_ALL_CLAIMED = ("{name} is marked as an escape opening but isn't checked: {why}. The description says the house "
                       "has no basements, no habitable attics and no sleeping lofts, the other spaces R319.1 asks for "
                       "one in: check it by hand")
NOT_PER_PART = ("this rule isn't written for each part (no for_each), and a state law's rules are checked only part "
                "by part: it isn't checked, so check it by hand")
COVERAGE = "6_coverage_report/*.rules.yaml"      # which pieces labeled rule have rules (python -m section_labeling coverage)
NAMES = "section_names.yaml"                      # plain names for them, by hand (wording only)
NOT_YET_ID = "not_checked_yet"
NOT_YET_NAME = "Not checked yet by Gordium: {first}{more}: check these by hand"
NOT_YET_WHY = ("Gordium doesn't check these sections of the {title} yet, so it never says {short} complies while any "
               "is left. Check each by hand: {all}. (The list: {file}.)")
NOT_YET_WAITING = ". Not checked yet by Gordium, even once the rooms are drawn (check these by hand): {all}"
NO_COVERAGE = ("Gordium can't tell which sections of the {title} it doesn't check yet ({why}): check the whole law by "
               "hand")
NOTHING_APPLIED = ("None of the {title} rules applied to the parts drawn (every one not applicable): nothing of this law "
                   "was checked, so check it by hand")
SECTIONS = "sections"             # an item's `open` for the sections not checked yet (design_checker/grouping.py)
# what the interior description says the house has none of: one item per claim, never hidden, counted toward nothing
HAS_NONE_ID = "has_none"
HAS_NONE_NAME = "{words}: not applicable"
HAS_NONE_WHY = "Not applicable: {said} ({source}). The rules this sets aside: {rules}"
# a claim that rests on a reading of the law, not on the drawings alone: shown as one to confirm (needs review)
HAS_NONE_READING_NAME = "{words}: not applicable if this reading is confirmed"
HAS_NONE_READING_WHY = ("Confirm: {said}, a reading to confirm ({source}). If it is right, these rules don't apply: "
                        "{rules}")
HAS_NONE_NO_RULES = "none of the rules checked turns on it"
ORDER = {present.FAILS: 0, present.REVIEW: 1, present.NOT_CHECKED: 2, present.COMPLIES: 3, present.NOT_APPLICABLE: 4}


def refuse_state_alone(jurisdiction) -> None:
    """A state law folder (one with a state.yaml) is no place: its rules are checked only through a place that
    inherits it (building_code_text decision, item 6). Named as the lot's jurisdiction, it is refused in words."""
    folder = _folder(jurisdiction)
    if (folder / STATE_SETTINGS).is_file():
        raise ValueError(f"{folder.name.replace('_', ' ')} is a state's law, not a place: its rules are checked only "
                         "for a lot in a place that inherits them (its jurisdiction.yaml `inherits:`)")


def _folder(jurisdiction) -> Path:
    p = Path(jurisdiction)
    return p if p.is_absolute() else REPO / p


# Each book's validation (its Context and the rule checks: the slow, file-pure part of laws), kept by a snapshot of
# every file and folder under the roots it can read from, taken before and after it runs (review round 9: watching
# its reads missed a file appearing, an edit during the run and a passing error). Kept only when the two snapshots
# agree and it raised nothing; used again only when a fresh snapshot equals the one it was kept by. Everything else
# laws gives (titles, scopes, sections, the list not checked yet) is worked out fresh at every call.
_VALIDATED: dict = {}


def _roots(folder: Path) -> list[Path]:
    """Where a book's validation can read from: the regulations (every place's and state's folders, the reviewers,
    the extraction guide) and the rule format's own files."""
    return [REPO / "regulations", REPO / "packages/rule_format/rule_format"]


def _snapshot(roots) -> tuple:
    """Every file and folder under the roots, each (path, size, change time), folders too (one gains or loses an
    entry when a file is added, deleted or renamed): any change anywhere changes it. Stat-only."""
    import os
    out = []

    def walk(top: str):
        try:
            with os.scandir(top) as entries:
                for e in entries:
                    if e.name == "__pycache__":
                        continue
                    try:
                        s = e.stat(follow_symlinks=False)
                    except OSError:
                        out.append((e.path, None, None))
                        continue
                    out.append((e.path, s.st_size, s.st_mtime_ns))
                    if e.is_dir(follow_symlinks=False):
                        walk(e.path)
        except OSError:
            out.append((top, None, None))

    for r in roots:
        try:
            s = os.stat(r)
            out.append((str(r), s.st_size, s.st_mtime_ns))
        except OSError:
            out.append((str(r), None, None))
        if os.path.isdir(r):
            walk(str(r))
    return tuple(sorted(out))


def _validate(folder: Path, book: Path) -> tuple[dict, bool]:
    """A book's validation: ({problems, documents, kinds, rules}, whether it raised). Rules only when it passes the
    rule checks. Never a crash (zoning's answer goes with it), never a rule used unchecked."""
    try:
        ctx = Context.for_jurisdiction(folder, use_cache=False)   # the same answer on every machine
        problems = ctx.problems + state_settings_problems(folder, ctx) + rulebook_file_problems(book, ctx)
        return {"problems": problems, "documents": ctx.sources,
                "kinds": {k: v for k, v in ctx.allowed().items() if k not in ("use", "district")},
                "rules": [] if problems else load(book)["rules"]}, False
    except Exception as e:
        return {"problems": [f"its sources can't be read ({type(e).__name__}: {e})"], "documents": {}, "kinds": {},
                "rules": []}, True


def _validated(folder: Path, book: Path) -> dict:
    """_validate, kept while nothing under its roots changes (and no reader it calls is swapped: a test's
    monkeypatch), each caller given its own copy. Fails closed: an edit during the run, or an error, is never kept."""
    import copy
    readers = (id(load), id(rulebook_file_problems), id(state_settings_problems),
               id(Context.for_jurisdiction.__func__))     # a class method's bound object is new at every look
    key = (str(folder), str(book), readers)
    roots = _roots(folder)
    before = _snapshot(roots)
    hit = _VALIDATED.get(key)
    if hit is not None and hit[0] == before:
        return copy.deepcopy(hit[1])
    result, raised = _validate(folder, book)
    if not raised and _snapshot(roots) == before:
        _VALIDATED[key] = (before, result)
    else:
        _VALIDATED.pop(key, None)
    return copy.deepcopy(result)


def laws(jurisdiction) -> dict:
    """The place and every state law it inherits, ready to check: {"place": its name, "laws": [{key, title, short,
    folder, rulebook, rules, problems, section_of, documents}]}. A rulebook that doesn't pass the rule checks gives
    no rules and its problems (needs review, never a row). Each book's validation is kept by the files it read
    (_validated); the rest is worked out at every call."""
    refuse_state_alone(jurisdiction)
    p = place_of(_folder(jurisdiction))
    out = []
    for folder, book in p.inherited_rulebooks():
        law = {"key": f"{folder.parent.name}/{folder.name}", "title": _title(folder), "folder": folder,
               "rulebook": book, "rules": [], "problems": [], "section_of": None, "documents": {},
               "not_checked_yet": [], "coverage_problem": None, "kinds": {}, **_scope_settings(folder)}
        law["short"] = law["title"].split(" (")[0]
        if book is None:
            law["problems"] = [NO_RULES.format(folder=law["key"])]
        else:
            law.update(_validated(folder, book))
            if not law["problems"]:
                try:
                    law["section_of"] = _sections(folder)
                except Exception as e:
                    law["problems"], law["rules"] = [f"its sources can't be read ({type(e).__name__}: {e})"], []
        law["not_checked_yet"], law["coverage_problem"] = _not_checked_yet(folder, law["rules"])
        out.append(law)
    return {"place": p.name, "laws": out}


def _not_checked_yet(folder: Path, rules: list) -> tuple[list[dict], str | None]:
    """([{section, name, label, file}] the law's pieces labeled rule or flag that have no rules in the rules loaded:
    the rule pieces first, in the order section_names.yaml gives, then the book's; then the flag pieces, in the
    book's order], the problem reading the list or None). Read from the generated coverage list, never from code. A piece
    it says has rules counts as not checked unless every one of those rules is among `rules` (a rulebook refused, or
    a list older than the rulebook, never makes a section look checked), and so does every piece its own
    `not_checked_yet` names (the two never disagree in a generated list; if they do, the more cautious stands)."""
    loaded = {r.get("id") for r in rules if isinstance(r, dict)}
    files = sorted(folder.glob(COVERAGE))
    if not files:
        return [], f"no {COVERAGE} in {folder.name}"
    missing = []
    try:
        for path in files:
            data = load(path)
            where = f"{folder.name}/{path.relative_to(folder).as_posix()}"
            listed = [str(p) for p in data.get("not_checked_yet") or []]
            for pid, entry in data["pieces"].items():
                ids = entry["rules"]
                if not ids or not set(ids) <= loaded or str(pid) in listed:
                    missing.append({"section": str(pid), "heading": str(entry.get("heading") or pid),
                                    "label": "flag" if entry.get("label") == "flag" else "rule", "file": where})
            seen = {m["section"] for m in missing}
            missing += [{"section": p, "heading": p, "label": "rule", "file": where} for p in listed if p not in seen]
    except Exception as e:          # a list that can't be read is needs review, never "everything is checked"
        return [], f"{path.name} can't be read ({type(e).__name__}: {e})"
    try:
        names = (load(folder / NAMES) or {}).get("names") or {} if (folder / NAMES).is_file() else {}
        names = names if isinstance(names, dict) else {}
    except Exception:               # wording only: the law's own headings stand in
        names = {}
    order = {pid: n for n, pid in enumerate(names)}
    # the rule pieces in section_names.yaml's order, then the book's; the flag pieces after them, in the book's order
    missing.sort(key=lambda m: (1, 0) if m["label"] == "flag" else (0, order.get(m["section"], len(order))))
    return [{**m, "name": names[m["section"]] if isinstance(names.get(m["section"]), str) and
             names[m["section"]].strip() else m["heading"]} for m in missing], None


def _scope_settings(folder: Path) -> dict:
    """state.yaml's `scope` (which buildings the law covers: code_scope.CODES, or None for every building) and its
    `waiting_why` (what its waiting row says; None: WAITING_WHY, the house code's words). Read as words only; a
    state.yaml that can't be read gives neither (its problem is said by state_settings_problems)."""
    try:
        s = load(folder / STATE_SETTINGS)
    except Exception:
        s = None
    s = s if isinstance(s, dict) else {}
    scope = s.get("scope") if s.get("scope") in code_scope.CODES else None
    why = s.get("waiting_why") if isinstance(s.get("waiting_why"), str) and s["waiting_why"].strip() else None
    return {"scope": scope, "waiting_why": " ".join(why.split()) if why else None}


def _title(folder: Path) -> str:
    """How the law's results are headed: state.yaml's results_title, else "<name> building code"; a state.yaml that
    can't be read gives the folder's name (its problem is said by state_settings_problems, never a crash)."""
    try:
        s = load(folder / STATE_SETTINGS)
    except Exception:
        s = None
    s = s if isinstance(s, dict) else {}
    words = lambda v: v.strip() if isinstance(v, str) and v.strip() else None
    return words(s.get("results_title")) or f"{words(s.get('name')) or folder.name.replace('_', ' ')} building code"


def _sections(folder: Path):
    """section(file, page, line): the code section a cited line is in ("R319.2.3"), from the state's sections
    files; "" for a line in none."""
    spans = {}
    for path in sorted((folder / "2_extracted_text").glob("*.sections.jsonl")):
        header, pieces = load_pieces(path)
        spans[header["file"]] = [(pg, a, b, pid.partition(":")[0]) for pid, piece in pieces.items()
                                 for pg, a, b in piece["lines"]]

    def section(file, page, line):
        return next((pid for pg, a, b, pid in spans.get(file, ()) if pg == page and a <= line <= b), "")
    return section


def _no_rooms(interior) -> bool:
    """No interior read yet: none given, or a readable description whose list of rooms is empty (massing). A
    description that leaves `rooms` out isn't waiting: the measuring says the rooms weren't read (needs review)."""
    if interior is None:
        return True
    return isinstance(interior, dict) and interior.get("format") == INTERIOR_FORMAT and interior.get("rooms") == []


def check(found: dict, interior, values: dict, allowed: dict) -> dict:
    """Every inherited law's rows and items for one design. `interior`: the interior description
    (gordium.interior/1, docs/interior/interior_description_format.md), or None when none is drawn. `values`: the
    building's measures (dwelling units…), `allowed`: the place's allowed values (its uses).

    Where the place inherits laws that each cover some buildings (state.yaml `scope`: New York's Residential Code and
    Building Code), code_scope.decide picks the one that covers this building from `values` and the description's
    `building` block, and only that one runs: a house the Residential Code covers is checked exactly as before. Where
    it can't tell (a fact missing, or both possible), each runs with a needs-review line saying why, first in its
    section, so neither reads as the answer (principle 4). The decision is the result's `code_scope`."""
    waiting = _no_rooms(interior)
    building = interior.get("building") if isinstance(interior, dict) else None
    scope = code_scope.decide(values, building) if any(law.get("scope") for law in found["laws"]) else None
    run = [law for law in found["laws"]
           if scope is None or law.get("scope") is None or scope["code"] in (None, law["scope"])]
    undecided = scope is not None and scope["code"] is None
    sections, items, rows, results, ids, readings = [], [], [], {}, set(), {}
    for law in run:
        measured = None if waiting else _measured(law, interior, readings)
        law_values, law_allowed = _law_values(law, values, allowed, building)
        # rules that can't be used are said whether or not rooms are drawn: never hidden behind "waiting"
        mine = _law_items(law, measured, law_values, law_allowed, rows, results) if not waiting or law["problems"]             else [_waiting_item(law)]
        if not waiting and not law["problems"]:   # rules refused: none was used (BAD_RULES says so); waiting stays
            mine += _not_yet_items(law)           # waiting, its row lists them (_waiting_item)
        if scope is not None and law.get("scope"):
            mine += _scope_items(law, scope)
        mine.sort(key=lambda i: ORDER[i["status"]])          # what fails first, then needs review (stable)
        for i in mine:                                       # one id per item, across laws too (hosts refuse twins)
            if i["id"] in ids:
                i["id"] = f"{i['id']}#{law['key']}"
            ids.add(i["id"])
        items += mine
        calm = waiting and not law["problems"] and not undecided    # a law only waiting for rooms
        sections.append({"key": law["key"], "title": law["title"],
                         "state": WAITING if calm else present.state(mine),
                         "summary": WAITING_WORDS if calm else present._law_summary(mine),
                         "rules": len(law["rules"]), "rulebook": _shown(law["rulebook"]),
                         "problems": list(law["problems"])})
    measured = next(iter(readings.values()), None)
    return {"sections": sections, "items": items, "rows": rows, "results": results, "waiting": waiting,
            "interior": None if measured is None else {k: measured[k] for k in ("parts", "problems", "not_checked",
                                                                                "has_none")},
            "interior_sha256": fingerprint(interior), **({"code_scope": scope} if scope is not None else {})}


def which_code(got: dict) -> dict | None:
    """The code decision as a host shows it at the top of the results (Ben, 2026-11-22: chosen for the architect,
    shown, never a choice offered): {code, title, why, cites: [{section, document, page, quote}], ask, assumes:
    [words]}, the very words of code_scope.decide; None where the place's laws don't split buildings between books."""
    scope = got.get("code_scope")
    return None if scope is None else {k: scope[k] for k in ("code", "title", "why", "cites", "ask", "assumes")}


ROUTES = "routes"
SCOPE_ID = "code_scope"
SCOPE_OPEN_NAME = "Which code governs this building: can't tell yet"
SCOPE_OPEN_WHY = ("Gordium can't tell whether the Residential Code or the Building Code of New York State covers this "
                  "building: {why} ({cites}). To settle it, {ask}. Both are shown; neither is the answer until then")
SCOPE_NAME = "This building is under the {book}"
SCOPE_WHY = "The {book} covers this building: {why} ({cites})"


def _measured(law: dict, interior, readings: dict) -> dict:
    """The parts a law's rules read, measured once per kind of reading: the house code's from the interior measuring
    (model_measurement.interior), the Building Code's from the routes (model_measurement.routes: story, space and
    corridor), in the same shape."""
    kind = ROUTES if law.get("scope") == code_scope.BUILDING else "interior"
    if kind not in readings:
        if kind == ROUTES:
            got = measure_routes(interior)
            readings[kind] = {"parts": got["parts"], "problems": [str(p) for p in got["problems"]],
                              "not_checked": [], "has_none": {}}
        else:
            readings[kind] = measure_interior(interior)
    return readings[kind]


def _law_values(law: dict, values: dict, allowed: dict, building) -> tuple[dict, dict]:
    """The building values and allowed values a law's rules read: the check's own, and for the Building Code the
    building block's measures (code_scope.building_measures: occupancy group, sprinkler system...). A proposed
    measure's kind (the law's drafted/records/proposed_measures.yaml) is added only for one given a value, so a law
    reads exactly what it did where none is given."""
    if law.get("scope") == code_scope.BUILDING:
        given = {k: values[k] for k in code_scope.FACTS if k in values}
        values = {**values, **code_scope.building_measures({**given, **(building if isinstance(building, dict) else {})})}
    kinds = {k: v for k, v in (law.get("kinds") or {}).items() if k in values and k not in allowed}
    return values, ({**allowed, **kinds} if kinds else allowed)


def _scope_items(law: dict, scope: dict) -> list[dict]:
    """The law's line on which code governs: needs review where code_scope can't tell (first in each candidate's
    section); for the Building Code chosen, a line saying why (counted toward nothing). None for the Residential Code
    chosen: a house's check reads exactly as before, the decision in the result's `code_scope`."""
    cites = ", ".join(c["section"] for c in scope["cites"])
    if scope["code"] is None:
        item = _own_item(law, f"{law['short'].lower()}.{SCOPE_ID}", SCOPE_OPEN_NAME, present.REVIEW,
                         SCOPE_OPEN_WHY.format(why=scope["why"], cites=cites, ask=scope["ask"]))
    elif scope["code"] == code_scope.BUILDING:
        book = _book(law)
        item = _own_item(law, f"{law['short'].lower()}.{SCOPE_ID}", SCOPE_NAME.format(book=book),
                         present.NOT_APPLICABLE, SCOPE_WHY.format(book=book, why=scope["why"], cites=cites))
    else:
        return []
    item["detail"]["citation"] = cites
    item["code_scope"] = dict(scope)
    return [item]


def fingerprint(interior) -> str | None:
    """sha256 of the interior description checked (its JSON, keys sorted), so a result says exactly which interior
    it was worked out from; None when none was given."""
    if interior is None:
        return None
    text = json.dumps(_plain(interior), sort_keys=True, ensure_ascii=True, default=repr, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(x):
    """The description with every mapping key as text (a YAML key may be a number: `1: a`), each non-text key
    written with its type so `1` and `"1"` stay apart, for a fingerprint that never fails."""
    if isinstance(x, dict):
        return {(k if isinstance(k, str) else f"{type(k).__name__}:{k!r}"): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def _shown(path) -> str | None:
    if path is None:
        return None
    try:
        return Path(path).relative_to(REPO).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _law_items(law, measured, values, allowed, rows, results) -> list[dict]:
    if law["problems"]:
        why = "; ".join(law["problems"][:3]) + (f" (and {len(law['problems']) - 3} more)" if len(law["problems"]) > 3
                                                 else "")
        return [_own_item(law, f"{law['short'].lower()}.rules", f"{law['short']} rules", present.REVIEW,
                          BAD_RULES.format(title=law["title"], why=why))]
    claims = measured.get("has_none") or {}
    got = each_part.check_parts(law["rules"], measured["parts"], values, allowed, claims)
    rows += got["rows"]
    for key, answer in got["results"].items():   # one rule id in two laws: the more cautious answer, never kinder
        results[key] = part_rules.rule_result([{"outcome": answer}] + ([{"outcome": results[key]}]
                                                                       if key in results else []))
    by_id = {r["id"]: r for r in law["rules"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    out = [_decorated(i, law, by_id.get(i["rule"])) for i in got["items"]]
    # a rule not written for each part is never dropped in silence: its own needs-review row and answer
    for n, rule in enumerate(law["rules"], 1):
        if isinstance(rule, dict) and not part_rules.is_part_rule(rule) and rule.get("kind") == "flag":
            out.append(_flag_item(law, rule, each_part._key(rule, n), values, allowed, results))
        elif isinstance(rule, dict) and not part_rules.is_part_rule(rule):
            key = each_part._key(rule, n)
            results[key] = part_rules.rule_result([{"outcome": "needs_review"}] + ([{"outcome": results[key]}]
                                                                                   if key in results else []))
            item = _own_item(law, f"{law['short'].lower()}.{key}", law["short"], present.REVIEW, NOT_PER_PART)
            out.append({**_decorated({**item, "rule": key}, law, rule), "reason": NOT_PER_PART})
    out += [_own_item(law, f"{law['short'].lower()}.interior#{n}", "Interior drawing", present.REVIEW,
                      INTERIOR_PROBLEM.format(why=why)) for n, why in enumerate(measured["problems"], 1)]
    out += [_own_item(law, f"{law['short'].lower()}.skipped#{n}", f"{skip.get('name') or skip.get('id')}: not checked",
                      present.REVIEW, _skipped(skip, claims))
            for n, skip in enumerate(measured["not_checked"], 1)]
    out += [_has_none_item(law, kind, claim, got["set_aside"].get(kind) or [], by_id) for kind, claim in claims.items()]
    # every row not applicable (left out of the panel; a claim's item counts toward nothing): never a law that
    # vanishes from the answer, or reads as checked when nothing was
    if not [i for i in out if i["status"] != present.NOT_APPLICABLE]:
        out.append(_own_item(law, f"{law['short'].lower()}.nothing_applied", f"{law['short']}: nothing checked",
                             present.REVIEW, NOTHING_APPLIED.format(title=law["title"])))
    return out


FLAG_WHY = "A person checks this (Gordium doesn't decide it): {note}"
FLAG_NOT_APPLICABLE = "Not applicable: {when} is not so, as stated ({names})"


def _flag_item(law: dict, rule: dict, key: str, values: dict, allowed: dict, results: dict) -> dict:
    """A flag written for the whole building (no for_each: the Building Code's classification and allowances): its
    own line, needs review with the rule's words for what to check, or not applicable where its applies_when is
    stated false (outcome() over the building's values, as a zoning flag). Never a pass."""
    from rule_format.rulebook import _outcome
    answer = _outcome(rule, values, allowed)
    results[key] = part_rules.rule_result([{"outcome": answer}] + ([{"outcome": results[key]}] if key in results
                                                                      else []))
    note = next((e.get("note") for e in rule.get("examples") or [] if isinstance(e, dict) and e.get("note")
                 and e.get("expect") == "needs_review"), None) or rule.get("notes") or rule.get("title") or key
    if answer == "not_applicable":
        when = str(rule.get("applies_when"))
        status, why = present.NOT_APPLICABLE, FLAG_NOT_APPLICABLE.format(
            when=when, names=", ".join(f"{n}: {values[n]}" for n in sorted(formula_names(when)) if n in values))
    else:
        status, why = present.REVIEW, FLAG_WHY.format(note=" ".join(str(note).split()))
    item = _own_item(law, f"{law['short'].lower()}.{key}", law["short"], status, why)
    return {**_decorated({**item, "rule": key}, law, rule), "reason": why}


def _skipped(skip: dict, claims: dict) -> str:
    """Why an escape opening isn't checked, naming only the spaces R319.1 also asks for one in that aren't settled by
    a claim (a reading claim still to confirm leaves its space named)."""
    name = skip.get("name") or skip.get("id")
    unread = [words for kind, words in SKIPPED_SPACES if (claims.get(kind) or {}).get("reading") is not False]
    if not unread:
        return SKIPPED_ALL_CLAIMED.format(name=name, why=skip.get("why"))
    where = unread[0] if len(unread) == 1 else ", ".join(unread[:-1]) + " or " + unread[-1]
    return SKIPPED.format(name=name, why=skip.get("why"), where=where,
                          are="isn't" if len(unread) == 1 else "aren't")


def _section(law: dict, rule: dict) -> str:
    """The code section a rule's first quote is in ("R318.8.1"), or "" where it can't be told."""
    first = next((s for s in rule.get("sources") or [] if isinstance(s, dict)), {})
    lines = first.get("lines") if isinstance(first.get("lines"), list) else []
    return law["section_of"](first.get("file"), first.get("page"), lines[0]) if law["section_of"] and lines else ""


def _has_none_item(law: dict, kind: str, claim: dict, keys: list, by_id: dict) -> dict:
    """One claim's item: "Ramps: not applicable", its words and source, and every rule it set aside (by title and
    section; the sections also as its citation). Status not applicable: shown, never counted (present.state). A
    claim marked as a reading ("an unfinished attic is not a habitable attic") is one to confirm: needs review."""
    rules = [by_id.get(k) or {"title": k} for k in keys]
    titled = [(str(r.get("title") or r.get("id") or ""), _section(law, r)) for r in rules]
    named = "; ".join(t if not sec or sec in t else f"{t} ({sec})" for t, sec in titled) or HAS_NONE_NO_RULES
    reading = claim.get("reading") is True
    why = (HAS_NONE_READING_WHY if reading else HAS_NONE_WHY).format(said=claim["words"], source=claim["source"],
                                                                      rules=named)
    words = claim["words"].rsplit(" has no ", 1)[-1]
    item = _own_item(law, f"{law['short'].lower()}.{HAS_NONE_ID}.{kind}",
                     (HAS_NONE_READING_NAME if reading else HAS_NONE_NAME).format(words=words[:1].upper() + words[1:]),
                     present.REVIEW if reading else present.NOT_APPLICABLE, why,
                     has_none={"kind": kind, "source": claim["source"], "reading": reading, "rules": list(keys)})
    item["detail"]["citation"] = ", ".join(dict.fromkeys(sec for _, sec in titled if sec))
    return item


def _decorated(item: dict, law: dict, rule: dict | None) -> dict:
    """A part's row as the panel shows it: the part and the rule in its name, the code section and the rule's own
    quote (with where it is) in its detail, its law to group it by."""
    rule = rule or {}
    title = rule.get("title") if isinstance(rule.get("title"), str) else item["rule"] or "rule"
    sources = [s for s in rule.get("sources") or [] if isinstance(s, dict)]
    doc = lambda s: (law["documents"].get(s.get("file")) or {}).get("title") or s.get("file") or ""
    where = []
    for s in sources:
        lines = s.get("lines") if isinstance(s.get("lines"), list) else []
        section = law["section_of"](s.get("file"), s.get("page"), lines[0]) if law["section_of"] and lines else ""
        where.append({"section": section, "document": doc(s), "page": s.get("page"),
                      "quote": " ".join(str(s.get("quote", "")).split())})
    first = where[0] if where else {"section": "", "document": "", "page": None, "quote": ""}
    citation = ", ".join(str(x) for x in (first["section"], first["document"],
                                          f"PDF p.{first['page']}" if first["page"] is not None else "") if x)
    return {**item, "name": f"{item['name']} · {title}", "group": present.LAW_GROUP, "law": law["title"],
            "law_short": law["short"], "law_key": law["key"],
            "code": {"section": first["section"], "quote": first["quote"]},
            "detail": {**item["detail"], "citation": citation,
                       "quotes": [{"text": w["quote"], "where": ", ".join(
                           str(x) for x in (w["section"], w["document"],
                                            f"PDF p.{w['page']}" if w["page"] is not None else "") if x)}
                           for w in where]}}


def _own_item(law: dict, item_id: str, name: str, status: str, reason: str, **more) -> dict:
    """An item of the law's that is no rule's row (waiting, rules refused, the interior drawing's problem)."""
    base = each_part._item(item_id, None, name, status, reason)
    return {**base, "group": present.LAW_GROUP, "law": law["title"], "law_short": law["short"], "law_key": law["key"],
            "code": None, **more}


FLAGS_WORDS = "Sections that call for a judgment Gordium doesn't raise yet: "


def _listed(missing: list[dict]) -> str:
    """Every section by name: the ones with requirements to check, then the ones calling for a judgment (flag)."""
    rules = "; ".join(f"{m['name']} ({m['section']})" for m in missing if m.get("label") != "flag")
    flags = "; ".join(f"{m['name']} ({m['section']})" for m in missing if m.get("label") == "flag")
    return ". ".join(x for x in (rules, FLAGS_WORDS + flags if flags else "") if x)


def _not_yet_items(law: dict) -> list[dict]:
    """The law's one needs-review line for the sections it has no rules for (none when every one has), or for a list
    of them that can't be read. One line in the panel; every section in its detail."""
    if law["coverage_problem"]:
        why = NO_COVERAGE.format(title=_book(law), why=law["coverage_problem"])
        return [_own_item(law, f"{law['short'].lower()}.{NOT_YET_ID}", "Not checked yet by Gordium: can't tell which "
                          "sections", present.REVIEW, why, open={"gordium": SECTIONS, "sections": None})]
    missing = law["not_checked_yet"]
    if not missing:
        return []
    first = ", ".join(f"{m['name']} ({m['section']})" for m in missing[:2])
    more = f" and {len(missing) - 2} more" if len(missing) > 2 else ""
    item = _own_item(law, f"{law['short'].lower()}.{NOT_YET_ID}", NOT_YET_NAME.format(first=first, more=more),
                     present.REVIEW, NOT_YET_WHY.format(title=_book(law), short=law["short"].lower(),
                                                        all=_listed(missing),
                                                        file=", ".join(dict.fromkeys(m["file"] for m in missing))))
    item["detail"]["citation"] = ", ".join(m["section"] for m in missing)
    item["open"] = {"gordium": SECTIONS, "sections": [m["section"] for m in missing]}   # for grouping: words only
    return [item]


def _book(law: dict) -> str:
    """The law's book from its title: "NY State Residential Code 2025" from "Egress (NY State Residential Code 2025)"."""
    t = law["title"]
    return t[t.index(" (") + 2:-1] if " (" in t and t.endswith(")") else t


def _waiting_item(law: dict) -> dict:
    why = (law.get("waiting_why") or WAITING_WHY) + (NOT_YET_WAITING.format(all=_listed(law["not_checked_yet"])) if law["not_checked_yet"] else "")
    if law["coverage_problem"]:
        why += ". " + NO_COVERAGE.format(title=_book(law), why=law["coverage_problem"])
    item = _own_item(law, f"{law['short'].lower()}.waiting", f"{law['short']}: {WAITING_WORDS}", present.NOT_CHECKED,
                     why, waiting=WAITING_REASON)
    # the sections, as the not-checked-yet line's detail gives them (the permit sheets print them from here)
    item["detail"]["citation"] = ", ".join(m["section"] for m in law["not_checked_yet"])
    return item


def add_to_view(view: dict, got: dict, place_name: str) -> None:
    """The laws' items into the panel's view: its items, groups, state and summary, and `sections`, one per law
    (zoning's first), each with its own state. The design's state is present.state over every item, so it is never
    kinder than any section's (a law waiting holds it at needs review)."""
    zoning = [i for i in view["items"] if i["group"] != present.LAW_GROUP]
    view["items"] = zoning + got["items"]
    # the most cautious of every item's and every law's own state (a law waiting counts as needs review)
    states = [present.state(view["items"])] + [present.REVIEW if s["state"] == WAITING else s["state"]
                                               for s in got["sections"]]
    view["state"] = min(states, key=[present.FAILS, present.REVIEW, present.COMPLIES].index)
    view["summary"] = present.summary(view["items"])
    # choice B (Ben, 2026-11-15): held at needs review only by a law still waiting (zoning complies, at least one law
    # waits, none fails or needs review), the headline is calm: grey, its words say why, no "?" mark. Only how the
    # headline looks: the state stays needs review, never a pass
    sections = [s["state"] for s in got["sections"]]
    view["waiting_only"] = (view["state"] == present.REVIEW and present.state(zoning) == present.COMPLIES
                            and WAITING in sections and all(s in (WAITING, present.COMPLIES) for s in sections))
    view["groups"] = present.grouped(view["items"])
    view["sections"] = [{"key": "zoning", "title": f"Zoning ({place_name})", "state": present.state(zoning),
                         "summary": present._summary(zoning)}] + [
        {k: s[k] for k in ("key", "title", "state", "summary")} for s in got["sections"]]
