"""What the sheets print, gathered from the check and proven to be the check's, or refused. Plain code, no AI.

    got = gather(result, about, interior)       # Refused (a ValueError) when anything doesn't add up

The sheets are a print-out of the check, never a second check (docs/permit_sheets/plan.md):
- every result is the check's own item status; an item about a part is paired with the check's raw row for it and
  the two must agree, and each law's counts must equal its section's own summary;
- the interior description must be the one the check worked from (its sha256), so geometry and results never mix
  two drawings;
- the rulebook must be the one the check used: the rules fingerprint the worker gave with the answer (`about`) must
  be today's, and every rule id and quote must be in the rulebook loaded now.
"""

import hashlib
from pathlib import Path

from design_checker import egress, each_part, present
from design_checker.protocol import rulebook_fingerprints, worker_fingerprint
from rule_format.place import places
from rule_format.rulebook import REPO, building_code_rulebook, load

from .words import Refused, result_words, worst

STATUS = each_part.STATUS                       # a raw row's outcome → the item status it must have


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _quote(rule: dict) -> str:
    first = next((s for s in rule.get("sources") or [] if isinstance(s, dict)), {})
    return " ".join(str(first.get("quote", "")).split())


def fingerprints_now() -> dict:
    """The worker's rules fingerprint for every place, read now (protocol.rulebook_fingerprints: what `hello` and
    every new-style answer's `about.rulebook` carry)."""
    return rulebook_fingerprints()


