"""Compile, then freeze (CLAUDE.md principle 1; docs/decisions/2026-11-23_laws_validation_speed.md): a state law's
validation (compile_law) is worked out once, in a fresh process, and frozen as a certificate beside it,
<state folder>/7_published_rulebooks/<book stem>.published.json, with the sha256 of everything it was worked out
from. While rules are draft (approval is deferred, principle 2) certificates are generated files, never committed
(.gitignore): built by `python -m rule_format publish` (CI before the tests, a session-wide pytest fixture, the
Revit add-in's install script, the goldens and permit-sheet commands when one is missing).

    python -m rule_format publish [folder]          # writes each state law's certificate (refused if it has problems)
    python -m rule_format publish --check [folder]  # a fresh compile must give the same bytes; names what changed

A certificate (FORMAT) is sorted-key JSON with no timestamps, so the same inputs give the same bytes on every
machine:

- `book`: the rulebook's path (from the repo) and sha256; `code_version`: each source's file and sha256 (sources.yaml);
- `inputs`: {path: sha256, or null for a file the compile tried to open that wasn't there}: every file the compile
  opened (recorded by an "open" audit hook in the fresh process, never a list kept by hand), with every file of the
  law folder (place_files, so a file that appears is caught) and the shared files every check reads (shared_files);
- `listed`: {folder: sha256 of its entry names} of every repo folder the compile listed (the same audit hook's
  os.scandir and os.listdir): the compile's answer can turn on which names exist, not only on what files say (a
  rule's notes may name a repo file: rulebook._in_repo walks the repo's names), so a name that appears or goes in
  any of them makes the certificate stale. Every folder of the law folder and of the shared files is listed too,
  whatever the compile lists (it also asks whether a file exists, which no audit event shows). Names tools make as
  they run, and what publish writes, are left out (rulebook.generated_name, the same rule the repo walk follows);
- `validator`: {path: sha256} of the repo's modules the compile imported (packages/);
- `outside_repo_reads`: files the compile opened outside the repo and outside Python's own installation (the code
  cache, say): must be empty, and publish refuses a certificate otherwise;
- `result`: compile_law's {problems, kinds, documents}, typed (a date stays a date, a set a set: _encode), so a
  certificate read back equals a live compile by value. Publish refuses a certificate with problems.

stale() is the cheap recheck (no compile): every input and validator file hashed again and the folder globbed again.
Nothing here keeps state between calls.
"""

import datetime
import hashlib
import json
import os
import site
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

from .rulebook import (PUBLISHED_SUFFIX, REPO, Context, building_code_rulebook, generated_name, load,
                       rulebook_file_problems, state_folders)
from .state_law import state_settings_problems

FORMAT = "gordium.published_law/1"
PUBLISHED = "7_published_rulebooks"
SUFFIX = PUBLISHED_SUFFIX
SOURCES = "1_source_documents/sources.yaml"
PUBLISH = "python -m rule_format publish"
LOCK = REPO / "regulations/jurisdictions/.publishing.lock"     # one publish at a time (pytest-xdist workers)
LOCK_STALE_S = 600


class PublishError(Exception):
    """The fresh compile process itself failed (not a law's problem: compile_law never raises)."""


# ---- the compile (the costly part, frozen) --------------------------------------------------------------------------

def compile_law(folder: Path, book: Path) -> dict:
    """The costly part of reading one state law, and the part that is frozen: {"problems": everything wrong with its
    sources, its settings and its rulebook (empty: the rules pass every rule check), "documents": its sources.yaml
    entries, "kinds": the measures its rules may name beyond use and district}. Never raises: sources that can't be
    read are a problem, so the law gives no rules (needs review, never a row). Reads nothing from the code cache
    (use_cache=False), so the same files give the same answer on every machine."""
    out = {"problems": [], "documents": {}, "kinds": {}}
    try:          # never a crash (zoning's answer goes with it), never a rule used unchecked
        ctx = Context.for_jurisdiction(folder, use_cache=False)   # the same answer on every machine
        out["problems"] = ctx.problems + state_settings_problems(folder, ctx) + rulebook_file_problems(book, ctx)
        out["documents"] = ctx.sources
        out["kinds"] = {k: v for k, v in ctx.allowed().items() if k not in ("use", "district")}
    except Exception as e:
        out["problems"] = [unreadable(e)]
    return out


