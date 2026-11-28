"""Compile, then freeze (rule_format/published.py): a state law's certificate is exactly what a fresh compile gives,
names every input it was worked out from, and `publish --check` fails on a change to any of them.

The end-to-end cases run on a copy of the repo's code and of one state law (Maine's, the smallest) in a temporary
folder, never on the repo's own files (round 10 of the New York code branch: tests that touched the shared regulations
tree raced other tests under parallel CI). Each `python -m rule_format` there runs the copy's own code (its packages
first on PYTHONPATH; the fresh compile checks it imported the copy's code).
"""

import datetime
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from rule_format import published
from rule_format.rulebook import REPO, building_code_rulebook

MAINE = "regulations/jurisdictions/maine/maine_state"
NY = "regulations/jurisdictions/new_york/new_york_state"
LAWS = (MAINE, NY, "regulations/jurisdictions/new_york/new_york_state_building")
CERT = f"{MAINE}/7_published_rulebooks/general.published.json"


def _copy_repo(dest: Path) -> Path:
    """A copy of the repo at dest that the compile can't tell from it: every name of the repo (an empty file for each,
    as the compile walks the repo's names: rulebook._in_repo), then the real bytes of the code the compile imports,
    the shared files and every state law's folder. No 7_published_rulebooks folder anywhere, as on a fresh clone
    (they hold only what publish writes, gitignored while rules are draft)."""
    for top, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if not published._left_out(d)]          # never into .git or a cache
        here = dest / Path(top).relative_to(REPO)
        here.mkdir(parents=True, exist_ok=True)
        for name in files:
            if not published._left_out(name):
                (here / name).write_bytes(b"")
    real = [f for package in ("rule_format", "document_extraction")
            for f in (REPO / "packages" / package / package).rglob("*")]
    real += published.shared_files(REPO) + [f for law in LAWS for f in (REPO / law).rglob("*")]
    for f in real:
        if f.is_file() and not published._generated(f.relative_to(REPO)):
            shutil.copyfile(f, dest / f.relative_to(REPO))
    return dest


def _run(repo: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(p) for p in sorted((repo / "packages").iterdir())))
    done = subprocess.run([sys.executable, "-P", "-m", "rule_format", "publish", *args], cwd=repo, env=env,
                          capture_output=True)
    return done.returncode, (done.stdout + done.stderr).decode("utf-8", "replace")


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    repo = _copy_repo(tmp_path_factory.mktemp("published") / "repo")
    assert not list(repo.rglob(published.PUBLISHED))
    code, said = _run(repo, *LAWS)             # every state law, in order: one's publishing never stales another
    assert code == 0 and said.count("written") == len(LAWS), said
    return repo


def test_a_certificate_is_the_same_bytes_from_two_fresh_runs_and_from_another_folder(copy):
    """Sorted keys, no timestamps, paths from the repo: two fresh compiles give the same bytes, and the copy (another
    folder on this machine) gives exactly the bytes the repo's own Maine law gives."""
    first = (copy / CERT).read_bytes()
    code, said = _run(copy, MAINE)
    assert code == 0, said
    assert (copy / CERT).read_bytes() == first
    assert published.fresh(REPO / MAINE) == {REPO / MAINE / "5_building_code_rules/drafted/general.yaml": first}


