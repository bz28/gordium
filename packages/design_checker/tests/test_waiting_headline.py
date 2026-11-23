"""Choice B (Ben, 2026-11-15): when zoning complies and egress has nothing to check yet because no rooms are drawn,
the headline reads "Zoning complies · Egress waiting: no rooms drawn yet", shown in a neutral grey "waiting" style
(not amber, no "?" mark). Only the look changes: the design's state stays needs review, never complies, in the
check's JSON, the command line's line, the Rhino panel and the Revit worker's answer.

What is pinned here:
- the headline's words, the waiting reason taken from the waiting item itself (another reason is said as it is);
- `waiting_only` is true only when zoning complies AND every law section is waiting or complies (one at least
  waiting), false when zoning fails or needs review or has nothing counted, or a law fails or needs review;
- the overall state is still needs review with `waiting_only` (view, sections, the result's line);
- the grey: rhino_logic's headline_state / headline_mark / headline_rgb, and the Rhino plugin wired to them.
"""

import copy
import sys

import pytest

from design_checker import egress, present
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))   # egress_house beside this file
import egress_house  # noqa: E402
from design_checker import rhino_logic as logic
from design_checker.check import check_site, summary
from host_source import host_text
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_egress import FACTS, ITHACA, SITE  # noqa: E402
from test_overlays_none_found import EVERY, NONE_FOUND, TODAY  # noqa: E402
from test_overlays_none_found import SITE as SAMPLE_LOT  # noqa: E402

RHINO = host_text("rhino", "plugin", purpose="wiring")
UI = host_text("rhino", "ui", purpose="wiring")
LAWS = egress.laws(ITHACA)


def body(src, name, until):
    return src[src.index(name):src.index(until, src.index(name) + len(name))]


def zoning(*statuses):
    return [{"id": f"R-1b.rule_{n}", "rule": f"R-1b.rule_{n}", "name": f"Rule {n}", "group": "building", "status": s}
            for n, s in enumerate(statuses)]


def law_item(short, status, waiting=None, n=0):
    item = {"id": f"{short.lower()}.{n}", "rule": None, "name": f"{short}: row {n}", "group": present.LAW_GROUP,
            "status": status, "law": short + " law", "law_short": short, "law_key": "x/" + short.lower()}
    return dict(item, waiting=waiting) if waiting else item


def section(short, state):
    return {"key": "x/" + short.lower(), "title": short + " law", "state": state, "summary": state}


def waiting_law(short="Egress", reason=egress.WAITING_REASON):
    return [law_item(short, present.NOT_CHECKED, waiting=reason)], section(short, egress.WAITING)


def viewed(zoning_items, *laws):
    """add_to_view over hand-made laws: each (items, section)."""
    got = {"items": [i for items, _ in laws for i in items], "sections": [s for _, s in laws]}
    view = {"items": copy.deepcopy(zoning_items)}
    egress.add_to_view(view, got, "City of Ithaca")
    return view


# ---- the headline's words --------------------------------------------------------------------------------------------

def test_the_headline_reads_zoning_complies_egress_waiting_no_rooms_drawn_yet():
    view = {"items": zoning(present.COMPLIES, present.COMPLIES)}
    egress.add_to_view(view, egress.check(LAWS, None, dict(egress_house.HOUSE), {}), "City of Ithaca")     # the real waiting egress
    assert view["summary"] == "Zoning complies · Egress waiting: no rooms drawn yet"
    assert view["waiting_only"] is True and view["state"] == present.REVIEW


def test_the_waiting_words_are_the_waiting_items_own_reason():
    """Another reason a law waits is said as the item gives it, never "no rooms drawn yet" by default."""
    items, _ = waiting_law(reason="the interior is being read")
    assert present.summary(zoning(present.COMPLIES) + items) == \
        "Zoning complies · Egress waiting: the interior is being read"
    assert egress._waiting_item(LAWS["laws"][0])["waiting"] == egress.WAITING_REASON == "no rooms drawn yet"


def test_zoning_keeps_its_counts_when_it_does_not_comply_and_a_law_with_rows_keeps_its_own():
    items, _ = waiting_law()
    assert present.summary(zoning(present.FAILS, present.COMPLIES) + items) == \
        "Zoning: 1 does not comply · 1 complies · Egress waiting: no rooms drawn yet"
    rows = [law_item("Egress", present.FAILS), law_item("Egress", present.COMPLIES, n=1)]
    assert present.summary(zoning(present.COMPLIES) + rows) == "Zoning complies · Egress: 1 does not comply · 1 complies"


# ---- waiting_only: only zoning complying and every law waiting or complying ------------------------------------------

def test_waiting_only_when_zoning_complies_and_every_law_waits_or_complies():
    assert viewed(zoning(present.COMPLIES), waiting_law())["waiting_only"] is True
    other = ([law_item("Fire", present.COMPLIES)], section("Fire", present.COMPLIES))
    assert viewed(zoning(present.COMPLIES), waiting_law(), other)["waiting_only"] is True
    assert viewed(zoning(present.COMPLIES), waiting_law(), waiting_law("Fire"))["waiting_only"] is True


@pytest.mark.parametrize("zoning_items", [zoning(present.FAILS, present.COMPLIES),
                                          zoning(present.REVIEW, present.COMPLIES),
                                          zoning(present.NOT_CHECKED, present.COMPLIES),
                                          zoning()],
                         ids=["zoning fails", "zoning needs review", "zoning waits on a fact", "nothing counted"])
def test_not_waiting_only_when_zoning_does_not_comply(zoning_items):
    view = viewed(zoning_items, waiting_law())
    assert view["waiting_only"] is False and view["state"] != present.COMPLIES
    assert not view["summary"].startswith("Zoning complies")


