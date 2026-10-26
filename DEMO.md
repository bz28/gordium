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

No install step this time (2026-10-26): no new Python packages and no new parts of Gordium since the last update,
and the five commands are the same, so `install.py` is not needed either.

Then **quit Rhino completely and open it again** (Rhino keeps the old Gordium loaded until it restarts).

## What's new (2026-10-26)

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
- **Not yet re-checked inside Rhino after today's changes.** Ben's test Rhino will run the scripted checks before
  he tells you to update; if something looks wrong, take a screenshot and send it to Ben.
- **Windows:** please confirm that no black console window appears and that Task Manager shows only one
  `python` checker while Rhino is open.
- **Ground is taken as flat** at the lot's level (the panel says so).
- **AI-drafted zones are not included** (left out on purpose while they are checked). Districts: R-1a, R-1b, R-3a.
- The address lookup needs the internet and works only for addresses in the **City** of Ithaca (not the Town).
