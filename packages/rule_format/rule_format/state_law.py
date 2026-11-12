"""A state's own law folder (regulations/jurisdictions/<state>/<name>/, with a state.yaml): its settings, and the
record of the second reading of its numbers (text_verification.yaml). Decided 2026-11-12:
docs/decisions/2026-11-12_building_code_text.md.

text_verification.yaml: a book's extracted text could misread a number (a stacked fraction "8 1/4" read as "8", "3/8"
as "5/8"), and a misread limit could pass a design that fails. So every number of every brought-in piece is read a
second time, independently, from the page images (by someone who has not seen the extracted text), and both readings
go through the same code (document_extraction/numbers.py). For each piece the file records the numbers as the
extracted text has them, the second reading's numbers, and whether they agree; where they differ, a flag. Code
checks: every piece is recorded, against the piece as cut now (its fingerprint); the two lists are compared here (so
"agrees" is code's verdict, not a word taken on trust); a piece whose lists differ has a flag;
and, where the code cache has the book, that the recorded numbers are exactly the extracted text's now.

Both readings put through numbers.py check the digits, never what the words around them mean: a "not" the code drops
is dropped from both, and they agree on the law backwards (it happened twice, 2026-11-12). So each number's comparison
is also read by a person from the whole printed sentence, without seeing numbers.py's words (second_reading_comparisons:
">=", "<=", ">", "<", "between" or "none"), and code checks it against what the recorded words say
(numbers.comparison); where they differ, a flag quoting the recorded number says which is right and why. Plain code.
"""

import datetime
from pathlib import Path

from .rulebook import STATE_SETTINGS, Context, cached, load, read_jsonl

VERIFICATION = "text_verification.yaml"
READINGS = ("agrees", "differs")
FIELDS = {"document", "copy_checked", "second_reading", "pieces", "notes"}
PIECE_FIELDS = {"piece_sha256", "numbers", "second_reading", "second_reading_numbers", "second_reading_comparisons",
                "flags"}


def state_settings_problems(folder: Path, ctx: Context) -> list[str]:
    """What's wrong with a state law folder's state.yaml: a name, and its law naming documents in sources.yaml."""
    try:
        s = load(Path(folder) / STATE_SETTINGS)
    except Exception as e:  # reported, never raised
        return [f"{STATE_SETTINGS} can't be read ({type(e).__name__}: {e})"]
    if not isinstance(s, dict) or set(s) - {"name", "law"}:
        return [f"{STATE_SETTINGS} must be a mapping of name and law only"]
    out = [] if isinstance(s.get("name"), str) and s["name"].strip() else ["no name"]
    law = s.get("law")
    if not (isinstance(law, dict) and law):
        return out + ["law names no document"]
    return out + [f"law.{k}: {v!r} is not in 1_source_documents/sources.yaml" for k, v in law.items()
                  if v not in ctx.sources]