def _law(key: str, about_rulebook: dict) -> dict:
    """A law's rulebook, as loaded now, with what proves it is the check's: its file's sha256 and the fingerprint of
    every place that inherits it."""
    folder = REPO / "regulations/jurisdictions" / key
    book = building_code_rulebook(folder)
    if book is None:
        raise Refused(f"no rulebook for {key}: the sheets can't say what the check was checked against")
    rules = {r["id"]: r for r in load(book)["rules"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    under = sorted(p.key for p in places() if folder.resolve() in [f.resolve() for f in p.inherits])
    return {"key": key, "rulebook": book.relative_to(REPO).as_posix(), "rulebook_sha256": _sha_file(book),
            "rules": rules, "fingerprints": {k: about_rulebook.get(k) for k in under}}


def check_rules_unchanged(about: dict | None) -> dict:
    """The rules fingerprint the check came with, proven equal to today's (else Refused). A result with no `about`
    can't say which rules decided it, so it is refused."""
    said = (about or {}).get("rulebook")
    if not isinstance(said, dict) or not said:
        raise Refused("the check result doesn't say which rules it used (no about.rulebook): let the command run "
                      "the check itself")
    now = fingerprints_now()
    changed = sorted(k for k in set(said) | set(now) if said.get(k) != now.get(k))
    if changed:
        raise Refused(f"the rules changed since this check ({', '.join(changed)}): check again, then make the sheets")
    return said


def checked(run, interior) -> dict:
    """Run the check (`run()`: check_site or check_description with this `interior`) and gather what the sheets
    print from its answer, with the rules fingerprint read before and after it: if the rules changed while the check
    ran, nothing is printed. The one way in, for the command and the goldens alike: a check result handed in from
    elsewhere can't say which rules decided it."""
    before = (fingerprints_now(), worker_fingerprint())
    result = run()
    got = gather(result, {"rulebook": before[0], "worker_fingerprint": before[1]}, interior)
    # read again once the sheets have loaded the rules they print from (gather): nothing changed since the check began
    if (fingerprints_now(), worker_fingerprint()) != before:
        raise Refused("the rules or Gordium's code changed while the check ran: check again")
    return got


def _key(row_or_part: dict) -> tuple:
    within = row_or_part.get("within") or {}
    return (row_or_part.get("rule"), row_or_part.get("part"), row_or_part.get("id"),
            within.get("id") if isinstance(within, dict) else within)


def gather(result: dict, about: dict | None, interior) -> dict:
    """Everything the three sheets print, each value with where in the check it came from."""
    if not isinstance(result, dict) or not isinstance(result.get("egress"), dict) or "view" not in result:
        raise Refused("not a check result (it has no `egress` and `view`): give check_site's result")
    said = check_rules_unchanged(about)
    eg = result["egress"]
    if egress.fingerprint(interior) != eg.get("interior_sha256"):
        raise Refused("this interior description isn't the one the check worked from (its sha256 differs): give the "
                      "same house file, or check again")
    items = [i for i in result["view"]["items"] if i.get("group") == present.LAW_GROUP]
    sections = [s for s in result.get("sections") or [] if s.get("key") != "zoning"]
    if not sections:
        raise Refused("the check result has no egress section")
    laws = {s["key"]: {**_law(s["key"], said), "title": s["title"], "state": s["state"], "summary": s["summary"],
                       "items": []} for s in sections}

    # every row the panel shows (not "not applicable") pairs with one item about the same rule and part, in order
    queue: dict = {}
    for row in eg.get("rows") or []:
        if row.get("outcome") in STATUS:
            queue.setdefault(_key(row), []).append(row)
    for n, item in enumerate(items, 1):
        law = laws.get(item.get("law_key"))
        if law is None:
            raise Refused(f"item {item.get('id')} names a law with no section ({item.get('law_key')})")
        waiting = item.get("waiting")
        words = result_words(item["status"], waiting)            # refuses a status it doesn't know
        row = None
        if item.get("part") is not None:
            got = queue.get(_key({**item["part"], "rule": item.get("rule")}))
            if not got:
                raise Refused(f"item {item['id']} is about a part the check gave no row for: the result isn't whole")
            row = got.pop(0)
            if STATUS[row["outcome"]] != item["status"]:
                raise Refused(f"item {item['id']} says {item['status']} but its row says {row['outcome']}: the result "
                              "contradicts itself")
        rule = law["rules"].get(item.get("rule")) if item.get("rule") else None
        if item.get("rule") and rule is None and not str(item["rule"]).startswith("rule #"):
            raise Refused(f"rule {item['rule']} isn't in {law['rulebook']}: the rules changed since this check")
        code = item.get("code") or {}
        if rule is not None and code.get("quote") and code["quote"] != _quote(rule):
            raise Refused(f"rule {item['rule']}'s words in {law['rulebook']} aren't the ones the check quoted: the "
                          "rules changed since this check")
        law["items"].append({"n": n, "item": item, "row": row, "rule": rule, "result": words,
                             "status": item["status"], "waiting": waiting})
    left = [r for rows in queue.values() for r in rows]
    if left:
        raise Refused(f"{len(left)} row(s) of the check aren't on its panel (first: {left[0].get('line')}): the "
                      "result isn't whole")
    for law in laws.values():
        mine = [x["item"] for x in law["items"]]
        if law["state"] == egress.WAITING:
            if not mine or not all(i.get("waiting") for i in mine):
                raise Refused(f"{law['title']} says it is waiting but has items that aren't")
        else:
            if present._law_summary(mine) != law["summary"]:
                raise Refused(f"{law['title']}'s items count {present._law_summary(mine)!r}, its section says "
                              f"{law['summary']!r}: the result isn't whole")
            if worst([law["state"], present.state(mine)]) != law["state"]:
                raise Refused(f"{law['title']}'s section says {law['state']} but its items are worse")
    return {"laws": list(laws.values()), "waiting": bool(eg.get("interior") is None),
            "interior_sha256": eg.get("interior_sha256"), "measured": eg.get("interior"), "interior": interior,
            "fingerprints": said, "worker_fingerprint": (about or {}).get("worker_fingerprint")}


def overall(got: dict) -> tuple[str, str | None]:
    """(the sheets' one headline status, its waiting words): the most cautious of every law's own state, never
    kinder than any item."""
    states, waits = [], None
    for law in got["laws"]:
        if law["state"] == egress.WAITING:
            states.append(present.NOT_CHECKED)
            waits = waits or next((x["waiting"] for x in law["items"] if x["waiting"]), None)
        else:
            states.append(law["state"])
        states += [x["status"] for x in law["items"]]
    s = worst(states)
    return s, (waits if s == present.NOT_CHECKED else None)