def test_a_certificate_names_what_it_was_worked_out_from(copy):
    cert = json.loads((copy / CERT).read_bytes())
    assert cert["format"] == published.FORMAT and cert["law"] == MAINE
    assert cert["book"]["path"] == f"{MAINE}/5_building_code_rules/drafted/general.yaml"
    assert cert["outside_repo_reads"] == [] and cert["result"]["problems"] == []
    sources = {d["file"]: d["sha256"] for d in published.load(copy / MAINE / published.SOURCES)["documents"]}
    assert cert["code_version"] == sources and len(sources) == 2
    inputs = cert["inputs"]
    for read in (f"{MAINE}/1_source_documents/sources.yaml", f"{MAINE}/state.yaml",
                 f"{MAINE}/2_extracted_text/icc.ibc.2009.sections.jsonl", "regulations/reviewers.yaml",
                 "regulations/document_extraction_guide/vocabulary.yaml", "packages/rule_format/rule_format/measures.yaml"):
        assert inputs[read], read                      # opened by the compile (the audit hook), with its sha256
    assert not any(p.endswith(".py") or "__pycache__" in p for p in inputs)
    assert not any("7_published_rulebooks" in p for p in inputs)      # never its own output
    assert {"packages/rule_format/rule_format/rulebook.py", "packages/rule_format/rule_format/published.py",
            "packages/document_extraction/document_extraction/book_text.py"} <= set(cert["validator"])
    assert published.result_of(cert) == published.compile_law(REPO / MAINE, building_code_rulebook(REPO / MAINE))


EDITS = {      # each kind of input, edited so it still reads (a YAML or Markdown comment, a Python comment)
    "the rulebook": (f"{MAINE}/5_building_code_rules/drafted/general.yaml", "\n# edited\n",
                     f"the rulebook changed: {MAINE}/5_building_code_rules/drafted/general.yaml"),
    "sources.yaml": (f"{MAINE}/1_source_documents/sources.yaml", "\n# edited\n",
                     f"input changed: {MAINE}/1_source_documents/sources.yaml"),
    "the extracted text": (f"{MAINE}/2_extracted_text/icc.ibc.2009.sections.jsonl", "",
                           f"input changed: {MAINE}/2_extracted_text/icc.ibc.2009.sections.jsonl"),
    "a shared registry": ("packages/rule_format/rule_format/measures.yaml", "\n# edited\n",
                          "input changed: packages/rule_format/rule_format/measures.yaml"),
    "a shared file": ("regulations/reviewers.yaml", "\n# edited\n", "input changed: regulations/reviewers.yaml"),
    "a validator module": ("packages/rule_format/rule_format/formula.py", "\n# edited\n",
                           "validator file changed: packages/rule_format/rule_format/formula.py"),
    "a new file in the law folder": (f"{MAINE}/4_term_definitions/notes.md", None,
                                     f"new input: {MAINE}/4_term_definitions/notes.md"),
}


def _edit(path: Path, extra: str | None) -> bytes | None:
    before = path.read_bytes() if path.exists() else None
    if extra is None:
        path.write_bytes(b"# a note\n")
    elif extra:
        path.write_bytes(before + extra.encode("utf-8"))
    else:                                        # the extracted text: its last piece given one more field
        lines = before.decode("utf-8").splitlines(keepends=True)
        row = json.loads(lines[-1])
        row["edited"] = True
        lines[-1] = json.dumps(row, ensure_ascii=False) + "\n"
        path.write_bytes("".join(lines).encode("utf-8"))
    return before


def _undo(path: Path, before: bytes | None):
    if before is None:
        path.unlink()
    else:
        path.write_bytes(before)


@pytest.mark.parametrize("kind", list(EDITS))
def test_publish_check_fails_on_a_changed_input_of_each_kind_and_names_it(copy, kind):
    """The eval: a fresh compile in a new process differs from the certificate, and the check says which file; the
    cheap recheck (stale, no compile) says it too. Undone, both pass again."""
    rel, extra, said = EDITS[kind]
    before = _edit(copy / rel, extra)
    try:
        code, out = _run(copy, "--check", MAINE)
        assert code == 1 and said in out, out
        assert any(said.split(": ", 1)[1] in w for w in published.stale(copy / MAINE, repo=copy)), kind
    finally:
        _undo(copy / rel, before)
    assert published.stale(copy / MAINE, repo=copy) == []


