"""docs/questions_for_architects.md is the complete, true list of what the architects must answer:

- every open question recorded anywhere (the same list as the workbook's Questions tab) is cited there by its
  tag, `[<id>#<n>]`, the n-th open question of that rule, definition or label, and nothing else is;
- every result-changing (🔴) item in docs/discrepancies_with_architects.md is cited as `[discrepancy <number>]`;
- what it says Gordium does is true of the code, and its lot numbers are recomputed from the stored outlines
  and the R-1b rule.

A question added, answered or renumbered without updating the page fails here, so the page can't silently
fall behind the files."""

import hashlib
import json
import math
import re
from collections import Counter

from openpyxl import load_workbook

from rule_export.workbook import tables
from rule_format.formula import evaluate
from rule_format.rulebook import MEASURE_KINDS, REPO, load

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DOC = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
DISCREPANCIES = (REPO / "docs/discrepancies_with_architects.md").read_text(encoding="utf-8")
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
R1B = {r["id"]: r for r in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]}
ANSWER_KEY = REPO / "test_data/answer_keys/new_york/ithaca_city/Gordium_Single_Family_Simple_v1.xlsx"


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


def test_no_blanket_promise_and_an_unsurveyed_lot_area_is_not_trusted():
    """The intro promises NEEDS REVIEW only where Gordium can't decide (each question says what it will do),
    and an unsurveyed lot area measured from a model gets NEEDS REVIEW (principle 4: unclear data is never a
    PASS), since 106 Ithaca Rd's drawn lot differs from the city's."""
    intro = DOC.split("**How to read each question**")[0]
    assert "where it can't decide, it gives **NEEDS REVIEW**" in intro
    lot_area = DOC.split("`[lot#1]`")[1].split("###")[0]
    until = next(line for line in lot_area.splitlines() if line.startswith("- **Until you answer:**"))
    model_clause = until.lower().split("when measured from a model", 1)[1]
    assert "needs review" in model_clause, until


def test_the_page_quotes_the_architects_own_lot_area():
    """What the page says their spreadsheet says is what it says."""
    typed = load_workbook(ANSWER_KEY, data_only=True)["Inputs"]["B5"].value
    assert f"your spreadsheet types {typed:,} sf (Inputs!B5)" in DOC
    assert "6,674.7" not in DOC


def test_the_stored_outlines_are_the_downloads_named_in_their_readme():
    readme = (SITE / "gis/README.md").read_text(encoding="utf-8")
    files = sorted((SITE / "gis").glob("*.json"))
    assert len(files) == 2
    for f in files:
        assert f"`{f.name}`" in readme
        assert f"SHA-256: `{hashlib.sha256(f.read_bytes()).hexdigest()}`" in readme, f.name


def _model_lot() -> tuple[list[float], float]:
    """The model's lot (model.3dm, layer Site): its sides in drawing order (front, side toward #104, rear, jog,
    long side) and its area."""
    import rhino3dm
    model = rhino3dm.File3dm.Read(str(SITE / "model.3dm"))
    site = next(i for i, layer in enumerate(model.Layers) if layer.FullPath == "Site")
    rings = [o.Geometry for o in model.Objects if o.Attributes.LayerIndex == site
             and isinstance(o.Geometry, rhino3dm.PolylineCurve) and o.Geometry.IsClosed]
    line = max(rings, key=lambda c: c.PointCount)
    points = [(line.Point(i).X, line.Point(i).Y) for i in range(line.PointCount)]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:]))) / 2
    return [math.dist(a, b) for a, b in zip(points, points[1:])], area


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
    """Every lot depth in §1.2's tables comes from the model or the stored city outline, every required rear
    yard is what the R-1b rule gives for it, and the 25 ft design is marked FAIL exactly when it falls short."""
    required_for = R1B["R-1b.rear_yard"]["check"].split(">=", 1)[1].strip()
    city, _, _ = _sides("city_tax_parcel_2026-10-20.json")
    (_, side, _, jog, long_side), _ = _model_lot()
    a, b, c = (side + long_side) / 2, (side + long_side + jog) / 2, (side + jog + long_side) / 3
    rows = {f"| (a) the {side:.2f} and {long_side:.2f} ft lines | {a:.1f} ft": a,
            f"| (b) the jog added to the {long_side:.2f} ft line it continues | ({side:.2f} + {long_side + jog:.2f}) ÷ 2 = {b:.2f} ft": b,
            f"| (c) average of every line that isn't front or rear | ({side:.2f} + {jog:.2f} + {long_side:.2f}) ÷ 3 = {c:.1f} ft": c,
            "| 90 ft (your spreadsheet)": 90, "| 92 ft (assessor's depth": 92,
            f"| {(city[4] + city[1]) / 2:.1f} ft (average of the two GIS sides)": (city[4] + city[1]) / 2,
            f"| {city[1]:.2f} ft (the long side in GIS)": city[1]}
    lines = [line.strip() for line in DOC.splitlines()]
    for start, depth in rows.items():
        row = next((line for line in lines if line.startswith(start)), None)
        assert row, f"no row starting {start!r}"
        required = evaluate(required_for, {"lot_depth": depth}, MEASURE_KINDS)
        shown = [float(x.replace(",", "")) for x in re.findall(r"\| ([\d,.]+) ft", row)]
        assert any(abs(x - required) < 0.05 for x in shown), (row, required)
        assert ("**FAIL**" in row) == (required > 25), row


def test_the_model_lot_figures_are_the_model_s():
    """§1.1's Model column and the model's area are measured from model.3dm."""
    sides, area = _model_lot()
    lines = [line.strip() for line in DOC.splitlines()]
    for label, length in zip(("Front (Ithaca Rd)", "Side (toward #104)", "Rear", "Jog", "Long side"), sides):
        row = next(line for line in lines if line.startswith(f"| {label} |"))
        assert row.split("|")[2].strip().startswith(f"{length:.2f} ft"), (row, length)
    assert f"**{area:,.1f} sf**" in DOC
