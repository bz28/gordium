"""docs/questions_for_architects.md is the complete, true list of what the architects must answer:

- every open question recorded anywhere (the same list as the workbook's Questions tab) is cited there by its
  tag, `[<id>#<n>]`, the n-th open question of that rule, definition or label, and nothing else is;
- every result-changing (🔴) item in docs/discrepancies_with_architects.md is cited as `[discrepancy <number>]`;
- what it says Gordium does is true of the code; its lot numbers match their sources (the County outline,
  recomputed from the stored file; the City outline, our recorded measurements of it, since the City's data
  isn't stored; the model, measured from model.3dm; their spreadsheet), and its rear yards follow the R-1b rule.

A question added, answered or renumbered without updating the page fails here, so the page can't silently
fall behind the files."""

import hashlib
import json
import math
import re

import pytest
from collections import Counter

from openpyxl import load_workbook

from rule_export.workbook import tables
from rule_format.formula import evaluate
from rule_format.rulebook import MEASURE_KINDS, MEASURES_FILE, REPO, load

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DOC = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
DISCREPANCIES = (REPO / "docs/discrepancies_with_architects.md").read_text(encoding="utf-8")
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
R1B = {r["id"]: r for r in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]}
ANSWER_KEY = REPO / "test_data/answer_keys/new_york/ithaca_city/Gordium_Single_Family_Simple_v1.xlsx"
# What we measured from the City's outline (the City's data itself may not be stored; see gis/README.md).
CITY = load(SITE / "gis/city_tax_parcel_measurements.yaml")
CITY_STATEMENT = ("Data contained in this product was amended by the GIS Program, City of Ithaca, NY from a file created by "
                  "Tompkins County Assessment Office. The originators do not warrant the accuracy or completeness of the "
                  "information portrayed by the data.")


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


def test_the_page_counts_what_is_left_from_the_files():
    """The research summary's "so N are left" is the number of questions recorded now."""
    left = re.search(r"so (\d+) are left", DOC)
    assert left and int(left.group(1)) == len(recorded_questions())


def test_every_result_changing_discrepancy_is_on_the_page():
    red = {m for m in re.findall(r"^\| (\d+\.\d+) \|.*🔴", DISCREPANCIES, re.M)}
    cited = set(re.findall(r"\[discrepancy (\d+\.\d+)\]", DOC))
    assert red, "the discrepancies table format changed; update this test"
    assert sorted(red - cited) == [] and sorted(cited - red) == []


def test_every_result_changing_discrepancy_of_another_place_says_where_it_is_tracked():
    """The page above is Ithaca's. Another place's result-changing (🔴) item (numbered P1, P2, ...) must name the
    file where its question is tracked, and that file must exist, so no such item is left with no one to answer it."""
    rows = re.findall(r"^\| (P\d+) \|(.*🔴.*)$", DISCREPANCIES, re.M)
    assert rows, "the other places' discrepancies table format changed; update this test"
    for number, row in rows:
        tracked = re.search(r"Tracked in `([^`]+)`", row)
        assert tracked, f"discrepancy {number} is result-changing but says nowhere where it is tracked"
        assert (REPO / tracked.group(1)).is_file(), f"discrepancy {number}: {tracked.group(1)} doesn't exist"


