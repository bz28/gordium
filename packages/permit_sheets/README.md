# permit_sheets

Prints the three egress sheets an architect attaches to a permit application, from Gordium's own check of the house:

| Sheet | What it shows |
|---|---|
| **G-001 Code analysis: egress** (G-002… if it runs long) | The check's results grouped as the panel groups them ([results grouping](../../docs/decisions/2026-11-16_results_grouping.md)): each failing rule on its own row (the part, the requirement and its rule id, required, proposed, the code section, what to change); then one row per part that needs review the architect can act on; then one row per cause Gordium can't read yet ("Handrails · 10 rules · not read from the model yet: check by hand"); then one row per part that complies. Each row's result is the most cautious of its rules and it gives every code section and the `code_analysis.csv` lines of its rules. The check's "Not checked yet by Gordium" line (the code sections Gordium has no rules for yet) is printed as a NEEDS REVIEW row with every section listed in a banner under it, and said under the egress result, so a set never reads as complete; while egress waits (no rooms drawn) the waiting row carries the same list and the result stays WAITING |
| **LS-101 Life-safety plan** (one per floor) | The floor's rooms from their outlines, sleeping rooms marked, each escape opening tagged with its result, stairs with UP/DN, the exit door, and a schematic of the way out (labelled "not checked by Gordium") |
| **A-601 Escape-window schedule** | Each sleeping room's escape openings: type, net clear width, height and area, sill height, grade floor, each against its limit with that rule's result, and the opening's result over all its rules |

Files: one SVG per sheet, `permit_sheets.pdf` (every sheet, 11 x 17 in), `code_analysis.csv` (every rule's own row,
with "Shown on G-001 as" naming its line on the sheet), `escape_window_schedule.csv` and `permit_sheets.xlsx`. Each sheet has a title block: project, address, date, the
rulebook (file, sha256, "draft"), the rules and code fingerprints, the interior's fingerprint, a blank stamp box,
and **"Prepared with Gordium: draft rules, verify before submission"**. Plain code, no AI; no new dependency (SVG
and PDF are written by `draw.py`, the XLSX by openpyxl as `project_report` does). The design and its review:
[docs/permit_sheets/plan.md](../../docs/permit_sheets/plan.md).

```
python -m permit_sheets <house.yaml> --model <model.3dm> --facts <facts.yaml> --project <project.yaml> --out <folder>
python -m permit_sheets <house.yaml> --site <site.json> --facts <facts.yaml> --project <project.yaml> --out <folder>
python -m permit_sheets --check      # every golden matches a fresh build (the tests run this too)
python -m permit_sheets --write      # record the goldens again, only when an answer should change
```

`<project.yaml>`: `title`, `address` (optional), `date` (YYYY-MM-DD). The sheets never read the clock; the date
is also the check's day.

## A print-out of the check, never a second check

The command runs the check itself (`design_checker`, as the plugin does) and prints from that answer
(`source.checked`). It stops, printing nothing, when anything doesn't add up:

- **Results:** each line's result is the check's item status, word for word: COMPLIES, DOES NOT COMPLY, NEEDS
  REVIEW, or WAITING: <the check's own reason> (`words.result_words`; any other status is refused); a grouped G-001
  row's is the most cautious of its rules'. An item about a part is paired with its raw row and the two must agree;
  every row the panel shows must be printed in the CSV (that each is cited by exactly one G-001 row holds by how G-001 is built, and is pinned by a test, not refused at run time); each law's summary
  must equal the checker's own count of its items (`present._law_summary`).
- **Never kinder than the worst row:** a window's line is the most cautious of all its rows; a bedroom with no window
  marked takes its own rows' result; no rows at all, or a window marked but not checked, is NEEDS REVIEW
  (`words.worst`, `tables.schedule_rows`).
- **Which rules:** the rules and code fingerprints (`protocol.rulebook_fingerprints`, `worker_fingerprint`) are read
  before the check and again after the sheets have loaded the rules; any change stops the command. Every rule id
  must be in the rulebook and every quote the rule's own.
- **Which drawing:** the interior description's fingerprint must be the one the check recorded
  (`egress.fingerprint`).
- **Numbers:** Required and Proposed are worked out from the rule's formula and the row's values, for reading only.
  They are never rounded toward compliance: a value that must be at least a limit rounds down, at most up, the limit
  the other way (lengths to 1/8 in, areas to 0.01 sq ft).

What the interior description can't place is said, never drawn as known: windows and doors have no plan position
(openings are tagged in their room, the exit door is named); rooms with no place in the house are drawn apart, to
scale each; a room with no outline is listed with its openings; a list left out (`stairs`) is "not read: NEEDS
REVIEW", never none.

## The code

| File | Job |
|---|---|
| `source.py` | Runs the check under the fingerprint guard; gathers and proves every value (`checked`, `gather`) |
| `tables.py` | The code-analysis and schedule rows, each with its rule id, part, values, citation and quote |
| `words.py` | Result words, the most cautious of several, lengths and areas, a rule's limit in words |
| `plan.py` | The life-safety plan's floors, rooms, stairs, tags and exits from the interior description |
| `sheets.py` | The sheets laid out: title block, tables, plan |
| `draw.py` | One drawing written as SVG and as PDF (Helvetica, measured with pdfminer's metrics) |
| `build.py` | The files; the project file's checks |
| `goldens.py` | The golden sheets in `test_data/goldens/permit_sheets/` |

## How we know it is right

`tests/test_permit_sheets.py`: every printed result equals the check's status; needs review and waiting never print
as complying, and waiting prints on all three sheets in the check's own words; a window's line is its worst row's; a
skipped window and a bedroom with none marked; the check's own items are printed; each refusal (an item that
disagrees with its row, a row missing from the panel, counts that don't add up, another interior, changed rules,
changed words); every row's values are the check's row's; the title block on every sheet; rounding; "not read" on
the plan; the SVG and PDF carry the same words; and the goldens of the five made-up houses, the Orangetown house and
a house with no rooms yet match a fresh build.

Not yet: the architect's recorded decision on a needs-review row (the check doesn't keep decisions yet), the firm's
own title block, positions for windows and doors (the interior format has none), and Revit/Rhino layout sheets.
