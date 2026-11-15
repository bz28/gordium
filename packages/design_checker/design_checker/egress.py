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
  says "Egress: waiting, no rooms drawn yet", so it never reads as all complying while egress waits. Zoning's own
  section can still say it complies.
- **An interior read:** every rule's rows (design_checker/each_part.py, the same outcome() as zoning's), each item
  naming its part ("Bedroom 2 › Window 5"), the code section and the rule's exact quote, and for a fail the change
  the rule asks ("sill height 48 in, needs ≤ 44 in"). A measure the measuring left without a value, or gave a reason
  for, needs review with that reason (each_part.cautious), unless the part fails whatever it is (2026-10-21).
- **Rules that don't pass the rule checks** (`python -m rule_format`'s, as zoning's rulebook must): one item, needs
  review, naming the problem; never a row from them. Zoning is still checked.

Loading is by place: a place's `inherits` (rule_format/place.py) names the state law folders, and each one's
rulebook is building_code_rulebook's. A state folder is never checked on its own (refuse_state_alone).
Design: docs/decisions/2026-11-12_building_code_text.md (item 6), docs/interior/interior_measurements.md.
"""

import hashlib
import json
from pathlib import Path

from model_measurement.interior import measure as measure_interior
from model_measurement.interior.read import FORMAT as INTERIOR_FORMAT
from rule_format import parts as part_rules
from rule_format.labels import load_pieces
from rule_format.place import place as place_of
from rule_format.rulebook import REPO, STATE_SETTINGS, Context, load, rulebook_file_problems

from design_checker import each_part, present

WAITING = "waiting"                                 # a law's section state while no interior is read
WAITING_WORDS = "waiting, no rooms drawn yet"
WAITING_WHY = ("Escape windows (size and sill), stairs (risers, treads, headroom, width) and the exit door are checked "
               "once the rooms are drawn; handrails, guards and sleeping lofts aren't read from the drawing yet, so "
               "their rules will need review. Until then this is not a pass")
BAD_RULES = "The {title} rules don't pass the rule checks (python -m rule_format), so none of them was used: {why}"
NO_RULES = "No rulebook in {folder}/5_building_code_rules/: nothing of this law was checked"
INTERIOR_PROBLEM = "The interior drawing: {why}"
NOTHING_APPLIED = ("None of the {title} rules applied to the parts drawn (every one not applicable): nothing of this law "
                   "was checked, so check it by hand")
ORDER = {present.FAILS: 0, present.REVIEW: 1, present.NOT_CHECKED: 2, present.COMPLIES: 3}


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


def laws(jurisdiction) -> dict:
    """The place and every state law it inherits, ready to check: {"place": its name, "laws": [{key, title, short,
    folder, rulebook, rules, problems, section_of, documents}]}. A rulebook that doesn't pass the rule checks gives
    no rules and its problems (needs review, never a row)."""
    refuse_state_alone(jurisdiction)
    p = place_of(_folder(jurisdiction))
    out = []
    for folder, book in p.inherited_rulebooks():
        settings = load(folder / STATE_SETTINGS) or {}
        title = settings.get("results_title") or f"{settings.get('name') or folder.name} building code"
        law = {"key": f"{folder.parent.name}/{folder.name}", "title": title, "short": title.split(" (")[0],
               "folder": folder, "rulebook": book, "rules": [], "problems": [], "section_of": None, "documents": {}}
        if book is None:
            law["problems"] = [NO_RULES.format(folder=law["key"])]
        else:
            try:
                ctx = Context.for_jurisdiction(folder, use_cache=False)   # the same answer on every machine
                law["problems"] = ctx.problems + rulebook_file_problems(book, ctx)
                law["documents"] = ctx.sources
            except Exception as e:                    # never a crash, never a rule used unchecked
                law["problems"] = [f"its sources can't be read ({type(e).__name__}: {e})"]
            if not law["problems"]:
                law["rules"] = load(book)["rules"]
                law["section_of"] = _sections(folder)
        out.append(law)
    return {"place": p.name, "laws": out}


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
    building's measures (dwelling units…), `allowed`: the place's allowed values (its uses)."""
    waiting = _no_rooms(interior)
    measured = None if waiting else measure_interior(interior)
    sections, items, rows, results, ids = [], [], [], {}, set()
    for law in found["laws"]:
        mine = _law_items(law, measured, values, allowed, rows, results) if not waiting else [_waiting_item(law)]
        mine.sort(key=lambda i: ORDER[i["status"]])          # what fails first, then needs review (stable)
        for i in mine:                                       # one id per item, across laws too (hosts refuse twins)
            if i["id"] in ids:
                i["id"] = f"{i['id']}#{law['key']}"
            ids.add(i["id"])
        items += mine
        sections.append({"key": law["key"], "title": law["title"],
                         "state": WAITING if waiting else present.state(mine),
                         "summary": WAITING_WORDS if waiting else present._summary(mine),
                         "rules": len(law["rules"]), "rulebook": _shown(law["rulebook"]),
                         "problems": list(law["problems"])})
    return {"sections": sections, "items": items, "rows": rows, "results": results,
            "interior": None if measured is None else {k: measured[k] for k in ("parts", "problems", "not_checked")},
            "interior_sha256": fingerprint(interior)}


def fingerprint(interior) -> str | None:
    """sha256 of the interior description checked (its JSON, keys sorted), so a result says exactly which interior
    it was worked out from; None when none was given."""
    if interior is None:
        return None
    text = json.dumps(interior, sort_keys=True, ensure_ascii=True, default=str, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    got = each_part.check_parts(law["rules"], measured["parts"], values, allowed)
    rows += got["rows"]
    for key, answer in got["results"].items():   # one rule id in two laws: the more cautious answer, never kinder
        results[key] = part_rules.rule_result([{"outcome": answer}] + ([{"outcome": results[key]}]
                                                                       if key in results else []))
    by_id = {r["id"]: r for r in law["rules"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    out = [_decorated(i, law, by_id.get(i["rule"])) for i in got["items"]]
    out += [_own_item(law, f"{law['short'].lower()}.interior#{n}", "Interior drawing", present.REVIEW,
                      INTERIOR_PROBLEM.format(why=why)) for n, why in enumerate(measured["problems"], 1)]
    if not out:          # every row not applicable (left out of the panel): never a law that vanishes from the answer
        out.append(_own_item(law, f"{law['short'].lower()}.nothing_applied", f"{law['short']}: nothing checked",
                             present.REVIEW, NOTHING_APPLIED.format(title=law["title"])))
    return out


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


def _waiting_item(law: dict) -> dict:
    return _own_item(law, f"{law['short'].lower()}.waiting", f"{law['short']}: {WAITING_WORDS}", present.NOT_CHECKED,
                     WAITING_WHY, waiting=WAITING_WORDS)


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
    view["groups"] = present.grouped(view["items"])
    view["sections"] = [{"key": "zoning", "title": f"Zoning ({place_name})", "state": present.state(zoning),
                         "summary": present._summary(zoning)}] + [
        {k: s[k] for k in ("key", "title", "state", "summary")} for s in got["sections"]]