def test_the_childcare_log_has_every_figure_and_verdict_the_eval_finds_apart_from_the_sheet():
    """Every figure the childcare eval marks outside its tolerance, and every rule whose verdict differs from the
    sheet's, has a row in the childcare log of docs/discrepancies_with_architects.md (named by its key in the eval
    file), so no difference is left out of review."""
    import yaml

    data = yaml.safe_load((REPO / "test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml")
                          .read_text(encoding="utf-8"))
    log = DISCREPANCIES.split("# Children's Odyssey", 1)[1]
    apart = [f"figures.{name}" for name, fig in data["figures"].items()
             if (fig.get("agreement") or {}).get("within_tolerance") is False]
    # the first test, still reported beside the one-sided test since 2026-11-21: a miss under it is logged too
    apart += [f"figures.{name}.agreement.before_2026_11_21" for name, fig in data["figures"].items()
              if ((fig.get("agreement") or {}).get("before_2026_11_21") or {}).get("within_tolerance") is False]
    assert any(".before_2026_11_21" in key for key in apart), "the eval file's format changed; update this test"
    # where Gordium's figure ends beside where the sheet's line ends: its own item, a miss logged too
    apart += [f"figures.{name}.agreement.end" for name, fig in data["figures"].items()
              if ((fig.get("agreement") or {}).get("end") or {}).get("within_tolerance") is False]
    apart += [f"storage.{key}" for key, value in data["storage"].items()
              if isinstance(value, dict) and value.get("within_tolerance") is False]
    apart += [rule.split(".", 1)[1] for rule, v in data["verdicts"]["rules"].items() if v["same"] is False]
    assert apart, "the eval file's format changed; update this test"
    assert [key for key in apart if f"`{key}`" not in log] == []
    unrouted = {room for fig in data["figures"].values()
                for room in (((fig.get("gordium") or {}).get("story") or {}).get("rooms_not_measured") or [])}
    assert unrouted and sorted(room for room in unrouted if room not in log) == []
    # a point the log names comes from the room it names it with (each room's own reason, as the eval file gives it)
    reasons = {room: why for fig in data["figures"].values()
               for room, why in (((fig.get("gordium") or {}).get("story") or {}).get("rooms_not_measured") or {}).items()}
    for sentence in re.split(r"(?<=[.;:])\s", log):
        for point in re.findall(r"\(\d+\.\d+, \d+\.\d+\)", sentence):
            owners = {room for room, why in reasons.items() if point in why}
            if owners:
                before = sentence[:sentence.index(point)]
                named = [room for room in reasons if room in before]
                assert named, (point, owners, sentence)
                nearest = max(named, key=before.rindex)          # the room named last before the point
                assert nearest in owners, (point, nearest, owners)
    # the accessory area complies under all four readings: the largest accessory area against 10% of the smallest
    # story area (decision 8), stated in the log with that limit
    limit = round(0.1 * min(data["storage"]["gordium_story_sf"]))
    assert f"{limit:,} sf" in log
    _tie_rooms_held_to_their_reason(log, reasons)
    # the guard rejects the two wrong shapes the log once had (review rounds 12 to 14) and two list and comma
    # wordings a clause split let through (round 15)
    p4 = "**6** rooms aren't measured. The 5 of P5 have no route to the exit `...0005bc94`. CORRIDOR (26) stops on a tie."
    assert p4 in log
    for wrong in ("**6** rooms have no route to one of the two exits: the 5 of P5 plus CORRIDOR (26) (which stops on a tie)",
                  "**6** rooms have no route to the exit: SPRINKLERED ABANDONED SPACE (32), and CORRIDOR (26) (which stops on a tie)",
                  "**6** rooms aren't measured, CORRIDOR (26) stops on a tie. CORRIDOR (26) does reach both exits",
                  "**6** rooms aren't measured. The 5 of P5 have no route; so has CORRIDOR (26), on a tie."):
        with pytest.raises(AssertionError):
            _tie_rooms_held_to_their_reason(log.replace(p4, wrong), reasons)


def _tie_rooms_held_to_their_reason(log, reasons):
    """A room stopped for a reason other than "has no route" (a tie) is held to its own reason: no sentence naming it
    says "no route" or "both exits" at all, and one says it stops on a tie. Checked by whole sentences (to a full stop
    or a table bar), never by clause, so no list or punctuation can separate a "no route" from the room it is about:
    the log gives such a room a sentence of its own."""
    clauses = re.split(r"(?<!\.)\.(?=\s|$)|\|", log)
    for room, why in reasons.items():
        if "has no route" in why:
            continue
        mine = [c for c in clauses if room in c]
        assert mine and not [c for c in mine if "no route" in c or "both exits" in c], (room, mine)
        if "equally short" in why:
            assert any("tie" in c or "equally short" in c for c in mine), (room, mine)


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


