"""How old the address lookup's "no overlay on this lot" is, said beside it, and when it stops counting (Ben,
2026-11-12; principle 4: an old or undated lookup never clears the overlays row).

    the host says the day of the check ("today", YYYY-MM-DD: the plugin's rhino_logic.city_day); the checker never
        reads the clock (principle 3: the same design, saved facts and day give the same answer)
    a finding at most present.LOOKUP_FRESH_DAYS (90) days old on that day  ->  the row is left out, and the site lines
        say "flood map and City maps looked up 2 months ago (2026-08-14)"
    older, dated after today, undated, or no day given  ->  the row stays (needs review) and says why, with the date

Every expected day count and age below is worked out by hand on a calendar, never by the code under test:
2026-08-14 -> 2026-11-12 is 17 + 30 + 31 + 12 = 90 days; 2026-08-13 is 91."""
import datetime as dt
import sys

import openpyxl
import pytest

from design_checker import __main__ as worker
from design_checker import present
from design_checker.check import check, check_site
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_overlays_none_found import EVERY, NONE_FOUND, SITE, _model, release_rows  # noqa: E402

TODAY = "2026-11-12"


def facts_found_on(date):
    return dict(EVERY, overlays_none_found=dict(NONE_FOUND, date=date))


def overlays_row(v):
    return next(i for i in v["items"] if i["id"] == "release.overlays")


@pytest.mark.parametrize("found, today, words", [
    ("2026-11-12", "2026-11-12", "today"),
    ("2026-11-11", "2026-11-12", "yesterday"),
    ("2026-10-31", "2026-11-12", "12 days ago"),
    ("2026-10-13", "2026-11-12", "30 days ago"),         # 30 days, not yet a whole month (13th to 12th)
    ("2026-10-12", "2026-11-12", "1 month ago"),
    ("2026-08-12", "2026-11-12", "3 months ago"),
    ("2026-08-13", "2026-11-12", "2 months ago"),        # a day short of three whole months
    ("2025-11-12", "2026-11-12", "12 months ago"),
    ("2024-11-12", "2026-11-12", "2 years ago"),
    ("2024-02-29", "2026-02-28", "23 months ago"),
])
def test_how_long_ago_is_said_in_plain_words(found, today, words):
    assert present.age_words(dt.date.fromisoformat(found), dt.date.fromisoformat(today)) == words


def test_a_recent_lookup_clears_the_row_and_the_site_lines_say_how_old_it_is():
    v = check_site(SITE, facts_found_on("2026-08-14"), today=TODAY)["view"]
    assert release_rows(v) == [] and v["state"] == present.COMPLIES
    assert ("Overlays: none found · flood map and City maps looked up 2 months ago (2026-08-14): FEMA Zone X, minimal "
            "flood hazard; the City's historic, gorge and zoning maps and parcel record · not confirmed"
            in v["header"]["sources"])


def test_ninety_days_counts_and_ninety_one_days_does_not():
    assert release_rows(check_site(SITE, facts_found_on("2026-08-14"), today=TODAY)["view"]) == []       # 90 days
    v = check_site(SITE, facts_found_on("2026-08-13"), today=TODAY)["view"]                              # 91 days
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW
    assert overlays_row(v)["reason"] == (
        "Overlays (historic, gorge, flood): the address lookup found none 91 days ago (2026-08-13), but a lookup "
        "counts for 90 days only (flood maps change): look the address up again in the start box, or check them by "
        "hand")
    assert not any(s.startswith("Overlays: none found") for s in v["header"]["sources"])


def test_a_year_old_lookup_keeps_the_row():
    v = check_site(SITE, facts_found_on("2025-11-11"), today=TODAY)["view"]
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW
    assert "366 days ago (2025-11-11)" in overlays_row(v)["reason"]


def test_without_a_day_from_the_host_no_lookup_counts_as_recent():
    """Backward compatible: a request without "today" still checks, but the age can't be told, so the row stays."""
    v = check_site(SITE, facts_found_on("2026-11-11"))["view"]
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW
    assert overlays_row(v)["reason"] == (
        "Overlays (historic, gorge, flood): the address lookup found none on 2026-11-11, but this check wasn't given "
        "today's date, so how old that is can't be told: check them by hand")


def test_a_lookup_dated_after_today_keeps_the_row():
    v = check_site(SITE, facts_found_on("2026-11-13"), today=TODAY)["view"]
    assert release_rows(v) == ["release.overlays"]
    assert overlays_row(v)["reason"] == (
        "Overlays (historic, gorge, flood): the address lookup found none, but its date (2026-11-13) is after today "
        "(2026-11-12), so how old it is can't be told: look the address up again in the start box, or check them by "
        "hand")


@pytest.mark.parametrize("date", ["Nov 11 2026", "2026-11-11T09:00", "11/11/2026", "2026-02-30", "2026-W46-3"])
def test_a_lookup_date_that_cant_be_read_keeps_the_row(date):
    v = check_site(SITE, facts_found_on(date), today=TODAY)["view"]
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW
    assert f"its date ({date}) can't be read" in overlays_row(v)["reason"]


@pytest.mark.parametrize("today", ["11/12/2026", "2026-11-12T10:00", "2026-02-30", "2026-W46-4", "", 20261112,
                                   dt.datetime(2026, 11, 12, 10)])
def test_a_day_from_the_host_that_isnt_a_day_is_refused(today):
    with pytest.raises(ValueError, match="today must be the day of the check"):
        check_site(SITE, facts_found_on("2026-11-11"), today=today)


