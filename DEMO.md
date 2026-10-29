# Gordium preview (the `demo` version)

`demo` is a **preview that combines the latest reviewed work** so you can try it in Rhino before it is final.
It is not final: things may change, and it is never the official version (that is `main`). Please tell Ben
what you find.

These steps are for Windows, typed in **PowerShell** (click **Start**, type `PowerShell`, press Enter). Where it
says `cd $HOME\Documents\gordium`, use the folder where you cloned Gordium if it is somewhere else.

## Switch to the preview (once)

1. Quit Rhino completely.
2. In PowerShell, paste these lines:

   ```
   cd $HOME\Documents\gordium
   git fetch
   git checkout demo
   git pull
   .\.venv\Scripts\pip install -e ".[dev]"
   ```

   The last line is **needed this once**: the preview adds a new part of Gordium (the address lookup), and this
   line tells Gordium's Python where to find it. It ends with `Successfully installed …`. Nothing new is
   downloaded from the internet besides Gordium itself; no new outside packages were added.
3. To check you are on the preview, run `git branch --show-current`: it should say `demo`.
4. Open Rhino again. You do **not** need to run `install.py` again: the preview has the same five commands
   (`GordiumStart`, `GordiumCheck`, `GordiumLive`, `GordiumFacts`, `GordiumOff`), and they already point to
   your gordium folder.

## Update later

When Ben says the preview has been updated:

```
cd $HOME\Documents\gordium
git pull
```

No install step this time (2026-10-28): no new Python packages and no new parts of Gordium since the last update,
and the commands are the same, so neither `pip install` nor `install.py` is needed.

Then **quit Rhino completely and open it again** (Rhino keeps the old Gordium loaded until it restarts).

## What's new (2026-10-28, late evening)

Everything in the evening's preview below (now all on `main`), plus:

- **GordiumStart opens its box faster.** After the first time, its districts, uses and questions are ready in about
  2 ms instead of about 2 s. The questions are the same.
- **The start box's amber line takes no room while it asks nothing.** When a question comes back, the box grows to
  show it, so Cancel and Draw are never cut off.
- **A span of readings is said whole in the row's detail** (for example "35'-0 5/8" to 35'-8 3/4""), rather than
  only one end of it.
- **The use-details group is now "Use details (for later)"**, so its heading fits the panel, and each of its rows
  says when to answer it. These rows stay "needs review" until you answer; they never pass.
