"""The worker's check_site takes the house's inside (protocol 1.2): `interior`, an interior description, beside the
site description. The egress laws are checked on it exactly as a direct check is; without one they wait; one that
can't be read never complies (docs/protocol/site_description_v1.md, "How the worker uses it";
docs/revit/revit_interior_reading_design.md, section 5)."""

import json
import sys

import pytest

from design_checker import conformance, egress, present
from design_checker.__main__ import answer
from design_checker.check import check_description
from design_checker import protocol
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
from test_egress import SILL, ranch, sill_too_high  # noqa: E402

SCENE = conformance.scenes()["01_box_house"]
SITE = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
FACTS = conformance.facts(SCENE)


def worker_check(interior=None, version="1.2", **more):
    """check_site through the worker, every field sent as JSON text, as the Revit add-in sends it."""
    request = {"id": 1, "cmd": "check_site", "protocol": version, "site": SITE, "facts": dict(FACTS), **more}
    if interior is not None:
        request["interior"] = interior
    reply = answer(json.loads(json.dumps(request)))
    assert reply["ok"], reply
    return reply["result"]


def egress_section(result):
    return next(s for s in result["sections"] if s["key"] != "zoning")


def law_rows(result, rule_id):
    return [i for i in result["view"]["items"] if i["group"] == present.LAW_GROUP and i["rule"] == rule_id]


def test_the_worker_speaks_1_2():
    assert protocol.PROTOCOL == "1.2"
    assert answer({"id": 1, "cmd": "hello", "protocol": "1.2"})["result"]["protocol"] == "1.2"


def test_the_examples_name_the_protocol_the_worker_speaks():
    """The worker's own help and the site description's page show the version a tool should send: today's."""
    import re
    from design_checker import __main__ as worker
    page = (REPO / "docs/protocol/site_description_v1.md").read_text(encoding="utf-8")
    shown = re.findall(r'"protocol": "(\d+\.\d+)"', (worker.__doc__ or "") + page)
    assert shown and set(shown) == {protocol.PROTOCOL}, shown


def test_a_report_with_an_interior_keeps_its_fingerprint_and_says_the_interior_itself_isnt_kept(tmp_path):
    """Principle 5: a saved report's egress rows trace to their interior. Today by its fingerprint, written in the
    report; the interior itself isn't kept beside the report yet (the reader's step keeps it), and the docs say so,
    so no one takes the report for reproducible from what is beside it."""
    from openpyxl import load_workbook
    report = tmp_path / "check.xlsx"
    result = worker_check(ranch(), report=str(report))
    assert result["report_error"] is None and report.exists()
    sha = egress.fingerprint(ranch())
    cells = [str(c.value) for ws in load_workbook(report).worksheets for row in ws.iter_rows() for c in row if c.value]
    assert any(sha in c for c in cells), "the report names the interior it was worked out from"
    assert not list(tmp_path.glob("*interior*")), "if the interior is now kept beside the report, update the docs and this test"
    page = (REPO / "docs/protocol/site_description_v1.md").read_text(encoding="utf-8")
    assert "the interior itself isn't kept beside the report" in page
    note = (REPO / "docs/revit/revit_interior_reading_design.md").read_text(encoding="utf-8")
    assert "don't pass it yet" not in note and "Not yet: keeping\n  the interior beside a saved report" in note


def test_an_interior_sent_to_the_worker_is_checked_exactly_as_a_direct_check():
    direct = check_description(SITE, dict(FACTS), interior=ranch())
    sent = worker_check(ranch())
    assert sent["egress"]["results"] == direct["egress"]["results"]
    assert sent["egress"]["interior_sha256"] == direct["egress"]["interior_sha256"] == egress.fingerprint(ranch())
    assert egress_section(sent)["state"] != egress.WAITING
    assert not any(i["id"] == "egress.waiting" for i in sent["view"]["items"])


def test_the_rows_turn_on_the_interior_sent():
    """The worked example (test_egress): the ranch's Bedroom 1 casement raised to a 48 in sill fails R319.2.3."""
    assert {r["status"] for r in law_rows(worker_check(ranch()), SILL)} == {present.COMPLIES}
    raised = law_rows(worker_check(sill_too_high()), SILL)
    assert present.FAILS in {r["status"] for r in raised}


def test_without_an_interior_egress_waits_as_before():
    result = worker_check()
    assert egress_section(result)["state"] == egress.WAITING
    assert result["egress"]["interior_sha256"] is None
    assert any(i["id"] == "egress.waiting" for i in result["view"]["items"])


@pytest.mark.parametrize("bad", ["not a house", [], {"format": "gordium.interior/1", "units": "in"},
                                 {"format": "gordium.interior/9", "units": "in", "rooms": []}])
def test_an_interior_that_cant_be_read_never_complies(bad):
    result = worker_check(bad)
    assert egress_section(result)["state"] != present.COMPLIES
    assert result["view"]["state"] != present.COMPLIES


def test_a_request_naming_an_older_minor_version_is_answered_with_its_interior_too():
    """A minor version only adds: the field is read whatever 1.x the request names (as extras.left_out_advice is)."""
    assert worker_check(ranch(), version="1.1")["egress"]["results"] == worker_check(ranch())["egress"]["results"]