def test_publish_check_passes_when_clean_and_fails_on_a_missing_or_hand_edited_certificate(copy):
    """Review round 1 (F1): on a fresh clone (no 7_published_rulebooks folders) Maine's compile walked the repo
    before New York's folders were made, so publishing New York made Maine's certificate stale at once. Clean, every
    law matches a fresh compile and none is stale."""
    code, out = _run(copy, "--check", *LAWS)
    assert code == 0 and out.count("matches a fresh compile") == len(LAWS), out
    assert [published.stale(copy / law, repo=copy) for law in LAWS] == [[]] * len(LAWS)
    cert = copy / CERT
    kept = cert.read_bytes()
    try:
        cert.write_bytes(kept.replace(b"\n", b"\r\n"))                # the same JSON, other bytes
        code, out = _run(copy, "--check", MAINE)
        assert code == 1 and "in its bytes only" in out, out
        cert.unlink()
        code, out = _run(copy, "--check", MAINE)
        assert code == 1 and "no certificate at" in out, out
        assert any("no certificate at" in w for w in published.stale(copy / MAINE, repo=copy))
    finally:
        cert.write_bytes(kept)


def test_publish_refuses_a_compile_that_reads_outside_the_repo(copy, tmp_path):
    """The code cache (or any file) outside the repo would make the answer differ by machine: a compile that opens one
    is refused, and no certificate is written."""
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("not law", encoding="utf-8")
    module = copy / "packages/rule_format/rule_format/state_law.py"
    kept, cert = module.read_bytes(), (copy / CERT).read_bytes()
    try:
        module.write_bytes(kept + f"\nopen({str(outside)!r}, 'rb').close()\n".encode("utf-8"))
        (copy / CERT).unlink()
        code, out = _run(copy, MAINE)
        assert code == 1 and "outside the repo" in out and "elsewhere.txt" in out, out
        assert not (copy / CERT).exists()
    finally:
        module.write_bytes(kept)
        (copy / CERT).write_bytes(cert)


def test_publish_refuses_a_law_with_problems_and_writes_nothing(copy):
    rulebook = copy / MAINE / "5_building_code_rules/drafted/general.yaml"
    kept, cert = rulebook.read_bytes(), (copy / CERT).read_bytes()
    try:
        rulebook.write_bytes(b"rules: 5\n")
        code, out = _run(copy, MAINE)
        assert code == 1 and "its law has a problem" in out, out
        assert (copy / CERT).read_bytes() == cert                     # the old one left as it was (and stale)
        assert any("the rulebook changed" in w for w in published.stale(copy / MAINE, repo=copy))
    finally:
        rulebook.write_bytes(kept)


def test_a_name_that_appears_anywhere_in_the_law_folder_makes_its_certificate_stale(copy):
    """Review round 1 (F2, confirmed by two sceptics): the compile also asks whether a file exists (a stat, which no
    audit event shows): a copy of a book kept outside the repo in 1_source_documents is a problem. New York's compile
    never listed that folder, so a copy appearing there left the certificate current while a live compile refused the
    law. Every folder of the law folder is listed now, whatever the compile lists."""
    cert = json.loads((copy / NY / "7_published_rulebooks/general.published.json").read_bytes())
    folders = {d.relative_to(copy).as_posix() for d in [copy / NY, *(copy / NY).rglob("*")] if d.is_dir()
               and not published._generated(d.relative_to(copy))}
    assert folders <= set(cert["listed"]) and f"{NY}/1_source_documents" in cert["listed"]
    (entry,) = [d for d in published.load(copy / NY / published.SOURCES)["documents"] if d.get("kept_outside_repo")]
    copied = copy / NY / "1_source_documents" / entry["file"]
    copied.write_bytes(b"%PDF a copy")
    try:
        assert any(f"folder {NY}/1_source_documents" in w for w in published.stale(copy / NY, repo=copy))
        code, out = _run(copy, "--check", NY)
        assert code == 1 and f"folder listing changed: {NY}/1_source_documents" in out, out
    finally:
        copied.unlink()
    assert published.stale(copy / NY, repo=copy) == []


