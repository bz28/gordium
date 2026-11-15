# Permit sheets from an egress check: plan

**Purpose:** agree how Gordium prints the three egress sheets an architect attaches to a permit application, before the code is written.\
**For:** Ben, a reviewer, the architects. No coding knowledge needed.\
**Kept current by:** whoever changes `packages/permit_sheets/`.

**Design source:** the egress design doc (Claude Docs "Egress in Gordium: design doc", §11 "Permit sheets", read 2026-11-15) names the three sheets and shows mock-ups of two of them. This plan follows it; where the doc's mock-up asks for something the check doesn't hold yet, that's said below.

## What it makes

One command checks a design (the model or site description, its lot facts and **the interior description**, `gordium.interior/1`) with `design_checker`, exactly as the plugin does, and turns that **check result** into files an architect can attach:

| Sheet | What it shows | Files |
|---|---|---|
| **G-001 Code analysis: egress** (more pages, G-002…, if it runs long) | Every egress item the check gave (`view.items` of the egress group): each rule's row for each part, and the check's own items that are no rule's row (the interior drawing's problems, escape openings marked but not checked, rules not written per part, rules refused, nothing applied, waiting), each with the part ("Bedroom 3 › Window 5"), the requirement, the required value, the proposed value, the result, the code section, and, for anything not complying, why | SVG (one per page), a page of the PDF, `code_analysis.csv`, a tab of the XLSX |
| **LS-101 Life-safety plan** (one per floor) | Each floor's rooms drawn from their outlines, sleeping rooms marked, each one's escape opening(s) tagged with their result, stairs drawn from their nosings with an UP arrow, the exit door named with its result, and a schematic of the way out (room → stair → exit door), labelled "not checked by Gordium" | SVG, a page of the PDF |
| **A-601 Escape-window schedule** | Each sleeping room and each marked escape opening: operation, net clear width × height, net clear area, sill height, grade floor or not, each against its limit, the opening's result and code sections | SVG, a page of the PDF, `escape_window_schedule.csv`, a tab of the XLSX |

All pages also go into one `permit_sheets.pdf`. Sheets are 11 × 17 in (ANSI B, landscape), the size most building departments take for a house, with a title block down the right edge: project, address, sheet title and number, page n of N, date, the rulebook (file, its sha256, "draft"), the rules and code fingerprints, the interior's fingerprint (the check's own: sha256 of the description as sorted-key JSON, `egress.fingerprint`, labelled so, since it isn't the file's sha256), and in a box of its own: **"Prepared with Gordium: draft rules, verify before submission"**. A blank box is left for the architect's stamp. Dimensions are in feet and inches (2'-8"), areas in sq ft, as on a permit set.

## Where every value comes from

The sheets are a print-out of the check, never a second check. Plain code, no AI.

