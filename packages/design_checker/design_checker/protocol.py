"""The worker's protocol version and what it says about itself (`hello`), for any design tool that talks to it.

A request to a new-style command (`hello`, `read_model`) names the protocol it speaks, {"protocol": "1.0", ...}: a
different major version is refused, since the two sides would read the same words differently. The five older
commands (check, start, facts, options, sample_site) are answered with or without it, exactly as before. Every
new-style answer carries `about()`: the protocol, the site description version, and fingerprints of the worker's
code (with the data it loads) and of each place's files a check reads, worked out again for every answer (about
30 ms), so any answer can be traced to exactly what gave it, even after a rule is edited while the worker runs.
"""

import hashlib
from pathlib import Path

from rule_format.place import places
from rule_format.rulebook import REPO

from .site_json import SCHEMA

PROTOCOL = "1.0"
LEGACY = ("check", "start", "facts", "options", "sample_site")


def _sha(files, root: Path) -> str:
    """sha256 over files, each by its path under `root` and its bytes, in path order."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode("utf-8") + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def _kept(path: Path) -> bool:
    """A file (its path under packages/) that is part of what the worker runs: not a cache, a test, or a hidden or packaging file."""
    return not any(p in ("__pycache__", "tests") or p.startswith(".") or p.endswith(".egg-info") for p in path.parts) \
        and path.suffix not in (".pyc", ".pyo")


def code_files() -> list[Path]:
    """Every file of every package (its code and the data it loads, such as rule_format/measures.yaml), tests and
    caches left out: a check reaches into most of them (project_report decides each row), so all are counted. And
    the shared files every check reads too: under regulations/ outside any place's folder (the rule topics,
    document_extraction_guide/vocabulary.yaml, and who may approve, reviewers.yaml: rule_format.rulebook), and the
    research reports under docs/research/ that definitions and rules cite (each cited heading must be there)."""
    packages, regulations = REPO / "packages", REPO / "regulations"
    shared = [f for f in regulations.rglob("*") if f.is_file() and "jurisdictions" not in f.relative_to(regulations).parts
              and not f.name.startswith(".")]
    shared += [f for f in (REPO / "docs/research").rglob("*") if f.is_file() and not f.name.startswith(".")]
    return [f for f in packages.rglob("*") if f.is_file() and _kept(f.relative_to(packages))] + shared


def place_files(folder: Path) -> list[Path]:
    """Every file of a place's folder a check can read: its settings, rules, definitions, labels, extracted text,
    what isn't checked yet; of its source documents only sources.yaml (their fingerprints), not the PDFs."""
    return [f for f in Path(folder).rglob("*") if f.is_file() and not f.name.startswith(".")
            and (f.parent.name != "1_source_documents" or f.name == "sources.yaml")]


def worker_fingerprint() -> str:
    """sha256 over the checker's code and the data it loads, shared rule files included (code_files), read now."""
    return _sha(code_files(), REPO)


def rulebook_fingerprints() -> dict:
    """{place: sha256 over the files of its folder a check can read (place_files)}, read now: the rules are read
    again at every check, so a rule edited while the worker runs shows here at once."""
    return {p.key: _sha(place_files(p.folder), p.folder) for p in places()}


def about() -> dict:
    return {"protocol": PROTOCOL, "site_schema": SCHEMA, "worker_fingerprint": worker_fingerprint(),
            "rulebook": rulebook_fingerprints()}


def speaks(request: dict) -> None:
    """Refuse (ValueError) a new-style request that doesn't name protocol 1.x."""
    said = request.get("protocol")
    if not isinstance(said, str) or said.split(".")[0] != PROTOCOL.split(".")[0]:
        raise ValueError(f"protocol {said!r} not spoken: this worker speaks {PROTOCOL} (send \"protocol\": "
                         f"\"{PROTOCOL}\"; a different major version is refused)")
