"""The permitted-use rule for each district, built by plain code from the chart's marks (page 2).

Each primary-use row has a mark per district: • (the use is listed as permitted), SP (special permit),
- (not listed). The chart never says what the marks mean, so the rule records that as an open question.
A mark with a footnote ("•[fn5]") sends the use to review, quoting the footnote. Every use the rule
decides about is cited by its own cell, so the inspector's use-row check applies.
"""


from rule_format.rulebook import district_name

from .chart_values import FOOTNOTE, footnotes

CHART_FILE = "zoning_charts_2026-04.pdf"
SECTION = "Primary Uses"
MARK_QUESTION = ("The chart has no legend for its marks. We read • as permitted and - as not permitted; SP "
                 "matches §325-9B(1)'s list of uses needing a special permit from the Planning and Development "
                 "Board. Confirm.")


def use_ids(uses: dict) -> dict[str, str]:
    """{row label without footnote markers: use id}, from the names in uses.yaml."""
    return {v["name"].strip(): k for k, v in uses.items()}


def use_rule(column: str, rows: dict[str, dict[str, dict]], uses: dict, notes: dict[str, dict],
             drafted_by: str) -> tuple[dict | None, list[str]]:
    """(the rule for this district, problems). rows: {row label: {column: cell}} for Primary Uses."""
    ids, problems = use_ids(uses), []
    allowed, special, footnoted, refused, sources, quoted = [], [], {}, [], [], set()
    for label, by_column in rows.items():
        name = FOOTNOTE.sub("", label).strip()
        cell = by_column.get(column)
        if name not in ids:
            problems.append(f"row {label!r} matches no use name in uses.yaml")
            continue
        if cell is None:
            problems.append(f"row {label!r}: no {column} cell")
            continue
        mark, marks = FOOTNOTE.sub("", cell["value"]).strip(), footnotes(cell["value"])
        use = ids[name]
        if mark == "•" and not marks:
            allowed.append(use)
        elif mark == "•":
            footnoted[use] = sorted(marks)
            quoted |= marks
        elif mark == "SP":
            special.append(use)
        elif mark == "-":
            refused.append(use)
            continue                                  # not decided by the rule's lists: fails because it isn't allowed
        else:
            problems.append(f"row {label!r}: unknown mark {cell['value']!r}")
            continue
        sources.append({"file": CHART_FILE, "page": cell["page"],
                        "cell": {"section": SECTION, "row": label.strip(), "column": column}})
    if not allowed:
        return None, problems + ["no use is marked • without a footnote"]
    for n in sorted(quoted, key=int):
        if n not in notes:
            return None, problems + [f"footnote {n} isn't under the table"]
        sources.append({"file": CHART_FILE, "page": 2, "lines": notes[n]["lines"], "quote": notes[n]["text"]})
    district = district_name(column)
    review = []
    if special:
        review.append({"when": f"use in {special!r}".replace("'", '"'),
                       "reason": f"Marked SP for {column} on the zoning chart (p.2)."})
    for use, marks in footnoted.items():
        review.append({"when": f'use == "{use}"',
                       "reason": f"Marked • for {column} with footnote {', '.join(marks)} (chart p.2), a condition to check."})
    examples = [{"given": {"use": allowed[0]}, "expect": "pass"}]
    if refused:
        examples.append({"given": {"use": refused[0]}, "expect": "fail"})
    if special:
        examples.append({"given": {"use": special[0]}, "expect": "needs_review"})
    rule = {"id": f"{district}.use", "kind": "rule", "topic": "uses",
            "title": "Permitted primary uses (chart p.2)",
            "check": f"use in {allowed!r}".replace("'", '"')}
    if review:
        rule["review_when"] = review
    rule |= {"sources": sources, "examples": examples, "open_questions": [MARK_QUESTION],
             "notes": f"Built by code from the {column} column of chart p.2: • uses pass, SP uses and footnoted "
                      "• uses go to review, uses marked - fail.",
             "drafted_by": drafted_by, "status": "draft"}
    if not refused:
        problems.append(f"{column}: every use is permitted or SP, so the rule has no failing example")
        return None, problems
    return rule, problems
