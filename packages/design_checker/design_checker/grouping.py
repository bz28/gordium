"""How a law's results are grouped for reading: the panel (present.grouped, present.summary) and the permit sheets
(packages/permit_sheets) group them the same way, from here. Presentation only: every item keeps its own status,
every item is in exactly one line, and the design's state (present.state) is never read or changed here.
Design and the architect's-eye review: docs/decisions/2026-11-16_results_grouping.md.

    got = lines(items)           # {tier: [line, …]} for one law's items, every item in exactly one line
    summary(items)      # "1 does not comply · 2 to review · 9 comply · 13 parts not read yet · 86 sections not checked yet"

The tiers, in the order they are shown:

1. **fails**: one line per part ("Bedroom 3 › Window 5: 1 does not comply (net clear area 5.12 sq ft, needs ≥ 5.7 sq
   ft)"), every failing rule in it. Never folded.
2. **review**: needs review the architect can act on: a decision (a rule a person judges), a value missing that the
   drawing can give, or one whose check fails on what was measured ("may not comply"), one line per part. Anything
   not plainly Gordium's own gap is here (an unknown status too): a line that is shown, never a fold.
3. **by_hand**: needs review only because Gordium can't read that part yet, one line per cause: the part kinds not
   read at all ("Not read from the model yet: handrails (13 rules), guards (7 rules): check by hand"), the details of
   parts it measures but not yet those (area wells…), and the sections it has no rules for yet. Each item keeps its
   needs-review status and is listed under its line.
4. **complies**: complies, and not applicable (the description says the house has none), one line per part, folded.
   Its heading names what it holds (tier_title): "Complies", "Not applicable", or "Complies or not applicable", so a
   not-applicable row is never under a heading, or in a count, that reads as a pass.
"""

import hashlib

from design_checker import present

FAILS_T, REVIEW_T, BY_HAND_T, COMPLIES_T, WAITING_T = "fails", "review", "by_hand", "complies", "waiting"
TIERS = [FAILS_T, REVIEW_T, BY_HAND_T, COMPLIES_T]
TITLES = {FAILS_T: "Does not comply", REVIEW_T: "Needs review", BY_HAND_T: "Check by hand: not read by Gordium yet",
          COMPLIES_T: "Complies"}
FOLDED = {COMPLIES_T}                    # shown folded; every other tier open
NOT_APPLICABLE = "not_applicable"        # an absent part's rows (the description says the house has none): folded
# the complies tier's heading by what it holds (tier_title): a not-applicable row is never under "Complies" alone
NOT_APPLICABLE_T, BOTH_T = "Not applicable", "Complies or not applicable"
NOT_READ, NOT_MEASURED, SECTIONS = "not_read", "not_measured", "sections"      # each_part.unsettled, egress
# plain names for a part kind, as an architect says them (wording only; any other kind: its own words)
KIND_WORDS = {"sleeping_room": ("bedroom", "bedrooms"), "emergency_escape_opening": ("escape window", "escape windows"),
              "stair": ("stair", "stairs"), "egress_door": ("exit door", "exit doors"),
              "handrail": ("handrail", "handrails"), "open_side": ("guard (open side)", "guards (open sides)"),
              "sleeping_loft": ("sleeping loft", "sleeping lofts"), "exterior_door": ("exterior door", "exterior doors"),
              "ramp": ("ramp", "ramps"), "alternating_tread_device": ("alternating tread device",
                                                                        "alternating tread devices"),
              "ships_ladder": ("ship's ladder", "ship's ladders"), "basement": ("basement", "basements"),
              "habitable_attic": ("habitable attic", "habitable attics"),
              "loft_room": ("room a loft opens to", "rooms a loft opens to")}
NOT_READ_TITLE = "Not read from the model yet: {causes}: check by hand"
NOT_MEASURED_TITLE = "Not measured from the model yet: {causes}: check by hand"
SECTIONS_TITLE = "Not checked yet by Gordium: {n} code section{s}: check by hand"
SECTIONS_UNKNOWN = "Not checked yet by Gordium: can't tell which code sections: check the whole law by hand"
MORE = 2                                  # a line names this many causes of a kind, then "and N more"