def unreadable(e: Exception) -> str:
    return f"its sources can't be read ({type(e).__name__}: {e})"


# ---- which files ----------------------------------------------------------------------------------------------------

def place_files(folder: Path) -> list[Path]:
    """Every file of a place's folder a check can read: its settings, rules, definitions, labels, extracted text,
    what isn't checked yet; of its source documents only sources.yaml (their fingerprints), not the PDFs."""
    return [f for f in Path(folder).rglob("*") if f.is_file() and not f.name.startswith(".")
            and (f.parent.name != "1_source_documents" or f.name == "sources.yaml")]


def shared_files(repo: Path = REPO) -> list[Path]:
    """The files every check reads beside a place's own: under regulations/ outside any place's folder (the rule
    topics, document_extraction_guide/vocabulary.yaml, who may approve: reviewers.yaml) and the research reports under
    docs/research/ that definitions and rules cite."""
    regulations = Path(repo) / "regulations"
    shared = [f for f in regulations.rglob("*") if f.is_file() and "jurisdictions" not in f.relative_to(regulations).parts
              and not f.name.startswith(".")]
    return shared + [f for f in (Path(repo) / "docs/research").rglob("*") if f.is_file() and not f.name.startswith(".")]


def _folder_inputs(folder: Path, repo: Path) -> set[str]:
    """The law folder's files (its certificates left out: they are the output) and the shared ones, from the repo."""
    own = [f for f in place_files(folder) if PUBLISHED not in f.relative_to(folder).parts]
    return {_rel(f, repo) for f in own + shared_files(repo)}


def _import_path(repo: Path) -> list[Path]:
    """The folders the fresh compile imports from, in order: every package folder of packages/."""
    return [p for p in sorted((Path(repo) / "packages").iterdir()) if p.is_dir() and not _left_out(p.name)]


def certificate_path(folder: Path, book: Path) -> Path:
    return Path(folder) / PUBLISHED / f"{Path(book).stem}{SUFFIX}"


def published_folders(repo: Path = REPO) -> list[tuple[Path, Path]]:
    """(state law folder, its rulebook) for every state law folder that has a rulebook, in a stable order."""
    return [(f, b) for f in state_folders(repo) if (b := building_code_rulebook(f)) is not None]


def _rel(path: Path, repo: Path) -> str:
    return Path(path).relative_to(repo).as_posix()


# Names never counted in a folder's listing (rulebook.generated_name): made by tools as they run, and what publish
# writes (the 7_published_rulebooks folders and the certificates). The one walk of the whole repo a compile makes
# (rulebook._in_repo: whether a name a rule's notes mention is a repo file) skips exactly these, so leaving them out
# never hides a name the compile could see, and publishing one law never changes another's listings.
_left_out = generated_name


def _generated(rel: Path) -> bool:
    return any(_left_out(part) for part in rel.parts)


def _always_listed(folder: Path, repo: Path) -> set[str]:
    """Every folder of the law folder (1_source_documents too) and of the shared files, listed whether or not the
    compile lists it: the compile also asks whether a file exists (a stat, which no audit event shows: a copy of a
    book kept outside the repo in 1_source_documents is a problem), so a name that appears or goes anywhere there
    must make the certificate stale."""
    tops = [Path(folder), Path(repo) / "docs/research"]
    regulations = Path(repo) / "regulations"
    # and where the fresh process imports from (fresh(): every folder of packages/ on its path, before Python's own):
    # a package folder that appears could hold a module the compile imports in place of Python's (review round 4)
    packages = Path(repo) / "packages"
    out = {_rel(regulations, repo), _rel(packages, repo)}
    out |= {_rel(d, repo) for d in _import_path(repo)}
    tops += [d for d in regulations.iterdir() if d.is_dir() and d.name != "jurisdictions" and not _left_out(d.name)]
    for top in tops:
        for here, dirs, _ in os.walk(top):
            dirs[:] = [d for d in dirs if not _left_out(d)]
            out.add(_rel(Path(here), repo))
    return out


def _listing(folder: Path) -> str | None:
    """The sha256 of a folder's entry names (files and folders, each marked; generated names left out), or None when
    there is no folder there: a name that appears in, or goes from, a folder the compile listed changes it."""
    try:
        with os.scandir(folder) as entries:
            names = sorted(("d " if e.is_dir() else "f ") + e.name for e in entries if not _left_out(e.name))
    except (FileNotFoundError, NotADirectoryError):
        return None
    return hashlib.sha256("/".join(names).encode("utf-8")).hexdigest()   # "/" is never in a name


