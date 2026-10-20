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


def question(facts: dict, entry: str, ids: tuple[str, ...]) -> dict:
    """The state of the open question in `entry` whose readings are `ids` (the readings the code measures):
    {"tag", "state": "open" | "answered" | "missing", "readings": the ids to measure, "by": who answered}."""
    by_id, tags = _law(_jurisdiction(facts))
    for tag, (where, _q, research) in tags.items():
        if where.rsplit(" ", 1)[-1] != entry:
            continue
        listed = tuple(r.get("id") for r in research.get("readings") or [])
        if set(listed) == set(ids):
            return {"tag": tag, "state": "open", "readings": listed, "by": None}
    for e in by_id.get(entry, []):
        for a in e.get("answers") or []:
            if isinstance(a, dict) and a.get("reading") in ids:
                return {"tag": f"{entry}:answered", "state": "answered", "readings": (a["reading"],),
                        "by": f"answered by {a.get('answered_by')}, {a.get('answered_on')}"}
    return {"tag": None, "state": "missing", "readings": (), "by": None}


def finding(facts: dict, entry: str, finding_id: str) -> dict | None:
    """A finding the measuring applies: {"id", "entry", "kind" (law | reading | answer), "confirm_with",
    "still_open", "answer", "text" (how it is shown)}, or None when the data no longer has it. An answer that
    picks the finding (`reading: <finding id>`) outranks it: shown as answered."""
    by_id, _ = _law(_jurisdiction(facts))
    for e in by_id.get(entry, []):
        for a in e.get("answers") or []:
            if isinstance(a, dict) and a.get("reading") == finding_id:
                return {"id": finding_id, "entry": entry, "kind": "answer", "confirm_with": None, "still_open": [],
                        "answer": a.get("answer"),
                        "text": f"{a.get('answer')} (answered by {a.get('answered_by')}, {a.get('answered_on')})"}
        for f in e.get("findings") or []:
            if isinstance(f, dict) and f.get("id") == finding_id:
                kind = f.get("kind")
                text = (f"the law: {f.get('answer')}" if kind == "law" else
                        f"Gordium's reading · confirm with {f.get('confirm_with')}: {f.get('answer')}")
                return {"id": finding_id, "entry": entry, "kind": kind, "confirm_with": f.get("confirm_with"),
                        "still_open": list(f.get("still_open") or []), "answer": f.get("answer"), "text": text}
    return None


def basis(found: dict | None) -> dict | None:
    """A finding as a measurement record carries it (its `basis`): what was applied and how it is shown."""
    if found is None:
        return None
    return {k: found[k] for k in ("id", "entry", "kind", "confirm_with", "text")}


def clear_cache() -> None:
    """Forget the files read (a test that changes them)."""
    _law.cache_clear()
