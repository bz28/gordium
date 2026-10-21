"""The architect stress test, CI sample: random designs built from Gordium's own starting house by the edits an
architect makes, each checked by Gordium and by the independent oracle (oracle.py), with the invariants in
harness.py (a: never a false pass; a2: the tax-map promise; b: no false fail on a clear case; c: monotonic; d: the
same design drawn differently; e: live update and determinism; f: reasons and no crash).

    GORDIUM_STRESS_DESIGNS=3000 GORDIUM_STRESS_SEED=7 pytest packages/design_checker/tests/stress/test_stress.py -s

runs a longer one (the default sample keeps CI near a minute); harness.py runs one in parallel from the command
line. Same seed, same designs, same answers.

A violation that is a known finding (KNOWN, each with its regression test in test_stress_findings.py, marked
xfail until the PR that owns the code fixes it) is reported, not failed; anything else fails this test."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import harness  # noqa: E402
import oracle  # noqa: E402

DESIGNS = int(os.environ.get("GORDIUM_STRESS_DESIGNS", "150"))
SEED = int(os.environ.get("GORDIUM_STRESS_SEED", "20261020"))


def _design(v):
    return generate.build(v["lot"], v["case"]["edits"])[0]


def _jog_stepped_line(v):
    """F1: a false pass on the jog lot that goes away when the stepped line (x = 62) may also be a rear line."""
    if not (v["invariant"] == "a" and v["lot"] == "jog" and v["rule"] in ("R-1b.side_yards",
                                                                          "R-1b.accessory_buildings")):
        return False
    d = _design(v)
    lt = dict(d["lot"])
    stepped = [[62.0, 80.0], [62.0, 120.0]]
    lt["sides"] = {**lt["sides"], "east": [s for s in lt["sides"]["east"] if s != stepped]}
    lt["unsure"] = lt["unsure"] + [stepped]
    return oracle.verdicts({**d, "lot": lt})[v["rule"]]["verdict"] not in (oracle.FAIL, oracle.NOT_PASS)


def _tax_map_area(v):
    """F2, by its cause: on a tax-map lot, coverage or lot area passes with each line 1 ft in (Gordium's worst case
    for area) and fails with each line 2 ft in. One that fails even at 1 ft is a new bug, not F2."""
    if not (v["invariant"] == "a2" and v["rule"] in ("R-1b.lot_coverage", "R-1b.lot_area_one_family_detached")):
        return False
    d = _design(v)
    one_ft = oracle.verdicts(d, tolerance=True, tolerance_ft=1.0)[v["rule"]]["slack"]
    two_ft = oracle.verdicts(d, tolerance=True)[v["rule"]]["slack"]
    return one_ft >= -oracle.EPS and two_ft < -oracle.EPS


def _drawing_changes_height(v):
    """F3: the height changes with the drawing, on a house with a floor moved on its own."""
    if not (v["invariant"] == "d" and v["rule"] == "R-1b.height" and "floor blocks" not in v.get("what", "")):
        return False
    floors = [p for p in _design(v)["parts"] if p["kind"] == "floor"]
    return any(sorted(map(tuple, f["outline"])) != sorted(map(tuple, floors[0]["outline"])) for f in floors)


def _side_names_swap(v):
    """F5: drawn the other way round, the side yard rows trade names; the rule's status and the numbers stay."""
    if not (v["invariant"] == "d" and v["rule"] == "R-1b.side_yards" and "outlines drawn" in v.get("what", "")):
        return False
    d = _design(v)
    order = v["what"].split()[-1]
    a, b = harness.gordium(d), harness.gordium(d, order)
    rows = [sorted((i["status"], i["proposed"]) for i in harness.items_by_rule(r)["R-1b.side_yards"]) for r in (a, b)]
    return harness.statuses(a) == harness.statuses(b) and rows[0] == rows[1]


# finding id -> how to recognise it (test_stress_findings.py has each one's regression test)
# Every finding is fixed (F1, F3, F5: PR #18, 77796ee; F2: rhino-ui, carried up in d43e11f): their matchers stay
# for reading old reports but none is excused here, so a return of any of them fails CI.
MATCHERS = {"F1": _jog_stepped_line, "F2": _tax_map_area, "F3": _drawing_changes_height, "F5": _side_names_swap}
def _typed_below_drawn(v):
    """F6 (open, for #14): stories complies on a plain-solid house whose typed count is below its floor blocks."""
    return v["invariant"] == "a" and v["rule"] == "R-1b.stories" and \
        oracle.measure(_design(v))["stories_typed_short"]