def tier_title(t: str, statuses) -> str:
    """A tier's heading, from the statuses of the items in it: the complies tier says "Not applicable" when nothing in
    it complies and "Complies or not applicable" when it holds both, so its heading (and the count beside it, every
    item in it) never reads as a pass for a rule the description set aside. Any other tier: its own title."""
    if t != COMPLIES_T:
        return TITLES[t]
    got = set(statuses)
    if NOT_APPLICABLE not in got:
        return TITLES[t]
    return BOTH_T if present.COMPLIES in got else NOT_APPLICABLE_T


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def kind_words(kind, n: int = 2) -> str:
    one, many = KIND_WORDS.get(kind) or ((str(kind).replace("_", " "),) * 2 if kind else ("part", "parts"))
    if kind and kind not in KIND_WORDS:
        many = one + "s"
    return one if n == 1 else many


def tier(item: dict) -> str:
    """Which tier an item is shown in. Only a needs-review item whose `open` says it is Gordium's own gap goes to
    by_hand; a fail is always fails; anything unknown is review (shown, never folded)."""
    st = item.get("status")
    if st == present.FAILS:
        return FAILS_T
    if item.get("waiting"):
        return WAITING_T
    if st in (present.COMPLIES, NOT_APPLICABLE):
        return COMPLIES_T
    gap = (item.get("open") or {}).get("gordium")
    if st == present.REVIEW and gap in (NOT_READ, NOT_MEASURED, SECTIONS):
        return BY_HAND_T
    return REVIEW_T


def _element_key(item: dict) -> tuple:
    p = item.get("part")
    if isinstance(p, dict):
        within = p.get("within") if isinstance(p.get("within"), dict) else {}
        # one line per thing the architect drew: a window read as an escape window and as an opening is one line
        if item.get("element"):
            return ("element", item["element"])      # its full name, room and all ("Bedroom 3 › Window 5")
        return ("part", p.get("part"), p.get("id"), within.get("id"))
    return ("item", item.get("id"))


def _line_key(item: dict, t: str) -> tuple:
    if t == BY_HAND_T:
        gap = item["open"]["gordium"]
        return (gap,) if gap in (NOT_READ, NOT_MEASURED) else ("item", item.get("id"))
    return _element_key(item)


def _short(item: dict) -> str:
    """The item's reason without its part's name in front ("net clear area 5.12 sq ft, needs ≥ 5.7 sq ft")."""
    reason = (item.get("reason") or "").strip()
    head = (item.get("element") or "") + ": "
    return reason[len(head):] if item.get("element") and reason.startswith(head) else reason


def _title_of_rule(item: dict) -> str:
    name, head = item.get("name") or "", (item.get("element") or "") + " · "
    return name[len(head):] if item.get("element") and name.startswith(head) else name


def _some(words: list[str]) -> str:
    words = list(dict.fromkeys(w for w in words if w))
    return ", ".join(words[:MORE]) + (f" and {len(words) - MORE} more" if len(words) > MORE else "")


def _own_title(item: dict) -> str:
    """A line of one item that is no part's (the interior drawing's problem, rules refused…): its own words."""
    name, reason = item.get("name") or item.get("id") or "", (item.get("reason") or "").strip()
    if not reason:
        return name
    if reason.lower().startswith((name.lower(), "the " + name.lower())):
        return reason                                 # "The interior drawing: …", never "Interior drawing: The interior…"
    # the reason opening with the name's own last words ("Ramps: not applicable" and "Not applicable: the description
    # says…"): said once ("Ramps: not applicable: the description says…"), never "not applicable: Not applicable"
    tail = name.rsplit(": ", 1)[-1].strip() if ": " in name else ""
    if tail and reason.lower().startswith(tail.lower() + ": "):
        reason = reason[len(tail) + 2:].lstrip()
    return f"{name}: {reason}"


def _section(item: dict) -> str:
    return ((item.get("code") or {}).get("section") or "").strip()


def _fails_title(mine: list[dict]) -> str:
    """"Bedroom 3 › Window 5: 1 does not comply (net clear area 5.12 sq ft, needs ≥ 5.7 sq ft: R319.2.1)": every
    failing rule's reason, each with its code section (two rules failing for one reason: both sections)."""
    if mine[0].get("element") is None:
        return "; ".join(_own_title(i) for i in mine)
    why = {}
    for i in mine:
        why.setdefault(_short(i), []).append(_section(i))
    said = [w + (f": {', '.join(dict.fromkeys(s for s in secs if s))}" if any(secs) else "") for w, secs in why.items()]
    return f"{mine[0]['element']}: {_plural(len(mine), 'does not comply', 'do not comply')} (" + "; ".join(said) + ")"


