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

from .rulebook import STATE_SETTINGS, Context, kept_text, load, read_jsonl, verification_files

SCOPES = ("residential_code", "building_code")   # a state.yaml `scope`: design_checker/code_scope.py CODES
VERIFICATION = "text_verification.yaml"
READINGS = ("agrees", "differs")
FIELDS = {"document", "copy_checked", "second_reading", "pieces", "notes", "not_verified"}
PIECE_FIELDS = {"piece_sha256", "numbers", "second_reading", "second_reading_numbers", "second_reading_comparisons",
                "flags"}
# A book whose numbers could not be read a second time (Maine's 2009 IBC: its page images are made from its own OCR,
# so no independent reading exists; docs/decisions/2026-11-20_commercial_egress_maine.md) says so, in words, in a
# top-level `not_verified`. Then each piece records only its fingerprint and its numbers as the extracted text has
# them, and never a second reading: none was made. code_numbers.py gives such a book's numbers to no rule (kind
# rule); a flag may use them in its drafted check, which never decides a result.
NOT_VERIFIED_PIECE_FIELDS = {"piece_sha256", "numbers"}


def state_settings_problems(folder: Path, ctx: Context) -> list[str]:
    """What's wrong with a state law folder's state.yaml: a name, the heading a check's results of its law go
    under (results_title, if given), and its law naming documents in sources.yaml."""
    try:
        s = load(Path(folder) / STATE_SETTINGS)
    except Exception as e:  # reported, never raised
        return [f"{STATE_SETTINGS} can't be read ({type(e).__name__}: {e})"]
    if not isinstance(s, dict) or set(s) - {"name", "law", "results_title", "scope", "waiting_why"}:
        return [f"{STATE_SETTINGS} must be a mapping of name, law, results_title, scope and waiting_why only"]
    out = [] if isinstance(s.get("name"), str) and s["name"].strip() else ["no name"]
    # which buildings the law covers, where a state has two books for egress (New York: the Residential Code and
    # the Building Code); a check runs a scoped law only where design_checker/code_scope.py finds it covers the building
    if "scope" in s and s["scope"] not in SCOPES:
        out.append(f"scope must be one of {', '.join(SCOPES)} (left out: the law covers every building)")
    if "waiting_why" in s and not (isinstance(s["waiting_why"], str) and s["waiting_why"].strip()):
        out.append("waiting_why must be words: what a check says this law will check once rooms are drawn")
    if "results_title" in s and not (isinstance(s["results_title"], str) and s["results_title"].strip()):
        out.append("results_title must be words: how a check's results of this law are headed, e.g. "
                   "\"Egress (NY State Residential Code 2025)\" (left out: \"<name> building code\")")
    law = s.get("law")
    if not (isinstance(law, dict) and law):
        return out + ["law names no document"]
    return out + [f"law.{k}: {v!r} is not in 1_source_documents/sources.yaml" for k, v in law.items()
                  if v not in ctx.sources]


def verification_problems(folder: Path, ctx: Context) -> tuple[list[str], list[str]]:
    """(problems, notes) for a state law folder's records of the second reading: text_verification.yaml, or one
    text_verification.<book>.yaml per book (rulebook.verification_files). Every book kept outside the repo needs one,
    naming it; a file naming another book, or a book twice, is a problem. Notes say what wasn't checked here."""
    folder = Path(folder)
    files = verification_files(folder)
    kept_outside = [n for n, e in ctx.sources.items() if e.get("kept_outside_repo") is True]
    if not files:
        return ([f"no {VERIFICATION}: every number of a book kept outside the repo is read twice"] if kept_outside
                else []), []
    problems, notes, named = [], [], []
    for path in files:
        try:
            named.append(load(path).get("document"))
        except Exception:
            named.append(None)
        p, n = _verification_problems(folder, ctx, path)
        prefix = "" if len(files) == 1 else f"{path.name}: "
        problems += [prefix + x for x in p]
        notes += n
    problems += [f"{name}: kept outside the repo, but no {VERIFICATION} (or text_verification.<book>.yaml) names it"
                 for name in kept_outside if name not in named]
    problems += [f"{name}: named by more than one record of the second reading" for name in sorted(
        {x for x in named if x is not None and named.count(x) > 1})]
    return problems, notes


def _verification_problems(folder: Path, ctx: Context, path: Path) -> tuple[list[str], list[str]]:
    """(problems, notes) for one record of the second reading of a book's numbers."""
    from document_extraction.numbers import COMPARISONS, comparisons, shown, statements_of_lines
    from .labels import piece_fingerprint
    book = load(path)
    optional = {"notes", "not_verified"}
    if not isinstance(book, dict) or not FIELDS - optional <= set(book) <= FIELDS:
        return [f"{path.name} must have {sorted(FIELDS - optional)} (and notes or not_verified, if any), "
                f"nothing else"], []
    unverified = "not_verified" in book
    if unverified and not (isinstance(book["not_verified"], str) and book["not_verified"].strip()):
        return [f"{path.name}: not_verified must say, in words, why no second reading could be made and what to "
                f"check the numbers against"], []
    name = book["document"]
    entry = ctx.sources.get(name)
    if entry is None:
        return [f"{path.name}: document {name!r} is not in sources.yaml"], []
    cut = folder / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl"
    rows = read_jsonl(cut)
    if rows[0].get("sha256") != entry.get("sha256"):
        return [f"{path.name}: the sections file was cut from another version of {name}"], []
    pieces = {p["id"]: p for p in rows[1:]}
    problems, notes = [], []
    second = book["second_reading"]
    if not (isinstance(second, dict) and {"by", "on", "how"} <= set(second) and isinstance(second["on"], datetime.date)):
        problems.append("second_reading must say by (who), on (a date) and how")
    if not (isinstance(book["copy_checked"], str) and book["copy_checked"].strip()):
        problems.append("copy_checked must say which copy of the book was read")
    recorded = book["pieces"] if isinstance(book["pieces"], dict) else {}
    problems += [f"{pid}: brought in but not in {path.name}" for pid in pieces if pid not in recorded]
    problems += [f"{pid}: in {path.name} but not a piece" for pid in recorded if pid not in pieces]
    text = None
    if name in ctx.pages:
        lines = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
        text = lambda p: [lines[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1)]
    else:
        notes.append(f"{path.name}: the recorded numbers weren't compared with the book's text here "
                     f"({ctx.uncached.get(name, 'its text is not loaded')})")
    for pid, e in recorded.items():
        if pid not in pieces:
            continue
        if unverified:                     # numbers recorded, never read a second time: none was made
            if not isinstance(e, dict) or set(e) != NOT_VERIFIED_PIECE_FIELDS:
                second = sorted(k for k in (e if isinstance(e, dict) else {}) if k.startswith("second_reading"))
                problems.append(f"{pid}: a book not verified (not_verified) records only "
                                f"{sorted(NOT_VERIFIED_PIECE_FIELDS)} for each piece"
                                + (f"; {second} claim a second reading that was never made" if second else ""))
                continue
            if e["piece_sha256"] != piece_fingerprint(pieces[pid], rows[0]["sha256"]):
                problems.append(f"{pid}: the piece changed since its numbers were recorded; record them again")
            if not (isinstance(e["numbers"], list) and all(isinstance(n, str) for n in e["numbers"])):
                problems.append(f"{pid}: numbers must be a list of the numbers as the extracted text has them")
            elif text is not None and e["numbers"] != [shown(s) for s in statements_of_lines(text(pieces[pid]))]:
                problems.append(f"{pid}: the recorded numbers are not the extracted text's numbers now")
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
    lines = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
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