def _rear_overhang_words(v):
    """F7 (open, for #18): drawn the other way round only the overhang words "toward the rear yard" change (the
    statuses and numbers are the same)."""
    if not (v["invariant"] == "d" and "outlines drawn" in v.get("what", "")):
        return False
    d = _design(v)
    a, b = harness.comparable(harness.gordium(d)), harness.comparable(harness.gordium(d, v["what"].split()[-1]))
    if len(a) != len(b) or any({**x, "reason": None} != {**y, "reason": None} for x, y in zip(a, b)):
        return False
    return all("toward the rear yard" in (x["reason"] or "") + (y["reason"] or "") for x, y in zip(a, b)
               if x["reason"] != y["reason"])


MATCHERS["F6"], MATCHERS["F7"] = _typed_below_drawn, _rear_overhang_words
def _plain_part_under_8_ft(v):
    """F8 (open, until #18 takes #14's definition): stories complies where every plain part that opens the count
    (#14: 7 ft or taller, or shorter but not at the ground) is under 8 ft (#18's own line), nothing standing typed."""
    if not (v["invariant"] == "a" and v["rule"] == "R-1b.stories"):
        return False
    d = _design(v)
    m = oracle.measure(d)
    if not m["stories_typed_short"]:
        return False
    ground = min(p["z0"] for p in d["parts"] if p["kind"] == "floor") if any(
        p["kind"] == "floor" for p in d["parts"]) else 0.0
    opening = [p for p in d["parts"] if p["kind"] == "solid" and (p["z1"] - p["z0"] >= 7 - 1e-6 or p["z0"] > ground)]
    return bool(opening) and all(p["z1"] - p["z0"] < 8 for p in opening)


def _wall_count_words(v):
    """F9 (open, for #18): drawn another way, only the number in "N walls without one" changes."""
    import re
    if not (v["invariant"] == "d" and "outlines drawn" in v.get("what", "")):
        return False
    d = _design(v)
    a, b = harness.comparable(harness.gordium(d)), harness.comparable(harness.gordium(d, v["what"].split()[-1]))
    words = re.compile(r"\d+ walls without one")

    def plain(rows):
        return [{**x, "reason": words.sub("N walls without one", x["reason"] or "")} for x in rows]
    return a != b and plain(a) == plain(b)


def _gapped_floor_blocks(v):
    """F10 (open): stories complies with a typed count below the floor blocks drawn, the blocks not one stack from
    the ground (a gap: the blocks above it aren't counted)."""
    if not (v["invariant"] == "a" and v["rule"] == "R-1b.stories"):
        return False
    d = _design(v)
    fl = sorted((p for p in d["parts"] if p["kind"] == "floor"), key=lambda p: p["z0"])
    gap = any(abs(b["z0"] - a["z1"]) > 1e-6 for a, b in zip(fl, fl[1:]))
    typed = d.get("typed_stories")
    return gap and typed is not None and typed < len(fl) and oracle.measure(d)["stories_typed_short"]


MATCHERS["F8"], MATCHERS["F9"], MATCHERS["F10"] = _plain_part_under_8_ft, _wall_count_words, _gapped_floor_blocks
def _side_row_names(v):
    """F11 (open, for #18): drawn another way, only the side yard rows' names change (compass or narrower/wider)."""
    if not (v["invariant"] == "d" and v["rule"] == "R-1b.side_yards" and "outlines drawn" in v.get("what", "")):
        return False
    d = _design(v)
    a, b = harness.comparable(harness.gordium(d)), harness.comparable(harness.gordium(d, v["what"].split()[-1]))

    def plain(rows):
        return sorted(str({**x, "name": None}) for x in rows)
    return a != b and plain(a) == plain(b)


MATCHERS["F11"] = _side_row_names
# open: F10 (#14), F11 (#18); F6-F9 fixed in #18: a return of those fails CI
KNOWN = {"F10": _gapped_floor_blocks, "F11": _side_row_names}


def known(v):
    return next((fid for fid, match in KNOWN.items() if match(v)), None)


@pytest.fixture(scope="module")
def fast():
    harness.fast_reads()
    yield
    harness.slow_reads()


def test_reading_the_citys_files_once_changes_no_result():
    """The stress test keeps the city's files after the first read (for speed). The same design checked with the
    real readers and with the kept copies gives exactly the same output."""
    harness.slow_reads()
    design, _ = generate.build("sample_tax", [{"op": "add_roof", "kind": "roof", "axis": 1, "over": 1.5,
                                               "fascia": 0.5, "inset": 3, "rise": 8}])
    slow = harness.gordium(design)
    harness.fast_reads()
    try:
        quick = harness.gordium(design)
    finally:
        harness.slow_reads()
    assert json.dumps(slow, sort_keys=True, default=str) == json.dumps(quick, sort_keys=True, default=str)


