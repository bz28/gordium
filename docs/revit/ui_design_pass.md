# Revit add-in: a design pass on the ribbon, the results panel and the marking list

**Purpose:** what an architect meets in Gordium's Revit add-in today, step by step with every friction point, and a proposed design (ribbon, results panel, a result's detail, guided fixes, the marking checklist, visual language, states) with what Revit 2025-2027 allows and a build plan in small PRs, each with how it is evaluated. Agreed by Ben on 2026-11-21 (section 6); built PR by PR.\
**For:** Ben; whoever builds the add-in's UI; architects trying the add-in.\
**Kept current by:** the PR that builds a part of it marks that part built (or changed, and why); Ben's decisions are written into section 6.

The interactive mockup is [ui_mockup/index.html](ui_mockup/index.html) (open it in a browser: one file, no network).
Every figure in it is from the Children's Odyssey eval (19 Libby St, Portland ME):
`test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml` (branch `feat/route-measures-2`),
`eval_marks.yaml` and `hand_check.yaml`, and the rule quotes from
`regulations/jurisdictions/maine/maine_state/5_building_code_rules/drafted/general.yaml` on the same branch.

Words used here: a **mark** is a Gordium field (a Revit shared parameter, such as `Gordium: Exit`) where the
architect states a fact Gordium never guesses. A **row** is one rule's result for one part (a story, a door). The
**worker** is the Python checker the add-in talks to. **WPF** is the Windows toolkit Revit's own panels are built
with.

## 1. Today's flow, step by step

Read from the code on `main` (a84da8a9): `App.cs`, `CheckProject.cs`, `ResultsPane.cs`, `ResultsView.cs`,
`PanelActions.cs`, `RevitMarks.cs` (`MarkForEgressCommand`), `Gordium.Revit.Reading/MarkingList.cs`,
`ResultRows.cs`, `ResultText.cs`, `CheckAgainState.cs`.

### Step 1: find Gordium in Revit

The **Gordium** tab has three panels, in this order: **Trial** (About, Check box house, Record scenes), **Check**
(Check my project), **Egress** (Mark for egress, Read inside, Record houses).

| # | Friction | Where |
|---|---|---|
| F1 | 7 buttons, of which 2 are for an architect. Five are trial and test tools (About, Check box house, Record scenes, Read inside, Record houses), and three of them draw new Revit models. An architect can't tell which to press. | `App.OnStartup` |
| F2 | The order is backwards: marking comes before checking in the work, but **Mark for egress** sits after **Check my project**, in a panel called "Egress" (zoning facts are marked too, on Project Information). | `App.OnStartup` |
| F3 | No icons: every button is text only (`PushButtonData` with no `LargeImage`), so the tab looks unfinished next to Revit's own. | `App.OnStartup` |
| F4 | Tooltips are paragraphs. Check my project's is 70 words ("...the lot facts on Project Information (Gordium's marks, added on first use)..."); Revit shows a short tooltip and a longer description on a longer hover (`LongDescription`), which isn't used. | `App.OnStartup` |
| F5 | "Read inside" says "nothing is sent to the checker yet" and only writes a log: a button an architect can press that does nothing they can see. | `ReadInteriorCommand` |

### Step 2: mark the facts (Mark for egress)