def _review_title(mine: list[dict]) -> str:
    if mine[0].get("element") is None:
        return "; ".join(_own_title(i) for i in mine)
    opens = [i.get("open") or {} for i in mine]
    said = []
    concerns = [o["concern"] for o in opens if o.get("concern")]
    if concerns:
        said.append("may not comply: " + "; ".join(dict.fromkeys(concerns)))
    decide = [_title_of_rule(i) for i, o in zip(mine, opens) if o.get("decide")]
    if decide:
        said.append("a person decides: " + ", ".join(dict.fromkeys(decide)))   # never shortened: each to decide
    notes = [w for o in opens for w in o.get("notes") or []]
    if notes:                                          # the row's own reason ("no egress doors"), as it is
        said.append(", ".join(dict.fromkeys(notes)))  # never shortened: what the architect has to act on
    inputs = [w for o in opens for w in o.get("inputs") or []]
    if inputs:
        said.append("to give: " + ", ".join(dict.fromkeys(inputs)))   # never shortened: each one to supply
    worked = [w for o in opens for w in o.get("worked") or []]
    if worked:
        said.append("worked out, not yet checked by the rules: " + _some(worked))
    gaps = [w for o in opens for w in o.get("gaps") or []]
    if gaps:
        said.append("not read yet: " + _some(gaps))
    if not said:                                       # an item with no `open` (not a part's row): its own words
        said.append(_some([_short(i) for i in mine]))
    return f"{mine[0]['element']}: {_plural(len(mine), 'needs review', 'need review')}: " + " · ".join(said)


def _complies_title(mine: list[dict]) -> str:
    if mine[0].get("element") is None:
        return "; ".join(_own_title(i) for i in mine)
    ok = sum(1 for i in mine if i["status"] == present.COMPLIES)
    na = len(mine) - ok
    words = [w for w in (_plural(ok, "complies", "comply") if ok else "",
                         _plural(na, "doesn't apply", "don't apply") if na else "") if w]
    return f"{mine[0]['element']}: " + " · ".join(words)


def _causes(mine: list[dict], gap: str) -> list[dict]:
    """The by-hand line's causes, in order: each part kind (or kinds) not read or not measured yet, its rules and
    its items."""
    out, at = [], {}
    for i in mine:
        o = i["open"]
        key = tuple(o.get("kinds") or []) if gap == NOT_READ else (o.get("kind"),)
        if key not in at:
            at[key] = {"kinds": list(key), "items": [], "measures": []}
            out.append(at[key])
        at[key]["items"].append(i)
        at[key]["measures"] += o.get("measures") or []
    return out


def _cause_parts(c: dict, gap: str) -> tuple[str, str]:
    """(what isn't read: "handrails", "escape window details: fully openable, path height and 20 more"; how many
    rules: "10 rules", "17 rules on 4 escape windows")."""
    rules = len({i.get("rule") or i.get("id") for i in c["items"]})
    if gap == NOT_READ:
        return " and ".join(kind_words(k) for k in c["kinds"]) or "parts", _plural(rules, "rule", "rules")
    parts = len({_element_key(i) for i in c["items"]})
    kind = c["kinds"][0] if c["kinds"] else None
    on = f" on {parts} {kind_words(kind, parts)}" if parts > 1 else f" on {c['items'][0].get('element')}" \
        if c["items"][0].get("element") else ""
    return f"{kind_words(kind, 1)} details: {_some(c['measures'])}", _plural(rules, "rule", "rules") + on


def _cause_words(c: dict, gap: str) -> str:
    what, rules = _cause_parts(c, gap)
    return f"{what} ({rules})"


def _sections_title(item: dict) -> str:
    sections = (item.get("open") or {}).get("sections")
    if not sections:
        return SECTIONS_UNKNOWN
    return SECTIONS_TITLE.format(n=len(sections), s="" if len(sections) == 1 else "s")