def test_every_question_says_what_happens_today_and_from_a_model():
    """Each question tells the architects what Gordium does today (typed numbers) and from a model, and which of
    the intro's three cases it is: NEEDS REVIEW, an assumed reading (which can give PASS, so it is named), or not
    checked yet. So the page never implies a safety net it doesn't have."""
    intro = DOC.split("**How to read each question**")[0]
    for case in ("**NEEDS REVIEW:**", "**Gordium assumes a reading:**", "That can give PASS", "**Not checked yet:**",
                 "Gordium can still report PASS"):
        assert case in intro, case
    lines = [line for line in DOC.splitlines() if line.startswith("- **Until you answer:** Today")]
    assert len(lines) == DOC.count("- **Until you answer:**") - 1           # all but the legend's own line
    measures = set(load(MEASURES_FILE))
    for line in lines:
        low = line.lower()                                     # wording checks ignore capitals
        assert "from a model" in low or "entered, not measured" in low, line
        # Every "… is/are entered, not measured" names a real input, however it is worded: the subject is the
        # clause before it (after the last . ; or :), less a leading "the".
        subjects = [re.sub(r"^the ", "", m.group(1).strip())
                    for m in re.finditer(r"([^.;:]*?)\s+(?:is|are) entered, not measured", low)]
        assert len(subjects) == low.count("entered, not measured"), line
        for thing in subjects:
            assert thing.replace(" ", "_") in measures, (thing, line)
        assert any(case in line for case in ("NEEDS REVIEW", "assumes", "not checked yet")), line


def test_an_unsurveyed_lot_area_is_not_trusted():
    """From a model, an unsurveyed lot area gets NEEDS REVIEW (principle 4: unclear data is never a PASS), since
    106 Ithaca Rd's drawn lot differs from the city's."""
    lot_area = DOC.split("`[lot#1]`")[1].split("###")[0]
    until = next(line for line in lot_area.splitlines() if line.startswith("- **Until you answer:**"))
    assert "needs review" in until.lower().split("from a model", 1)[1], until


def test_the_page_quotes_the_architects_own_lot_area():
    """What the page says their spreadsheet says is what it says."""
    typed = load_workbook(ANSWER_KEY, data_only=True)["Inputs"]["B5"].value
    assert f"your spreadsheet types {typed:,} sf (Inputs!B5)" in DOC
    assert "6,674.7" not in DOC