def test_publishing_and_the_repo_walk_leave_out_the_same_names():
    """Review round 1 (F3): the listings a certificate keeps leave out the names tools make and what publish writes;
    the compile's one walk of the repo (rulebook._in_repo) must leave out exactly the same, or a certificate could miss
    a name the compile sees. One rule for both."""
    from rule_format import rulebook
    assert published._left_out is rulebook.generated_name
    assert published.PUBLISHED in rulebook.GENERATED_NAMES and published.SUFFIX == rulebook.PUBLISHED_SUFFIX
    for name in ("__pycache__", ".git", "bin", "obj", "x.egg-info", "general.published.json", published.PUBLISHED):
        assert rulebook.generated_name(name), name



def test_every_name_the_repos_gitignore_files_ignore_is_a_generated_name():
    """Review round 2 (P3): Rhino's <model>.rhl lock and .3dmbak backup (in .gitignore) sat beside committed models in
    folders Maine's compile walks, so opening a test model made its certificate stale. Every simple pattern of every
    .gitignore (a name, a folder, or *.suffix) is a name the listings and the repo walk leave out."""
    from fnmatch import fnmatch
    from rule_format import rulebook
    checked = 0
    for ignore in [REPO / ".gitignore", *REPO.glob("apps/*/.gitignore")]:
        for line in ignore.read_text(encoding="utf-8").splitlines():
            pattern = line.strip().rstrip("/")
            if not pattern or pattern.startswith("#") or "/" in pattern:
                continue                          # a path (under one folder), not a name: its last part is below
            name = pattern.replace("*", "x").replace("[cod]", "c")
            assert fnmatch(name, pattern), pattern
            if name.endswith(tuple(importlib.machinery.all_suffixes())):
                assert not rulebook.generated_name(name), pattern    # importable: it must show (the test below)
                continue
            assert rulebook.generated_name(name), (ignore.name, pattern)
            checked += 1
    assert checked >= 10
    # a path (under one folder): some part of it is a generated name, so the listings and the walk leave it out
    # (merge of #228 into PR #266: the pane's apartment answer, a path, was ignored but listed in Maine's certificate)
    paths = 0
    for ignore in [REPO / ".gitignore", *REPO.glob("apps/*/.gitignore")]:
        for line in ignore.read_text(encoding="utf-8").splitlines():
            pattern = line.strip().rstrip("/")
            if pattern and not pattern.startswith("#") and "/" in pattern:
                assert any(rulebook.generated_name(part.replace("*", "x")) for part in pattern.split("/")), pattern
                paths += 1
    assert paths >= 5


def test_a_rhino_lock_beside_a_model_leaves_mains_certificate_current(copy):
    models = copy / "test_data/host_conformance/models"
    lock = models / "01_box_house.rhl"
    assert models.is_dir()
    lock.write_bytes(b"locked")
    try:
        assert published.stale(copy / MAINE, repo=copy) == []
    finally:
        lock.unlink()


def test_a_compiled_module_beside_a_validator_module_makes_the_certificate_stale(copy):
    """Review round 3 (two sceptics): .pyd and .pyc names were left out of listings, but Python imports a compiled
    extension beside rulebook.py in its place, so stale() said current while a fresh compile ran other code. No
    name Python can import is a generated name."""
    from rule_format import rulebook
    assert not any(rulebook.generated_name("m" + s) for s in importlib.machinery.all_suffixes())
    shadow = copy / "packages/rule_format/rule_format" / f"state_law{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    shadow.write_bytes(b"not a module")
    try:
        assert any("packages/rule_format/rule_format" in w for w in published.stale(copy / MAINE, repo=copy))
    finally:
        shadow.unlink()
    assert published.stale(copy / MAINE, repo=copy) == []


