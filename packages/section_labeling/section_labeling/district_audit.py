"""The district coverage audit: is each district's zoning covered?

One generated table (`6_coverage_report/residential_districts.md`) answers it for every piece of the law labeled
`rule` or `flag` (3_section_labels) and every district a jurisdiction's audit lists. Each cell says one of:

    rulebook        the district's rulebook has a rule for it (which rule ids)
    flag            the district's rulebook flags it, so the architect sees NEEDS REVIEW (which ids)
    parked          on Ben's later list (which item)
    open_question   waiting on the architects or the City (a link to the question)
    not_applicable  the law itself keeps it out of this district (the reason, with the law's own words)
    missing         nothing covers it (why, how important, and whether every result already says so)

What a person decides (why a piece doesn't apply, what is parked, what is missing) is written once, by hand, in
`<jurisdiction>/residential_coverage.yaml`. Everything else is worked out here, from the files, and checked, so a
decision can't claim more than the files show:

- a rule named as covering a piece must exist in that district's rulebook, be of the right kind (`rulebook`: a
  rule; `flag`: a flag, or a rule that sends some cases to review), and cite the piece (a source or a finding's
  source inside the piece's lines, or a definition in 4_term_definitions that cites the piece and defines a
  measure the rule's formulas use). A rule that doesn't cite it may only be named with `mapped:`, the reason in
  words, shown in the table as Gordium's mapping, not a citation;
- every rule that cites a piece must be named in that piece's decisions for that district (`rules` or `also`),
  so a rulebook change can't leave a stale "not applicable" or "missing" beside a rule that now covers it;
- the law's words given for "not applicable" must really be on the page (the same matcher rule sources use);
- a parked item must be on the later list kept in the decisions file; an open question's link must exist;
- every rule and flag piece has decisions for every district, exactly once.

The second half lists every rule in every district's rulebook with the measures its formulas need (measured
from the model by model_measurement, stated by the architect, or neither) and the tests that check it on a
model in test_data/test_sites (a real Rhino model, or a scenario drawn by code from hand-worked YAML).

Plain code, no AI. The output is generated, never hand-edited; `python -m section_labeling audit --check` (CI)
fails when it differs from a fresh build, so a rulebook change that isn't regenerated fails.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from document_extraction.sections import piece_keys
from rule_format import formula
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, Context, load, locate, read_jsonl, rulebook_for

DECISIONS = "residential_coverage.yaml"
OUTPUT = "6_coverage_report/residential_districts.md"
LAW = "chapter_325_zoning_2026-10.pdf"
STATUSES = ("missing", "open_question", "parked", "flag", "rulebook", "not_applicable")    # worst first
WORDS = {"missing": "MISSING", "open_question": "open question", "parked": "parked", "flag": "flag (needs review)",
         "rulebook": "in the rulebook", "not_applicable": "not applicable"}
PRIORITIES = {"high": "a real design rule that should exist; a design can pass today that the law forbids",
              "medium": "a real rule that should exist; it turns on facts Gordium doesn't ask for yet",
              "low": "a narrow or cautious gap (a permission not used, a rare case, or a pointer)",
              "operational": "how a property is run or permitted, not what is drawn",
              "other_project": "a different kind of project (not a building on a residential lot)"}
DECISION_FIELDS = {"status", "rules", "also", "mapped", "why", "quote", "file", "page", "piece", "item", "link",
                   "priority", "note"}


def _law_rows(j: Path):
    header, pieces = load_pieces(j / "2_extracted_text" / f"{Path(LAW).stem}.sections.jsonl")
    labels = (load(j / "3_section_labels" / f"{Path(LAW).stem}.yaml") or {}).get("labels", {})
    return header, pieces, labels


def _formula_names(rule: dict) -> set[str]:
    texts = [rule.get("check"), rule.get("applies_when")] + [r.get("when") for r in rule.get("review_when") or []]
    return set().union(*(formula.names(t) for t in texts if t)) if any(texts) else set()


def citations(rule: dict, owner: dict, definitions: dict) -> dict[str, str]:
    """{piece id: how this rule cites it}: a source, a finding's source, or a definition of a measure it uses."""
    out: dict[str, str] = {}

    def add(sources, how):
        for s in sources or []:
            lines = s.get("lines") or []
            if s.get("file") != LAW or len(lines) != 2:
                continue
            for n in range(lines[0], lines[1] + 1):
                if (pid := owner.get((s.get("page"), n))) and pid not in out:
                    out[pid] = how
    add(rule.get("sources"), "cited")
    for f in rule.get("findings") or []:
        add(f.get("sources"), f"cited in finding {f.get('id', '?')}")
    used = _formula_names(rule)
    for term, (pieces, measures) in definitions.items():
        if used & measures:
            for pid in sorted(pieces):        # a set: sorted, so the output is the same on every run
                out.setdefault(pid, f"via definition {term}")
    return out


