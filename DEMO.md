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

Then **quit Rhino completely and open it again** (Rhino keeps the old Gordium loaded until it restarts).

Only if Gordium then says a module is missing (for example `No module named ...`), also run:

```
.\.venv\Scripts\pip install -e ".[dev]"
```

## What's new in this preview

- **Moving one floor into a yard** now says **does not comply** (before, it said "needs review"). An overhanging
  floor is part of the building, so it must stay out of the yard like the rest of it.
- **A building that crosses a lot line fails**, and the message names the building and the line, for example
  "The main building crosses the side lot line".
- **More of the real world is measured:** pitched roofs, eaves (the roof edge that overhangs the wall; the law
  lets eaves reach up to 2'-0" into a yard, and Gordium never decides on its own that an overhang is eaves),
  garages and other accessory buildings (they count toward lot coverage), and corner lots (the second street side
  gets a front-type yard).
- Where the law has more than one reasonable reading, Gordium checks **every reading**: it says complies only if
  all of them pass, does not comply only if all of them fail, and needs review otherwise.
- **Address lookup in the start box:** type the address and press **Look up**. Gordium fills in the lot from the
  City tax map, the street side, whether it's a corner lot, and a suggested zoning district, each with where it
  came from (this takes up to about 45 seconds). Anything doubtful is shown in amber with the reason. You still
  tick **I confirm** for the zoning district. **Cancel** puts everything back exactly as it was.
- **One start box at a time:** opening a second one while one is open does nothing.

## Known limits

- **Windows is not fully tested yet.** Most of this was built and tried on a Mac. If something looks wrong or a
  window shows an error, take a screenshot and send it to Ben.
- **Ground details are still rough:** how the ground is drawn, and the ground levels the lookup finds (an
  estimate from a national elevation map), are simple for now, so height and story results on a sloped lot may
  say needs review. Treating the ground as flat for this first version is decided but not in this preview yet.
- **No "These are eaves" button yet:** a yard that is wide enough only when a roof overhang is left out shows
  needs review, because there is no way in Rhino yet to confirm the overhang is eaves.
- **AI-drafted zones are not included.** Only the hand-checked R-1b rules are in this preview; the other
  districts drafted by AI are still being checked and are left out on purpose.
- The address lookup needs the internet and works only for addresses in the **City** of Ithaca (not the Town).
  If it can't help, the box says why and you fill it in by hand.
