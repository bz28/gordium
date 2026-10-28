"""How the measuring code follows what research settled and what is still open, read from the city's own files
(definitions, rules and section labels), never typed into the code. Plain code, no AI.

The measuring code knows how to measure each reading of a question (an engineer writes each one, principle 6);
which readings are still in play is data:

- an **open question** (`open_questions` + its `research`, with `readings` by id): every reading the research
  lists is measured, and the checker says complies only if all of them pass (check.every_reading);
- an **answer** from the architects or the City (`answers`, with `reading: <id>`) outranks everything: only the
  reading it picks is measured, and it says who answered;
- a **finding** (`findings`): kind `law` is the code's own words, applied as the law; kind `reading` is
  Gordium's reading, applied and shown as "Gordium's reading · confirm with …". Its `still_open` tags name the
  parts of its question that are still open: those are measured under every reading.

The code names a question by its entry and the ids of the readings it can measure, so a question renumbered in
the data is still found, and a question the data no longer lists (answered without saying which reading, or
removed) stops the measurement (needs review), never a guess.
"""

import functools
from rule_format.rulebook import REPO, open_question_tags, research_entries

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"     # the one city measured so far


@functools.lru_cache(maxsize=8)
def _law(jurisdiction: str) -> tuple:
    entries = research_entries(REPO / jurisdiction)
    by_id = {}
    for where, e in entries:
        by_id.setdefault(where.rsplit(" ", 1)[-1], []).append(e)
    return by_id, open_question_tags(entries)


def _jurisdiction(facts: dict) -> str:
    return facts.get("jurisdiction") or ITHACA


def _answers(by_id: dict, entry: str) -> list[dict]:
    return [a for e in by_id.get(entry, []) for a in e.get("answers") or [] if isinstance(a, dict)]


def _who(a: dict) -> str:
    return f"answered by {a.get('answered_by')}, {a.get('answered_on')}"


def question(facts: dict, entry: str, ids: tuple[str, ...]) -> dict:
    """The state of the open question in `entry` whose readings are `ids` (the readings the code measures):
    {"tag", "state": "open" | "answered" | "missing", "readings": the ids to measure, "by": who answered}.
    An answer comes first: one that picks a reading the code measures decides it; one on this question that
    picks anything else (or no reading) replaces every reading, and the code can't follow it: missing."""
    by_id, tags = _law(_jurisdiction(facts))
    mine = [(tag, q, tuple(r.get("id") for r in research.get("readings") or []))
            for tag, (where, q, research) in tags.items() if where.rsplit(" ", 1)[-1] == entry]
    asked = {q for _tag, q, listed in mine if set(listed) == set(ids)}
    for a in _answers(by_id, entry):
        if a.get("reading") in ids:
            return {"tag": f"{entry}:answered", "state": "answered", "readings": (a["reading"],), "by": _who(a)}
        if a.get("question") in asked:
            return {"tag": None, "state": "missing", "readings": (), "by": _who(a)}
    for tag, _q, listed in mine:
        if set(listed) == set(ids):
            return {"tag": tag, "state": "open", "readings": listed, "by": None}
    return {"tag": None, "state": "missing", "readings": (), "by": None}


def finding(facts: dict, entry: str, finding_id: str) -> dict | None:
    """A finding the measuring applies: {"id", "entry", "kind" (law | reading | answer), "confirm_with",
    "still_open", "answer", "text" (how it is shown)}, or None when the data no longer has it. An answer outranks
    it and replaces it: one that picks the finding (`reading: <finding id>`) is shown as answered; one to the
    finding's question that picks anything else gives None (the measuring stops: Gordium's reading is never
    applied or shown against an answer)."""
    by_id, _ = _law(_jurisdiction(facts))
    found = next((f for e in by_id.get(entry, []) for f in e.get("findings") or []
                  if isinstance(f, dict) and f.get("id") == finding_id), None)
    for a in _answers(by_id, entry):
        if a.get("reading") == finding_id and found is not None and a.get("question") == found.get("question"):
            return {"id": finding_id, "entry": entry, "kind": "answer", "confirm_with": None, "still_open": [],
                    "answer": a.get("answer"), "text": f"{a.get('answer')} ({_who(a)})"}
        if found is not None and a.get("question") == found.get("question"):
            return None
    if found is None:
        return None
    kind = found.get("kind")
    text = (f"the law: {found.get('answer')}" if kind == "law" else
            f"Gordium's reading · confirm with {found.get('confirm_with')}: {found.get('answer')}")
    return {"id": finding_id, "entry": entry, "kind": kind, "confirm_with": found.get("confirm_with"),
            "still_open": list(found.get("still_open") or []), "answer": found.get("answer"), "text": text}


def basis(found: dict | None) -> dict | None:
    """A finding as a measurement record carries it (its `basis`): what was applied and how it is shown."""
    if found is None:
        return None
    return {k: found[k] for k in ("id", "entry", "kind", "confirm_with", "text")}


def clear_cache() -> None:
    """Forget the files read (a test that changes them)."""
    _law.cache_clear()