def _definitions(j: Path, owner: dict) -> dict[str, tuple[set, set]]:
    """{term: (pieces its sources sit in, measures it defines)} from 4_term_definitions/definitions.yaml."""
    path = j / "4_term_definitions/definitions.yaml"
    out = {}
    for term, e in ((load(path) or {}) if path.exists() else {}).items():
        pieces = {owner[(s["page"], n)] for s in e.get("sources") or [] if s.get("file") == LAW
                  and len(s.get("lines") or []) == 2 for n in range(s["lines"][0], s["lines"][1] + 1)
                  if (s["page"], n) in owner}
        out[term] = (pieces, set(e.get("measures") or []))
    return out


def disclosed_sections(j: Path) -> list[str]:
    """The sections every result already lists as not checked (not_checked_yet.yaml), as '325-16A'."""
    path = j / "not_checked_yet.yaml"
    entries = (load(path) or {}).get("not_covered", []) if path.exists() else []
    return [m for e in entries for m in re.findall(r"§\s*(325-[\dA-Z.]+)", str(e.get("section", "")))]


def is_disclosed(pid: str, sections: list[str]) -> bool:
    """§325-28 covers 325-28B and 325-28C; §325-2 doesn't cover 325-28C."""
    return any(pid == s or (pid.startswith(s) and pid[len(s)].isalpha() and pid[len(s)].isupper()) for s in sections)


def model_tests(j: Path) -> dict[str, list[str]]:
    """{rule id: [what checks it on a model]}, from test_data/test_sites/<place>: a design file's `compare` (each
    row of the architects' spreadsheet, checked on the site's Rhino models by model_measurement/tests/test_models.py)
    and a scenario's `expected` (and its `then`'s; design_checker/tests/test_scenarios.py)."""
    place = j.relative_to(REPO / "regulations/jurisdictions")
    root = REPO / "test_data/test_sites" / place
    out: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.yaml")) if root.exists() else []:
        data = load(path)
        if not isinstance(data, dict):
            continue
        rel = path.relative_to(root).as_posix()
        if isinstance(data.get("compare"), dict) and any(path.parent.glob("*.3dm")):
            for rid in data["compare"].values():
                out.setdefault(rid, []).append(f"real model {path.parent.name} ({rel})")
        expected = dict(data.get("expected") or {}) if isinstance(data.get("expected"), dict) else {}
        then = data.get("then")
        if isinstance(then, dict) and isinstance(then.get("expected"), dict):
            expected |= then["expected"]
        for rid in expected:
            out.setdefault(rid, []).append(f"scenario {path.stem.split('_')[0]}")
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def measure_sources() -> tuple[set, set]:
    """(measured from the model, stated by the architect): the names model_measurement fills in."""
    from model_measurement.measure import STATED, UNITS
    return set(UNITS), set(STATED) | {"district"}


