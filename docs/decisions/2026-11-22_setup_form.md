# The Setup form: the architect states the facts in one place (2026-11-22)

**Purpose:** what the Revit add-in shows when a fact the check needs is missing, what it writes and when, and why.\
**For:** Ben; engineers changing the add-in's Setup form (`apps/revit_addin`, `Setup.cs`, `SetupView.cs`, `SetupFlow.cs`); architects trying the add-in.\
**Kept current by:** the PR that changes which facts the form asks, what it suggests, or when it writes.

## Decision

**Ben approved, 2026-11-22:** the design pass's piece 7 (the facts to mark, as a checklist in the pane) and piece 9
(writing a mark from the panel) are merged into one piece, **Setup** (docs/revit/ui_design_pass.md, section 4).

1. **Check project** first looks at the facts. When one the check needs is missing, the Gordium pane opens the
   **Setup form** instead of the old "Nothing was checked: fill these in first" list, and the **Mark facts** button
   opens the same form instead of its text dialog. When nothing is missing, the check runs as before.
2. **Project facts are a real form**: a dropdown where the answer is one of a known list (Zone: the districts the
   place has rulebooks for; Use: every City use by the chart's own name, the district's permitted ones first, a
   special-permit one saying so, then the others "not on the district's list of uses", so the true use can always be
   stated (its use row then doesn't comply, as the rulebook's list decides; never a pass); the zone and use count as set
   only word for word, as the checker reads them, the ground's words in any case, as the check reads them; Ground from: its two words), Yes/No toggles, a number box for the stories, and
   **Pick on plan** for the street edge (Revit's pick on Revit's thread, each edge said back and confirmed; the edge
   picked is kept in the form as "not saved yet" and written by Save with the other facts, in the same transaction). Each field shows the law
   it answers: the mark's own tooltip. The form lists **every mark Marks.cs binds to Project Information** (data, not a
   hand list), each under a heading found from what it feeds (`facts.*`: the lot and the building; `building.*`: which
   building code; `has_none`: what the building has none of), so marks added to Marks.cs appear with no change to the
   form. A text mark Gordium has no word list for yet is a text box (one line in `SetupFacts.Listed` makes it a dropdown).
3. **Facts inside the building are a checklist**, one line per fact with its counts ("Escape opening: 0 of 119 windows
   and doors set"), why Gordium can't read it from the model, what a blank leaves, **Select them** (selects the unset
   elements, or every element of the unset types, so they are set together in Properties), and the line folded away
   once done. Needed lines come first.