def test_a_new_package_folder_makes_every_certificate_stale(copy):
    """Review round 4 (two sceptics): the fresh compile imports from every folder of packages/, before Python's own
    installation, but New York's certificates didn't list packages/ itself, so a new package folder (which could hold
    a module named like one the compile imports, yaml say) left them current while a fresh compile differed."""
    new = copy / "packages/aaa_new"
    new.mkdir()
    try:
        for law in LAWS:
            assert any("folder packages" in w for w in published.stale(copy / law, repo=copy)), law
        code, out = _run(copy, "--check", NY)
        assert code == 1 and "packages" in out, out
    finally:
        new.rmdir()
    assert [published.stale(copy / law, repo=copy) for law in LAWS] == [[]] * len(LAWS)


def test_a_same_size_edit_to_a_validator_module_is_compiled_from_its_source_never_its_old_cache(copy):
    """Review round 5 (two sceptics): the fresh compile could run a module's old __pycache__ .pyc after a same-size
    edit with its time kept (Python trusts a cache by its source's size and time to the second), so the certificate
    paired the new source's sha256 with the old code's answer, and neither stale() nor --check could see it. The
    compile now always runs the source the validator hashes: here the edit adds a problem, and publish refuses."""
    module = copy / "packages/rule_format/rule_format/state_law.py"
    kept, cert = module.read_bytes(), (copy / CERT).read_bytes()
    old, new = b'out = [] if isinstance(s.get("name")', b'out = [1]if isinstance(s.get("name")'
    assert kept.count(old) == 1 and len(old) == len(new)
    import importlib.util
    stat = module.stat()
    subprocess.run([sys.executable, "-c", f"import py_compile; py_compile.compile({str(module)!r}, "
                    f"cfile={importlib.util.cache_from_source(str(module))!r})"], check=True)   # the old code's cache
    try:
        module.write_bytes(kept.replace(old, new))
        os.utime(module, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        code, out = _run(copy, MAINE)
        assert code == 1 and "its law has a problem: 1" in out, out
    finally:
        module.write_bytes(kept)
        os.utime(module, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        (copy / CERT).write_bytes(cert)
    assert published.stale(copy / MAINE, repo=copy) == []

# ---- in-process -----------------------------------------------------------------------------------------------------

def test_the_typed_json_keeps_dates_and_sets_and_refuses_what_it_cant_keep():
    value = {"downloaded_on": datetime.date(2026, 11, 21), "groups": {"R-3", "B", "A-4"}, "n": [1, 2.5, None, True]}
    back = published._decode(json.loads(published.dumps(published._encode(value))))
    assert back == value and type(back["downloaded_on"]) is datetime.date and isinstance(back["groups"], set)
    assert published.dumps(published._encode({"s": {"b", "a"}})) == published.dumps(published._encode({"s": {"a", "b"}}))
    for bad in ({"$set": [1]}, {1: "a"}, float("nan"), object()):
        with pytest.raises(TypeError):
            published._encode(bad)


def test_stale_refuses_an_unknown_format_and_unreadable_certificates(tmp_path, monkeypatch):
    folder = REPO / MAINE
    book = building_code_rulebook(folder)
    path = tmp_path / "general.published.json"
    monkeypatch.setattr(published, "certificate_path", lambda f, b: path)
    for data, said in ((b"{", "isn't readable JSON"), (b'{"format": "gordium.published_law/0"}', "isn't a gordium"),
                       (b'{"format": "gordium.published_law/1"}', "isn't a gordium"), (b'{"format": "gordium.published_law/2"}', "can't be read as")):
        path.write_bytes(data)
        (why,) = published.stale(folder, book)
        assert said in why and "python -m rule_format publish" in why


def test_ensure_publishes_only_what_is_missing_or_stale(monkeypatch, tmp_path):
    """The pytest fixture's and the commands' entry: a current certificate is never compiled again."""
    calls = []
    monkeypatch.setattr(published, "LOCK", tmp_path / ".lock")
    monkeypatch.setattr(published, "published_folders", lambda repo=REPO: [(Path("a"), Path("a.yaml")),
                                                                           (Path("b"), Path("b.yaml"))])
    state = {"a": [], "b": ["stale (input changed: x)"]}
    monkeypatch.setattr(published, "stale", lambda f, b, repo=REPO: state[str(f)])
    monkeypatch.setattr(published, "publish", lambda f: calls.append(str(f)) or {})
    monkeypatch.setattr(published, "certificate_path", lambda f, b: tmp_path / str(f))
    assert published.ensure() == [] and calls == ["b"]
    calls.clear()
    (tmp_path / "b").write_text("{}", encoding="utf-8")          # there but stale: the commands only say so
    assert published.ensure(missing_only=True) == ["stale (input changed: x)"] and calls == []
    (tmp_path / "b").unlink()                                    # missing: published
    assert published.ensure(missing_only=True) == ["stale (input changed: x)"] and calls == ["b"]
    assert not (tmp_path / ".lock").exists()


def test_a_report_a_rule_cites_must_be_under_docs_research_where_certificates_list_it():
    """Review round 1 (F2's class, a sceptic's sweep): a rule's `report` was checked only to exist (a stat, which no
    audit event shows), wherever it was: one outside docs/research/ (a folder every certificate lists) could appear or
    go without the certificate going stale. A report must be under docs/research/."""
    from rule_format import rulebook
    assert rulebook._report_problems({"report": "docs/research/2026-10-20_architect_questions.md"}, "r") == []
    for elsewhere in ("packages/rule_format/README.md", "docs/research/../../packages/rule_format/README.md"):
        assert (REPO / elsewhere).is_file() and rulebook._report_problems({"report": elsewhere}, "r"), elsewhere


def test_a_certificate_keeps_the_repo_names_its_rules_mention_not_the_whole_repos_listing(copy):
    """Ithaca's zoning and Maine's rules ask whether a file a rule's notes name is in the repo (rulebook._in_repo, which
    walks the repo's names). A certificate keeps each name asked and its answer, not a listing of every folder the walk
    went through: with that, any new file anywhere (a Revit recording, a new test) made the certificate stale, and in
    the middle of a test session every check of that law needed review. A name asked that appears or goes still
    makes it stale."""
    cert = json.loads((copy / CERT).read_bytes())
    assert cert["repo_names"] and all(cert["repo_names"].values())
    assert not any(d.startswith(("test_data", "apps", "docs/revit")) for d in cert["listed"])
    elsewhere = copy / "test_data/a_new_recording.json"
    elsewhere.write_bytes(b"{}")
    try:
        assert published.stale(copy / MAINE, repo=copy) == []
    finally:
        elsewhere.unlink()
    name = next(iter(cert["repo_names"]))
    found = [p for p in copy.rglob(name) if not published._generated(p.relative_to(copy))]
    kept = {p: p.read_bytes() for p in found}
    for p in found:
        p.unlink()
    try:
        assert any(f"a file named {name} went from the repo" in w for w in published.stale(copy / MAINE, repo=copy))
    finally:
        for p, data in kept.items():
            p.write_bytes(data)
    assert published.stale(copy / MAINE, repo=copy) == []


def test_one_compile_works_out_what_its_certificates_share_once(monkeypatch):
    """Review round 1 of PR 4 (F1): a place has a certificate per district (21 for Ithaca), and each worked out the
    same inputs, listings and validator again (about 22 s of a 37 s publish). They are worked out once per folder."""
    ithaca = REPO / "regulations/jurisdictions/new_york/ithaca_city"
    calls = []
    real = published._shared
    monkeypatch.setattr(published, "_shared", lambda *a: calls.append(1) or real(*a))
    books = published.books_of(ithaca)[:3]                     # three districts, so three certificates
    monkeypatch.setattr(published, "books_of", lambda folder: books)
    monkeypatch.setattr(published, "compiled", lambda f, b: {"problems": [], "kinds": {}, "documents": {}})
    out = json.loads(published._child(str(ithaca), str(REPO), [], [True]))
    assert calls == [1] and len(out) == 3
