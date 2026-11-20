"""A saved report keeps the interior its egress rows were worked out from beside it (<report name>.interior.json), the
way it keeps its site (the Revit interior design note, section 5; section 7, step 3): written first, the earlier
report's set aside and put back if the new report can't be moved in, and never an earlier check's interior left
beside a new report, whichever file is the one that can't be written, set aside or moved in."""

import json
import os
import sys
from pathlib import Path

import pytest

from design_checker import conformance
from design_checker.check import INTERIOR_SUFFIX, SITE_SUFFIX, _aside, check_description
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
from test_egress import ranch, sill_too_high  # noqa: E402

SITE = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
FACTS = conformance.facts(conformance.scenes()["01_box_house"])


def checked(report, interior=None):
    return check_description(json.loads(json.dumps(SITE)), dict(FACTS), report, interior=interior)


def files(folder: Path) -> dict:
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def test_the_interior_is_kept_and_a_check_without_one_never_leaves_the_earlier_one(tmp_path):
    report = tmp_path / "house.xlsx"
    interior = tmp_path / ("house" + INTERIOR_SUFFIX)
    assert checked(report, ranch())["report_error"] is None
    assert sorted(files(tmp_path)) == ["house.interior.json", "house.site.json", "house.xlsx"]
    assert json.loads(interior.read_text(encoding="utf-8")) == json.loads(json.dumps(ranch()))
    assert checked(report, sill_too_high())["report_error"] is None               # replaced by the new check's
    assert json.loads(interior.read_text(encoding="utf-8")) == json.loads(json.dumps(sill_too_high()))
    assert checked(report)["report_error"] is None                                # a check with no interior
    assert sorted(files(tmp_path)) == ["house.site.json", "house.xlsx"]           # the earlier interior is gone


def test_an_interior_that_cant_be_written_means_no_report_and_the_earlier_files_stay(tmp_path, monkeypatch):
    report = tmp_path / "house.xlsx"
    checked(report, ranch())
    before = files(tmp_path)
    real = Path.write_text

    def refuse(self, *args, **kwargs):
        if self.name.endswith(INTERIOR_SUFFIX + ".part"):
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", refuse)
    result = checked(report, sill_too_high())
    assert result["report_error"].startswith("the interior description beside the report: Permission denied")
    assert files(tmp_path) == before                                              # the earlier report, untouched


def test_a_report_that_cant_be_moved_in_leaves_the_earlier_report_beside_its_own_site_and_interior(tmp_path, monkeypatch):
    report = tmp_path / "house.xlsx"
    checked(report, ranch())
    before = files(tmp_path)
    real = os.replace

    def locked(src, dst):                    # Windows: the earlier report open in Excel
        if Path(dst) == report:
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", locked)
    assert checked(report)["report_error"].startswith("Permission denied")        # even a check with no interior
    assert files(tmp_path) == before
    assert checked(report, sill_too_high())["report_error"].startswith("Permission denied")
    assert files(tmp_path) == before


def test_an_earlier_interior_that_cant_be_set_aside_is_said_and_nothing_changes(tmp_path, monkeypatch):
    report = tmp_path / "house.xlsx"
    interior = tmp_path / ("house" + INTERIOR_SUFFIX)
    checked(report, ranch())
    before = files(tmp_path)
    real = os.replace

    def locked(src, dst):
        if Path(src) == interior:
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", locked)
    result = checked(report, sill_too_high())
    assert result["report_error"] == (f"the interior description beside the report: Permission denied ({interior}), "
                                      f"so the new report wasn't saved ({report})")
    assert files(tmp_path) == before                                              # the site set aside went back too


def test_an_interior_that_cant_be_moved_in_takes_the_new_report_and_site_with_it(tmp_path, monkeypatch):
    report = tmp_path / "house.xlsx"
    interior = tmp_path / ("house" + INTERIOR_SUFFIX)
    real = os.replace

    def stuck(src, dst):
        if Path(dst) == interior:
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", stuck)
    result = checked(report, ranch())
    assert result["report_error"].startswith("the interior description beside the report: Permission denied")
    assert list(tmp_path.iterdir()) == []                 # no report beside a site with no interior, nothing half-done


def test_a_check_stopped_midway_leaves_no_part_file_and_never_puts_an_earlier_interior_back(tmp_path, monkeypatch):
    report = tmp_path / "house.xlsx"
    interior = tmp_path / ("house" + INTERIOR_SUFFIX)
    checked(report, ranch())
    real = os.replace

    def moved_then_stopped(src, dst):
        real(src, dst)
        if Path(dst) == report:
            raise KeyboardInterrupt
    monkeypatch.setattr(os, "replace", moved_then_stopped)
    with pytest.raises(KeyboardInterrupt):
        checked(report)
    assert report.exists() and not interior.exists() and not _aside(interior).exists()
    assert not (tmp_path / ("house" + SITE_SUFFIX)).exists()     # a report with no site at worst, never a wrong one
    assert not list(tmp_path.glob(".*"))