4. **Suggestions** are shown with what each is based on, and written only when the architect clicks **Accept** (one, or
   all of a line's). Gordium suggests:
   - *Sleeping room*: Yes from the room's name (Bedroom, BR 2, Bed, Bdrm, Sleeping, Bunk room); never from its area,
     and never a No (a suggested No could hide a bedroom).
   - *Escape opening*: in each sleeping room (marked, or only suggested: the basis says so), the largest operable
     window by its frame as Yes ("the law measures its clear opening, which the check reads once set"; "if another
     window is the intended one, pick it instead"), its other windows No (one per sleeping room is what R310.1 asks),
     a fixed window No; a window or door opening only to rooms marked not sleeping No. Nothing for a window in a room
     not marked either way, or a door to a sleeping room.
   - *Exit door*: a door with a Room on one side only, on the entry level (taken as the lowest level with a door to
     the outside; the basis says so, and that a garage with no Room looks like outside), Yes; a door between two rooms
     No. Each dwelling unit needs one (R311.1): the basis says to keep Yes on its main one.
   - *Operation*, once per type: from the family and type name (Casement, Double Hung, Awning, Slider, Fixed, Picture,
     Single-Flush, Pocket, Bifold...).
   - *Room use* (a building that isn't a house): from the room's name, the marking list's own table.
5. **Gordium writes only on the architect's click**, and each click is **one undoable transaction named for Gordium**:
   Save writes the project facts chosen, the street edge picked among them ("Gordium: project facts"), Accept writes the suggestions accepted ("Gordium:
   suggestions accepted"). A field never touched is never written (a blank stays blank); a value that isn't one of the
   field's choices, or a count under its least, is refused with why and not written. Neither name is the check's own,
   so results shown go stale after either (as after any edit); one Ctrl+Z takes a whole Save or accept back.
6. **When everything needed is set, the check runs by itself** (after a Save, an accept, a value set in Properties or
   an undo), but only when the form was waiting for something: an edit to a form that had nothing to wait for (Mark
   facts on a project already set) runs nothing. Next time the facts are in the model, so Check goes straight to
   results.
7. **Check now anyway** is always there. It sends the facts that are set; each required one missing is left out, and
   the checker makes the rules it decides need review (the use rule, the yards measured from the street, the lot width);
   a lot surveyed not stated is read as traced from the tax map, never as surveyed. The results start with "Checked
   without N facts" and **Set up the facts**. The zone is the one exception: it chooses the rules, so without it nothing
   can be checked, and the form says so. Within a session, Check project doesn't show the form again for exactly the
   facts left out by Check now anyway, but sends the check as Check now anyway does (no street pick, the
   results headed "Checked without N facts"); a fact newly missing shows it again.
8. **Wording follows the building**: "house" only for a one- or two-family dwelling; any other use, or none stated,
   is "building" ("This building has no stairs"; "Inside the building").

**What is needed** (the form shows, and the check waits): the four facts the check sends nothing without (zone, use,
lot surveyed, street edge: host_core.facts.REQUIRED), any project fact holding what Gordium can't read (the check would
refuse it), and the three inside facts whose blank leaves a whole kind unread (sleeping room on every room, escape
opening on every window and door, exit door on every door). The operations, the clear openings, the "these are all the
stairs" ticks, the has-none ticks and the escape-route marks are shown, but never hold the check back: a blank one makes
its rules need review, never a pass.

## Why

- **The architect states facts in one place.** Before, a missing zone was a bullet list and Revit's whole Project
  Information dialog; interior marks were a modal text dialog cut at 25 rows (design pass F6 to F11, F14). Now every
  fact the check needs is in the pane, with its choices and the law it answers.
- **Gordium writes only on the architect's Save, in one transaction.** A value written by a button, not typed, is
  still the architect's: they chose it. One transaction per click is one Ctrl+Z, Revit's own way back.
- **Never a guessed value** (principles 2 and 4). A suggestion is data until accepted, says what it is based on, and
  is never in a Save. A blank stays blank, so "not stated" stays "needs review".
- **Never a false pass.** Check now anyway leaves out what isn't set; the checker's own rules say what that makes
  need review (checked: on the box house, leaving out the use, the street line or the lot surveyed gives no new
  complies, only more needs review; pinned by `ProjectCheckTests.Check_now_anyway_sends_what_is_stated_and_every_missing_fact_is_needs_review`).

## Not done, and why

- **Zone from the address** (packages/site_lookup's City of Ithaca adapter reads the City's zoning map): not wired. It
  needs the network from the worker during setup, and a lookup's district is only a suggestion the architect accepts or not, never
  the mark itself; the wiring is a worker command that runs the adapter and returns the district with its source and
  date, shown as a suggestion beside the Zone dropdown.
- **Confirming a maker's clear opening with one click**: not offered. Gordium already fills a maker's published clear
  opening as a draft where it holds that maker's data for the exact product (`MakerClearOpenings`, Marvin's); confirming
  it means checking the hardware option and stating the clear offset, which the formula doesn't give, so the checklist
  lists what Gordium holds for each type and the architect states it in the type's marks.
- **The marks the building-code branch adds** (occupancy groups, sprinkler system...): they appear in the form under
  "Which building code" and "The lot and the building" as soon as they are in Marks.cs; their word lists become
  dropdowns with one line each in `SetupFacts.Listed` (until then, text boxes the worker checks).

## How we know

`apps/revit_addin/tests/Gordium.Revit.Reading.Tests/SetupTests.cs` (each pinned: reverted, the test fails): every
Project Information mark is a field once; the fields' kinds and choices; a Save writes only what was chosen and a blank
stays blank; one line per fact with counts; sleeping rooms suggested from names only and never No; the largest
operable window suggested saying so; the exit door on the entry level; operations per type; a suggestion never written
by itself; when the form shows and when the check runs; Check now anyway remembered for the same facts only; a write
makes results stale; one Save is one undo step; the words by building type. `ProjectCheckTests`: Check now anyway
against the real checker, and never without the zone. `RealWorkerTests.Options_give_the_districts_with_a_rulebook_and_the_use_names`.
