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
.\.venv\Scripts\pip install -e ".[dev]"
```

The last line is **needed for this update** (2026-10-21 evening): Gordium now uses one more measuring library,
`numpy`, to fit roof planes. It ends with `Successfully installed …`.

Then **quit Rhino completely and open it again** (Rhino keeps the old Gordium loaded until it restarts).

## What's new in this preview (2026-10-21 evening)

The full guide for this version is the PDF Ben sends with it (*Gordium demo guide*): what Gordium knows, what it
assumes, what it doesn't cover yet, and how it works. The short version:

- **Three districts:** R-1a, R-1b and R-3a, each hand-written from the law and checked.
- **Address lookup** fills in the lot (State tax-parcel map), the street side, corner lot and a *suggested* zoning
  district (City zoning map); you tick **I confirm**.
- **The largest legal starting house** is drawn for the lot (2 ft back from every limit on a tax-map lot).
- **Every reading** where the law or the data allows more than one (tax-map lines ±2 ft, eaves, which line is the
  rear, which building is the main one): complies only if all pass.
- **Neighbouring building footprints** shown around the lot, on screen only.
- **Zoning report…** opens on a *Check* sheet that matches the panel row for row, with citations and links.
- **Ground is taken as flat** at the lot's level in this version (the panel says so).

## Known limits

- **Look up only addresses in R-1a, R-1b or R-3a for now.** For an address in another district (say R-2a) the
  zone menu wrongly falls back to R-1a; a fix is coming in the next update.
- **Stories:** draw buildings with Gordium's floor blocks (the starting house uses them). A building drawn as one
  plain solid makes the Stories row ask you to enter the number of stories, and there is no box for it yet; a fix
  is coming in the next update.
- **Windows is not fully tested yet.** If something looks wrong or a window shows an error, take a screenshot and
  send it to Ben.
- **AI-drafted zones are not included** (left out on purpose while they are checked).
- The address lookup needs the internet and works only for addresses in the **City** of Ithaca (not the Town).
