# PR 15 build spec: Gordium in Rhino, UI

Status: approved by Claude on Ben's delegation (2026-10-20), after three critique rounds (each round: a practicing architect and a pro-tools product designer, both cold). Mockup: https://claude.ai/artifact/E18rXU59kG8rLUZa1hgktQ (boards 1–8). Example throughout: 106 Ithaca Rd, R-1b, one-family dwelling.

**How to read this.** Each item is one acceptance criterion. The tag says how it is verified:
- **[code]**: a pytest test, with no Rhino (plain Python: measurement, rules, result model, formatting, report).
- **[rhino]**: a scripted check inside Rhino 8 via `rhinocode`, with evidence (a viewport capture or the panel's data dumped to JSON).
- **[both]**: the logic is tested in code, and the behavior is confirmed once in Rhino.

A PR is done when every item has its test, and each test fails if the behavior is removed.

**Terms used below.**
- **Item:** one row of the result list (e.g. Rear yard).
- **Status:** one of four:
  - **complies** ✓
  - **does not comply** ✕
  - **needs review** ?
  - **not checked**: needs input, or not in this release.
- **Setup problem** (⚠) is never an item status.
- **At limit:** zero margin at 1/8" resolution.

---

## A. Start box (board 1; simplified as approved by Ben, 2026-10-20: this section supersedes the earlier one)

A1 [rhino] **Command and dialog.** `GordiumStart` (and `GordiumCheck` on an empty file) opens one modal box, titled "New zoning check". `GordiumFacts` and the panel's **Edit site…** open the same box, titled "Zoning check · site". A Change or Pick button closes the box, runs the pick in the model, and opens the box again with the result.

A2 [code] **Rows, in this order** (`rhino_logic.box_rows`, tested in CI):
1. **Address** and **[Look up]**. The lookup is a later PR; until then it reads "Look up (coming soon)", disabled, and the facts come from the lot as drawn.
2. **Zoning district**, with its source ("entered by you" today; "from City map" once the lookup exists), a dropdown, and **☐ I confirm**. One district today; more than one later.
3. **Use**: a dropdown.
4. **Lot**: "<area> sf · from the tax map (±2 ft, approximate)" or "… · from your survey", with **Use my survey…** (pick the surveyed outline).
5. **Street side**: the street's name, or "the highlighted line", with **Change…** (pick another lot line), and **Corner lot?** (Not answered / No: one street / Yes: two streets). It is never guessed: while it is unanswered the amber line asks it and the yards need review (§325-19C).
6. **Ground**: what the ground is and where it came from. Today that is "flat at the lot level · as drawn", or the spot grades or terrain with their range. Its actions are **Place spot grades…**, **Pick terrain…** and **I'll regrade: set finished ground…**, plus one tick, **☐ No regrading near the house**.
7. One line: "Not checked yet: overlays (historic, gorge, flood) · pitched roofs".
8. An uncertain case the box can't settle shows as **one amber line with the action**:
   - a corner lot → "This lot faces two streets: pick the front";
   - two zones → "This lot is in two zones: pick the zone that applies";
   - (with the lookup) not found or offline → manual entry.
9. **[Cancel] [Draw]**.

A3 [code] **"I confirm" is unticked on every new project.** On an existing project it is ticked only if the same district was confirmed at an earlier Draw. **Draw is enabled only when it is ticked**, with "Confirm the district to continue." beside it (`rhino_logic.district_confirmed`, `can_draw`).

A4 [code] **No regrading near the house.** Ticked, the ground shown counts as the finished grade, and height is checked normally. Unticked, with only the existing ground, height and stories need review (C5). Ground set with "I'll regrade" is finished ground (`rhino_logic.ground_facts`).

A5 [code] **Every fact has a source.** Each fact the box sets is saved as {value, source, confirmed_by, date} in the .3dm (`Gordium / fact_sources`). A Change records the source "entered by you". The checker never reads the sources, only the values. The panel shows them (Site facts, when no row is selected), and the report's Check tab lists them (`rhino_logic.fact_sources`, `present.source_lines`).

A6 [rhino] **Removed from the box:**
- existing building, roof, floor-to-floor, the "Ground is" select, and the massing radio;
- the starting building is always drawn with the envelope (a "Hide starting house" toggle sits in the panel, and hiding it doesn't stop it being checked);
- floor-to-floor stays 11'-8" in code, editable later through GordiumFacts.

A7 [rhino] **Look.** System default buttons and checkboxes; no brand accent color.

## B. Generated massing and envelope (board 2)

B1 [code] **All numbers come from the drawn lot.** No figure is typed in from elsewhere. For the example (73'-0" × 90'-0"):
- lot area 6,570 sf;
- coverage allowance 25% = 1,642.5 sf;
- envelope 53'-0" × 42'-6" = 2,252 sf;
- massing 53'-0" × 30'-11" = 1,639 sf (24.94%), placed at the 25'-0" front yard;
- rear yard 34'-1".

B2 [both] **The starting massing is legal by construction.** It is the largest box inside every yard, no taller than 35'-0", at or under the coverage limit, with stories = floor count. A code test asserts every rule result is complies or needs review, never does not comply, for the generated massing on any test lot.

B3 [rhino] **One group.** The massing is a single group of N floor solids on layer `Gordium::Massing`, so a Move moves the house, and the command line reports "Moved 1 group".

B4 [both] **A floor moved alone** gives needs review on Stories: "Floors misaligned".

B5 [rhino] **Buildable envelope.**
- **Plan:** the area inside the yards, drawn see-through.
- **3D views:** a see-through height plane at 35'-0".
- **Toggle:** "Show buildable envelope" in the panel.
- **Label:** "Buildable envelope 2,252 sf · Coverage allows 1,642 sf (25%) · Height plane 35'-0" (3D views)".

B6 [rhino] **Command line.** GordiumStart prints one line: "created 1 group (3 floor solids) on Gordium::Massing".

## C. Measurement honesty (needs-review triggers)

C1 [code] **Never a false pass.** Any missing, ambiguous or approximate input gives needs review, never complies.

C2 [code] **Tax-map tolerance** of ±2'-0".
- Each lot-dependent value is evaluated at the worst case over ±2'-0": lengths directly, and areas and percentages by offsetting the lot outline.
- If the item would not comply at that worst case, it needs review, with the reason "Lot lines are from the tax map (±2'-0")…" plus the worst-case value.
- On the example lot this flags Front yard, both Side yards and Lot coverage; Rear yard (+11'-7"), Lot width (+23'-0") and Lot area (6,570 sf; 6,248 sf at the worst case, 71' × 88') still comply. (Corrected 2026-10-20: lot area was listed by mistake; the worst-case method applies to every lot-dependent item, areas and percentages as well as lengths.)

C3 [code] **Grade not set** → Building height and Stories need review ("no grade").

C4 [both] **Grade recomputed after every footprint change** from the terrain, or from the spot-grade points, at the new wall locations. If it can't be recomputed (e.g. points no longer at the walls), Height and Stories need review: "Spot grades no longer at building walls · Set grade…". This happens on board 4: the house moved 13'-7" and 2 of 6 points are off the walls.

C5 [code] **"Existing grade" selected** → Height and Stories need review: "Measured from existing grade; code uses finished grade".

C6 [code] **Roof not flat** → Height needs review: "Roof not flat; this roof's height rule isn't checked in this release".

C7 [code] **Height** follows §325-3 verbatim. It is measured from the grade plane (the average of finished ground level at the exterior walls, per the GRADE PLANE definition) to the highest level of a flat roof. Where roof sections vary, the highest section counts.

C8 [both] **Measured scope.**
- Every item states what was measured, e.g. "1 group, 3 solids on Gordium::Massing · footprint 1,639 sf"; selecting the item highlights those objects.
- Any closed solid or polysurface on the lot outside the checked set adds a needs-review row: "2 objects on the lot not included · Add to check…".

C9 [code] **Precision.**
- Measured to 1/8 in.; values are never rounded toward compliance.
- Near a limit, values are shown with one more decimal (24.94%).
- At a limit, values are shown at 1/8" resolution ("25'-0" exact").
- "at limit" means zero margin at 1/8".

C10 [code] **Fails under every reading.** When an item fails under every reading the code allows, the detail says "Fails under every reading considered (…)". If any reading would comply, the item needs review instead of failing.

C11 [code] **Interpretation notes for the user.** A note on a reading Gordium chose is phrased for the user, e.g. "Gordium reads X as Y; confirm with the zoning office". Internal phrasing such as "question for the architects" never appears in the UI.

## D. Panel (boards 3, 4)

D1 [rhino] **Structure.** A docked Eto panel:
- a header;
- a TreeGridView list on top;
- a splitter;
- a lower pane showing the selected row, following keyboard up/down;
- no back arrow.

D2 [code] **Header contents.**
- Address, district and use, with an "Edit site…" button.
- The code edition the rulebook was compiled from: "Ch. 325 as on eCode360, retrieved 2026-10-19 (incl. Ord. 2025-12) · District Regulations Chart, Apr 2026".
- The summary.
- A "Draft rulebook" tag.
- The lot and grade sources, with "Pick survey lot lines…" and "Set grade…" while they are approximate or unset.

D3 [code] **Summary rule.** One function produces the summary used by the panel, the viewport status and the report, with identical text everywhere.
- It counts every row, Site rows included.
- Bad news comes first; zero counts are dropped; ✓ is never shown.
- Examples: "7 need review · 3 comply · 3 not checked" (board 2) and "1 does not comply · 2 need review · 7 comply · 3 not checked" (board 4).

D4 [both] **Columns.**
- Mark | Item | Proposed | Req. ≥/≤ | Margin.
- The column header carries the ≥ / ≤, so value cells hold plain values ("22'-6"", "25%"). Margins read like "+11'-7"", "−2'-6"", "at limit", "+0.06%". Not checked rows carry their reason in the Item text ("Parking · needs input"), so they never widen the value columns.
- The value columns are sized to their content and never truncated; only Item truncates. Minimum panel width 320.

D5 [code] **Groups,** in order: Does not comply · Needs review · Complies (Site rows included, labelled "Site · …") · Not checked · Not covered by this rulebook. Section headers aren't selectable.

D6 [both] **Side yards** are two rows, "Side yard, West" and "Side yard, East", and the plan shows the same values.

D7 [code] **Not checked.**
- Rows: "Parking · needs input", "Dwelling units · needs input" (the Enter… buttons live in the lower pane: "Enter bedrooms and parking spaces", "Enter the number of units, including any ADU"), and "Overlays · not in this release" (historic, gorge, flood).
- **Not covered by this rulebook:** a collapsible group listing the sections not encoded: §325-16A and B height exceptions, §325-18 yard projections, §325-19C corner lots, §325-25 accessory structures, §325-28 ADUs.

D8 [rhino] **Refresh** keeps the selected item (by item id), the expanded groups and the scroll position.

D9 [rhino] **Zoom to and row clicks.**
- "Zoom to" is disabled until a row is selected.
- Each item defines its own view: yards → Top; height → front elevation.
- A double-click on a row zooms too.

D10 [rhino] **Footer:**
- the "Show buildable envelope" checkbox;
- "?" for the legend and symbols;
- "Zoom to";
- "Zoning report…".

## E. Detail (lower pane; board 5)

E1 [code] **Contents.** Each detail shows:
- the status;
- the proposed vs required line, e.g. "20'-0" proposed < 22'-6" required → short 2'-6"";
- the measured scope (C8);
- the code text quoted verbatim, including the chart row label and the R-1B cell, plus any footnote. Example: "Rear (minimum, % of depth or feet, whichever is less)" · R-1B "25% / 50 ft" ¹⁶ · "(16) But not less than 20 ft.";
- the citation;
- the calculation;
- a "to comply" hint where one exists;
- the precision sentence (C9).

E2 [code] **Citation format,** as an examiner writes it: "§325-8, District Regulations Chart, R-1b, Rear yard column, note 16" and "§325-8A(14)". The PDF page appears only as the link target. One format on every surface, the report included.

E3 [code] **Link targets.** Each cited section has its own link target; no two sections share a URL (a test enforces this). Every link resolves to a real document, never a placeholder.

E4 [code] **Chart-cell quotes** exist for Rear yard, Front yard ("Front (minimum)" · R-1B "25 ft"), Lot coverage ("Percent of lot area" · R-1B "25%", plus the §325-8A(10) sentence) and Height ("Height in feet" · R-1B "35 ft", note 10).

E5 [both] **Building height detail.**
- The full §325-3 HEIGHT OF BUILDING and GRADE PLANE definitions.
- The spot-grade points listed individually with their locations and elevations.
- A section diagram labelled "Diagram, not to scale", showing the lot lines and yards.
- "Zoom to opens the front elevation".

## F. Viewport drawing (boards 2, 4, 6b)

F1 [rhino] **All plan graphics come from a DisplayConduit;** no model objects are added for annotation.

F2 [rhino] **Plan contents:**
- a phantom-pattern property line;
- one dimension per lot edge, with "(approx.)" on a tax-map lot;
- dimensions for the front yard, the rear yard, and the West and East side yards;
- a translucent hatch in the required yards;
- dashed yard lines and envelope;
- the street labelled "ITHACA RD · R.O.W. / FRONT LOT LINE";
- yard labels.

There is no scale bar, north arrow, legend or section marker; the legend is behind "?".

F3 [rhino] **Labels** are screen-size, horizontal 2D text with a halo or backing so they stay readable on light and dark viewports.

F4 [code] **Status symbols in the plan** match the panel: review labels are prefixed "? " and drawn amber; failing labels are prefixed "✕ " and drawn red.

F5 [rhino] **Red** appears only on the encroachment strip, hatched between the wall and the yard line; the massing itself stays neutral.

F6 [both] **Status box,** top right: the summary (D3) plus a second line ("Draft rulebook", plus the lot and grade sources when approximate).

F7 [both] **Out of date.** When the model changes, the viewport and the panel go to "Checking…" / "Out of date" on the same 300 ms rule. In that state:
- the status colors and the red hatch are dropped;
- the dimensions draw neutral;
- the status box shows "Out of date" or "Checking…".

F8 [rhino] **Theme colors.** They follow Rhino's viewport background brightness, so the same drawing works in dark and light.

## G. Notice (board 4)

G1 [both] **When it appears.** Drawn by the DisplayConduit in the active viewport only, bottom left, at the end of a command (never during a drag), only for items that newly stop complying. It has no window and no button.

G2 [code] **Several new failures in one command** merge into one notice: "2 items no longer comply: Rear yard, Lot coverage".

G3 [rhino] **It clears** at the next command or after about 6 s. While it shows, the status box still shows "Draft rulebook".

G4 [rhino] **No command-line echo** except on Gordium's own commands; Move prints only Rhino's own message.

## H. States (boards 6, 6b)

H1 [code] **Checking…** appears only while a check is running, and only after 300 ms. Rows keep their names, show no mark and "—", and Zoom to is disabled.

H2 [code] **Check could not run** is a separate state: "⚠ Check could not run" with a Retry button and the reason in the lower pane. Rows show no mark and "—".

H3 [code] **Setup problems** use ⚠ with a real fix button and never count as rule results:
- (with the later site-lookup PR: address not found, multiple parcels, City map offline);
- district not supported → "Edit site…";
- building not found → "Pick building…";
- model units not feet/inches → "Units…";
- massing extends outside the lot → "Zoom to";
- rulebook damaged → "Reinstall…".

H4 [code] **Rule-level problems** are needs review (?) with a reason: measurement failed (e.g. an open solid), floors misaligned, objects on the lot not included.

H5 [code] **"–"** means only not checked (needs input, or not in this release). Stale rows draw no mark.

## I. Zoning report (button "Zoning report…")

I1 [code] **The report** is the architects'-format workbook from PR 10, plus:
- the draft-rulebook label;
- the lot source and grade source;
- the summary (D3, identical text);
- the not-checked and not-covered lists;
- every citation in the E2 format, with links.

I2 [code] **The report shows the same statuses as the panel.** No result appears in the report that the panel doesn't show, and the other way round.

## J. Visual system

J1 [rhino] **Type:** the system font; 13 regular, 13 semibold, 11 small, and 15 for the summary only.

J2 [rhino] **Colors:** Eto SystemColors for all chrome. The only added colors are red (does not comply) and amber (needs review), with shades keyed to panel and viewport brightness. No teal or brand accent.

J3 [code] **Symbols:** ✕ does not comply, ? needs review, ✓ complies, – not checked, ⚠ setup problem. Every status is a shape plus words, never color alone.

J4 [rhino] **Contrast:** hint text is at least 4.5:1 on its background in both themes.

J5 [code] **Vocabulary** uses the code's own terms: Front yard, Side yard (West/East), Rear yard, Lot coverage, Building height, Stories, "R-1b" written the same way everywhere. "Proposed" is used, not "provided".

## K. Out of scope for this release

- Existing buildings and nonconforming conditions (Existing | Proposed | Required).
- Notes and a "variance requested" state.
- "Bake zoning graphics" to layers, and a zoning table on a Layout for permit sets.
- Overlay districts (historic, gorge protection, flood); they are listed under Not checked.
- Pitched, hip and gambrel roof height; gable and hip massing.
- Corner lots (§325-19C) and accessory structures (§325-25); they are listed under Not covered.
- Districts other than R-1b, which give "District not supported".
- Survey-to-parcel comparison and automatic lot-line lookup; that is the separate site-lookup proposal.