def lines(items: list[dict]) -> dict:
    """{tier: [line]} for one law's items (a law all waiting is shown as it is by the caller, present.grouped). A line:
    {key, tier, title, status (the most cautious of its items), mark, items: [ids], causes?: [{words, items}]}.
    Every item is in exactly one line; the lines keep the items' order within a tier."""
    got, at = {t: [] for t in TIERS}, {}
    for i in items:
        t = tier(i)
        if t == WAITING_T:          # a law all waiting is shown as it always was (present.grouped); one waiting
            t = REVIEW_T            # item among others is shown with what is to review, never dropped
        key = (t,) + _line_key(i, t)
        if key not in at:
            at[key] = []
            got[t].append((key, at[key]))
        at[key].append(i)
    # the parts that may not comply (a check that fails on what was measured) first among those to review; Gordium's
    # gaps in a fixed order: the parts not read at all, then the details not measured, then the sections
    got[REVIEW_T].sort(key=lambda km: not any((i.get("open") or {}).get("concern") for i in km[1]))
    got[BY_HAND_T].sort(key=lambda km: {NOT_READ: 0, NOT_MEASURED: 1}.get(km[0][1], 2))
    out = {}
    for t in TIERS:
        out[t] = []
        for key, mine in got[t]:
            # the key names the part or cause, not the position, so a line the architect opened stays open on the
            # same part after an edit reorders the lines; a part's failures are shown open, never folded
            line = {"key": f"{t}#" + hashlib.sha1(repr(key).encode()).hexdigest()[:10], "tier": t,
                    "items": [i["id"] for i in mine], "folded": t != FAILS_T,
                    "status": min((i["status"] for i in mine), key=_caution), "rules": len(mine)}
            if t == FAILS_T:
                line["title"] = _fails_title(mine)
            elif t == REVIEW_T:
                line["title"] = _review_title(mine)
            elif t == COMPLIES_T:
                line["title"] = _complies_title(mine)
            elif key[1] in (NOT_READ, NOT_MEASURED):
                causes = _causes(mine, key[1])
                line["causes"] = [{"words": _cause_words(c, key[1]), "what": _cause_parts(c, key[1])[0],
                                   "rules": _cause_parts(c, key[1])[1], "items": [i["id"] for i in c["items"]]}
                                  for c in causes]
                line["title"] = (NOT_READ_TITLE if key[1] == NOT_READ else NOT_MEASURED_TITLE).format(
                    causes=", ".join(c["words"] for c in line["causes"]))
                # its items in cause order, so the line's list reads cause by cause
                line["items"] = [x for c in line["causes"] for x in c["items"]]
            else:
                line["title"] = _sections_title(mine[0]) if (mine[0].get("open") or {}).get("gordium") == SECTIONS \
                    else _own_title(mine[0])
            line["mark"] = present.MARK.get(line["status"], present.MARK[present.REVIEW])
            # its name alone, without its result: what the panel shows while its results are out of date
            line["name"] = line["title"].split(": ")[0] if t == BY_HAND_T \
                else (mine[0].get("element") or mine[0].get("name") or line["title"])
            out[t].append(line)
    return out


CAUTION = [present.FAILS, present.REVIEW, present.NOT_CHECKED, present.COMPLIES, NOT_APPLICABLE]


def _caution(status) -> int:
    """How cautious a status is (a fail first); one this module doesn't know counts as needs review, never kinder."""
    return CAUTION.index(status) if status in CAUTION else CAUTION.index(present.REVIEW)


def counts(items: list[dict]) -> dict:
    """What the headline counts, as an architect counts them: the rules that fail (each its own fix), the lines to
    review (one per part, or per item that is no part's), the rules that comply, the causes Gordium can't read yet
    (each part kind, or kind's details), and the code sections not checked yet (None: can't tell which)."""
    got = lines(items)
    by_hand = [ln for ln in got[BY_HAND_T] if ln.get("causes") is not None]
    sections = [ln for ln in got[BY_HAND_T] if ln.get("causes") is None]
    by_id = {i["id"]: i for i in items}
    n_sections, unknown = 0, False
    for ln in sections:
        s = (by_id[ln["items"][0]].get("open") or {}).get("sections")
        if (by_id[ln["items"][0]].get("open") or {}).get("gordium") == SECTIONS and s:
            n_sections += len(s)
        else:
            unknown = True
    return {"fails": sum(1 for i in items if i.get("status") == present.FAILS),
            "review": len(got[REVIEW_T]),
            "complies": sum(1 for i in items if i.get("status") == present.COMPLIES),
            "not_applicable": sum(1 for i in items if i.get("status") == NOT_APPLICABLE),
            "not_read": sum(len(ln["causes"]) for ln in by_hand),
            "sections": n_sections, "sections_unknown": unknown}


def summary(items: list[dict]) -> str:
    """A law's one line, counting what an architect counts (counts()): "1 does not comply · 2 to review · 9 comply ·
    13 parts not read yet · 86 sections not checked yet". No zero counts, never a check mark; when the law needs review
    with nothing failing and nothing to review (only what Gordium can't read yet), it says "needs review" first,
    so the line never reads as a pass (present._summary's rule). Nothing at all: "nothing checked"."""
    c = counts(items)
    parts = []
    if c["fails"]:
        parts.append(_plural(c["fails"], "does not comply", "do not comply"))
    if c["review"]:
        parts.append(f"{c['review']} to review")
    if c["complies"]:
        parts.append(_plural(c["complies"], "complies", "comply"))
    if c["not_read"]:
        parts.append(_plural(c["not_read"], "part", "parts") + " not read yet")
    if c["sections"]:
        parts.append(_plural(c["sections"], "section", "sections") + " not checked yet")
    if c["sections_unknown"]:
        parts.append("sections not checked yet: can't tell which")
    if parts and present.state(items) != present.COMPLIES and not c["fails"] and not c["review"]:
        parts.insert(0, present.WORDS[present.REVIEW][0])
    return " · ".join(parts) or "nothing checked"