class Audit:
    """Every decision resolved and checked, for one jurisdiction."""

    def __init__(self, j: Path, data: dict | None = None, books: dict[str, Path] | None = None):
        """`data`: the decisions (default: the jurisdiction's file); `books`: a rulebook file per district in
        place of rulebook_for's (tests change one without touching the repository)."""
        self.j = j
        self.problems: list[str] = []
        self.header, self.pieces, self.labels = _law_rows(j)
        self.data = (load(j / DECISIONS) or {}) if data is None else data
        self.districts: list[str] = list(self.data.get("districts") or [])
        self.parked: dict = dict(self.data.get("parked") or {})
        self.ctx = Context.for_jurisdiction(j)
        self.owner = {k: pid for pid, p in self.pieces.items() for k in piece_keys(p)}
        self.definitions = _definitions(j, self.owner)
        self.books: dict[str, dict[str, dict]] = {}
        for d in self.districts:
            path = (books or {}).get(d) or rulebook_for(j, d)
            if path is None:
                self.problems.append(f"{d}: no rulebook")
                self.books[d] = {}
                continue
            self.books[d] = {r["id"]: r for r in (load(path) or {}).get("rules", [])}
        self.cites = {d: {rid: citations(r, self.owner, self.definitions) for rid, r in rules.items()}
                      for d, rules in self.books.items()}
        self.disclosed = disclosed_sections(j)
        self.rows = [pid for pid in self.pieces if self.labels.get(pid, {}).get("label") in ("rule", "flag")]
        self.cells: dict[str, dict[str, list[tuple[str, dict]]]] = {}   # piece -> district -> [(part what, decision)]
        self._resolve()

    # -- reading and checking the decisions ------------------------------------------------------------------

    def _resolve(self):
        self.problems += [f"{DECISIONS}: unknown key {k!r} (reused decisions start with _)" for k in self.data
                          if k not in ("districts", "parked", "pieces") and not str(k).startswith("_")]
        self.problems += [f"parked {k}: needs `name` and `decided`" for k, v in self.parked.items()
                          if not (isinstance(v, dict) and v.get("name") and v.get("decided"))]
        given = self.data.get("pieces") or {}
        for pid in sorted(given.keys() - set(self.rows)):
            self.problems.append(f"{pid}: has decisions but isn't a rule or flag piece")
        for pid in self.rows:
            parts = given.get(pid)
            if not isinstance(parts, list) or not parts:
                self.problems.append(f"{pid}: no decisions (a list of parts, each with `what`)")
                continue
            cell = self.cells[pid] = {d: [] for d in self.districts}
            for i, part in enumerate(parts):
                where = f"{pid} part {i + 1}"
                if not isinstance(part, dict) or not part.get("what"):
                    self.problems.append(f"{where}: needs `what`")
                    continue
                for d, decision in self._spread(part, where).items():
                    self._check(pid, d, decision, f"{where} ({d})")
                    cell[d].append((part["what"], decision))
            for d in self.districts:
                named = {r for _, dec in cell[d] for r in self._expand(d, dec.get("rules", [])) + list(dec.get("also", []))}
                for rid, cited in self.cites[d].items():
                    if pid in cited and rid.split(".", 1)[1] not in named:
                        self.problems.append(f"{pid} ({d}): {rid} {cited[pid]} but no decision names it "
                                             "(add it to `rules`, or to `also` if it covers none of the parts)")

    def _spread(self, part: dict, where: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for key, decision in part.items():
            if key in ("what", "note"):
                continue
            names = self.districts if key == "all" else [k.strip() for k in str(key).split(",")]
            for d in names:
                if d not in self.districts:
                    self.problems.append(f"{where}: unknown district {d!r}")
                elif key != "all" and d in out and out[d] is not part.get("all"):
                    self.problems.append(f"{where}: {d} decided twice")
                elif key == "all" and d in out:
                    continue                      # a district's own decision wins over `all`
                else:
                    out[d] = decision if isinstance(decision, dict) else {}
        for d in self.districts:
            if d not in out:
                self.problems.append(f"{where}: no decision for {d}")
        if part.get("note"):
            out = {d: dict(dec, note=dec.get("note") or part["note"]) for d, dec in out.items()}
        return out

    def _expand(self, d: str, rules) -> list[str]:
        """Rule id suffixes; a trailing * matches every rule with that prefix, and '*' alone the whole rulebook."""
        out = []
        for r in rules or []:
            ids = [i.split(".", 1)[1] for i in self.books[d]]
            out += ["*"] if r == "*" else [i for i in ids if i.startswith(r[:-1])] if str(r).endswith("*") else [r]
        return out

    def _check(self, pid: str, d: str, dec: dict, where: str):
        p = self.problems
        status = dec.get("status")
        p += [f"{where}: unknown field {k!r}" for k in sorted(dec.keys() - DECISION_FIELDS)]
        if status not in STATUSES:
            p.append(f"{where}: status must be one of {STATUSES}")
            return
        if status in ("rulebook", "flag"):
            ids = self._expand(d, dec.get("rules"))
            if not ids:
                p.append(f"{where}: name the rules (`rules`)")
            uncited, reviews = [], False
            for rid in ids:
                if rid == "*":                    # the whole rulebook: only ever a mapping
                    uncited.append(rid)
                    continue
                rule = self.books[d].get(f"{d}.{rid}")
                if rule is None:
                    p.append(f"{where}: {d}.{rid} isn't in the rulebook")
                    continue
                if status == "rulebook" and rule.get("kind") != "rule":
                    p.append(f"{where}: {d}.{rid} is a {rule.get('kind')}, not a rule (status flag?)")
                reviews |= rule.get("kind") == "flag" or bool(rule.get("review_when"))
                if pid not in self.cites[d].get(f"{d}.{rid}", {}):
                    uncited.append(rid)
            if status == "flag" and ids and not reviews:
                p.append(f"{where}: none of {', '.join(ids)} ever says needs review (no flag, no review_when)")
            if uncited and not dec.get("mapped"):
                p.append(f"{where}: {', '.join(uncited)} don't cite the piece: say why in `mapped`, or name others")
            if dec.get("mapped") and not uncited and ids:
                p.append(f"{where}: every rule named cites the piece; drop `mapped`")
        for rid in dec.get("also") or []:
            if pid not in self.cites[d].get(f"{d}.{rid}", {}):
                p.append(f"{where}: `also` names {d}.{rid}, which doesn't cite the piece")
        if status in ("not_applicable", "missing", "open_question") and not dec.get("why"):
            p.append(f"{where}: say why (`why`)")
        if status == "not_applicable":
            if not dec.get("quote"):
                p.append(f"{where}: give the law's own words (`quote`)")
            elif not self._quote_found(pid, dec):
                p.append(f"{where}: quote not found: {dec['quote']!r}")
        if status == "parked" and dec.get("item") not in self.parked:
            p.append(f"{where}: parked item must be one of {sorted(self.parked)}")
        if status == "open_question":
            path, _, heading = str(dec.get("link", "")).partition("#")
            target = REPO / path
            if not path or not target.is_file():
                p.append(f"{where}: link {dec.get('link')!r} isn't a file in the repository")
            elif heading and heading not in target.read_text(encoding="utf-8"):
                p.append(f"{where}: {path} has no {heading!r}")
        if status == "missing" and dec.get("priority") not in PRIORITIES:
            p.append(f"{where}: priority must be one of {list(PRIORITIES)}")

    def _quote_found(self, pid: str, dec: dict) -> bool:
        file = dec.get("file", LAW)
        pages = self.ctx.pages.get(file, {})
        if "page" in dec:
            return bool(locate(dec["quote"], pages.get(dec["page"], {})))
        if dec.get("piece") not in (None, *self.pieces):
            return False
        keys = list(piece_keys(self.pieces[dec.get("piece", pid)]))   # inside a piece, across its page breaks
        joined = {i: pages.get(pg, {}).get(n, []) for i, (pg, n) in enumerate(keys)}
        return bool(locate(dec["quote"], joined))

    # -- the table ---------------------------------------------------------------------------------------

    def status(self, pid: str, d: str) -> str:
        found = {dec.get("status") for _, dec in self.cells.get(pid, {}).get(d, [])}
        return next((s for s in STATUSES if s in found), "missing")

    def _title(self, pid: str) -> str:
        return " ".join(self.pieces[pid]["title"].replace("|", "/").split())

    def _pages(self, pid: str) -> str:
        pages = sorted({pg for pg, _, _ in self.pieces[pid]["lines"]})
        return f"p.{pages[0]}" if len(pages) == 1 else f"pp.{pages[0]}–{pages[-1]}"

    def _short(self, pid: str, d: str) -> str:
        parts = self.cells.get(pid, {}).get(d, [])
        worst = self.status(pid, d)
        ids = list(dict.fromkeys(r for _, dec in parts if dec.get("status") in ("rulebook", "flag")
                                 for r in self._expand(d, dec.get("rules")) if r != "*"))
        whole = any("*" in (dec.get("rules") or []) for _, dec in parts)
        names = (", ".join(ids[:3]) + (f" +{len(ids) - 3} more" if len(ids) > 3 else "")) if ids else (
            "whole rulebook" if whole else "")
        if worst == "rulebook":
            return f"✓ {names}"
        if worst == "flag":
            return f"flag: {names}"
        text = {"missing": "**MISSING**", "open_question": "open question", "parked": "parked: " + ", ".join(
            dict.fromkeys(dec.get("item", "") for _, dec in parts if dec.get("status") == "parked")),
            "not_applicable": "n/a"}[worst]
        return text + (f" (partly ✓ {names})" if names and worst != "not_applicable" else "")

    def counts(self) -> dict[str, Counter]:
        return {d: Counter(self.status(pid, d) for pid in self.rows) for d in self.districts}

    def missing(self) -> list[dict]:
        """The gaps: each (what, why, priority, note, districts) once, with every piece it applies to (eleven
        nonconforming-use sections are one gap). Ranked by priority, then silent before already disclosed on every
        result, then the most districts, then the law's order."""
        found: dict[tuple, dict] = {}
        for order, pid in enumerate(self.rows):
            for i, what in enumerate(self._parts(pid)):
                groups: dict[tuple, list[str]] = {}
                for d in self.districts:
                    dec = self.cells[pid][d][i][1]
                    if dec.get("status") == "missing":
                        groups.setdefault((dec.get("priority"), dec.get("why"), dec.get("note", "")), []).append(d)
                for (priority, why, note), ds in groups.items():
                    key = (what, priority, why, note, tuple(ds), is_disclosed(pid, self.disclosed))
                    gap = found.setdefault(key, {"pieces": [], "what": what, "districts": ds, "priority": priority,
                                                 "why": why, "note": note, "disclosed": key[-1], "order": order})
                    gap["pieces"].append(pid)
        rank = list(PRIORITIES)
        return sorted(found.values(), key=lambda m: (rank.index(m["priority"]) if m["priority"] in rank else 9,
                                                     m["disclosed"], -len(m["districts"]), m["order"]))

    def _parts(self, pid: str) -> list[str]:
        first = self.districts[0] if self.districts else None
        return [what for what, _ in self.cells.get(pid, {}).get(first, [])]

    def _where(self, ds: list[str]) -> str:
        return f"all {len(ds)} districts" if ds == self.districts else ", ".join(ds)

    def _sections(self, pids: list[str]) -> str:
        if len(pids) == 1:
            return f"§{pids[0]} {self._title(pids[0])}"
        return ", ".join(f"§{p}" for p in pids)

    def _decision_text(self, pid: str, d: str, dec: dict) -> str:
        """One decision in words. Rule ids without the district, so districts decided alike read as one line."""
        s = dec["status"]
        if s in ("rulebook", "flag"):
            ids = [r for r in self._expand(d, dec.get("rules")) if r != "*"]
            how = [f"`{rid}`" + (f" ({cited})" if (cited := self.cites[d].get(f"{d}.{rid}", {}).get(pid))
                                 else " (mapped)") for rid in ids]
            text = f"{WORDS[s]}: " + ("the whole rulebook" if "*" in (dec.get("rules") or []) else ", ".join(how))
            if dec.get("mapped"):
                text += f". Gordium's mapping, not a citation: {dec['mapped']}"
        elif s == "not_applicable":
            where = (f"{dec.get('file', LAW)} p.{dec['page']}" if "page" in dec
                     else f"§{dec['piece']}" if dec.get("piece") else "this piece")
            text = f"not applicable: {dec['why']} The law: “{dec['quote']}” ({where})"
        elif s == "parked":
            item = self.parked[dec["item"]]
            text = f"parked: {item['name']} ({item['decided']})" + (f". {dec['why']}" if dec.get("why") else "")
        elif s == "open_question":
            text = f"open question: {dec['why']} ({dec['link']})"
        else:
            text = f"**MISSING** ({dec['priority']}): {dec['why']}"
        if dec.get("also"):
            text += f" (also cites the piece: {', '.join(f'`{r}`' for r in dec['also'])}; covers none of this part)"
        if dec.get("note"):
            text += f" Note: {dec['note']}"
        return text

    def render(self) -> str:
        n, ds = len(self.rows), self.districts
        counts = self.counts()
        total = Counter()
        for c in counts.values():
            total.update(c)
        labels = Counter(self.labels[pid]["label"] for pid in self.rows)
        missing = self.missing()
        top = [m for m in missing if m["priority"] in ("high", "medium")]
        rest = [m for m in missing if m["priority"] not in ("high", "medium")]
        everywhere = lambda ok: [pid for pid in self.rows if all(self.status(pid, d) in ok for d in ds)]
        every = lambda ok: len(everywhere(ok))
        anywhere = sum(1 for pid in self.rows if any(self.status(pid, d) == "missing" for d in ds))
        cells_by = {d: Counter(m["priority"] for m in missing for _ in m["pieces"] if d in m["districts"]) for d in ds}
        out = ["# Residential coverage: is each district's zoning covered?", "",
               "Generated by `python -m section_labeling audit` from the rulebooks (5_zoning_rules), the section labels, "
               f"the term definitions, model_measurement and test_data, with the decisions in `{DECISIONS}`. Never "
               "hand-edit; CI fails if it is out of date.", "",
               "## Summary", "",
               f"Every piece of Chapter 325 labeled **rule** ({labels['rule']}) or **flag** ({labels['flag']}), "
               f"{n} pieces, against each of the {len(ds)} residential districts ({', '.join(ds)}): {n * len(ds)} "
               "cells.", "",
               f"**In short.** {every({'rulebook', 'flag'})} pieces are in every district's rulebook (or flagged for "
               f"review): {', '.join('§' + p for p in everywhere({'rulebook', 'flag'}))}. "
               f"{every({'not_applicable'})} don't apply in any of these districts; {every({'parked'})} are "
               f"parked on the later list; {anywhere} are MISSING in at least one district. Of the gaps, {len(top)} are "
               "real rules that should exist (high or medium, listed first below); the rest are narrow or cautious "
               "gaps, how a property is run, or other kinds of project. Nothing here is a rule written in this table: "
               "the list says what is missing, ranked.", "",
               "Each cell says one of:", "",
               "- **in the rulebook**: the district's rulebook has a rule for it (the rule ids);",
               "- **flag (needs review)**: the rulebook flags it, so the architect sees NEEDS REVIEW;",
               "- **parked**: on Ben's later list;",
               "- **open question**: waiting on the architects or the City;",
               "- **not applicable**: the law itself keeps it out of the district (with the law's words);",
               "- **MISSING**: nothing covers it.", "",
               "A piece with several parts takes its worst part's status (MISSING first, then open question, parked, "
               "flag, in the rulebook, not applicable), so a cell never says more is covered than its weakest part. "
               "A rule counts as covering a piece only if it cites the piece (a source or finding inside its lines, "
               "or a definition from the piece that defines a measure the rule uses); otherwise the table marks it "
               "*mapped* and says why. The zoning chart's own cells are not rows here (each chart number is checked "
               "against the chart reader); the rules tables at the end list every rule, chart-based ones too.", "",
               "| Status | " + " | ".join(ds) + " | All |", "|---|" + "---|" * (len(ds) + 1)]
        for s in STATUSES:
            out.append(f"| {WORDS[s]} | " + " | ".join(str(counts[d][s]) for d in ds) + f" | {total[s]} |")
        out.append("| **pieces** | " + " | ".join(str(n) for _ in ds) + f" | {n * len(ds)} |")
        out += ["", "MISSING cells by priority (a piece missing in two parts counts twice):", "",
                "| Priority | " + " | ".join(ds) + " |", "|---|" + "---|" * len(ds)]
        out += [f"| {k} | " + " | ".join(str(cells_by[d][k]) for d in ds) + " |" for k in PRIORITIES]
        out += ["", f"### MISSING, ranked ({len(missing)} gaps)", "",
                "Ranked by how much each matters, then gaps no result mentions before ones every result already lists "
                "as not checked (`not_checked_yet.yaml`), then how many districts. Priorities:", ""]
        out += [f"- **{k}**: {v}" for k, v in PRIORITIES.items()]
        for heading, group, start in (("**Real rules that should exist** (high and medium; listed here, not written):",
                                       top, 1),
                                      ("**The rest** (low, operational, other projects):", rest, len(top) + 1)):
            out += ["", heading, ""]
            for k, m in enumerate(group, start):
                said = "every result lists it as not checked" if m["disclosed"] else "no result mentions it"
                out.append(f"{k}. **{m['what']}** ({self._sections(m['pieces'])}). {self._where(m['districts'])}; "
                           f"{m['priority']}; {said}. {m['why']}" + (f" Note: {m['note']}" if m["note"] else ""))
        out += ["", "## The table", "",
                "✓ = in the rulebook (rule ids); flag = the rulebook flags it (NEEDS REVIEW); n/a = not applicable; "
                "(partly ✓ …) = some parts are covered by those rules, the rest not. Each piece's reasons are in "
                "the next section.", "",
                "| Piece | Title | Label | " + " | ".join(ds) + " |", "|---|---|---|" + "---|" * len(ds)]
        for pid in self.rows:
            out.append(f"| §{pid} | {self._title(pid)} | {self.labels[pid]['label']} | "
                       + " | ".join(self._short(pid, d) for d in ds) + " |")
        out += ["", "## Each piece, part by part", ""]
        for pid in self.rows:
            out += [f"### §{pid} {self._title(pid)} ({self.labels[pid]['label']}, {self._pages(pid)})", ""]
            for i, what in enumerate(self._parts(pid)):
                out.append(f"- **{what}**")
                groups: dict[str, list[str]] = {}
                for d in ds:
                    groups.setdefault(self._decision_text(pid, d, self.cells[pid][d][i][1]), []).append(d)
                out += [f"  - {self._where(g)}: {t}" for t, g in groups.items()]
            out.append("")
        out += self._rules_section()
        return "\n".join(out) + "\n"

    def _rules_section(self) -> list[str]:
        model, stated = measure_sources()
        tests = model_tests(self.j)
        out = ["## Every rule in each rulebook: measured? tested on a model?", "",
               "**Measures**: each name the rule's formulas use, and where its value comes from: *model* = "
               "model_measurement measures it from the Rhino model; *stated* = the architect states it (the model "
               "can't show it); *none* = nothing fills it in, so the rule can only say needs review. A flag has no "
               "check: it always says needs review where it applies. **Tested on a model**: *real model* = the "
               "architects' Rhino models of a test site (model_measurement/tests/test_models.py checks this rule's "
               "result on them); *scenario* = a design worked by hand from the law, drawn by code and checked "
               "(design_checker/tests/test_scenarios.py, in test_data/test_sites/…/scenarios).", ""]
        for d in self.districts:
            rules = self.books[d]
            kinds = Counter(r.get("kind") for r in rules.values())
            tested = sum(1 for rid in rules if tests.get(rid))
            out += [f"### {d}: {kinds['rule']} rules, {kinds['flag']} flags; {tested} checked on a model", "",
                    "| Rule | Kind | Ch. 325 pieces it cites | Measures | Tested on a model |", "|---|---|---|---|---|"]
            for rid, rule in rules.items():
                cited = ", ".join(f"§{p}" for p in self.pieces if p in self.cites[d][rid]) or "— (the chart only)"
                names = sorted(_formula_names(rule))
                where = lambda n: "model" if n in model else "stated" if n in stated else "**none**"
                measures = ", ".join(f"{n} ({where(n)})" for n in names) or "—"
                out.append(f"| `{rid}` | {rule.get('kind')} | {cited} | {measures} | "
                           + (", ".join(tests.get(rid, [])) or "**none**") + " |")
            out.append("")
        return out


def build(j: Path, **kw) -> tuple[str | None, list[str]]:
    """(the report, problems). With any problem there is no report: a decision the files don't back is refused."""
    audit = Audit(j, **kw)
    if audit.problems:
        return None, audit.problems
    return audit.render(), []


def places() -> list[Path]:
    """Every jurisdiction with an audit decisions file."""
    return sorted(p.parent for p in (REPO / "regulations/jurisdictions").rglob(DECISIONS))
