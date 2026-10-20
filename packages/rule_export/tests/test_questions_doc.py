"""docs/questions_for_architects.md is the complete, true list of what the architects must answer:

- every open question recorded anywhere (the same list as the workbook's Questions tab) is cited there by its
  tag, `[<id>#<n>]`, the n-th open question of that rule, definition or label, and nothing else is;
- every result-changing (🔴) item in docs/discrepancies_with_architects.md is cited as `[discrepancy <number>]`;
- what it says Gordium does is true of the code, and its lot numbers are recomputed from the stored outlines
  and the R-1b rule.

A question added, answered or renumbered without updating the page fails here, so the page can't silently
fall behind the files."""

import json
import math
import re
from collections import Counter

import pytest

from rule_export.workbook import tables
from rule_format.formula import evaluate
from rule_format.rulebook import MEASURE_KINDS, REPO, load

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DOC = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
DISCREPANCIES = (REPO / "docs/discrepancies_with_architects.md").read_text(encoding="utf-8")
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
R1B = {r["id"]: r for r in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]}


def recorded_questions() -> list[str]:
    """`<id>#<n>` for every open question, in the Questions tab's order (the one list of them)."""
    seen, tags = Counter(), []
    for row in tables(ITHACA)["Questions"]["rows"]:
        seen[row[2]] += 1
        tags.append(f"{row[2]}#{seen[row[2]]}")
    return tags


def test_every_recorded_question_is_on_the_page_and_nothing_else():
    cited = re.findall(r"`\[([^\]`\s]+#\d+)\]`", DOC)
    recorded = recorded_questions()
    assert len(recorded) == len(set(recorded))
    assert sorted(set(recorded) - set(cited)) == [], "open questions missing from docs/questions_for_architects.md"
    assert sorted(set(cited) - set(recorded)) == [], "the page cites questions no file records (answered or renumbered?)"
    assert [t for t, n in Counter(cited).items() if n > 1] == [], "each question is cited once"


def test_every_result_changing_discrepancy_is_on_the_page():
    red = {m for m in re.findall(r"^\| (\d+\.\d+) \|.*🔴", DISCREPANCIES, re.M)}
    cited = set(re.findall(r"\[discrepancy (\d+\.\d+)\]", DOC))
    assert red, "the discrepancies table format changed; update this test"
    assert sorted(red - cited) == [] and sorted(cited - red) == []


def test_every_needs_review_claim_is_true_of_the_code():
    """Today measurements are typed in, and only a rule with a review condition gives NEEDS REVIEW. So each
    'Until you answer' line that promises NEEDS REVIEW must be about measuring a model (being built), or name
    an R-1b rule that really has a review condition. Otherwise the page would promise a safety net that
    doesn't exist, and a typed number could PASS unnoticed."""
    claims = [line for line in DOC.splitlines() if line.startswith("- **Until you answer:**") and "NEEDS REVIEW" in line]
    assert claims
    for line in claims:
        backed = any(R1B.get(rule_id, {}).get("review_when") for rule_id in re.findall(r"R-1b\.[a-z_]+", line))
        assert "from a model" in line.lower() or backed, line


def _sides(file: str) -> tuple[list[float], float, int]:
    """A stored parcel outline as its sides (consecutive edges within 8 degrees of each other are one side, so
    a curve drawn as short edges is one side), its area, and how many edges make up the first side."""
    ring = json.loads((SITE / "gis" / file).read_text())["features"][0]["geometry"]["rings"][0]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2
    sides, edges, heading = [], [], None
    for a, b in zip(ring, ring[1:]):
        h = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        if heading is not None and abs((h - heading + 180) % 360 - 180) < 8:
            sides[-1] += math.dist(a, b)
            edges[-1] += 1
        else:
            sides.append(math.dist(a, b))
            edges.append(1)
        heading = h
    return sides, area, edges[0]


def test_the_lot_outline_figures_come_from_the_stored_outlines():
    """§1.1's GIS numbers are recomputed from the outlines stored with the test site, not copied by hand."""
    city, city_area, front_edges = _sides("city_tax_parcel_2026-10-20.json")
    county, county_area, _ = _sides("county_parcel_2026-10-20.json")
    # in the order both rings run: front, long side, jog, rear, side toward #104
    assert [round(x, 2) for x in city] == [75.83, 101.13, 10.35, 69.51, 92.12]
    assert [round(x, 2) for x in county] == [73.52, 101.13, 10.35, 68.86, 92.00]
    for text in (f"{city[0]:.1f} ft along a curve of {front_edges} segments", f"{city[4]:.2f} ft", f"{city[3]:.2f} ft",
                 f"{city[2]:.2f} ft", f"{city[1]:.2f} ft", f"{county[0]:.2f} ft, straight", f"{county[4]:.2f} ft",
                 f"{county[3]:.2f} ft", f"**{city_area:,.1f} sf**", f"**{county_area:,.1f} sf**",
                 f"by about {round(city_area - county_area)} sf"):
        assert text in DOC, text


def test_the_rear_yard_tables_follow_the_r1b_rule():
    """Every required rear yard in §1.2's two tables is what the R-1b rule gives for that depth, and the 25 ft
    design is marked FAIL exactly when it falls short."""
    required_for = R1B["R-1b.rear_yard"]["check"].split(">=", 1)[1].strip()
    city, _, _ = _sides("city_tax_parcel_2026-10-20.json")
    side, long_side, jog = 90.28, 99.37, 10.47                   # the model's lot (see the model test below)
    rows = {"| (a) ": (side + long_side) / 2, "| (b) ": (side + long_side + jog) / 2,
            "| (c) ": (side + jog + long_side) / 3, "| 90 ft": 90, "| 92 ft": 92,
            "| 96.6 ft": (city[4] + city[1]) / 2, "| 101.13 ft": city[1]}
    lines = [line.strip() for line in DOC.splitlines()]
    for start, depth in rows.items():
        row = next(line for line in lines if line.startswith(start))
        required = evaluate(required_for, {"lot_depth": depth}, MEASURE_KINDS)
        shown = [float(x.replace(",", "")) for x in re.findall(r"\| ([\d,.]+) ft", row)]
        assert any(abs(x - required) < 0.05 for x in shown), (row, required)
        assert ("**FAIL**" in row) == (required > 25), row


def test_the_model_lot_figures_are_the_model_s():
    """The model's sides and area on the page are measured from model.3dm (needs rhino3dm; skipped without it)."""
    rhino3dm = pytest.importorskip("rhino3dm")
    model = rhino3dm.File3dm.Read(str(SITE / "model.3dm"))
    site = next(i for i, layer in enumerate(model.Layers) if layer.FullPath == "Site")
    rings = [o.Geometry for o in model.Objects if o.Attributes.LayerIndex == site
             and isinstance(o.Geometry, rhino3dm.PolylineCurve) and o.Geometry.IsClosed]
    line = max(rings, key=lambda c: c.PointCount)
    points = [(line.Point(i).X, line.Point(i).Y) for i in range(line.PointCount)]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:]))) / 2
    assert sorted(round(math.dist(a, b), 2) for a, b in zip(points, points[1:])) == [10.47, 67.72, 73.0, 90.28, 99.37]
    assert f"**{area:,.1f} sf**" in DOC