CARD_ORDER = {"fix_model": 0, "mark": 1, "measure_by_hand": 2, "decide": 3}   # what the architect can change first


def cause_cards(items: list[dict]) -> list[dict]:
    """The "Fix these first" cards (docs/revit/ui_design_pass.md section 2.3): the needs-review items grouped by their
    first cause (panel_data's `causes`, the one to act on first), each card {key, kind, words, elements, items,
    rules, field?, fields?}: one job however many rows it clears. Words and ids only: every item keeps its status, every item with a
    cause is on exactly one card, an item with none on none. Cards in the order the architect can act on them (the
    model and its marks first, then what is measured by hand, then what a person decides), then by how many rows each
    clears, then as first met."""
    cards, at = [], {}
    for i in items:
        cs = i.get("causes") if i.get("status") == present.REVIEW else None
        if not cs or not isinstance(cs[0], dict) or not cs[0].get("key"):
            continue
        c = cs[0]
        if c["key"] not in at:
            at[c["key"]] = {"key": c["key"], "kind": c.get("kind"), "words": c.get("words"), "elements": [],
                            "items": [], "rules": 0}
            if c.get("rooms"):
                at[c["key"]]["rooms"] = list(c["rooms"])
            for k in ("field", "fields"):          # the description field a mark needs (panel_data's note)
                if c.get(k):
                    at[c["key"]][k] = list(c[k]) if isinstance(c[k], list) else c[k]
            cards.append(at[c["key"]])
        card = at[c["key"]]
        card["items"].append(i["id"])
        card["elements"] += [e for e in c.get("elements") or [] if e not in card["elements"]]
    cards = _rooms_together(cards)
    for card in cards:
        card["rules"] = len({next((i.get("rule") or i["id"] for i in items if i["id"] == x), x) for x in card["items"]})
    order = {c["key"]: n for n, c in enumerate(cards)}
    return sorted(cards, key=lambda c: (CARD_ORDER.get(c["kind"], len(CARD_ORDER)), -len(c["items"]), order[c["key"]]))


def _rooms_together(cards: list[dict]) -> list[dict]:
    """The rooms cards (key "rooms:…": rooms the measuring couldn't route) that share a room made one card: the 5
    rooms with no route are one job, whether a row stops at them for the story's travel, its room-door travel or a
    room's own common path. The card is keyed by every room it names (sorted) and names them as its elements; its
    words are made again from every room it names (panel_data._rooms_cause), or, when a joined card doesn't list
    its rooms, are the first joined card's words. Any other card is left as it is, in its place."""
    rooms = [c for c in cards if str(c["key"]).startswith("rooms:")]
    merged = []
    for c in rooms:
        into = [m for m in merged if set(m["elements"]) & set(c["elements"])]
        for m in into[1:]:                       # two groups this card joins: one
            into[0]["parts"] += m["parts"]
            into[0]["elements"] = sorted(set(into[0]["elements"]) | set(m["elements"]))
            merged.remove(m)
        if into:
            into[0]["parts"].append(c)
            into[0]["elements"] = sorted(set(into[0]["elements"]) | set(c["elements"]))
        else:
            merged.append({"parts": [c], "elements": sorted(c["elements"])})
    from design_checker import panel_data
    first = {}
    for m in merged:
        found = {r["id"]: r for c in m["parts"] for r in c.get("rooms") or []
                 if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]}
        items = [x for c in m["parts"] for x in c["items"]]
        card = {"key": "rooms:" + ",".join(m["elements"]), "kind": m["parts"][0]["kind"],
                "words": m["parts"][0]["words"], "elements": m["elements"], "items": list(dict.fromkeys(items)),
                "rules": 0}
        if set(found) == set(m["elements"]):     # its words from every room it names, as each row's are made
            card["words"] = panel_data._rooms_cause(found)["words"]
            card["rooms"] = [found[r] for r in m["elements"]]
        first[id(m["parts"][0])] = card
    out, gone = [], {id(c) for m in merged for c in m["parts"]}
    for c in cards:
        if id(c) in first:
            out.append(first[id(c)])
        elif id(c) not in gone:
            out.append(c)
    return out