- **Result:** the check's own status for that item (`view.items[].status`, which is `outcome()`'s). An item about a part (`part` given) is paired with its raw row (`egress.rows[]`, by rule, part kind, part id and the part it sits in, in order, so two rows alike pair one to one) and the two must agree. An item with no part (the check's own items above) prints its status and reason as given. If an item and its row disagree, a part's item has no row, or a status isn't one of the four known ones, nothing is printed: the command stops and says why. The egress section's own summary ("1 does not comply · 126 need review · 9 comply") must equal the summary worked out again from the items by the checker's own counting (`present._summary`), and a waiting law's must be the check's waiting words with every item waiting, or the command stops.
- **Rule id, code section, citation, quote:** the check's item (`rule`, `code.section`, `detail.citation`, `detail.quotes`).
- **Proposed:** the part's measured values in the check (`egress.rows[].values`, by measure name). A value missing prints "not measured" with the measuring's reason. **Rounding never favours compliance** (the checker's rule, `present.PRECISION`): lengths to 1/8 in with `present.feet_inches`, areas to 0.01 sq ft; a value that must be at least a limit rounds down, one that must be at most a limit rounds up, and the required value the other way (`present._toward`). So a 44.06 in sill prints 3'-8 1/8", never 3'-8" beside "3'-8" max".
- **Required:** worked out from the rule's own formula with the part's values, for display only (the same as `project_report`'s "table limit"): "5.7 sq ft min", "3'-8" max". A formula of another shape prints the formula itself. It never decides the result.
- **Room outlines, stair nosings, window operation:** the interior description. Its sha256 must equal the one the check recorded (`egress.interior_sha256`), or the command stops: the sheets can never mix one drawing's results with another drawing's geometry.
- **The rulebook, and proof it is the one the check used.** The check result alone doesn't say which rulebook decided it (`egress` keeps rows, results, interior and its sha256 only), so a rulebook loaded later could have a changed formula under the same quote. So **the command runs the check itself**, in the same process, and makes the sheets from that answer: it reads the worker's rules fingerprint and code fingerprint (`protocol.rulebook_fingerprints()` and `worker_fingerprint()`, what `hello` gives) before the check, and again once the sheets have loaded the rules they print from (after the check), and stops if either changed in between. There is one way in, used by the command and the goldens alike. (A saved worker answer can't be used: the worker's `check_site` takes no interior today, so its egress always waits. Giving the worker an interior is a protocol change, left for the Revit work.)

  The title block prints both fingerprints and the rulebook file's sha256; every rule id must be in that rulebook, and each item's quote must be the rule's own first quote.

The CSVs carry, on every row, the item id, rule id, part kind and id, measure names and values, citation and quote, so any number on a sheet can be found in the check result.

## Never a false pass

- Results print in capitals, word for word: **COMPLIES**, **DOES NOT COMPLY**, **NEEDS REVIEW**, **WAITING: NO ROOMS DRAWN YET** (the words after "WAITING:" are the check's own, its waiting item's `waiting`; a waiting item without them stops the command). "Needs review" and "waiting" are never shortened, coloured green or ticked. Colour is always paired with the word, so a black-and-white print reads the same.
- A window's line in the schedule is the most cautious of every row the check gave for that window (fail, then needs review, then complies), so one window that complies on size but needs review on "opens to a yard" reads NEEDS REVIEW. **No rows is never "complies":** a window marked as an escape opening that the check didn't check (in a room that isn't a sleeping room: `egress.interior.not_checked`, its "skipped" item) prints NEEDS REVIEW with the check's reason, and so does any listed window with no rows at all. A sleeping room with no opening marked prints the most cautious of every row the check gives the room itself (R319.1, R319.6…: DOES NOT COMPLY today); if the check has no row about it, NEEDS REVIEW.
- Each sheet's headline status is the egress section's state from the check, and never kinder than the worst row on that sheet.
- No rooms drawn yet: every sheet still prints, each saying WAITING: NO ROOMS DRAWN YET, never an empty table that could read as nothing wrong.
- Rows the check left out because they don't apply are not printed (the check doesn't give them as items). The code analysis says how many rules were checked and how many rows each result has, so the totals can be compared with the check's own summary.

## What it can't show yet (said on the sheets)

- **Window and door positions.** The interior description gives each window and door in its own elevation, not where it sits in the plan. So escape openings are tagged inside their room, not drawn in the wall, the exit door is named in a note, and the exit route is a diagram (bedroom → stair → exit door), labelled as a diagram. The plan says so in a note. A position for openings and doors in the format is a follow-up (not in this PR: the format belongs to the measuring code).
- **Rooms with no place in the house.** A description whose rooms overlap on one floor (the Orangetown house: each room drawn from its own corner) can't be drawn as one plan; those rooms are drawn apart, side by side, with a note. A room with no outline or no floor elevation (the Orangetown basement) can't be drawn at all: it is listed in a box beside the plan with its tagged escape openings, so nothing marked vanishes.
- **Not read is not none.** The format says a list left out means it wasn't read (`stairs` missing), an empty list means there are none. The plan says which: "Stairs: not read from the drawing, NEEDS REVIEW" (Orangetown), "Exit door: not read from the drawing, NEEDS REVIEW" (house 3), or "No stairs". An absent stair or door is never drawn as if the house had none.
- **The way out isn't checked.** No rule in the rulebook checks the route from a bedroom to the exit, so the route is drawn only as a schematic, labelled "schematic, not checked by Gordium", never with a result of its own. Where the stairs or doors weren't read, it says that instead.
- **The architect's decisions on "needs review" rows** (the doc's basement row: "Reviewed: architect's decision printed here"). The check doesn't record decisions yet, so every needs-review row prints NEEDS REVIEW with its reason; a decision column is left for later.
- **The firm's title block** and Revit/Rhino layout sheets: later (the doc's §11 order: Revit reading next).

## How it's tested

- **Goldens:** the five made-up interior houses, the Orangetown house and one with no rooms (waiting), each checked with the same plain test lot through the same fingerprint-guarded function the command uses (a site description in place of a .3dm), written to `test_data/goldens/permit_sheets/<house>/`. A test rebuilds them and needs every file the same (`python -m permit_sheets --check`; `--write` to record again only when an answer should change).
- **Pins (each fails when its rule is reverted):** every printed result equals the check's status; the check's own items (Orangetown's "stairs weren't read" and its 4 skipped windows) print as NEEDS REVIEW and the counts equal the section summary; a skipped window is NEEDS REVIEW on A-601; a changed rule formula with its quote unchanged stops the command; a 44.06 in sill prints 3'-8 1/8"; "not read" stairs and doors say so on LS-101; a needs-review or waiting row never prints COMPLIES; a window's line is never kinder than its worst row; a disagreement between item and row, an unknown status, a different interior or a changed rule stops the command; every CSV row's rule id, citation, quote and values are the check's; the title block carries the disclaimer, date, rulebook sha256 and interior sha256; the waiting house prints WAITING on all three sheets.
- **The PDF is read back** with `pdfplumber` (already a dependency) in the tests, so what a reviewer opens is what was checked, not only the SVG.

## How it's built

`packages/permit_sheets/`: a README, the code, `tests/`. No new dependency: SVG and PDF are written by plain code (the PDF uses the standard Helvetica font, its widths from `pdfminer`, already installed, so text is measured and never runs out of its cell); the XLSX by `openpyxl`, as `project_report` does. The same drawing (lines, boxes, text) is written as SVG and as PDF, so the two always match. Output is byte-for-byte the same for the same inputs (no clock: the date is given).

```
python -m permit_sheets <house.yaml> --model <model.3dm> --facts <facts.yaml> --project <project.yaml> --out <folder>
python -m permit_sheets <house.yaml> --site <site.json> --facts <facts.yaml> --project <project.yaml> --out <folder>
python -m permit_sheets --check      # every golden matches a fresh build
python -m permit_sheets --write      # record the goldens again
```

`<project.yaml>` gives the title block's project name, address and date. There is no `apps/command_line` in the repo, so the command is the package's own, like `project_report`'s.