- **QUICKSTART's walkthrough numbers match today's starting house** at 106 Ithaca Rd (51'-4" × 29'-8"), which
  changed when Gordium began trying each reading of the tax-map lot lines.

## What was new on 2026-10-28, evening

Everything in the morning's preview below, plus:

- **Faster.** Gordium is ready sooner after Rhino opens, and each check comes back quicker: the rules are read once
  and kept, and a formula is worked out once instead of at every check. The answers are the same.
- **No file open? It says so.** With every Rhino file closed, `GordiumStart`, `GordiumCheck` and every panel button
  say "Open a Rhino model first." instead of failing. Nothing is touched.
- **Red is never hidden.** A part that does not comply is drawn over any amber part, so in Top view an amber eaves
  strip no longer covers the failing wall under it.
- **After an edit, the row that newly fails is brought into view** and selected, with its group opened.
- **The detail reads plainly first.** The result ("Required: 24'-1 7/8" to 32'-10 1/8"") and the law's words come
  first. The formula, what was measured and the chart's own cell are under **How it's worked out**, closed until
  you open it. Nothing is dropped, and the citation and its links stay in view.
- **Shorter Delta words.** A maximum you pass reads "over", and "≥ +" means at least that much to spare.
- **"I checked this" means confirmed by you.** On the street's row it confirms the street and its corner answer.
  A box default you left as it was is never saved as confirmed by you.
- **The use row names the use** ("Use: One-family dwelling, detached"). Before, its name was cut off ("One- /
  family d…").
- **A row waiting on several facts says "Answer 4 questions…"** on its button and in its window's title. Before,
  the whole list of facts was cut off. The window's dropdowns line up.
- **Smaller fixes in the start box:**
  - a found lookup's note ("Shown dashed: …") is a plain line under the amber question, not part of it;
  - the hidden address suggestions no longer leave a gap under Address;
  - the **About this project** and **Quick answers** labels sit at the top of their rows.

## What was new on 2026-10-28, morning

Everything in the 2026-10-27 preview below, plus:

- **Start from an empty file.** `GordiumStart` opens an empty start box. Type the address (after 4 letters a list
  offers City of Ithaca addresses) and press **Look up**, or **Enter the site by hand…**. The lot it finds is only
  shown, dashed: nothing is drawn in your model until **Draw**.
- **The district is yours to confirm.** Tick **This is the lot's district** before Draw. Picking another district
  unticks it, so a tick always belongs to the district shown.
- **About this project.** The start box asks the facts that shape the building's outline: a stream or inlet near
  the lot, and the South Hill Overlay. Each starts on **Not answered**; Gordium never assumes. **Quick answers**
  fills both in one click.
- **Use details are answered later.** Who lives there and a home business sit in the panel's collapsed **Use
  details** group. Each row's **Enter…** button opens a small window that asks only what that row needs.
- **Every panel change is one Undo step**, and Undo takes back only that change, never your own earlier edit.
- **A window says what Gordium is doing**, with the seconds so far. A check, the starting house and the zoning
  report have **Cancel**; a lookup has **Cancel lookup**. Cancel changes nothing, and a check you cancel stays
  cancelled until your next edit.
- **New rules in all nine districts:** the 20 ft setback from a stream or inlet (§325-26), the South Hill Overlay
  (§325-8E, R-1 and R-2), homes per attached building (R-3a, R-3aa, R-3b, RU) and more than one main building on a
  lot. Each says **needs review** until Gordium has what it needs (from your model or your answers).
- **Corner lot? is yours to answer.** After Look up the box shows what the lookup found ("No: one street" or
  "Yes: two streets"). Change it and Draw keeps your answer (it used to save the lookup's).

## What was new on 2026-10-27

Everything in the 2026-10-26 preview below, plus:

- **All nine residential districts.** Besides R-1a, R-1b and R-3a you can now pick **R-2a, R-2b, R-2c, R-3aa,
  R-3b and RU**. Their rules were written out by hand from the chart and the code (like R-1a and R-3a), so they are
  still drafts: tell Ben anything that looks wrong.
- **Occupancy and home occupations.** Every district now also lists how many unrelated people may live in a
  dwelling unit and the home occupation rules. Gordium can't see these in a massing model, so they show as
  **? needs review** until you tell it (never as complies). You can answer them in the start box, right under
  **Use** (each question with its answer beside it; the box fits a laptop screen). A floor area takes decimals
  (500.4); anything that isn't a plain number is not kept, and the box says so at once.
- **The Use list fits the district.** After you pick a district, **Use** lists that district's uses, the permitted
  ones first, with a note when a use needs a special permit or isn't allowed there. Where the district's rules need
  more about the use (for example how many dwelling units), the start box asks right under Use. Leave one blank and
  the rules that need it say **needs review**; a row that waits for one has a **Tell Gordium in Edit site…** button.
- **Address suggestions.** Type at least 4 characters of an address in the start box and pause: a list of City of
  Ithaca addresses that start that way appears under it. Use **Down**/**Up** and **Enter**, or click one. No town
  typed? Gordium looks it up in the City ("106 Ithaca Rd" becomes "106 Ithaca Rd, Ithaca, NY").
- **You can stop a slow check.** A check that takes a while shows a small window, "Esc or Cancel to stop", and the
  panel says "Checking…" with what it is doing. Press **Esc** or **Cancel**: nothing in the model changes and
  nothing is shown as checked until you press **Check again**. With **Check after every edit** on, the re-check runs
  in the background, so Rhino never freezes while you keep drawing.
- **The part that breaks a rule is coloured.** Red where it does not comply, amber where it needs review, on the
  part of the building concerned (not the whole house).
- **Dimensions look like a drawing.** Each yard is dimensioned square from the lot line to the wall, where the yard
  is shortest when it fails, with a faint line at the required distance. Lines and colours are hidden behind the
  building when you look at it in 3D, as they would be in a drawing.
- **Lines to snap to.** The buildable outline and each yard's required line are drawn as real (locked) curves on
  the Gordium::Envelope layer, so you can snap to them with Osnap while you draw. On a tax-map lot the outline is the
  cautious one (2'-0" in from every lot line); the outline as drawn is dashed.
- **The starting house in floors.** The starting house is drawn floor by floor on its own sublayers
  (Gordium::Massing::Floor 1, Floor 2…), so you can hide or edit one floor. A note says what limited its size (for
  example "lot coverage 25%").
- **Every panel change is one Undo.** Each panel button or tick is one step for Rhino's Undo (Cmd+Z / Ctrl+Z), and
  the ticks follow what Undo puts back.

## What was new on 2026-10-26

Everything in the 2026-10-25 preview below, plus:

- **R-3a side-yard eaves are checked against the right side.** On an R-3a lot the two side yards can differ (one
  must be 10 ft). Gordium now checks each side's eaves against that side's own minimum, so an eave that reaches too
  far into the 10 ft side yard no longer complies. The earlier false pass (it could say such an eave complied) is
  fixed: you no longer need to check these eaves by hand. If the house sits exactly in the middle, so either side
  could be the 10 ft one, Gordium checks it both ways and says so.
- **One click on a street edge takes the whole street.** When you pick the street side with **Change…**, click any
  piece of the street edge: Gordium keeps the whole street (on the sample, Ithaca Rd's 8 short tax-map pieces,
  75'-10" of frontage) and says what it kept. It never runs round a corner. Where it can't tell whether the lot line
  bends along the same street or turns a corner, it asks: answer **Yes** or **No**. **Enter** asks the question again
  (it needs a real answer: guessing either way could pass a lot that doesn't comply); **Esc** changes nothing (the
  street side stays as it was). On a corner lot, click each street once, then press Enter when done.
- **Draw stays off until a typed address is looked up.** If you type a new address, Draw waits: "Press Look up to
  find … first." Look up, or put the lot's own address back (or clear it), and Draw is on again.
- **The Check button.** Nothing re-checks by itself any more unless you tick **Check after every edit** in the
  panel. After an edit the results grey out ("Model changed since the last check — press Check"), so you never
  read old results as current; press **Check** to bring them up to date.
- **A compact "no longer complies" notice.** When an edit breaks a rule, a small notice names it (for example
  "Rear yard no longer complies"). It sits in a part of the view that is clear of your model, never on top of
  it (if no part is clear, only the panel shows it), and it goes away as soon as it no longer applies. The panel
  says it too.

## What was new on 2026-10-25

Everything in the 2026-10-22 evening preview below, plus three fixes found by testing it in Rhino:

- **"Keep my building" says plainly that your lot is replaced.** When you Draw with a new address after working on
  the old one, the question now names your lot as it came (your surveyed lot, the lot you drew, or your lot) and the
  Keep answer names the new address, for example: **Keep my building and check it on 96 Ithaca Road's lot (your
  surveyed lot will be replaced)**. A new address is a new site: the lot is always replaced, whichever answer you
  pick; Keep keeps only your buildings and checks them on the new lot. (This is what it already did; now it says so.)
- **Undo and Redo of a new-address Draw are exact.** **Undo** brings back the old address and its drawing, with
  nothing of the new address left on screen (no leftover lot outline or dashed lookup outline). **Redo** brings the
  new address back as it was drawn. After either one Gordium checks the model again, so the panel matches what you see.
- **The neighbourhood stays locked when you unlock Gordium.** The neighbourhood's parcels, streets and notes stay
  locked when you lock and then unlock the Gordium layer, so you can't move the City's lines by accident. Your own
  layers behave as Rhino normally does.

## What was new on 2026-10-22, evening

Everything in the morning preview below, plus:

- **Look up shows before it draws.** In **Edit site…**, typing an address and pressing **Look up** fills in the
  address and the district and shows the new lot as a **dashed outline**. Nothing in your model changes yet.
- **Draw with a new address starts clean.** Gordium clears what it drew for the old address (its lot, the starting
  house as it drew it) and draws the new lot and a new starting house. One **Undo** puts it all back.
- **Your own work is never removed without asking.** If you moved the starting house, drew buildings, or drew or
  picked your own lot, Gordium asks once: **Start fresh**, **Keep my building and check it on the new lot** (when
  you have one), or **Cancel**.
- The last button says **Draw** when pressing it will draw something, and **Check** when it only checks.
- **An address that isn't found** (or a lookup that couldn't reach the map) is said in the box. Draw draws nothing
  for it.
- **Fewer repeated questions.** A lot in two zones is asked about once. The street's name from your address stays
  after Draw.

## What was new this morning (2026-10-22)

Everything in the 2026-10-21 evening preview, plus:

- **"To comply" advice you can trust.** Every "To comply" line is checked by Gordium before it is shown: doing what
  it says makes that row comply, and no other row gets worse. A yard's advice is the requirement for every part of
  the building ("keep every part of the building at least 25'-0" from the front lot line — now 22'-0" at its
  closest"); an eaves row says "eaves included".
- **"Not checked yet"** for rules Gordium doesn't cover: "Not in Gordium yet — coming in a later version. Check this
  by hand for now", with the section to check.
- **Corner lots.** Click **Change…** on the street side and pick every lot line on a street (Enter when done). Lot
  width is the frontage on ONE street (§325-8, Column 7), never measured along two. If Gordium can't tell whether
  two lines are one street or two, it asks.
- **A building partly over a lot line** never complies, and says what to do first: "First: move it back onto the
  lot."
- **Uneven ground and separate buildings.** A shed or garage on its own lower ground is read on its own ground; a
  balcony drawn just off the wall is still part of the house.
- **The neighbourhood** (parcels, streets, footprints) stays locked where it should, even if you lock the Gordium
  layer, and anything Gordium can't remove is said, never drawn twice.
- **Windows:** no black console window when Gordium starts its helpers, and only one checker runs per Rhino.

## Known limits

- **Keyboard check wanted:** at the street question press Enter (asks again) and Esc (nothing changes) and tell Ben.
- **Corner lots get no starting house** (which yard is the front is still an open question for the architects):
  after a lookup of a corner lot, draw your building yourself.
- **Checked inside Rhino on a Mac, not yet on Windows** (2026-10-28: start flow, Undo, the start box's questions,
  progress and Cancel). If something looks wrong, take a screenshot and send it to Ben.
- **Windows:** please confirm that no black console window appears and that Task Manager shows only one
  `python` checker while Rhino is open.
- **Ground is taken as flat** at the lot's level (the panel says so).
- **AI-drafted zones are not included** (left out on purpose while they are checked). Districts: the nine
  residential ones (R-1a, R-1b, R-2a, R-2b, R-2c, R-3a, R-3aa, R-3b, RU), each written by hand.
- The address lookup needs the internet and works only for addresses in the **City** of Ithaca (not the Town).