@pytest.mark.parametrize("status", [present.FAILS, present.REVIEW])
def test_not_waiting_only_when_a_law_has_a_real_failure_or_review(status):
    # a fail is held by the state already (never needs review); the review case holds "every law waits or complies"
    other = ([law_item("Fire", status)], section("Fire", status))
    view = viewed(zoning(present.COMPLIES), waiting_law(), other)
    assert view["waiting_only"] is False and view["state"] == status


def test_not_waiting_only_when_egress_checked_rows():
    rows = [law_item("Egress", present.COMPLIES), law_item("Egress", present.REVIEW, n=1)]
    view = viewed(zoning(present.COMPLIES), (rows, section("Egress", present.REVIEW)))
    assert view["waiting_only"] is False and view["state"] == present.REVIEW


def test_not_waiting_only_when_everything_complies():
    """Nothing waits: the design complies, and waiting_only (a needs review's look) never applies to it."""
    view = viewed(zoning(present.COMPLIES), ([law_item("Egress", present.COMPLIES)], section("Egress", present.COMPLIES)))
    assert view["state"] == present.COMPLIES and view["waiting_only"] is False


# ---- never a pass ----------------------------------------------------------------------------------------------------

def test_waiting_only_keeps_the_state_at_needs_review_everywhere():
    """A real check of the sample lot with every fact answered and no overlay found: zoning complies, egress waits."""
    r = check_site(SAMPLE_LOT, dict(EVERY, overlays_none_found=NONE_FOUND), today=TODAY)
    v = r["view"]
    assert v["waiting_only"] is True and v["summary"] == "Zoning complies · Egress waiting: no rooms drawn yet"
    assert v["state"] == present.REVIEW                                   # the JSON's state: never complies
    assert r["summary"]["state"] == "review" and r["summary"]["text"] == v["summary"]   # the command line's line
    assert [s["state"] for s in v["sections"]] == [present.COMPLIES, egress.WAITING]
    assert summary([{"Error": "PASS", "Requirement": "x", "Rule id": "R-1b.x"}], v["items"])["state"] == "review"


def test_the_check_with_unanswered_facts_is_not_waiting_only():
    v = check_site(SITE, dict(FACTS))["view"]
    assert v["waiting_only"] is False and v["state"] == present.REVIEW


# ---- the grey: rhino_logic, and the Rhino plugin wired to it -------------------------------------------------------

def test_the_headline_is_shown_waiting_only_for_a_needs_review_the_check_called_waiting_only():
    assert logic.headline_state({"state": present.REVIEW, "waiting_only": True}) == logic.WAITING == "waiting"
    assert logic.headline_state({"state": present.REVIEW, "waiting_only": False}) == present.REVIEW
    assert logic.headline_state({"state": present.REVIEW}) == present.REVIEW
    for state in (present.FAILS, present.COMPLIES):         # never a fail shown calm, never a pass shown as waiting
        assert logic.headline_state({"state": state, "waiting_only": True}) == state
    assert logic.headline_state({"waiting_only": True}) == logic.WAITING   # no state: needs review, never complies
    assert logic.headline_state({}) == logic.headline_state(None) == present.REVIEW


def test_the_waiting_headline_has_no_mark_and_a_neutral_grey_of_its_own():
    assert logic.headline_mark(logic.WAITING) == ""
    assert logic.headline_mark(present.REVIEW) == "?" and logic.headline_mark(present.FAILS) == "✕"
    assert logic.headline_mark(present.COMPLIES) == logic.headline_mark("stale") == ""
    amber, plain = ((138, 88, 0), (233, 180, 76)), ((36, 40, 44), (225, 228, 230))   # gordium_ui.status_color's
    for dark in (False, True):
        r, g, b = grey = logic.headline_rgb(logic.WAITING, dark)
        assert max(r, g, b) - min(r, g, b) <= 12                           # neutral: no hue
        assert grey not in (amber[dark], plain[dark])
        assert sum(abs(x - y) for x, y in zip(grey, plain[dark])) >= 150   # clearly apart from the complying ink
    for state in (present.REVIEW, present.FAILS, present.COMPLIES, "stale"):
        assert logic.headline_rgb(state, False) is None and logic.headline_rgb(state, True) is None
    assert f"FromArgb({amber[0][0]}, {amber[0][1]}, {amber[0][2]})" in body(UI, "def status_color(", "\ndef ")
    assert f"FromArgb({plain[1][0]}, {plain[1][1]}, {plain[1][2]})" in body(UI, "def status_color(", "\ndef ")


def test_the_rhino_plugin_shows_the_waiting_headline_grey_without_a_mark():
    apply = body(RHINO, "def _check_apply(", "\ndef ")
    assert 'o.message = (logic.headline_state(view), view["summary"],' in apply
    draw = body(RHINO, "def draw_screen(", "\ndef _status_rows(")
    assert 'logic.WAITING: logic.WAITING}.get(state, "complies"), dark)' in draw
    assert "mark = logic.headline_mark(state)" in body(RHINO, "def _status_rows(", "\ndef ")
    color = body(UI, "def status_color(", "\ndef ")
    assert color.index("grey = logic.headline_rgb(status, dark)") < color.index('if status == "does_not_comply"')
    assert 'if status not in ("does_not_comply", "needs_review", logic.WAITING):' in \
        body(UI, "def eto_status_color(", "\ndef ")
    header = body(UI, "def _header(", "\ndef ")
    assert "waiting = view is not None and logic.headline_state(view) == logic.WAITING" in header
    assert 'eto_status_color(logic.WAITING) if waiting' in header