def test_a_date_object_is_taken_as_its_day():
    assert release_rows(check_site(SITE, facts_found_on("2026-11-11"), today=dt.date(2026, 11, 12))["view"]) == []


def test_same_design_same_facts_same_day_same_answer_and_the_day_is_the_only_clock(monkeypatch):
    """The checker never reads the clock: with the place's day function made to fail, the check still runs, and the
    answer moves only with the day the host gives."""
    from design_checker import rhino_logic
    monkeypatch.setattr(rhino_logic, "city_day", lambda *a, **k: pytest.fail("the checker read the clock"))
    facts = facts_found_on("2026-08-14")
    a, b = (check_site(SITE, facts, today=TODAY)["view"] for _ in range(2))
    assert (a["state"], a["summary"], a["header"]["sources"]) == (b["state"], b["summary"], b["header"]["sources"])
    later = check_site(SITE, facts, today="2026-11-13")["view"]
    assert a["state"] == present.COMPLIES and later["state"] == present.REVIEW


def test_nothing_on_the_check_path_reads_the_clock():
    """The day comes only from the host: no clock read anywhere in the checker's own modules (a fallback to the
    computer's date would pass every dated test above while the real date is near theirs)."""
    import re
    for module in ("check.py", "present.py", "reading_set.py"):
        source = (REPO / "packages/design_checker/design_checker" / module).read_text(encoding="utf-8")
        assert not re.search(r"\.today\(|\.now\(|\butcnow\(|time\.time\(|\bcity_day\(", source), module


def test_the_worker_passes_the_hosts_day_and_still_answers_without_one(tmp_path):
    model = str(_model(tmp_path, [(0, 0), (60, 0), (60, 110), (0, 110)]))
    facts = facts_found_on("2026-11-11")
    ask = {"id": 1, "cmd": "check", "model": model, "facts": facts}
    dated = worker.answer(dict(ask, today=TODAY))
    undated = worker.answer(ask)
    assert dated["ok"] and undated["ok"]
    assert release_rows(dated["result"]["view"]) == []
    assert release_rows(undated["result"]["view"]) == ["release.overlays"]
    bad = worker.answer(dict(ask, today="12 Nov"))
    assert not bad["ok"] and "today must be the day of the check" in bad["error"]


def test_the_command_line_says_its_own_day(tmp_path, monkeypatch, capsys):
    """python -m design_checker <model> <facts>: the command line is a host too, and says the place's day."""
    import yaml
    model = _model(tmp_path, [(0, 0), (60, 0), (60, 110), (0, 110)])
    facts = tmp_path / "facts.yaml"
    facts.write_text(yaml.safe_dump({"lot_facts": facts_found_on("2026-11-11")}), encoding="utf-8")
    monkeypatch.setattr(worker, "city_day", lambda *a: TODAY)
    assert worker.main([str(model), str(facts)]) == 0
    out = capsys.readouterr().out
    assert "Gordium · " in out and "Overlays · not in this release" not in out
    monkeypatch.setattr(worker, "city_day", lambda *a: "2027-02-10")   # 91 days on
    assert worker.main([str(model), str(facts)]) == 0
    assert "Overlays · not in this release" in capsys.readouterr().out


def test_the_plugin_says_the_day_in_every_check_request():
    """The one check request the plugin builds (_check_begin, used by GordiumCheck and the live re-check) carries
    the place's own day; nothing else in it reads the clock for the checker."""
    source = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    begin = source[source.index("def _check_begin("):source.index("def _check_apply(")]
    assert '"today": logic.city_day()' in begin
    assert source.count('"cmd": "check"') == 1


def test_the_finding_is_dated_by_ithacas_day_never_the_utc_day():
    """At 10 pm in Ithaca on 2026-10-20 (02:00 UTC on the 21st) the lookup's own facts carry the UTC day; the finding
    takes the place's day the host will compare it with. A lookup answer without that day records no finding."""
    from design_checker import rhino_logic as logic
    from design_checker.lookup_box import box_payload
    from site_lookup.adapters.ithaca_city.lookup import lookup
    from test_lookup_box import T
    from test_overlays_none_found import _apply
    late = dt.datetime(2026, 10, 21, 2, 0, tzinfo=dt.timezone.utc)
    fx = T.load("106_ithaca_rd")
    result = lookup(fx["address"], T.Fake(fx), late)
    assert result["facts"]["overlays"]["date"] == "2026-10-21"             # the UTC day, as site_lookup writes it
    f, _ = _apply(box_payload(result, late))
    assert f["overlays_none_found"]["date"] == "2026-10-20"                # Ithaca's
    f, _ = _apply(box_payload(result))                                     # no day of the place: no finding
    assert "overlays_none_found" not in f
    assert logic.overlays_none_found(box_payload(result), [(0, 0), (1, 0), (1, 1)]) is None


def _check_sheet(path):
    ws = openpyxl.load_workbook(path)["Check"]
    return [str(c) for row in ws.iter_rows(values_only=True) for c in row if c is not None]


def test_the_report_says_the_age_when_cleared_and_the_reason_when_too_old(tmp_path):
    fresh, stale = tmp_path / "fresh.xlsx", tmp_path / "stale.xlsx"
    check_site(SITE, facts_found_on("2026-08-14"), report_path=fresh, today=TODAY)
    check_site(SITE, facts_found_on("2026-07-12"), report_path=stale, today=TODAY)
    assert any("flood map and City maps looked up 2 months ago (2026-08-14)" in c for c in _check_sheet(fresh))
    cells = _check_sheet(stale)
    assert any("found none 123 days ago (2026-07-12)" in c and "look the address up again" in c for c in cells)
    assert not any("looked up" in c for c in cells)