def _sha(path: Path) -> str | None:
    """A file's sha256, or None when there is no file there (a file that can't be read raises)."""
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# ---- the typed JSON (a certificate read back equals the live compile by value) --------------------------------------

def _encode(o):
    if isinstance(o, dict):
        if any(not isinstance(k, str) for k in o):
            raise TypeError(f"a key that isn't text: {next(k for k in o if not isinstance(k, str))!r}")
        if len(o) == 1 and next(iter(o)).startswith("$"):
            raise TypeError(f"a mapping whose only key starts with $ ({next(iter(o))}) reads as a typed value")
        return {k: _encode(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_encode(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return {"$set": sorted((_encode(v) for v in o), key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(o, tuple):
        return {"$tuple": [_encode(v) for v in o]}
    if type(o) is datetime.date:
        return {"$date": o.isoformat()}
    if type(o) is datetime.datetime:
        return {"$datetime": o.isoformat()}
    if o is None or type(o) in (str, int, bool):
        return o
    if type(o) is float:
        if o != o or o in (float("inf"), float("-inf")):
            raise TypeError(f"a number JSON can't keep exactly: {o!r}")
        return o
    raise TypeError(f"a value of type {type(o).__name__} can't be frozen: {o!r}")


def _decode(o):
    if isinstance(o, dict):
        if len(o) == 1:
            (k, v), = o.items()
            if k == "$set":
                return {_decode(x) for x in v}
            if k == "$tuple":
                return tuple(_decode(x) for x in v)
            if k == "$date":
                return datetime.date.fromisoformat(v)
            if k == "$datetime":
                return datetime.datetime.fromisoformat(v)
        return {k: _decode(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_decode(v) for v in o]
    return o


def dumps(certificate: dict) -> bytes:
    """A certificate's bytes: sorted keys, one layout, UTF-8, no timestamps (the same inputs, the same bytes)."""
    return (json.dumps(certificate, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def result_of(certificate: dict) -> dict:
    """The frozen compile_law result, as compile_law returns it (dates, sets and all)."""
    return _decode(certificate["result"])


# ---- the fresh process ----------------------------------------------------------------------------------------------

# Runs in a fresh interpreter: the audit hook is set before anything of the repo is imported, so every file the
# import and the compile open is seen. Stdout is the certificate alone (anything the compile prints goes to stderr).
_CHILD = """
import sys
on, seen = [True], []
def _hook(event, args):
    if on and event in ("open", "os.scandir", "os.listdir"):
        seen.append((event, args[0] if args else None))
sys.addaudithook(_hook)
out, sys.stdout = sys.stdout.buffer, sys.stderr
from rule_format import published
out.write(published._child(sys.argv[1], sys.argv[2], seen, on))
out.flush()
"""


def _child(folder: str, repo: str, seen: list, on: list) -> bytes:
    """In the fresh process: compile the law, then build its certificate from what was opened, listed and
    imported."""
    if Path(repo).resolve() != REPO:
        raise PublishError(f"the fresh process imported the code of {REPO}, not of {repo}")
    folder = Path(folder).resolve()
    book = building_code_rulebook(folder)
    if book is None:
        raise PublishError(f"no rulebook in {folder}")
    result = compile_law(folder, book)
    on.clear()                                          # nothing opened after this point is the compile's
    opened = list(seen)
    modules = sorted({Path(f).resolve() for m in list(sys.modules.values())
                      if isinstance(f := getattr(m, "__file__", None), str)})
    return dumps(_certificate(folder, book, result, opened, modules))


def _python_roots() -> list[Path]:
    """Python's own installation (the interpreter, its standard library, installed packages): read by any import,
    never law. A root that holds the repo itself is left out, so nothing of the repo is ever taken for Python's."""
    paths = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix, *site.getsitepackages(),
             site.getusersitepackages(), *(sysconfig.get_paths().values())}
    if sys.pycache_prefix:                      # fresh()'s own empty cache folder: compiled from source, this run
        paths.add(sys.pycache_prefix)
    roots = []
    for p in sorted(paths):
        r = Path(p).resolve()
        if not (REPO == r or REPO.is_relative_to(r)):
            roots.append(r)
    return roots


def _certificate(folder: Path, book: Path, result: dict, seen: list, modules: list[Path]) -> dict:
    roots, packages = _python_roots(), REPO / "packages"
    inputs, listed, outside = set(), set(), set()
    for event, raw in seen:
        if isinstance(raw, int):                       # an open file descriptor: no path to say
            continue
        p = Path(os.path.abspath(os.fsdecode(raw if raw is not None else ".")))
        try:
            p = p.resolve()
        except OSError:
            pass
        if any(p.is_relative_to(r) for r in roots):    # Python's own installation (a venv inside the repo too)
            continue
        if not p.is_relative_to(REPO):
            outside.add(str(p))
            continue
        rel = p.relative_to(REPO)
        if event != "open":
            if not _generated(rel):
                listed.add(rel.as_posix())
        elif "__pycache__" in rel.parts or (p.suffix == ".py" and p.is_relative_to(packages)):
            continue                                   # code: counted below as the validator
        elif PUBLISHED in rel.parts:
            continue                                   # what publish writes, never an input of its own
        else:
            inputs.add(rel.as_posix())
    inputs |= _folder_inputs(folder, REPO)
    listed |= _always_listed(folder, REPO)
    validator = {_rel(m, REPO): _sha(m) for m in modules if m.is_relative_to(packages)}
    sources = load(folder / SOURCES).get("documents") or []
    return {
        "format": FORMAT,
        "law": _rel(folder, REPO),
        "book": {"path": _rel(book, REPO), "sha256": _sha(book)},
        "code_version": {d.get("file"): d.get("sha256") for d in sources if isinstance(d, dict)},
        "inputs": {p: _sha(REPO / p) for p in sorted(inputs)},
        "listed": {d: _listing(REPO / d) for d in sorted(listed)},
        "validator": dict(sorted(validator.items())),
        "outside_repo_reads": sorted(outside),
        "result": _encode({"problems": result["problems"], "kinds": result["kinds"],
                           "documents": result["documents"]}),
    }


def fresh(folder: Path) -> bytes:
    """A law folder's certificate, compiled now in a fresh Python process running this repo's code."""
    # this repo's packages alone: another entry (an empty one is the folder it runs in) would change what the import
    # lists, so the certificate would differ by machine; everything else comes from Python's own installation
    ours = [str(p) for p in _import_path(REPO)]
    # and never the repo's compiled caches (__pycache__): Python trusts one by its source's size and time to the
    # second, so a same-size edit could run the old code beside the new source's sha256 (review round 5). The child
    # compiles every module from its source, into an empty folder of its own, written nowhere
    with tempfile.TemporaryDirectory(prefix="gordium_publish_") as cache:
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(ours), PYTHONPYCACHEPREFIX=cache,
                   PYTHONDONTWRITEBYTECODE="1")
        done = subprocess.run([sys.executable, "-P", "-c", _CHILD, str(Path(folder).resolve()), str(REPO)],
                              capture_output=True, env=env, cwd=str(REPO))
    if done.returncode != 0:
        why = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise PublishError(f"the fresh compile of {_shown(folder)} failed: {why[-1] if why else done.returncode}")
    return done.stdout


def refusals(certificate: dict) -> list[str]:
    """Why a certificate may not be published: the law's problems, and any read outside the repo."""
    out = [f"its law has a problem: {p}" for p in certificate["result"]["problems"]]
    out += [f"the compile read a file outside the repo ({p}): a check must give the same answer on every machine"
            for p in certificate["outside_repo_reads"]]
    return out


# ---- publish, check, stale ------------------------------------------------------------------------------------------

def publish(folder: Path) -> list[str]:
    """Write a law folder's certificate from a fresh compile: [] when written, else why it was refused (nothing is
    written then; an older certificate is left as it is, and stale() refuses it)."""
    folder = Path(folder).resolve()
    book = building_code_rulebook(folder)
    if book is None:
        return []
    data = fresh(folder)
    if why := refusals(json.loads(data)):
        return why
    path = certificate_path(folder, book)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")      # a dot file: never one of the folder's inputs
    temp.write_bytes(data)
    os.replace(temp, path)
    return []


def check(folder: Path) -> list[str]:
    """[] when the certificate on disk is exactly what a fresh compile gives now, else what differs, by name."""
    folder = Path(folder).resolve()
    book = building_code_rulebook(folder)
    if book is None:
        return []
    path = certificate_path(folder, book)
    data = fresh(folder)
    new = json.loads(data)
    why = refusals(new)
    try:
        old_bytes = path.read_bytes()
    except FileNotFoundError:
        return why + [f"no certificate at {_shown(path)}: run {PUBLISH}"]
    if old_bytes == data:
        return why
    try:
        old = json.loads(old_bytes)
    except ValueError as e:
        return why + [f"{_shown(path)} isn't readable JSON ({e}): run {PUBLISH}"]
    return why + (differences(old, new) or [f"{_shown(path)} differs from a fresh compile in its bytes only "
                                            f"(edited by hand?): run {PUBLISH}"])


def differences(old: dict, new: dict) -> list[str]:
    """What changed between two certificates, by name: the format, the book, each source, input and validator file,
    the result."""
    if not isinstance(old, dict) or old.get("format") != FORMAT:
        return [f"its certificate's format is {old.get('format') if isinstance(old, dict) else None!r}, not "
                f"{FORMAT}: run {PUBLISH}"]
    out = []
    for key, what in (("book", "the rulebook"),):
        if old.get(key) != new.get(key):
            out.append(f"{what} changed: {new[key]['path']}")
    for key, what in (("code_version", "source"), ("inputs", "input"), ("validator", "validator file"),
                      ("listed", "folder listing")):
        a, b = old.get(key) or {}, new.get(key) or {}
        for name in sorted(set(a) | set(b)):
            if name not in a:
                out.append(f"new {what}: {name}" + (" (not there)" if b[name] is None else ""))
            elif name not in b:
                out.append(f"{what} no longer read: {name}")
            elif a[name] != b[name]:
                out.append(f"{what} " + ("appeared" if a[name] is None else "gone" if b[name] is None
                                         else "changed") + f": {name}")
    for key in ("law", "outside_repo_reads", "result"):
        if old.get(key) != new.get(key):
            out.append(f"its {key.replace('_', ' ')} differs")
    return out


def stale(folder: Path, book: Path | None = None, repo: Path = REPO) -> list[str]:
    """[] when a law's certificate still matches its files, else why not, by name (no compile: every input and
    validator file hashed again, every folder listed again, and the law folder and shared files globbed again for a
    file that appeared)."""
    folder = Path(folder)
    book = book or building_code_rulebook(folder)
    if book is None:
        return []
    return _read(folder, book, repo)[0]


def frozen(folder: Path, book: Path, repo: Path = REPO) -> dict:
    """compile_law's answer for a state law, read from its certificate after checking it still matches every file it
    was worked out from (stale's checks): {"problems", "documents", "kinds"} as compile_law gives them, and "book":
    the rulebook's bytes, exactly the ones whose sha256 the certificate holds (read once, so a rulebook saved between
    the check and its reading is never taken for the one checked). A certificate that is missing, stale, of an
    unknown format or unreadable gives a problem saying so and how to publish, no documents, no kinds and no book:
    the law gives no rules (needs review, never a row). There is no live compile to fall back on. Never raises."""
    try:
        why, cert, book_bytes = _read(Path(folder), Path(book), Path(repo))
        if not why:
            result = result_of(cert)
            if not (isinstance(result, dict) and result.get("problems") == [] and isinstance(result.get("documents"), dict)
                    and isinstance(result.get("kinds"), dict)):
                why = [f"{_shown(certificate_path(folder, book))} holds no usable result: run {PUBLISH}"]
    except Exception as e:      # never a crash (zoning's answer goes with it), never a rule used unchecked
        why = [f"{_shown(certificate_path(folder, book))} can't be checked ({type(e).__name__}: {e}): run {PUBLISH}"]
    if why:
        return {"problems": why, "documents": {}, "kinds": {}, "book": None}
    return {"problems": [], "documents": result["documents"], "kinds": result["kinds"], "book": book_bytes}


def _read(folder: Path, book: Path, repo: Path) -> tuple[list[str], dict | None, bytes | None]:
    """(why the certificate doesn't match its files, or [], the certificate, the rulebook's bytes)."""
    path = certificate_path(folder, book)
    try:
        cert = json.loads(path.read_bytes())
    except FileNotFoundError:
        return [f"no certificate at {_shown(path)}: run {PUBLISH}"], None, None
    except ValueError as e:
        return [f"{_shown(path)} isn't readable JSON ({e}): run {PUBLISH}"], None, None
    if not isinstance(cert, dict) or cert.get("format") != FORMAT:
        return [f"{_shown(path)} isn't a {FORMAT} certificate: run {PUBLISH}"], None, None
    out = []
    try:
        book_bytes = book.read_bytes() if book.is_file() else None
        now = {"path": _rel(book, repo), "sha256": None if book_bytes is None else hashlib.sha256(book_bytes).hexdigest()}
        if cert["law"] != _rel(folder, repo) or cert["book"] != now:
            out.append(f"the rulebook changed: {_rel(book, repo)}")
        for key, what in (("inputs", "input"), ("validator", "validator file")):
            for name, sha in cert[key].items():
                now = _sha(Path(repo) / name)
                if now != sha:
                    out.append(f"{what} " + ("appeared" if sha is None else "gone" if now is None else "changed")
                               + f": {name}")
        for name, sha in cert["listed"].items():
            if _listing(Path(repo) / name) != sha:
                out.append(f"a name appeared in or went from the folder {name}")
        for name in sorted(_folder_inputs(folder, Path(repo)) - set(cert["inputs"])):
            out.append(f"new file: {name}")
        out += refusals(cert)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        return ([f"{_shown(path)} can't be read as a {FORMAT} certificate ({type(e).__name__}: {e}): run {PUBLISH}"],
                None, None)
    return [f"{_shown(path)} is stale ({w}): run {PUBLISH}" for w in out], cert, book_bytes


def ensure(missing_only: bool = False, repo: Path = REPO) -> list[str]:
    """Publish every state law whose certificate is missing (or, unless missing_only, stale), one publisher at a time
    across processes (pytest-xdist workers). Returns what couldn't be published, and with missing_only the
    certificates left stale; never raises for a law's problem."""
    def todo():
        out = []
        for folder, book in published_folders(repo):
            why = stale(folder, book, repo)
            if why and (not missing_only or not certificate_path(folder, book).is_file()):
                out.append(folder)
        return out
    if not todo():
        return _left_stale(repo) if missing_only else []
    with _lock():
        notes = []
        for folder in todo():
            try:
                notes += [f"{_shown(folder)}: {w}" for w in publish(folder)]
            except PublishError as e:
                notes.append(str(e))
    return notes + (_left_stale(repo) if missing_only else [])


def _left_stale(repo: Path) -> list[str]:
    return [w for folder, book in published_folders(repo) for w in stale(folder, book, repo)]


class _lock:
    """A lock file made only where there is none (open mode "x"): one publisher at a time; a lock left by a process
    that died is taken after LOCK_STALE_S."""
    def __enter__(self):
        while True:
            try:
                LOCK.open("xb").close()                # made only if there is none (exclusive)
                return self
            except FileExistsError:
                try:
                    if time.time() - LOCK.stat().st_mtime > LOCK_STALE_S:
                        LOCK.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass
                time.sleep(0.2)

    def __exit__(self, *exc):
        LOCK.unlink(missing_ok=True)


def _shown(path) -> str:
    p = Path(path)
    return p.relative_to(REPO).as_posix() if p.is_absolute() and p.is_relative_to(REPO) else str(p)


def folders_named(where: str | None) -> list[Path]:
    """The state law folders a command names: none named, every one with a rulebook; a state law folder, itself; a
    place, the state law folders it inherits."""
    if not where:
        return [f for f, _ in published_folders()]
    from .place import folder_of, place
    folder = folder_of(where).resolve()
    if (folder / "state.yaml").is_file():
        return [folder]
    return list(place(folder).inherits)


def main(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog=PUBLISH)
    parser.add_argument("folder", nargs="?", help="a state law folder or a place (default: every state law)")
    parser.add_argument("--check", action="store_true", help="a fresh compile must give the same bytes")
    args = parser.parse_args(argv)
    failed = 0
    for folder in folders_named(args.folder):
        try:
            why = check(folder) if args.check else publish(folder)
        except PublishError as e:
            why = [str(e)]
        book = building_code_rulebook(folder)
        shown = _shown(certificate_path(folder, book)) if book else f"{_shown(folder)} (no rulebook)"
        verb = "matches a fresh compile" if args.check else "written"
        print(f"{'✗' if why else '✓'} {shown}" + ("" if why else f": {verb}") + "".join(f"\n    {w}" for w in why))
        failed += bool(why)
    return 1 if failed else 0