The button adds Gordium's marks to the project if missing, fills makers' clear openings as drafts, and opens a
**TaskDialog** (Revit's modal message box) titled "Gordium: mark for egress" whose headline is one of four
sentences ("Some marks are not set or can't be read") and whose body is `MarkingList.Text(list, maxRows: 25)`: plain
text, "TO MARK  Room: STORAGE (13)" then each mark indented, then "... and 14 more (every row is in the log)", then
"Logged to C:\...".

| # | Friction | Where |
|---|---|---|
| F6 | A modal text box: nothing in it can be clicked. To mark CLOSET (40) the architect reads its name, closes the dialog, finds the room in the model or a schedule, selects it, finds `Gordium: Use` in Properties (the marks sit in Revit's **Data** group among the project's own fields), types a word from a list the dialog only names, and presses the button again to see the list again. About 8 actions per element; the Children's Odyssey model has 39 rooms, each with three route marks. | `MarkForEgressCommand.Execute` |
| F7 | Cut at 25 rows; the rest are "in the log", a file path an architect won't open. | `MarkingList.Text` |
| F8 | No progress: nothing says "31 of 39 rooms marked". The headline flips from "Some marks are not set" to "Every room, window and door is marked" only at the end. | `MarkingListResult.Headline` |
| F9 | Typed words: `Gordium: Use` and `Gordium: Exit` are text fields where a word outside Gordium's list is "not understood". The list of words is only in the dialog's text and the parameter's description. | `RoomUses`, `ExitKinds` |
| F10 | Suggestions are text: "suggested: Day care (named "CLASSROOM"); set it yourself to accept". Accepting is the same 8 actions as F6. | `MarkingList.SleepingSuggestion`, `UseSuggestion` |
| F11 | Problems that stop whole kinds being read (18 enclosed areas with no Room on the Odyssey's first read, a stair hidden by a Generic Model) are lines of text at the top of the dialog, mixed with summary lines; none can be selected. | `MarkingList.Text` |

### Step 3: check (Check my project)

One click reads the model outside and inside, adds marks, may ask for the street edge, sends one check, and opens
the dockable pane **"Gordium: Check my project"**, tabbed behind Properties.

| # | Friction | Where |
|---|---|---|
| F12 | Revit freezes for the whole check: the read and the worker's answer are both waited for on Revit's own thread (`Task.Run(...).GetAwaiter().GetResult()`), and the panel says only "Checking...". No progress, no time estimate, no cancel. | `CheckProjectCommand.Run` |
| F13 | The street-edge pick asks, for each click, "Use the 60.0 ft lot edge from (x, y) to (x, y) as the street line?" in shared coordinates, default **No**. Architects don't read edges as coordinates; they see the edge. | `PickStreet` |
| F14 | A required fact missing: "Nothing was checked: fill these in first" with bullets and **Open Project Information**, which opens Revit's dialog with every project field; the architect looks for "Gordium: Zone" among them, closes it, clicks Check again. Fine, but 4 actions for each round. | `ResultsView.ShowMissing` |
| F15 | A failed check shows a TaskDialog *and* the panel's line, both with an exception name and a log path ("Nothing was checked: InvalidOperationException ... (logged to C:\...)"). | `CheckProjectCommand.Check` |

### Step 4: read the results

Top to bottom: the title "Gordium: Check my project" (again, under the pane's own title) with **Check again**; "Checked
14:32 · project"; an italic status line; the state in colour; one line of count chips per law ("Zoning",
"Egress"); the worker's groups as WPF Expanders (group, then line, then row, then the row's **Law** expander:
up to four levels of folding); then "What wasn't read from the model" and "Details" (phase, options, file paths).

| # | Friction | Where |
|---|---|---|
| F16 | The headline is the worker's state word, and the chips are the worker's words: "needs review", "8 need review". Nothing says *what to do first*. On the Odyssey eval every one of the 8 route rows needs review, for 3 different causes; the panel shows 8 rows, not 3 jobs. | `ResultRows.Counts`, `GroupBlock` |
| F17 | A needs-review row says why, but not what to do, and offers nothing to do it with. "Exit access travel distance" needs review because "the point (165.625, 70.156) has no route to any exit (a path 12 in clear of every corner, through door centres and rooms it may cross)". The 5 rooms without a route (CLOSET (40), ELEC. (21), SPRINKLERED ABANDONED SPACE (32) and (33), STORAGE (13)) are named only inside the measuring's story; a coordinate in feet is the only pointer. Show in model selects the row's part, here the story's level, not the rooms. | `ResultRows.Row`, `ResultsPane.ShowElements` |
| F18 | Clicking anywhere on a row's text selects and zooms: an architect reading the list changes their view by accident, and loses where they were. There is no "select without zoom" and no way back. | `ResultsView.RowBlock` |
| F19 | The law's words are behind a fold per row, with "where" as text ("R319.2.2, 2025 Residential Code of New York State (RCNYS), PDF p.102"). No link opens the source at that page, so "the law's exact words with a link" is half there. | `ResultsView.RowBlock` |
| F20 | Figures are a sentence ("net clear height 20 in, needs ≥ 24 in"); how far off appears only when the worker gives a `delta` (zoning rows). An egress row never shows how far off, by design today (`ResultRows`: "never worked out here"). | `ResultRows.Row` |
| F21 | Grey "stale" covers everything after any edit, even moving a tag; the only way out is the small Check again in the corner. Safe (no stale pass), but the architect can't see which rows the edit could have changed, and the fix-then-recheck loop is slow. | `ResultRows.Stale`, `ChangesTheCheck` |
| F22 | Colours: fixed RGB (red #C62828, amber #B26A00, green #2E7D32, grey #757575) on Windows' system colours, not Revit's. In Revit's dark theme (2024 on) the panel stays a light Windows window, and the default WPF Expander and Button chrome look foreign in both themes. Red and green differ mostly in hue (hard for the 1 in 12 men with red-green colour blindness); the verdict word saves it, the colour bar and chips don't. | `ResultsView.ColorOf`, constructor |
| F23 | No search, filter or keyboard: Up/Down don't move through rows, Enter doesn't show, Ctrl+C doesn't copy a row. On a 137-row egress check this matters. | `ResultsView` |
| F24 | Developer words reach the architect: file paths, "the worker", element labels as "Windows id 341207", "Logged to C:\...". | `PanelContent.Files`, `CheckProjectCommand.Label` |

### What a needs-review row asks, and whether the panel can do it

The 8 rows of the Odyssey eval (`eval_comparison.yaml`, `verdicts.rules`), all **needs review**:

| Rule | Why (the eval) | What the architect must do | From the panel today? |
|---|---|---|---|
| IBC 1016.1 travel distance (200 ft) | 5 rooms have no route to an exit; over the rooms with a route the longest walk is 110.2 ft, from STORAGE (11). Also a flag rule, so a person decides it even once measured | find why each of the 5 rooms has no route (a door not drawn or not read, a room it may not cross, a corner closer than 12 in) and fix the model or the marks | No: the rooms are named nowhere clickable |
| NFPA 101 16.2.6.2(2) travel (150 ft) | same 5 rooms | same | No |
| IBC 1014.3 common path (75 ft) | 6 rooms (the 5, plus CORRIDOR (26)) have no route to one of the two exits; 43.5 ft over the rest | same | No |
| NFPA 101 16.2.5.3.1 common path (100 ft) | same 6 rooms | same | No |
| IBC 1018.4 dead end | the corridor isn't straight legs meeting at right angles: dead ends and width not measured in this first version (decision 6) | measure the dead end by hand (the sheet: 21'-6", 10 ft wide) | No: nothing says "check by hand" or where |
| NFPA 101 16.2.5.2 dead end | same | same | No |
| IBC 1015.2.1 remoteness | a flag rule (a person decides); the figures meet it: exits 187.2 ft apart, at least 1/3 of the 213.0 ft diagonal (71.0 ft) | confirm the measure and that two exits are what 1015.1 requires | Partly: the figures show; nothing to record the decision |
| IBC 508.2.1 accessory storage | a flag rule; the figures meet it under all four readings of where an area is measured (outer faces: 1,414 sf of 10% x 16,540 sf = 1,654 sf) | confirm, and check Table 503's limit too | Partly, as above |

Notes on the figures, so no one mistakes the mockup for a different result: five of the eight are drafted as
**flags** (IBC 1016.1, 1014.3, 1018.4, 1015.2.1, 508.2.1: a person decides, so they need review even when measured);
the three NFPA rows are rules, needing review here only for what wasn't measured. The remoteness figure is Gordium's
**farthest-apart pair**, 187.164 ft (decision 7), not the sheet's pair (Gordium measures that one 183.706 ft); the
ratio 0.8788 meets the one-third the rule needs, but the rule is a **flag**, so its verdict is needs review, never
"complies". The 71.0 ft is 212.985 / 3; today the worker gives the ratio, not that length (section 4, PR 5). The eval
doesn't say *why* each of the 5 rooms has no route; the mockup shows only what `eval_marks.yaml` records of each room
(CLOSET (40): "a 2.5 by 3 ft closet whose one door (D06) opens into KITCHEN 10"; SPRINKLERED ABANDONED SPACE (32): the
sheet's "DOOR PERMANENTLY FIXED SHUT"), never a reason it doesn't give.

### The five biggest problems

1. **Needs review is a dead end** (F16, F17): the panel says why, not what to do, and offers no way to do it; the
   elements a fix needs (the 5 rooms) aren't clickable.
2. **Marking is a modal text dump** (F6 to F11): about 8 actions per element, no progress, cut at 25 rows.
3. **The ribbon mixes test tools with the product** (F1 to F5): 7 unlabelled-by-icon buttons, 2 of them for architects.
4. **Revit freezes during a check, and every edit greys everything** (F12, F21): the fix-and-recheck loop, the
   one an architect lives in, is the slowest part.
5. **It doesn't look or behave like Revit** (F18, F22, F23): no dark theme, hue-only status colours, accidental
   zooms, no keyboard.

## 2. The proposed design

### 2.1 What stays (the rules the design keeps)

- **Never a false pass.** Green only for the worker's "complies"; a stale result is never green; a flag rule
  whose figures meet the limit is still needs review (the mockup's remoteness and storage rows). Nothing the panel
  does turns a needs review into a pass: a guided fix ends with **Check again**, and only the worker's answer
  changes a verdict.
- **The architect marks; Gordium never guesses.** A suggestion is shown as a suggestion and is written only by the
  architect's own click on a value they chose. Blank stays "not stated".
- **The worker's words and figures.** The panel shows the worker's numbers. Where the design needs a figure the
  worker doesn't send yet (a limit in feet, an egress row's how far off, the rooms without a route as elements), it
  becomes a worker change (section 4, PR 5), never arithmetic in the add-in.
- **The law's exact words**, with where they are, and now a link that opens them.

### 2.2 Ribbon

```
Gordium tab
 ┌ Check ───────────────────────┐ ┌ Results ───┐ ┌ Help ─────┐
 │ [Check     ] [Mark    ]      │ │ [Panel   ] │ │ About     │
 │ [project ✓ ] [facts ☐ ]      │ │            │ │ Settings  │
 └──────────────────────────────┘ └────────────┘ └───────────┘
 (Trial panel: only in a trial build, or with GORDIUM_TRIAL=1)
```

- Two large buttons, in work order reversed by importance: **Check project** (the thing they came for) and
  **Mark facts** (opens the panel on its checklist tab). **Panel** shows or hides the dockable pane (a toggle Revit
  remembers). Help: About, Settings.
- 32 px and 16 px icons, light and dark variants (Revit 2024 on switches ribbon icons by theme), drawn on the same
  grid: a check-mark in a plan outline; a tag with a tick.
- Tooltip: one line ("Check this project against its zoning and egress rules"); `LongDescription`: three short
  lines (what is read, where results appear, that nothing is sent when a fact is missing).
- The five test tools move to a **Trial** panel created only in a trial build or when `GORDIUM_TRIAL=1`, so the
  trial loses nothing.

### 2.3 The panel: information architecture

One dockable pane, **Gordium**, tabbed with Properties (as today, same pane id so Revit keeps where it is docked).
Three levels, never more than one fold deep:

```
Gordium (pane)
├─ Header: project · story checked · checked at 14:32 · [Check again]
├─ Tabs:  Results  |  Facts to mark (progress)
│
├─ Results
│   ├─ Summary: the state in words + a count bar (does not comply / needs review / complies / not checked)
│   ├─ "Fix these first": needs review grouped by cause, each a card with what to do and how many rules it clears
│   ├─ Filter chips + search
│   └─ The list, worst first: Does not comply › Needs review (by cause) › Check by hand › Complies (folded)
│        └─ a row → Detail (slides in, Back returns to the same scroll position)
│              ├─ verdict, rule, part
│              ├─ Why it needs review + What to do (separate boxes)
│              ├─ Measured vs limit (+ how far off, the worker's)
│              ├─ The law's words (quote, section, page, "Open the law")
│              ├─ Elements (each with Show; Show all)
│              └─ [Guided fix] when the cause has one
│
└─ Facts to mark (the checklist)
    ├─ Progress: sections done / to do / to confirm
    └─ Sections: Project facts · Spaces with no Room · Room use · Can be locked · Pass through · Exits · Clear widths
         └─ each: count, what an unset one leaves unchecked, the elements (Select all unset → Properties)
```

**Sort: worst first, then what the architect can act on first.** Does not comply (by how far off, largest first),
then needs review the architect can act on (the worker's tier 2, `docs/decisions/2026-11-16_results_grouping.md`),
grouped by **cause**: one card per cause, so "5 rooms have no route to an exit" is one job that clears 4 rows, not 4
rows. Then "check by hand: not read by Gordium yet" (tier 3), then complies and not applicable, folded. The worker
already makes the tiers; the cause grouping needs it to say which rows share a cause (PR 5).

### 2.4 The main screens

**Project summary (top of Results).** One sentence first, in the worker's state: "Needs review: nothing fails; 8
route rules need review". A count bar under it, segments in status colours with their numbers written on them
(never colour alone). Then "Fix these first" with up to three cause cards, each: the cause in plain words, how many
rules it affects, the first action as a button. For the Odyssey:

1. *5 rooms have no route to an exit*: 4 rules. [Resolve]
2. *The corridor's shape isn't measured yet*: 2 rules, check by hand. [How to check]
3. *Figures meet the limit; a person decides*: 2 flag rules. [Review]

**The results list.** Each row is two lines at the docked width (about 340 px):

```
[? ] Exit access travel distance                     IBC 1016.1
     5 rooms not measured · longest found 110.2 ft of 200 ft
```

A status glyph (shape, not just colour), the rule's plain name, the section right-aligned, and one line of
figures or the short cause. Single click **selects the row** (highlight, and the row's elements are selected in
Revit with no zoom); double click or Enter opens its detail; the **Show** button (or Space) zooms. Up/Down move,
Ctrl+C copies the row as the text file says it. Search matches rule names, sections and element names; filter
chips match the count bar.

**A result's detail.** Back arrow and the row's position ("3 of 8"), then:

- *Verdict and rule*: "Needs review · Exit access travel distance · IBC 2009 1016.1 · 1st floor".
- *Why*: the worker's reason in a sentence, the jargon kept out ("5 rooms have no route to any exit: a walk 12 in
  clear of every corner, through door centres and the rooms it may cross").
- *What to do*: numbered, each step a button where the panel can do it ("Show the 5 rooms", "Open the guided fix").
- *Measured vs limit*: the figure, the limit, and a bar; for a partial figure the bar is hatched and says so
  ("110.2 ft over the rooms with a route: not a pass while 5 rooms aren't measured"). How far off in the worker's
  words when it gives them.
- *The law's words*: each quote in full, in a quotation style, with "IBC 2009, p. 267, lines 14-17" and **Open the
  law**, which opens the source at that page (a local PDF with `#page=`, or the publisher's page).
- *Elements*: each a line with its name as the architect knows it ("CLOSET (40)", "Door D06", never "Rooms id
  341207"), a Show button, and "Show all".

**Guided fix.** Opens from a cause card or a detail. A short checklist of the elements the cause names, each with
what Gordium knows of it and the actions the architect can take; progress at the top; nothing is resolved by
Gordium:

```
Resolve: 5 rooms with no route to an exit        0 of 5 looked at
  Each needs a legal walk out. A walk may not cross kitchens, storage rooms or closets (IBC 1014.2 item 4)
  or a room that can be locked (item 2), and passes only through rooms marked Pass through.
  ☐ CLOSET (40)   opens only into KITCHEN (10), door D06           [Show] [Its door] [Properties]
  ☐ STORAGE (13)                                                   [Show] ...
  ...
  For each: ( ) I changed the design  ( ) I changed a mark  ( ) Leave it: stays needs review
  [Check again]  (only the check changes a verdict)
```

A guided fix whose answer is a mark ("Mark exits": a door in an outside wall with no `Gordium: Exit`) shows the
choices as buttons with Gordium's exact words (Exterior door at discharge, Exit stair enclosure, ..., Not an exit);
v1 selects the door and opens Properties at the mark; v2 writes the chosen word (section 6, decision 1).

**The marking checklist (Facts to mark).** Replaces the TaskDialog. A progress line ("5 of 7 done, 2 to confirm"),
then one section per kind of fact, each a row with its count and state, expanding to its elements:

- *Done* (tick): every element has a value Gordium reads.
- *To do* (empty box, amber): some unset; the count and what that leaves unchecked ("a room with no Use is never
  crossed by a route"). **Select the N unset** selects them all in Revit: Properties then edits them in one go, the
  bulk edit architects already use.
- *To confirm* (half box, blue): set, but on an assumption the list names (the Odyssey: every mark is an eval
  assumption, Gordium standing in for the architect; pass through on 15 rooms is the lenient reading).
- Problems that stop a whole kind being read (an enclosed area with no Room, a conflict) are the first section,
  each element selectable.

### 2.5 Visual language (WPF-feasible)

**Type** (Segoe UI, Revit's own; sizes in WPF device-independent pixels):

| Token | Size / weight | Use |
|---|---|---|
| `type.state` | 15 / SemiBold | the summary sentence |
| `type.title` | 13 / SemiBold | detail title, cause card title |
| `type.body` | 12 / Regular | rows, reasons (Revit's panels use 12) |
| `type.caption` | 11 / Regular | sections, figures' units, timestamps |
| `type.overline` | 10 / SemiBold, +4% tracking | group headings ("NEEDS REVIEW · 8") |
| `type.quote` | 12 / Regular, Georgia or Cambria | the law's words, so they read as the law's and not Gordium's |
| `type.figure` | 12 / SemiBold, tabular numerals | measured and limit figures, aligned |

**Colour tokens**, one `ResourceDictionary` per theme, swapped when Revit's theme changes:

| Token | Light | Dark |
|---|---|---|
| `bg.pane` | #F4F5F7 | #2B3038 |
| `bg.surface` | #FFFFFF | #343A44 |
| `bg.hover` | #EEF1F5 | #3D4450 |
| `bg.selected` | #DCE9FA | #2F4A6E |
| `line` | #D7DBE1 | #4A5260 |
| `text` | #1D2229 | #E7EAEE |
| `text.muted` | #5B6470 | #A9B1BC |
| `accent` | #0B66D0 | #5AA2F5 |
| `status.fail` | #C2410C (vermilion) | #FF8A5B |
| `status.review` | #9A6700 (amber), fill #FFF4D6 | #F2C14E, fill #4A3F1E |
| `status.pass` | #0F7B6C (blue-green) | #4CC6B3 |
| `status.na` | #6B7280 | #9AA3AE |
| `status.stale` | hatched `text.muted` | hatched `text.muted` |

The status hues follow the Okabe-Ito colour-blind-safe set (vermilion, amber, blue-green), and **every status has its
own shape and word**: fail an octagon with ✕, needs review a triangle with ?, complies a circle with ✓, not
applicable a dash, stale a clock. Colour is never the only signal. Text tokens are chosen for 4.5:1 contrast on
their surfaces (PR 1 tests it).

**Spacing and shape.** A 4 px grid: rows 8 px padding, sections 16 px apart, the pane's gutters 12 px; corner radius
4 (Revit's own controls are near-square); 1 px lines; no shadows except the detail sliding in. Controls restyled
(Button, ToggleButton, ListBox, Expander, ScrollBar) in the dictionary, so no default WPF chrome shows.

**Icons.** One 16 px set, 1.5 px strokes, drawn as WPF `Geometry` resources so they recolour with the theme: the
five status glyphs, show (crosshair), select (cursor), open law (book), properties, back, recheck, filter, search.

### 2.6 States

| State | What the pane shows |
|---|---|
| Not checked yet | The Gordium mark, one sentence ("Check this project against its zoning and egress rules"), **Check project** and **Mark facts first**, and the checklist's progress if marks exist. |
| Checking | The last results stay, dimmed, with a progress line by stage: "Reading the model (rooms 39)... Checking (Gordium's checker)... "; Check again becomes Cancel. Revit is not frozen during the checker's part (PR 8). |
| Nothing checked: facts missing | "Nothing was checked: 2 facts are missing", each fact as a row with its own **Set** button (opens Project Information, the field named) and why it's needed; Check again. |
| Error | One plain sentence ("Gordium's checker stopped before answering"), **Try again**, and **Copy details for support** (the exception and the log path go to the clipboard, not the screen). No TaskDialog as well. |
| Stale | A banner: "The model changed after this check (14:32). The results may not hold." with **Check again**; rows keep their words, lose their colour (as today: never a stale green), and rows whose elements the edit touched get a dot ("changed since"). |
| Empty law | A law with nothing checked says so ("Zoning: not checked: no lot in this model"), never an empty space. |
| Project closed / another project active | "These results are for Children's Odyssey. Switch to it to show elements." Show buttons disabled with that as their tooltip. |

### 2.7 Keyboard and selection

- Up/Down: move through rows; Enter: open the detail; Backspace or Alt+Left: back; Space: show (zoom); Ctrl+C:
  copy the row; Ctrl+F: search; Esc: clear the search, then leave the panel (focus back to the view).
- A single click selects the row and its elements in Revit **without moving the view**; zoom is an explicit
  Show. This removes the accidental zoom (F18) and lets Properties follow the panel.
- Two-way: when the architect selects elements in the model (Revit's `SelectionChanged`), rows about them get a
  marker and the filter "Selected elements" appears.
- Show remembers the view before it zoomed, and **Back to my view** returns to it (one level).

## 3. What Revit 2025 to 2027 and WPF allow

| Need | How | Since | Note |
|---|---|---|---|
| A docked panel | `IDockablePaneProvider`, WPF `FrameworkElement` | 2014 | as today |
| Follow Revit's light/dark theme | `UIThemeManager.CurrentTheme`, `UIApplication.ThemeChanged` | 2024 | swap the token dictionary; the canvas has its own (`CurrentCanvasTheme`) |
| Know what the architect selected | `UIApplication.SelectionChanged` | 2023 | for the two-way selection |
| Select and zoom | `Selection.SetElementIds`, `UIDocument.ShowElements` | old | through the one ExternalEvent, as today |
| Open Project Information, Properties | `PostCommand(ProjectInformation)`; `GetDockablePane(PropertiesPalette).Show()` | old | Properties can't be scrolled to a field by the API: the panel names the field |
| Write a mark from the panel | a Transaction in the ExternalEvent | old | makes the results stale, rightly (an edit is an edit); undoable with Ctrl+Z |
| Draw routes, the diagonal, markers on the canvas | `DirectContext3D` (lines), `TemporaryGraphicsManager` (clickable in-canvas icons) | 2018 / 2022 | no transaction, nothing saved, no stale; to confirm on 2027 in the trial |
| Not freeze Revit during the check | read on Revit's thread (API rule), send and wait off it, raise an ExternalEvent or use the WPF Dispatcher with the answer | old | element labels are read before sending, as today |
| Open the law at its page | `Process.Start` with `UseShellExecute` on a PDF `#page=` or a URL | .NET | needs the worker to send the source file and page with each quote |
| Icons that follow the theme | `PushButtonData.LargeImage` and Revit 2024's theme-aware ribbon images | 2024 | light and dark PNGs |
| Smooth long lists | `ListBox` with `VirtualizingStackPanel`, `DataTemplate`s | WPF | 500 rows stay instant; today's nested Expanders build everything opened |
| .NET 8 (2025-2026) and .NET 10 (2027) | plain WPF, no third-party UI kit | | nothing here needs one |

Not feasible or not worth it: a web view inside the pane (WebView2 can conflict with Revit's own copy and adds a
browser to the add-in); scrolling Properties to a field; colouring elements in the view through overrides (a model
change that would make every result stale).

## 4. Build plan in small PRs

Each PR is reviewable and evaluable on its own; the first four change only the add-in's look and behaviour, never
a verdict. Every PR keeps the existing `ResultRowsTests` and `ResultTextTests` green (the words of every row stay the
text file's).

| PR | What | How we know it is right |
|---|---|---|
| 1 | **Tokens and theme**: the two token dictionaries, restyled controls, status glyphs, theme following | a unit test computes every text token's contrast on its surfaces (at least 4.5:1); screenshots of the Odyssey results in both themes on Revit 2025 and 2027; the screenshots run through a deuteranopia and protanopia simulation and every status is still told apart |
| 2 | **Ribbon**: two large buttons with icons, short tooltips and long descriptions, Panel toggle; test tools behind a trial switch | screenshot in both themes; the trial runbook's steps still work with `GORDIUM_TRIAL=1`; a release build shows no test tool |
| 3 | **Results list**: virtualized list, worst-first sort, filter chips, search, single click selects (no zoom), Show, keyboard | the sort and filter in `Gordium.Revit.Reading` (Revit-free) with tests: every row in exactly one place, a failure never below a needs review, a stale list has no green; 1,000 fake rows scroll and filter in under 100 ms; a keyboard-only walkthrough in the trial |
| 4 | **Detail view**: why / what to do, measured vs limit, the law's words with Open the law, elements with names architects use | snapshot tests of the detail model for every row of the box house and the Odyssey answer; a test that every figure shown is one the worker sent (no figure made in the add-in) |
| 5 | **Worker: what the panel needs** (Python, `design_checker`): each needs-review row's cause as data (a kind: mark, fix the model, measure by hand, a person decides; and the element ids it names, such as the rooms with no route), the limit as a length where the rule's is a ratio, how far off for egress rows, each quote's source file and page | pytest: on the Odyssey description the 8 route rows come out as 3 causes (5 rooms, the corridor shape, 2 flag rules), the room ids are the 5 rooms of `eval_comparison.yaml`; a how far off is never larger than the margin under any reading (as zoning's delta) |
| 6 | **Cause cards and guided fixes v1**: selecting the elements, opening Properties at the named mark, the "looked at" checklist, Check again with what changed ("2 rows changed: travel distance now complies") | an architect task test on the Odyssey model (unmarked copy): time from first check to every needs-review row having a decided next step (fixed and rechecked, checked by hand, or decided), today's panel against this one; target half the time and no row left unvisited |
| 7 | **Facts to mark**: the checklist in the pane, replacing the TaskDialog; Select the N unset; suggestions shown | a task test: mark the unmarked Odyssey model from scratch (39 rooms, 4 exits, 3 door types), clicks and minutes against today's dialog plus a schedule; a test that the checklist's done/to-do counts equal `MarkingListResult`'s for every interior house |
| 8 | **A check that doesn't freeze Revit**: send and wait off Revit's thread, progress by stage, Cancel | trial: the time Revit's UI thread is blocked during a check of the Odyssey model, before and after (target: only the read); cancel leaves the previous results stale, never shown as the new ones |
| 9 | **Writing a mark from the panel** (if Ben agrees, decision 1): a value written only on the architect's click on a chosen word, one undoable transaction | tests that no write happens without a click choosing the value, that a suggestion is never written by itself, that the results go stale after a write, and that Ctrl+Z restores the old value |
| 10 | **On the canvas**: the route walked, the rooms with no route, the diagonal and the exit pair drawn as temporary graphics while a detail is open | screenshots; a test that showing them makes no transaction (the results don't go stale) |

The eval that matters most, for PRs 6 and 7 together: **one architect, the Children's Odyssey model unmarked, from
"open the model" to "every needs-review item has a decided next step"**, timed, with the panel today and with the new
one, and every place they hesitated written down. The Odyssey is a good test: its 8 route rows need review for 3
different reasons, and one of them (the 5 rooms) can only be resolved in the model.

## 5. The five biggest changes proposed

1. **Needs review becomes a job**: grouped by cause, each with what to do and a guided fix that selects the
   elements, opens Properties at the right mark, and ends with Check again.
2. **Marking becomes a checklist in the panel**, with progress and "select the N unset" for one bulk edit, in
   place of the modal text dialog.
3. **A two-button ribbon** (Check project, Mark facts) with icons; the test tools hidden outside the trial.
4. **A result's detail** with the law's exact words and a link that opens them at the page, the measured figure
   against the limit, how far off, and the elements by their names; single click selects, Show zooms.
5. **A Revit-native look**: theme tokens that follow Revit's light and dark themes, colour-blind safe status
   colours each with its own shape and word, keyboard throughout, and a check that doesn't freeze Revit.

## 6. Decisions for Ben

**Decided (Ben, 2026-11-21):** the approach is agreed ("lgtm as long as it's optimal and best practice for
architects"), with each recommendation below: v1 first and v2 after PR 7's task test (1); the "I've checked this"
note as a note only, once the approval layer has a place for it (2); no automatic check (3); the worker additions (4).
The build follows section 4, one PR at a time, each judged by its own eval; a choice an architect's task test shows
is worse than the alternative is changed, not kept.

1. **Write marks from the panel?** v1 only selects and opens Properties (no change to how marks are written). v2
   writes the word the architect clicks, in one undoable transaction. Recommendation: v2 after the task test of PR 7.
2. **"I've checked this" on a flag rule** (remoteness, storage): record who decided and when, shown beside the row,
   the verdict staying needs review (never complies). Recommendation: yes, as a note only; it needs a place in the
   format, so it waits for the approval layer's design.
3. **Check again automatically** after the model has been idle for a few seconds? Recommendation: no for now (a
   check reads the whole model); show "changed since" dots instead.
4. **The worker additions of PR 5** (causes as data, limits as lengths, egress how far off, quote sources).
   Recommendation: yes; they keep every figure the worker's.

## Sources

- The add-in's code on `main` (a84da8a9), files named in section 1.
- `docs/revit/revit_reading_design.md` section 9 (the results panel as built) and
  `docs/revit/revit_interior_reading_design.md` sections 3, 5a and 10 (the marks).
- `docs/decisions/2026-11-16_results_grouping.md` (the worker's tiers).
- The eval: `test_data/answer_keys/portland_me_19_libby_st/` (`hand_check.yaml`, `eval_marks.yaml`; and
  `eval_comparison.yaml` on `feat/route-measures-2`, made by `packages/model_measurement/tests/make_eval_comparison.py`).
- Revit API: `UIThemeManager` and `ThemeChanged` (Revit 2024 API), `SelectionChanged` (Revit 2023 API),
  `TemporaryGraphicsManager` (Revit 2022 API), `DirectContext3D` (Revit 2018 API); each to confirm on Revit 2027 in
  the Windows trial (`docs/revit/windows_trial_runbook.md`).
- Okabe, M. and Ito, K., "Color Universal Design" (2008), for the colour-blind-safe hues.