def test_the_architect_stress_sample(fast, capsys):
    out = harness.run(DESIGNS, SEED, workers=1, shrink_each=False, known=known)
    unknown = [v for v in out["violations"] if not v["known"]]
    with capsys.disabled():
        print(f"\nstress test: {out['designs']} designs (seed {out['seed']}) in {out['seconds']} s; invariants run: "
              f"{out['checks_run']}; designs with a violation: {out['violating_designs']}; oracle undecided by rule: "
              f"{out['undecided']}")
        for v in out["violations"]:
            print(f"  {v['known'] or 'NEW'} {v['severity']} {v['invariant']} {v['rule']} {v.get('what', '')} "
                  f"{v['lot']} {json.dumps(v['case']['edits'])}")
    if os.environ.get("GORDIUM_STRESS_OUT"):
        Path(os.environ["GORDIUM_STRESS_OUT"]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    assert out["checks_run"]["a"] == DESIGNS and out["checks_run"]["f"] == DESIGNS
    assert min(out["checks_run"][k] for k in ("c", "d", "e")) > 0
    assert not unknown, "new violations (not a known finding): " + json.dumps(unknown, default=str)[:4000]


# ---- review round 2 pins ------------------------------------------------------------------------------------------

def _forced(monkeypatch, rule):
    """Gordium made to say `rule` complies on every row (a planted false pass)."""
    real = harness.run_site

    def run_site(site, facts, extras=None):
        res = real(site, facts, extras)
        for item in res["view"]["items"]:
            if item.get("rule") == rule:
                item["status"] = harness.COMPLIES
        return res
    monkeypatch.setattr(harness, "run_site", run_site)


def test_a_new_false_pass_is_never_merged_into_a_known_findings_entry(fast, monkeypatch):
    """Round 2, P1: two jog-lot designs, each a false pass on the side yards (planted). The first is a known
    finding, the second is not: it must come back as its own, unrecognised violation (merging first and asking
    'known?' only of the kept one hid it)."""
    first = {"op": "move_house", "dx": 19, "dy": 0}
    second = {"op": "move_house", "dx": -6, "dy": 0}
    cases = iter([{"lot": "jog", "edits": [e], "deep": {}, "probe": {}} for e in (first, second)])
    monkeypatch.setattr(generate, "random_case", lambda rng: next(cases))
    _forced(monkeypatch, "R-1b.side_yards")
    out = harness.run(2, 0, shrink_each=False, known=lambda v: "FX" if v["case"]["edits"] == [first] else None)
    side = [v for v in out["violations"] if v["invariant"] == "a" and v["rule"] == "R-1b.side_yards"]
    assert [v["known"] for v in side if v["case"]["edits"] == [second]] == [None]
    assert [v["known"] for v in side if v["case"]["edits"] == [first]] == ["FX"]


def test_f2_is_recognised_by_its_cause_not_by_its_rule(fast, monkeypatch):
    """Round 2, P2: the tax-map lot's starting house (49'-0" x 30'-3") pulled 2 ft back (1,580 sf). With each lot
    line 1 ft in (the old area worst case, F2) it already fails: 1,580 > 25% of 71 x 88 = 1,562. A 'complies' there
    is not F2 (Gordium losing its tolerance altogether would look like this): it must not be taken for F2. The same
    house 3 in. back instead (1,494.5 sf) is F2's cause exactly: passes at 1 ft per line, fails at 2 ft."""
    case = {"lot": "sample_tax", "edits": [{"op": "stretch", "face": 1, "amount": 2.0}]}
    d, _ = generate.build(case["lot"], case["edits"])
    _forced(monkeypatch, "R-1b.lot_coverage")
    found = [v for v in harness.check_answers(d, harness.gordium(d))
             if v["invariant"] == "a2" and v["rule"] == "R-1b.lot_coverage"]
    assert found
    assert _tax_map_area({**found[0], "lot": case["lot"], "case": case}) is False
    assert known({**found[0], "lot": case["lot"], "case": case}) is None
    just_over = [{"op": "stretch", "face": 1, "amount": 0.25}]     # F2 itself: passes at 1 ft, fails at 2 ft
    assert _tax_map_area({"invariant": "a2", "rule": "R-1b.lot_coverage", "lot": "sample_tax",
                          "case": {"edits": just_over}}) is True
