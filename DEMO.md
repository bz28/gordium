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

No install step this time (2026-10-22): no new Python packages since the last update.

Then **quit Rhino completely and open it again** (Rhino keeps the old Gordium loaded until it restarts).

## What's new in this preview (2026-10-22)

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

- **Not yet re-checked inside Rhino after today's changes.** Ben's test Rhino will run the scripted checks before
  he tells you to update; if something looks wrong, take a screenshot and send it to Ben.
- **Windows:** please confirm that no black console window appears and that Task Manager shows only one
  `python` checker while Rhino is open.
- **Ground is taken as flat** at the lot's level (the panel says so).
- **AI-drafted zones are not included** (left out on purpose while they are checked). Districts: R-1a, R-1b, R-3a.
- The address lookup needs the internet and works only for addresses in the **City** of Ithaca (not the Town).