def test_only_shareable_data_is_stored_and_it_is_what_was_downloaded():
    """The County outline is stored as downloaded (its fingerprint is in the README). The City's data may not be
    redistributed, so no City file is stored: only our measurements, with the URL and the raw response's
    fingerprint, and the statement the City asks derived products (the page) to carry."""
    readme = (SITE / "gis/README.md").read_text(encoding="utf-8")
    assert sorted(f.name for f in (SITE / "gis").iterdir()) == ["README.md", "city_tax_parcel_measurements.yaml",
                                                                 "county_parcel_2026-10-20.json"]
    county = SITE / "gis/county_parcel_2026-10-20.json"
    assert f"SHA-256: `{hashlib.sha256(county.read_bytes()).hexdigest()}`" in readme
    assert set(json.loads(county.read_text(encoding="utf-8"))["features"][0]["attributes"]) == {
        "SWISPRINTK", "LOCADDR", "ZONING", "FRONTAGE", "DEPTH", "PROPCLASS"}        # nothing personal
    assert re.fullmatch(r"[0-9a-f]{64}", CITY["sha256"]) and CITY["url"].startswith("https://")
    # Why the City's data isn't stored, with its sources: the parcel layer's terms, and the zoning layer's
    # consent clause (the precaution's reason). The County's terms are cited the same way.
    city_part = readme.split("**`city_tax_parcel_measurements.yaml`**")[1]
    for cited in ("https://www.arcgis.com/sharing/rest/content/items/87c2aae68e0b405d8b9dcb7a0cc9cf06?f=json",
                  "https://services5.arcgis.com/R1JbITZvSQHJsl5r/arcgis/rest/services/City_Zoning/FeatureServer/info/itemInfo?f=json",
                  "may not be reproduced or redistributed without the express written consent of the originator"):
        assert cited in city_part, cited
    assert "https://www.arcgis.com/sharing/rest/content/items/505beb987c93401b8445777a8bb9bda6?f=json" in readme
    header = " ".join(line.lstrip("# ").strip() for line in (SITE / "gis/city_tax_parcel_measurements.yaml").read_text(encoding="utf-8").splitlines())
    assert CITY_STATEMENT in header
    assert CITY_STATEMENT in DOC


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
    ring = json.loads((SITE / "gis" / file).read_text(encoding="utf-8"))["features"][0]["geometry"]["rings"][0]
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
    """§1.1's GIS numbers: the County's recomputed from its stored outline, the City's from our measurements of
    it (city_tax_parcel_measurements.yaml)."""
    sides = CITY["sides_ft"]
    city = [sides[k]["length"] for k in ("front", "long_side", "jog", "rear", "side_toward_104")]
    city_area, front_edges = CITY["area_sf"], sides["front"]["edges"]
    county, county_area, _ = _sides("county_parcel_2026-10-20.json")
    # in the order the County ring runs: front, long side, jog, rear, side toward #104
    assert [round(x, 2) for x in county] == [73.52, 101.13, 10.35, 68.86, 92.00]
    for text in (f"{city[0]:.1f} ft along a curve of {front_edges} segments", f"{city[4]:.2f} ft", f"{city[3]:.2f} ft",
                 f"{city[2]:.2f} ft", f"{city[1]:.2f} ft", f"{county[0]:.2f} ft, straight", f"{county[4]:.2f} ft",
                 f"{county[3]:.2f} ft", f"**{city_area:,.1f} sf**", f"**{county_area:,.1f} sf**",
                 f"by about {round(city_area - county_area)} sf"):
        assert text in DOC, text


def test_the_rear_yard_tables_follow_the_r1b_rule():
    """Every lot depth in §1.2's tables comes from its source (the model, their spreadsheet, the County's
    assessor depth, our measurements of the City outline), every required rear
    yard is what the R-1b rule gives for it, and the 25 ft design is marked FAIL exactly when it falls short."""
    required_for = R1B["R-1b.rear_yard"]["check"].split(">=", 1)[1].strip()
    city = [CITY["sides_ft"][k]["length"] for k in ("front", "long_side", "jog", "rear", "side_toward_104")]
    (_, side, _, jog, long_side), _ = _model_lot()
    typed_depth = load_workbook(ANSWER_KEY, data_only=True)["Inputs"]["B4"].value          # their "Lot depth"
    county = json.loads((SITE / "gis/county_parcel_2026-10-20.json").read_text(encoding="utf-8"))
    assessor_depth = county["features"][0]["attributes"]["DEPTH"]
    a, b, c = (side + long_side) / 2, (side + long_side + jog) / 2, (side + jog + long_side) / 3
    rows = {f"| (a) the {side:.2f} and {long_side:.2f} ft lines | {a:.1f} ft": a,
            f"| (b) the jog added to the {long_side:.2f} ft line it continues | ({side:.2f} + {long_side + jog:.2f}) ÷ 2 = {b:.2f} ft": b,
            f"| (c) average of every line that isn't front or rear | ({side:.2f} + {jog:.2f} + {long_side:.2f}) ÷ 3 = {c:.1f} ft": c,
            f"| {typed_depth} ft (your spreadsheet)": typed_depth, f"| {assessor_depth} ft (assessor's depth": assessor_depth,
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