def verification_problems(folder: Path, ctx: Context) -> tuple[list[str], list[str]]:
    """(problems, notes) for a state law folder's text_verification.yaml. Notes say what wasn't checked here."""
    from document_extraction.numbers import COMPARISONS, comparisons, shown, statements_of_lines
    from .labels import piece_fingerprint
    folder = Path(folder)
    path = folder / VERIFICATION
    kept_outside = [n for n, e in ctx.sources.items() if e.get("kept_outside_repo") is True]
    if not path.exists():
        return ([f"no {VERIFICATION}: every number of a book kept outside the repo is read twice"] if kept_outside
                else []), []
    book = load(path)
    if not isinstance(book, dict) or not FIELDS - {"notes"} <= set(book) <= FIELDS:
        return [f"{VERIFICATION} must have {sorted(FIELDS - {'notes'})} (and notes, if any), nothing else"], []
    name = book["document"]
    entry = ctx.sources.get(name)
    if entry is None:
        return [f"{VERIFICATION}: document {name!r} is not in sources.yaml"], []
    cut = folder / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl"
    rows = read_jsonl(cut)
    if rows[0].get("sha256") != entry.get("sha256"):
        return [f"{VERIFICATION}: the sections file was cut from another version of {name}"], []
    pieces = {p["id"]: p for p in rows[1:]}
    problems, notes = [], []
    second = book["second_reading"]
    if not (isinstance(second, dict) and {"by", "on", "how"} <= set(second) and isinstance(second["on"], datetime.date)):
        problems.append("second_reading must say by (who), on (a date) and how")
    if not (isinstance(book["copy_checked"], str) and book["copy_checked"].strip()):
        problems.append("copy_checked must say which copy of the book was read")
    recorded = book["pieces"] if isinstance(book["pieces"], dict) else {}
    problems += [f"{pid}: brought in but not in {VERIFICATION}" for pid in pieces if pid not in recorded]
    problems += [f"{pid}: in {VERIFICATION} but not a piece" for pid in recorded if pid not in pieces]
    text = None
    if name in ctx.pages:
        lines = {(r["page"], r["line"]): r["text"] for r in read_jsonl(cached(entry, ".jsonl"))[1:]}
        text = lambda p: [lines[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1)]
    else:
        notes.append(f"{VERIFICATION}: the recorded numbers weren't compared with the book's text here "
                     f"({ctx.uncached.get(name, 'its text is not loaded')})")
    for pid, e in recorded.items():
        if pid not in pieces:
            continue
        if not isinstance(e, dict) or set(e) - PIECE_FIELDS:
            problems.append(f"{pid}: fields must be among {sorted(PIECE_FIELDS)}")
            continue
        if e.get("piece_sha256") != piece_fingerprint(pieces[pid], rows[0]["sha256"]):
            problems.append(f"{pid}: the piece changed since its numbers were read; read them again")
        if e.get("second_reading") not in READINGS:
            problems.append(f"{pid}: second_reading must be one of {READINGS}")
        if not isinstance(e.get("second_reading_numbers"), list):
            problems.append(f"{pid}: needs second_reading_numbers (what the second reading found; code compares)")
            continue
        agree = e["second_reading_numbers"] == e.get("numbers")       # code decides, never the word in the file
        if e.get("second_reading") == "agrees" and not agree:
            problems.append(f"{pid}: says the readings agree, but its two lists of numbers differ")
        if e.get("second_reading") == "differs" and agree:
            problems.append(f"{pid}: says the readings differ, but its two lists of numbers are the same")
        if not agree and not e.get("flags"):
            problems.append(f"{pid}: the readings differ, so it needs a flag saying which is right and why")
        problems += _comparison_problems(pid, e, COMPARISONS, comparisons)
        if text is not None and e.get("numbers") != [shown(s) for s in statements_of_lines(text(pieces[pid]))]:
            problems.append(f"{pid}: the recorded numbers are not the extracted text's numbers now")
    return problems, notes


def numbers_of(folder: Path, ctx: Context, name: str) -> dict[str, list[str]]:
    """Each piece's numbers as the extracted text has them (for writing text_verification.yaml; needs the cache)."""
    from document_extraction.numbers import shown, statements_of_lines
    entry = ctx.sources[name]
    lines = {(r["page"], r["line"]): r["text"] for r in read_jsonl(cached(entry, ".jsonl"))[1:]}
    rows = read_jsonl(Path(folder) / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl")
    return {p["id"]: [shown(s) for s in statements_of_lines([lines[(pg, n)] for pg, a, b in p["lines"]
                                                             for n in range(a, b + 1)])] for p in rows[1:]}


def _comparison_problems(pid: str, e: dict, allowed: tuple, comparisons) -> list[str]:
    """Each number's comparison as a person read it from the printed sentence, against what its recorded words say;
    a difference needs a flag quoting the recorded number."""
    numbers, read = e.get("numbers"), e.get("second_reading_comparisons")
    if not isinstance(numbers, list):
        return [f"{pid}: needs numbers"]
    if not (isinstance(read, list) and len(read) == len(numbers) and all(r in allowed for r in read)):
        return [f"{pid}: needs second_reading_comparisons, one of {allowed} for each of its {len(numbers)} numbers "
                f"(what the printed sentence says of each, read without numbers.py)"]
    flags = " ".join(str(f) for f in e.get("flags") or [])
    return [f"{pid}: {n!r} is recorded as {c!r}, but the printed sentence reads {r!r}; a flag quoting {n!r} must say "
            f"which is right and why" for n, c, r in zip(numbers, comparisons(numbers), read)
            if c != r and f"'{n}'" not in flags]
