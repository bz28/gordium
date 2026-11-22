# Gordium in Rhino: from scratch

For an architect who has just opened Rhino. About 10 minutes the first time, then 1 minute per project.

Gordium checks your massing against the City of Ithaca zoning rules (the residential districts R-1a, R-1b, R-2a, R-2b,
R-2c, R-3a, R-3aa, R-3b and RU, for now;
the sample project below is an R-1b one-family house) while you design. Every item is **✓ complies**, **✕ does not comply**, **? needs review** or **– not checked**. It
never says "complies" unless it is sure (see [What "needs review" means](#what-needs-review-means)).

**Contents:** [Set up (once)](#what-you-need-once) · [Your first project](#your-first-project-step-by-step) ·
[Test it yourself](#test-it-yourself) · [Troubleshooting](#troubleshooting) · [Getting updates](#getting-updates) ·
[On Windows](#on-windows)

## What you need (once)

About 20 minutes on a new Mac. (On a Windows PC, follow [On Windows](#on-windows) instead.) Three words used
below:

- **Terminal**: the Mac app where you type commands. To open it: press **Cmd+Space**, type `Terminal`, press
  **Enter**. To run a command, paste it in and press **Enter**.
- **Repository**: Gordium's project folder, kept on GitHub (a website that stores code).
- **Branch**: a version of that folder still being worked on. Until it is finished and merged, the Rhino part of
  Gordium is on the branch `rhino-ui`; after that it is on `main`, and you skip the `git checkout rhino-ui` line.

1. **Get access.** The Gordium repository is private. Make a free account at [github.com](https://github.com) and
   send Ben your GitHub username. He adds you; GitHub emails you an invitation: click **Accept invitation**.
2. **Make a GitHub token** (the password Terminal uses for GitHub; your normal password doesn't work there). On
   github.com: your picture (top right) → **Settings** → **Developer settings** → **Personal access tokens** →
   **Tokens (classic)** → **Generate new token (classic)**. Tick **repo**, click **Generate token**, and copy the
   token (it starts with `ghp_`). Keep it for step 5.
3. **Install Rhino 8.**
4. **Install Python 3.12 to 3.14** (3.12, 3.13 or 3.14; 3.15 not yet supported. Python is the language
   Gordium's checking is written in). Already have one of those? Skip to the check. Otherwise, from
   [python.org/downloads/macos](https://www.python.org/downloads/macos/), download the newest **Python 3.14.x**
   "macOS 64-bit universal2 installer" (not 3.15), open it and click through. Check in a **new** Terminal window:

   ```
   python3.14 --version
   ```

   You should see `Python 3.14.` and a number. If you installed 3.12 or 3.13 instead, type `python3.12` or
   `python3.13` here and in step 6.
5. **Download Gordium** into your Documents folder. This makes the folder `Documents/gordium`; every path below
   assumes it is there.

   ```
   cd ~/Documents && git clone https://github.com/bz28/gordium.git
   ```

   It asks for your **Username** (your GitHub username) and **Password**: paste the token from step 2 (nothing
   shows as you paste; that's normal) and press Enter. You should see `Cloning into 'gordium'...` and then
   `done.` Your Mac remembers the token, so it won't ask again.
   - `Repository not found` or `Authentication failed`: accept the invitation (step 1), or make the token
     again with **repo** ticked (step 2), then run the line again.
   - If a box says *"The git command requires the command line developer tools"*, click **Install**, wait for it
     to finish, then run the line again. (Or run `xcode-select --install` first.)
6. **Set up Gordium's Python.** Paste all four lines at once:

   ```
   cd ~/Documents/gordium
   git checkout rhino-ui
   python3.14 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

   The second line says `Switched to a new branch 'rhino-ui'`. The last one prints a lot for a minute or two and
   ends with `Successfully installed …` (a list that includes `gordium-0.1.0`). Gordium's checking runs in this
   `.venv` Python (a private copy of Python inside the gordium folder), in the background; Rhino only draws what
   it says. No AI runs while you design.
   - `python3.14: command not found`: go back to step 4 (or use the version you installed: `python3.12`,
     `python3.13`).
   - `requires a different Python`, or pip tries to build something and fails: the `.venv` was made with an
     unsupported Python. Delete it and make it again with a supported one (the **start-over lines**):

     ```
     cd ~/Documents/gordium
     rm -rf .venv
     python3.14 -m venv .venv
     .venv/bin/pip install -e ".[dev]"
     ```
   - The last line ends with a red `ERROR`: check you are online and run it again. If it still fails, send Ben
     the last 20 lines it printed.

## Install in Rhino (once)

1. **Open Rhino 8** and start a new file.
2. **Open the ScriptEditor:** type `ScriptEditor` in Rhino's command line and press Enter (or Tools →
   ScriptEditor). A script window opens. This also starts Rhino's Python, which Gordium needs: in every Rhino
   session, open the ScriptEditor once before using Gordium.
3. **Open the installer:** in the ScriptEditor, **File → Open…**. In the file window press **Cmd+Shift+G**, paste
   the line below, press Enter, then click **Open**:

   ```
   ~/Documents/gordium/apps/rhino_plugin/install.py
   ```

   (Or click your way there: Documents → gordium → apps → rhino_plugin → `install.py`.)
4. **Run it:** click the **Run** button (▶) in the ScriptEditor.
5. Rhino's command line shows six lines, then one more step:

   ```
   Gordium: GordiumStart -> gordium_start.py
   Gordium: GordiumCheck -> gordium_check.py
   Gordium: GordiumLive -> gordium_live.py
   Gordium: GordiumFacts -> gordium_facts.py
   Gordium: GordiumOff -> gordium_off.py
   Gordium: GordiumPanel -> gordium_panel.py
   ```

   These six are now Rhino commands, kept between sessions. You can close the ScriptEditor.
6. **Once: let the Gordium panel come back with Rhino.** Gordium's results appear in a panel docked beside
   Rhino's own (Properties, Layers). Rhino remembers where you put it, and reopens it at launch, but only Gordium
   can fill it. So: **Rhino → Settings… → General**, and in **"Run these commands every time Rhino starts"** add
   the line `GordiumPanel`. (It only sets up the panel: no check runs, nothing in the model changes.) Without it,
   a Gordium tab Rhino reopens shows "container is empty" until you run a Gordium command.

Used to Rhino's command line? Instead of steps 3 and 4, type
`_-RunPythonScript "/Users/<your Mac username>/Documents/gordium/apps/rhino_plugin/install.py"` (the full path; in
Terminal, `echo ~` prints the `/Users/…` part).

## Getting updates

When Ben says there is a new version:

1. In Terminal:

   ```
   cd ~/Documents/gordium && git pull
   ```

   It lists the files that changed (or says `Already up to date.`).
2. **Quit Rhino completely (Cmd+Q) and open it again.** Rhino keeps the old Gordium loaded until it is quit;
   closing the window is not enough. You don't need to install in Rhino again.
3. If Gordium then says a module is missing (`No module named …`), run step 6's last line again:
   `cd ~/Documents/gordium && .venv/bin/pip install -e ".[dev]"`.

## On Windows

**Windows hasn't been tested yet: please report anything that goes wrong.** The steps are the same as on a Mac,
typed in **PowerShell** (the Windows app where you type commands: click **Start**, type `PowerShell`, press
**Enter**) instead of Terminal.

**Please confirm one thing:** while Gordium runs in Rhino (GordiumStart, a check, Zoning report…), **no black
terminal window should appear**. Gordium starts its checker with no window on Windows; if one still pops up, tell
us which step showed it. Zoning report… should open the report in Excel (or your spreadsheet app).

1. **Get access**, as on the Mac ([step 1](#what-you-need-once): a GitHub account; accept Ben's invitation). You
   don't need a token on Windows: Git asks you to sign in to GitHub in your browser instead.
2. **Install Rhino 8.**
3. **Install Git** (the tool that downloads Gordium and its updates) from
   [git-scm.com](https://git-scm.com/downloads/win): run the installer and keep every default.
4. **Install Python 3.12 to 3.14** (3.12, 3.13 or 3.14; 3.15 not yet supported). From
   [python.org/downloads/windows](https://www.python.org/downloads/windows/), download and run the **Python
   Install Manager** (the website's main download; it installs the newest Python, which may be 3.15). Then, in a
   new PowerShell window, add 3.14 and check:

   ```
   py install 3.14
   py list
   ```

   `py list` shows the Pythons installed; one of them must be `3.14` (or `3.13` / `3.12`). A newer one (3.15) can
   be there too, but Gordium can't use it yet, so step 6 asks for 3.14 by name. (Running the website's installer
   again only says the latest version is already installed: `py install 3.14` is how to add 3.14.)
   - If `py install 3.14` says *can't open file '…\install'* (an older Python launcher) or that `py` is not
     recognized: from the same page download the **Python 3.14.x**
     "Windows installer (64-bit)" (not 3.15), tick **"Add python.exe to PATH"** on its first screen, click
     **Install Now**, and check with `py --list`.
5. **Download Gordium** into your Documents folder (this makes `Documents\gordium`):

   ```
   cd $HOME\Documents
   git clone https://github.com/bz28/gordium.git
   ```

   If a window asks you to sign in to GitHub, choose **Sign in with your browser** and approve it. You should see
   `Cloning into 'gordium'...` and then `done.`
6. **Set up Gordium's Python.** Paste these four lines:

   ```
   cd $HOME\Documents\gordium
   git checkout rhino-ui
   py -3.14 -m venv .venv
   .\.venv\Scripts\pip install -e ".[dev]"
   ```

   (Installed 3.13 or 3.12 instead? Type `py -3.13` or `py -3.12`.) The last line ends with
   `Successfully installed …` (a list that includes `gordium-0.1.0`).

   The `git checkout rhino-ui` line is needed: the main version has no Rhino part yet (no `apps` folder), and
   `git pull` alone won't add it. To check which version you have, run `git branch --show-current`: it should
   say `rhino-ui`.
   - `requires a different Python`, or `Microsoft Visual C++ 14.0 or greater is required`: the `.venv` was made
     with an unsupported Python (usually 3.15, picked by a plain `py`). Delete it and make it again (the
     **start-over lines**):

     ```
     cd $HOME\Documents\gordium
     Remove-Item -Recurse -Force .venv
     py -3.14 -m venv .venv
     .\.venv\Scripts\pip install -e ".[dev]"
     ```

   - Any other red `ERROR`: send Ben the last 20 lines it printed.
7. **Install in Rhino.** File Explorer's "Documents" is often your OneDrive Documents, which is a different
   folder from the one PowerShell cloned into, so don't look for gordium there. Instead, in PowerShell, get the
   installer's full path:

   ```
   cd $HOME\Documents\gordium
   Resolve-Path apps\rhino_plugin\install.py
   ```

   It prints something like `C:\Users\<you>\Documents\gordium\apps\rhino_plugin\install.py`: select it and copy
   it (Ctrl+C). (`explorer .` opens this gordium folder in File Explorer, if you want to see it.) Then open Rhino 8,
   type `ScriptEditor` and press Enter. In the ScriptEditor, **File → Open…**, paste the path into the
   **File name** box, press Enter, then click **Run** (▶). Rhino's command line shows the same six
   `Gordium: …` lines as [on the Mac](#install-in-rhino-once). As on the Mac, open the ScriptEditor once in every
   Rhino session before using Gordium. Then, once: **Tools → Options → General**, and in **"Run these commands
   every time Rhino starts"** add the line `GordiumPanel`, so the Gordium panel Rhino reopens at launch is filled.
8. **Getting updates:** in PowerShell,

   ```
   cd $HOME\Documents\gordium; git pull
   ```

   then **close Rhino completely (File → Exit) and open it again**: Rhino keeps the old Gordium loaded until it
   is closed. If Gordium says a module is missing, run step 6's last line again from the gordium folder.

## Your first project, step by step

1. **New file.** File → New, a template in **feet** (any units work; feet is easiest to read).
2. **Type `GordiumStart`** and press Enter.
   - On an empty file the start box opens empty and **Draw** stays off until an address is looked up. To try
     Gordium, look up 106 Ithaca Rd: the State tax map's lot (7,033 sf, its front curving along Ithaca Road),
     placed with the street along the bottom of Top view, the lot behind it. A lot the maps don't know:
     **Enter the site by hand…** (you say the lot is in the City of Ithaca, draw the lot and pick the district and
     street side; no neighbourhood).
   - To use your own lot instead, first draw it as one closed polyline on a layer named `Site`, then run
     `GordiumStart`.
   Whenever Gordium takes more than a moment, a small window says what it is doing, with the seconds so far: Rhino
   keeps drawing meanwhile. A check, the starting house and the zoning report have **Cancel** (starting the
   checker and reading the lot facts have none: they are quick once it runs); **Esc** stops it too while that
   window is in front (anywhere else in Rhino, Esc keeps its usual meaning). Cancel stops the
   work and changes nothing: a **Draw** cancelled while Gordium works out the starting house draws nothing (the
   model is as it was before the box); once it is drawn, Cancel stops only the check that follows. A cancelled
   check leaves the panel saying "Check cancelled" (press **Check again**); a cancelled report leaves the file as it
   was. Live re-checks after an edit run in the background: the panel says "Checking…" with what it is doing and
   its own **Cancel**.
3. **The start box** opens (filled in from your lot, if you drew one). Read it top to bottom:
   - **Address**: type it and press **Look up** (or Enter). After 4 characters and a short pause, a list under the
     box offers the City of Ithaca addresses that start that way (the City's own address list, asked live, never
     kept; Town of Ithaca addresses never appear): **Down**/**Up** and **Enter**, or a click, picks one; **Esc**
     closes the list. Offline, it quietly says "Suggestions unavailable" and typing works as before. No town
     typed? Look up asks for the address in the City ("106 Ithaca Rd" becomes "106 Ithaca Rd, Ithaca, NY"). If a
     lookup finds no lot, the box says so and that the lot shown is still the one you had. Gordium asks the public map services (it takes up to
     45 seconds; the box says what it is doing as it goes, "Looking up … · Reading the City zoning map…", with a
     moving mark and the seconds so far, and **Cancel lookup** stops it: nothing it would have filled in
     changes, and your ticks stay as you left them). Look up only shows what it found: the address and a suggested zoning
     district fill in, and the lot it found is shown dashed. Nothing in the model changes until **Draw**, which
     draws that lot from the tax map (its street at the bottom of Top view), the street side and whether it's a
     corner lot, each with where it came from (not the ground: for now it is assumed flat, see **Ground** below).
     Anything doubtful is amber with the reason: tick **I checked this** once you have, or change it; until then
     the items that depend on it need review. An address typed and not looked up keeps Draw off ("Press Look up to
     find … first."); on a lot already drawn, type the lot's own address back, or clear it, and Draw is on again
     (in a new file Draw needs a lookup that finds the lot, or **Enter the site by hand…**). If the lookup can't
     help (offline, not found, outside the City of Ithaca), the box says why: correct the address and Look up
     again, or put back the lot's own address (or clear it) and fill the rest in by hand. Outside the City: Draw
     stays off for that address, and in a new file by hand is refused, until a live lookup of that same address
     finds the lot, or you close the box. Another address looked up and found can be drawn; by hand stays refused.
   - **Zoning district**: "entered by you" (R-1b, R-1a, R-2a, R-2b, R-2c, R-3a, R-3aa, R-3b and RU can be picked),
     or after Look up "suggested by Gordium · City of Ithaca zoning map, used live". Either way, tick **I confirm**: Draw stays off until you do,
     on every new project, after every lookup and after you pick another district (a tick is for one district),
     because the City's online map is informational: the district is your statement.
   - **Use**: one-family dwelling, detached.
   - **About this project**: the facts you know at the start that shape the building's outline: whether an
     accessory dwelling unit (ADU) is on the lot (a detached one is a building of its own), a stream or inlet
     near the lot (and how far), whether the lot is in the South Hill Overlay, how many homes an attached building
     holds, how many cars the lot's private garages hold (R-1 and R-2). Each is a one-click dropdown ("No stream within 20 ft") and **starts on Not answered**: Gordium never
     assumes. Leave one unanswered and the rows that need it say "needs review", as always. Hover a question for
     its full wording. Answers are saved with the project; change them in Edit site… .
     Who lives there (household) and a home business are asked later, when you plan
     the interior: they sit in the
     panel's collapsed **Use details (for later)** group (still needs review, not counted among the building's
     problems, never a pass). Each row says "Answer when you plan the interior: …" and has its **Enter…** button.
   - **Lot**: its area and where it came from: "7,033 sf · from the tax map (±2 ft, approximate)". Gordium treats
     tax-map lines as uncertain by 2 ft: anything that only holds if they're exact needs review. **Use my
     survey…** to pick your surveyed outline instead.
   - **Street side**: the lot line on the street (highlighted). **Change…** to pick another. **Corner lot?**: answer
     it (one street or two). Gordium never guesses: until you answer, the yards need review. One click on a street
     keeps the whole street, however many pieces the tax map drew it in, and stops at the corner; the command line
     says what it kept ("Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage"). Where the lot line bends with no clear
     corner, Gordium asks, and needs your Yes or No (neither guess is safe).
   - **Ground**: for now Gordium assumes the ground is **flat at the lot level and finished** (no regrading); the
     rows for height and stories say "assuming flat ground", and so does the report. That assumption decides them
     only when Look up found the lot level (its ground falls less than 6 inches across the lot). Height is measured
     from the average ground level at the walls (the grade plane, §325-3), so on a sloping lot, or with no ground
     looked up, height and stories **need review**, saying how far the ground falls: check them against your
     survey. (Spot grades, terrain and regrading, which let Gordium check them on a slope, come back in a later
     release.)
   - An amber line appears when the box can't decide something itself, with what to do (for example "This lot
     faces two streets: pick the front").

   Any button that picks something closes the box, lets you pick in the model, and opens it again.
4. **Draw.** You see:
   - the lot's property line with each edge's length (in Top view);
   - the buildable envelope, see-through blue: the space every yard and the height limit leave;
   - on a locked layer **Gordium::Envelope**, real curves to snap to (Osnap): the buildable outline at ground
     level and each yard's required line in full. On a tax-map lot (any lot not marked as from a survey) the
     outline 2'-0" in from every lot line is solid and everything as drawn dashed; where nothing is left 2'-0" in,
     only the dashed one. Gordium replaces them at every check (never measured; Undo never stops on them); untick
     **Show buildable envelope** to hide them;
   - the largest legal starting building: three floor blocks (11'-8" floor to floor), one group, each floor on its
     own sublayer `Gordium::Massing::Floor 1`, `Floor 2`, `Floor 3` (a `Gordium::Massing::Roof` sublayer is made for
     your roof). **Hide starting house** in the panel hides it (it is still checked). On a lot from the tax map it
     keeps 2'-0" back from every limit, so it complies even if the tax map is 2 ft off; on a survey it goes to the
     limits. The panel says why it is that size, for example "Largest house that complies even if the tax-map lines
     are 2'-0" off; limited by lot coverage 25%. Use my survey… for the full size.". Where the district lets the
     two side yards differ (R-2b: one side 10 ft, the other 5 ft), the starting house takes the 10 ft yard on one
     side only: the side that gives the larger house, else the left as seen from the street. The note says which,
     for example "Side yards: 10'-0" on the left (west), 5'-0" on the right (east), seen from the street."; under the
     panel's Starting house fact, **Switch side yards** redraws it with the sides swapped (one Undo step; proven by
     the checker first, and never over a house you have moved or edited). The blue envelope and every check stay
     cautious: the envelope keeps the larger side yard on both sides;
   - on a tax-map lot the blue envelope is the cautious one: every lot line 2'-0" nearer;
   - on a looked-up lot, the **neighbourhood** 750 ft around it, like a site context drawing, all kept in the file:
     the neighbouring tax parcels and the street centerlines in grey on locked `Gordium::Context` layers; the
     neighbouring building footprints as outlines (no heights) on the unlocked `Gordium::Context::Buildings` layer,
     so you can drag and edit them (an outline you edit is yours: Gordium never removes or redraws it); a north
     arrow, a 100 ft scale bar and the sources. The check never measures any of it, and says so if a solid on those
     layers sits over the lot. **Show neighbourhood** in the panel turns it off and on (kept with the file);
   - with **Show on-screen labels** ticked in the panel (off at first): each yard's and lot edge's label, and the
     status box top right (e.g. "? 2 need review · 8 comply · 1 to answer · 1 not checked in this release"). Off, a failing yard's shortfall still
     shows ("✕ Rear yard 21'-2", needs 22'-6"");
   - the **Gordium panel** (a floating window): every item, bad news first.
5. **Make an edit.** Move, stretch or add solids as you normally would. The results grey out: the panel and the
   status box say "Model changed since the last check — press Check". Press **Check** in the panel (first button
   at the top). Tick **Check after every edit** in the panel to have Gordium check again by itself half a second
   after you stop (kept with the file). After a check:
   - when something newly stops complying, a short note appears bottom left ("✕ Rear yard no longer complies ·
     29'-6" proposed · 30'-0" required · −0'-6""). It goes by itself;
   - only the offending part of the building is coloured: the part inside a required yard, or above the height
     limit. Red where it fails under every reading; amber where it fails only under some (for example within the
     tax map's 2'-0" of a lot line). The rest stays neutral;
   - in Top view each yard is dimensioned as a drawing is: square to its lot line from the wall facing it, red
     where it fails, amber where it needs review, complying ones neutral grey; it shows its number only, on its
     line or just past its end (✕ or ? before it when something is wrong; the yard's name and what it needs are in
     the panel); when the nearest part is not the ground-floor wall the number says what it is measured to, e.g.
     "22'-0" (to 2nd-floor overhang)" (the number itself and its result are unchanged); the required line is dashed
     across it, tagged "min 10'-0"" where the yard fails or needs review;
     what is wrong is placed first and every number stays in view; in the Front
     and Right views the height is dimensioned up from the grade plane, the limit faint. Zoomed out to the
     neighbourhood the dimensions give way.
   - in Top view Gordium's lines (the lot line, the envelope's outline, the dimensions) are drawn over everything,
     so none is lost under a roof; in Perspective and the elevations they hide behind your solids, as Rhino's own
     lines do.
6. **Read the panel.** Click any row. The bottom half shows the city's exact words, the examiner-style citation
   ("§325-8, District Regulations Chart, R-1b, Rear yard column, note 16") with links to the page, and what to
   change ("To comply: move the building 0'-6" farther from that lot line."). **How it's worked out** (closed at
   first) opens the working: the formula with the values written in, what was measured, and the chart's own cell. **Zoom to** (or a double-click) frames the item: yards in Top, height in a front elevation.
7. **Zoning report…** checks the model as it is now and writes the report: `<your model>_gordium_report.xlsx`,
   next to your model file, or in your **Documents** folder (`untitled_gordium_report.xlsx`) if the model isn't
   saved yet. It has the same results as the panel. The line above the buttons says "Report saved to …" with the
   full path, and the report opens in your spreadsheet app. That's Excel, or Numbers (free from the App Store), or
   any app that opens .xlsx. If none is set up, open the file yourself from that folder. If the report can't be
   written, the same line says why.

## The other commands

| Command | What it does |
|---|---|
| `GordiumCheck` | Check the model now: your own design, or (on an empty file) the start flow. Writes the report (so does **Zoning report…** in the panel). |
| `GordiumLive` | Turn **Check after every edit** on or off for this file (the same as the panel's tick). |
| `GordiumFacts` | Open the start box again to change the site facts (the panel's **Edit site…** does the same). |
| `GordiumOff` | Stop Gordium and clear its drawing. Nothing in your model is changed. |

Gordium never changes your model, except for what you ask: the starting building and a looked-up lot. Everything
else (the envelope, the red, the labels, the status box) is drawn on top and disappears with `GordiumOff`.

## What "needs review" means

"? needs review" means **Gordium can't be sure, so it won't say it complies**. The row's reason says why, and
usually what fixes it:

- **The lot lines are from the tax map** and the item is within 2'-0" of its limit: "at worst 23'-0" against
  25'-0" · Pick survey lot lines…".
- **The grade isn't set**, or the spot grades aren't at the building's walls any more (after you move it):
  height and stories wait for it.
- **The code leaves a question open** (for example whether an upper-floor overhang counts in a side yard). Gordium
  works the design out under every reading. If the result doesn't depend on the question (every answer gives
  the same result), the row simply complies. If it does depend on it, the row needs review and names the question,
  because only the zoning office can settle it.
- **Something on the lot isn't measured**: a solid not on the `Building` layer (a shed on Default, an imported
  garage). Lot coverage counts every building on the lot, so it needs review until you **Add to check…**.
  A **linked block** (a block linked to another file) whose file is missing, can't be read or has changed since
  it was loaded can't be placed at all, so it counts as on the lot and touching the house, and the row says which
  file and what to do, for example "Linked file 'garage.3dm' has changed since it was loaded: reload it (Edit ▸
  Blocks ▸ Block Definitions, select it, then Update; or type -BlockManager, Update, All) so Gordium can see where
  it is", or, for a moved file, "Linked file 'garage.3dm' can't be found at /Users/you/site/garage.3dm: relink it
  to where the file is now (Edit ▸ Blocks ▸ Block Definitions, select it, then Properties ▸ Filename: Browse to
  the file) so Gordium can see where it is". Once the file is put right, the check places the block by its own
  shape like any other object: still on the lot, it stays in this row until you **Add to check…**.
- **It needs a fact the model can't show** (bedrooms, parking spaces, dwelling units, rooms let for profit,
  whether it is a conversion, the number of stories): its button names them when that fits, for example **Enter bedrooms
  and parking spaces…**, or says how many, for example **Answer 3 questions…**. It opens a small window that asks only them (a number, or Not answered / No / Yes). **OK** saves just
  those answers, each "entered by you" with the date, as one Undo step, and checks again; **Cancel** (or Esc)
  changes nothing. Left blank, a fact stays unanswered and its rule keeps needing review (never read as 0 or no).
  Answers to the start box's questions show there too the next time you open **Edit site…**. A row that needs a
  site fact (the lot, the district, the street side, Corner lot?) has an **Edit site…** button instead.

"– not checked" means Gordium doesn't check it yet (parking needs bedroom and parking counts; overlays come in a
later release). "Not checked yet" lists the code sections not in Gordium yet (coming in a later version): check
those by hand for now; each row names its section.

The rules are a **draft**, not yet reviewed by a licensed professional; the panel says so at the top.

## Test it yourself

Every number below is checked by a test in the repository (`packages/design_checker/tests/test_quickstart.py`),
so the guide and Gordium can't drift apart.

### Rhino basics you'll need

- **Select the house:** click it once. The three floors are one group, so they move together.
- **Move by an exact distance:** `Move`, click a start point, type the distance (for example `5`), press Enter,
  click the direction.
- **Move one face:** Cmd+Shift+click a face to select just that face. Then drag the Gumball arrow, or click the
  arrow and type a distance.
- **Undo:** Cmd+Z.
- **Draw a box:** `Box`, then two corners and a height.

### The starting house at 106 Ithaca Rd

Looked up, 106 Ithaca Rd is the lot as the State tax map draws it (parcel 84.-2-6): 7,033 sf, 75'-10" wide along
Ithaca Road (its front is a gentle curve) and about 101 ft deep, with a short jog at the back. In Top view the
street is along the bottom (the lot faces south-east); "back" below means away from the street (up in Top view).
The side yards are named by compass, as on a site plan: the southwest one is on your left as you face the lot from
the street, the northeast one on your right. The starting house is 51'-4" wide and 29'-8" deep, 35'-0" tall, in three floors
of 11'-8".

The lot lines are from the tax map, so each one could be up to 2 ft off the unlucky way. The house is drawn to
comply even then: it keeps at least 2'-0" back from every limit, and its footprint is at most 25% of the smallest
lot the tax map allows:
- front yard 27'-0 3/4" (needs 25'-0");
- side yard, southwest 12'-0 1/2" (needs 10'-0"); northeast, 12'-0 3/8";
- coverage 21.7% (the limit is 25%).

Fifteen rows need review from the start, and that is Gordium being honest, not a mistake:
- **New structures at least 20 ft from an inlet wall or stream bank**: the start box's stream question was left
  Not answered, so this row waits on it ("say whether any inlet wall or stream bank … is within 20 ft of the lot").
  Answer it with the row's **Answer 2 questions…** button and the row is decided.
- **Rear yard**: which of the short lines at the back count as side lot lines and which as the rear lot line is an
  open question for the architects (it decides the lot's depth, and so the rear yard's requirement). The list
  shows the tightest reading, 36'-3 3/8" against 32'-10 1/8", each marked "(varies)", and its Delta reads
  "+3'-5 1/4" if confirmed (at least +0'-5 1/4" under every reading)", the least under any reading, the tax map's
  2 ft too (the list says it shorter: "worst +0'-5 1/4"" over "if confirmed"). The row's details give the
  range each can take (34'-11 7/8" to 36'-3 3/8" against 24'-1 7/8" to 32'-10 1/8"), and the reason says so once: "Complies under every
  reading, but it depends on an open question: which lot lines count as side and which as rear; confirm with the
  zoning office".
- **Eaves into front yard** waits on the same question, and on the height (its limit grows with the height bonus,
  and the height waits on the ground, below).
- **Building height** (35'-0", at the limit) and **Stories** (3, at the limit): the lookup found the ground falls
  about 14.2 ft across this lot, and Gordium is assuming it flat, so neither can be decided: "the ground falls about
  14.2 ft across the lot, but Gordium assumes it flat: height is measured from the average ground level at the
  walls (the grade plane, §325-3), which Gordium can't set yet: check height and stories against your survey". The
  header's Ground line says the same. On a lot the lookup finds level, both comply.
- **Which code governs this building: can't tell yet**, one at the head of each egress section (the NY Residential
  Code's and the NY Building Code's): with the stories undecided, Gordium can't tell whether the house is within the
  Residential Code's three stories above grade plane (R101.2), so both books wait and neither is the answer
  ("To settle it, state the building's stories above grade plane"). On a lot the lookup finds level, the stories
  comply and only the Residential Code's section shows.
- **Private garage: not more than three cars**: the start box's garage question was left Not answered, so this row
  waits on it ("enter how many cars the lot's private garages hold, all together …"). Answer it with the row's
  **Enter the cars the private garages hold…** button: three or fewer complies; over three, the row then asks how
  many garages there are (whether the three cars are for each garage or the whole lot is an open question).
- The six **accessory dwelling unit** rows (one per parcel, two bedrooms, not in the primary front yard, the attached
  ADU's 40%, the detached ADU's size and its setbacks) and **One-family occupancy**: the start box's ADU question was
  left Not answered, so they wait on it ("say whether an accessory dwelling unit (ADU), attached or detached, is on
  the lot"). Answer it with an ADU row's **Enter whether an ADU is on the lot…** button: **No ADU on the lot** and
  the six ADU rows go (they don't apply), and One-family occupancy joins **Use details (for later)**, waiting only
  on who lives there.

Lot area complies even at the tax map's worst case.

### Simple tests

1. **Tick Show on-screen labels** in the panel: each yard's label and the status box appear in Top view. Untick it:
   they go (the yard lines stay).
2. **Move the house 5 ft back.** Front yard 32'-0 5/8": complies. The rear yard still needs review (the open
   question above).
3. **Move it 10 ft back instead.** Rear yard 24'-11 7/8" to 26'-6 1/8": **needs review**. **Now move it 15 ft back:**
   Rear yard 19'-11 7/8" to 21'-8 3/8": **does not comply**, "still 1'-1 7/8" short under every reading": short
   under every reading of the back lines and of the tax map. (From 11 to 13 ft back it still needs review: under some readings of the
   back lines and of the tax map it could still comply. From 14 ft back it does not comply.) A note appears, and the strip of the house that is over
   turns red.
4. **Undo, then pull the rear wall 11 ft back** (Cmd+Shift+click the back face, Gumball 11). Lot coverage 29.7%
   against 25%: **does not comply**, even on the largest lot the tax map allows.
5. **Undo, then raise the roof 4 ft** (the top face of Floor 3). On this sloping lot Building height 39'-0" still
   **needs review** (the ground, as above). On a lot the lookup finds level it **does not comply**, 4'-0" over
   (the height doesn't depend on the lot lines), and only the part above 35'-0" turns red.
6. **Undo, then move the southwest wall 3 ft out** (Cmd+Shift+click the face on your left, seen from the street).
   Side yard, Southwest 9'-0 1/2": **needs review**, 0'-11 1/2" short as drawn, "+1'-0 1/2" if the tax-map lines
   are 2 ft off the other way" (it complies if the tax map's line is out the lucky way). **Move it 5 ft out
   instead:** 7'-0 1/2": **does not comply**, 2'-11 1/2" short, "still 0'-11 3/8" short if the tax-map lines are 2 ft
   off the other way" (rounded down: never more than certain), and that strip turns red.
7. **Undo.** Everything is back to the starting results.

### Harder tests

8. **A garage: `Box` 12 × 20 × 10 ft on the Default layer**, behind the house. "Objects on the lot not included"
   and Lot coverage need review: coverage counts every building on the lot. **Add to check…** puts it on the
   Building layer, and it is measured.
9. **Move one floor on its own** (Floor 2, 3 ft to the right, seen from the street). Stories needs review: "floors misaligned".
10. **The height bonus** (§325-16C: a taller house if every yard is larger): raise the roof 3 ft (38'-0"), move the
    house 3 ft back, and pull each side wall 3 ft in. On this lot Building height **needs review**: the bonus needs
    the rear yard larger too, and which lines are the rear lot line is the open question above (and the ground, as
    above).
11. **Delta in words, as drawn and if the tax-map lines are 2 ft off:** after test 2 the Front yard row's details
    read "+7'-0 5/8" (+5'-0 5/8" if the tax-map lines are 2 ft off)" (the list says it shorter, on two lines:
    "+7'-0 5/8"" over "worst +5'-0 5/8""); in test 6 the Southwest side yard reads "0'-11 1/2" short (+1'-0 1/2" if the tax-map lines are 2 ft
    off the other way)" (3 ft out: it may comply) and "2'-11 1/2" short (still 0'-11 3/8" short if the tax-map lines
    are 2 ft off the other way)" (5 ft out: the red strip). A maximum passed says "over" instead of "short" (test
    5's "4'-0" over"). The same in the report and the note. With a survey it reads the margin itself: after test 2,
    "+7'-0 5/8"".
12. **Corner lot:** Edit site… → Corner lot? Yes: two streets. The yards need review (which yard is the front is
    an open question for a corner lot).
13. **A survey:** with a surveyed lot, a new starting house goes to the limits: 55'-4" × 31'-8", its southwest
    side yard at 10'-0 1/4", complying (its sides are whole inches, rounded down, so it sits just inside the
    10 ft limit).
14. **Other units:** start in a Millimeters, Meters or Inches template. The results are the same: Gordium works
    in feet and converts at Rhino's edge.
15. **A backyard cottage (a detached ADU, §325-28):** draw a `Box` 20 × 16 × 18 ft on the Building layer behind
    the house, at least 5 ft from the side and rear lot lines. Answer **ADU on the lot** (in **Edit site…**, or an
    ADU row's **Enter whether an ADU is on the lot…**); the ADU's rows then ask the rest with their **Enter…**
    buttons: detached, new construction, one on the parcel, two bedrooms. Then they ask for its building: **Pick the
    ADU's building…** and click the box. The ADU's rows are decided: not nearer the street than the house:
    complies. 5 ft or more from the side and rear lot lines: it is, under every reading, but on this lot it needs
    review like the house's rear yard ("Complies under every reading, but it depends on an open question: which lot
    lines count as side and which as rear"); in R-1, 5 ft to under 6 ft also needs review (whether §325-25C's 6 ft
    applies too is an open question). Its size (320 sf footprint, 18 ft, at most 2 stories) **needs
    review** here, as the house's height does: the ground falls about 14.2 ft and Gordium assumes it flat. On a lot
    the lookup finds level it complies, and made 22 ft tall it **does not comply** (20 ft at most). Move it in front
    of the house: **does not comply** (not in the primary front yard). The cottage still counts toward lot coverage.

### What counts as a problem

- A row saying **complies** that you think doesn't (a false pass): the most important kind. Please send it
  with the file.
- A number that's wrong, or rounded in Gordium's favor.
- Something that should be drawn but isn't, or is drawn in the wrong place.
- Rhino closing or freezing (see Troubleshooting).

"Needs review" with a reason is not a problem: it's Gordium saying it can't be sure.

## Troubleshooting

- **"no .venv found above …"**: the repository's Python environment is missing. Paste the four set-up lines of
  step 6 ([Mac](#what-you-need-once), [Windows](#on-windows)), then run the command again.
- **"Microsoft Visual C++ 14.0 or greater is required"** or **"requires a different Python"** while setting up:
  the wrong Python version made the `.venv` (Gordium needs 3.12 to 3.14; 3.15 not yet supported). Delete the
  `.venv` and make it again with 3.14: run the four **start-over lines** in step 6 (the block with
  `rm -rf .venv` on a [Mac](#what-you-need-once), `Remove-Item -Recurse -Force .venv` on
  [Windows](#on-windows)), not the first set-up block; paste all four, starting with the `cd` line. On Windows, if `py list` doesn't show 3.14,
  run `py install 3.14` first.
- **Nothing happens / the commands aren't found**: run the install step again. If the ScriptEditor hasn't been
  opened in this Rhino session, open it once (Tools → ScriptEditor). That starts Rhino's Python.
- **I can't see the panel**: it is a floating window and may be behind Rhino or on another desktop (Mission
  Control). Run `GordiumCheck` again to bring it back.
- **"Gordium: ⚠ couldn't … (it was skipped; details in …gordium_errors.log)"**: one drawing or panel step failed
  and was skipped; the check itself is unaffected. Please send that log file.
- **A check refuses with "â€”" in a quote** (Windows): your copy of Gordium reads files the old way. Update
  Gordium (`git pull`) and restart Rhino. (Older versions needed `PYTHONUTF8=1` set before starting Rhino.)
- **Rhino closed unexpectedly**: please send
  1. the newest `Rhinoceros-….ips` in `~/Library/Logs/DiagnosticReports/`;
  2. `gordium_errors.log` and `gordium_worker.log` from your temporary folder (in Terminal: `open $TMPDIR`);
  3. what you were doing just before.

  Your model is in Rhino's autosave (File → Open Recent, or the recovered file Rhino offers on restart).
