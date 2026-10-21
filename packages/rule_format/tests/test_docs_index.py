"""The docs index (docs/README.md) lists every document, links only to files that exist, and every document in
docs/ opens with the standard header (Purpose, For, Kept current by).

A newcomer finds documents through the index, so a document missing from it is as good as lost, and a broken
link is a dead end. The header says in three lines what a document is for, who it is for and who keeps it
current, so a reader knows at once whether to read on.
"""

import re

from rule_format.rulebook import REPO

INDEX = REPO / "docs" / "README.md"
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADER = ("**Purpose:**", "**For:**", "**Kept current by:**")


def _documents():
    """Every document the index must list: all of docs/, every README in packages/, regulations/, apps/ and
    test_data/, and every other Markdown page in apps/ (the quickstart). Dated eval records count too."""
    found = set(REPO.glob("docs/**/*.md")) - {INDEX}
    for root in ("packages", "regulations", "apps", "test_data"):
        found |= set((REPO / root).rglob("README.md"))
    found |= set((REPO / "apps").rglob("*.md"))
    return {p.relative_to(REPO).as_posix() for p in found}


def _links(text, base):
    """Each relative link in `text`, as a path from the repository root (anchors dropped)."""
    out = set()
    for target in LINK.findall(text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue                                            # a web link or a link inside the page
        out.add((base / target.split("#")[0]).resolve().relative_to(REPO.resolve()).as_posix())
    return out


def test_every_document_is_in_the_index():
    listed = _links(INDEX.read_text(encoding="utf-8"), INDEX.parent)
    missing = sorted(_documents() - listed)
    assert not missing, f"add these to docs/README.md: {missing}"


def test_every_link_in_the_index_exists():
    listed = _links(INDEX.read_text(encoding="utf-8"), INDEX.parent)
    broken = sorted(p for p in listed if not (REPO / p).exists())
    assert not broken, f"docs/README.md links files that don't exist: {broken}"


def test_every_doc_opens_with_the_standard_header():
    """The three header lines sit right under the title, before any other text."""
    missing = []
    for path in sorted(REPO.glob("docs/**/*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        top = lines[2:5]
        if not (lines[0].startswith("# ") and len(top) == 3
                and all(line.startswith(h) for line, h in zip(top, HEADER))):
            missing.append(path.relative_to(REPO).as_posix())
    assert not missing, f"these docs need the Purpose / For / Kept current by header under the title: {missing}"


def test_the_checks_see_real_files():
    """Guards the tests above against passing on nothing (a wrong REPO or glob)."""
    assert len(_documents()) > 10 and "docs/how_rules_are_checked.md" in _documents()
