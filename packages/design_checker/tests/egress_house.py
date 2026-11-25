"""The facts that make a test house one New York's Residential Code covers (design_checker/code_scope.py,
docs/decisions/2026-11-22_which_ny_code.md): a detached one-family dwelling of not more than three stories above
grade plane (RCNYS R101.2 item 1). Every test house has three levels at most (test_data/interior_houses, the
Orangetown house: basement, main and second floor, the attic unfinished), so three is a bound true of each. Without
them a check can't tell which code governs, and runs both with a needs-review line (test_code_scope.py)."""

HOUSE = {"use": "one_family_detached", "stories_above_grade_plane": 3}

# the place's own allowed values (its uses), as check_site passes them to egress.check: the code choice reads its uses
# (code_scope.decide: a use the place doesn't list needs review), so a test passes these, never an empty stand-in
from rule_format.rulebook import REPO as _REPO, Context as _Context  # noqa: E402

ALLOWED = _Context.for_jurisdiction(_REPO / "regulations/jurisdictions/new_york/ithaca_city").allowed()
