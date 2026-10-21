# Gordium in Rhino: from scratch

For an architect who has just opened Rhino. About 10 minutes the first time, then 1 minute per project.

Gordium checks your massing against the City of Ithaca zoning rules (R-1b, one-family houses, for now) while
you design. Every item is **✓ complies**, **✕ does not comply**, **? needs review** or **– not checked**. It
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
5. Rhino's command line shows five lines:

   ```
   Gordium: GordiumStart -> gordium_start.py
   Gordium: GordiumCheck -> gordium_check.py
   Gordium: GordiumLive -> gordium_live.py
   Gordium: GordiumFacts -> gordium_facts.py
   Gordium: GordiumOff -> gordium_off.py
   ```

   These five are now Rhino commands, kept between sessions. You can close the ScriptEditor.

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
   **File name** box, press Enter, then click **Run** (▶). Rhino's command line shows the same five
   `Gordium: …` lines as [on the Mac](#install-in-rhino-once). As on the Mac, open the ScriptEditor once in every
   Rhino session before using Gordium.
8. **Getting updates:** in PowerShell,

   ```
   cd $HOME\Documents\gordium; git pull
   ```

   then **close Rhino completely (File → Exit) and open it again**: Rhino keeps the old Gordium loaded until it
   is closed. If Gordium says a module is missing, run step 6's last line again from the gordium folder.

## Your first project, step by step

1. **New file.** File → New, a template in **feet** (any units work; feet is easiest to read).
2. **Type `GordiumStart`** and press Enter.
   - On an empty file Gordium draws its sample lot (106 Ithaca Rd, 73 ft × 90 ft) so you can try it at once.
   - To use your own lot instead, first draw it as one closed polyline on a layer named `Site`, then run
     `GordiumStart`.
3. **The start box** opens, filled in from the lot as drawn. Read it top to bottom:
   - **Address**: recorded on the project and the report. (Look up from the City's map is coming soon.)
   - **Zoning district**: R-1b, "entered by you". Tick **I confirm**: Draw stays off until you do, on every new
     project, because Gordium doesn't look up the zoning map yet.
   - **Use**: one-family dwelling, detached.
   - **Lot**: its area and where it came from: "6,570 sf · from the tax map (±2 ft, approximate)". Gordium treats
     tax-map lines as uncertain by 2 ft: anything that only holds if they're exact needs review. **Use my
     survey…** to pick your surveyed outline instead.
   - **Street side**: the lot line on the street (highlighted). **Change…** to pick another. **Corner lot?**: answer
     it (one street or two). Gordium never guesses: until you answer, the yards need review.
   - **Ground**: for now Gordium assumes the ground is **flat at the lot level and finished** (no regrading), so
     height and stories are checked; their rows say "assuming flat ground", and so does the report. (Spot grades,
     terrain and regrading come back in a later release.)
   - An amber line appears when the box can't decide something itself, with what to do (for example "This lot
     faces two streets: pick the front").

   Any button that picks something closes the box, lets you pick in the model, and opens it again.
4. **Draw.** You see:
   - the lot's property line with each edge's length (in Top view);
   - the buildable envelope, see-through blue: the space every yard and the height limit leave;
   - the largest legal starting building: three floor blocks (11'-8" floor to floor), one group, on the
     `Gordium::Massing` layer. **Hide starting house** in the panel hides it (it is still checked). On a
     lot from the tax map it keeps 2'-0" back from every limit, so it complies even if the tax map is 2 ft off;
     on a survey it goes to the limits;
   - with **Show on-screen labels** ticked in the panel (off at first): each yard's and lot edge's label, and the
     status box top right ("? 2 need review · 8 comply · 2 not checked"). Off, a failing yard's shortfall still
     shows ("✕ Rear yard 21'-2", needs 22'-6"");
   - the **Gordium panel** (a floating window): every item, bad news first.
5. **Make an edit.** Move, stretch or add solids as you normally would. Half a second after you stop, Gordium
   re-checks:
   - when something newly stops complying, a short note appears bottom left ("✕ Rear yard no longer complies ·
     29'-6" proposed · 30'-0" required · −0'-6""). It goes by itself;
   - only the part of the building inside a required yard, or above the height limit, turns red. The rest stays
     neutral;
   - in Top view each yard is drawn as measured, marked ✓ ? or ✕.
6. **Read the panel.** Click any row. The bottom half shows the city's exact words, the examiner-style citation
   ("§325-8, District Regulations Chart, R-1b, Rear yard column, note 16") with links to the page, how it was
   measured and worked out, and what to change ("To comply: move the building 0'-6" farther from that lot
   line."). **Zoom to** (or a double-click) frames the item: yards in Top, height in a front elevation.
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
| `GordiumLive` | Turn live re-checking after each edit on or off. |
| `GordiumFacts` | Open the start box again to change the site facts (the panel's **Edit site…** does the same). |
| `GordiumOff` | Stop Gordium and clear its drawing. Nothing in your model is changed. |

Gordium never changes your model, except for what you ask: the starting building and the sample lot. Everything
else (the envelope, the red, the labels, the status box) is drawn on top and disappears with `GordiumOff`.

## What "needs review" means

"? needs review" means **Gordium can't be sure, so it won't say it complies**. The row's reason says why, and
usually what fixes it:

- **The lot lines are from the tax map** and the item is within 2'-0" of its limit: "at worst 23'-0" against
  25'-0" · Pick survey lot lines…".
- **The grade isn't set**, or the spot grades aren't at the building's walls any more (after you move it):
  height and stories wait for it.
- **The code leaves a question open** (for example whether an upper-floor overhang counts in a side yard). Gordium
  works the design out under every reading. If it complies under all of them it says so, but it still needs
  review, because only the zoning office can settle the question.
- **Something on the lot isn't measured**: a solid not on the `Building` layer (a shed on Default, an imported
  garage). Lot coverage counts every building on the lot, so it needs review until you **Add to check…**.

"– not checked" means Gordium doesn't check it yet (parking needs bedroom and parking counts; overlays come in a
later release). "Not covered by this rulebook" lists code sections still to be checked by hand.

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

### The starting house on the sample lot

The sample lot is 106 Ithaca Rd: 73'-0" × 90'-0", from the tax map. The starting house is 49'-0" wide and
31'-10" deep, 35'-0" tall, in three floors of 11'-8".

It keeps 2'-0" back from every limit because the lot lines are from the tax map, so it complies even if the
tax map is 2 ft off:
- front yard 27'-0" (needs 25'-0");
- side yards 12'-0" (need 10'-0");
- rear yard 31'-2" (needs 22'-6");
- coverage 23.8% (the limit is 25%).

Building height 35'-0" and Stories 3 comply, at the limit, each saying "assuming flat ground".

### Simple tests

1. **Tick Show on-screen labels** in the panel: each yard's label and the status box appear in Top view. Untick it:
   they go (the yard lines stay).
2. **Move the house 5 ft back (away from the street).** Front yard 32'-0", rear yard 26'-2": both comply.
3. **Move it 10 ft back instead.** Rear yard 21'-2" against 22'-6" required: **does not comply, −1'-4"**.
   A note appears bottom left, and only the strip of the house inside the rear yard turns red.
4. **Undo, then pull the rear wall 6 ft back** (Cmd+Shift+click the rear face, Gumball 6). Lot coverage 28.3%
   against 25%: **does not comply**, with "reduce the footprint by at least …".
5. **Undo, then raise the roof 3 ft** (the top face of Floor 3). Building height 38'-0": **does not comply either
   way**. Over 35'-0", and the height bonus (§325-16C) would need every yard 3 ft larger: "Front yard 27'-0",
   needs ≥ 28'-0"". Only the part above 35'-0" turns red.
6. **Undo, then widen the house 4 ft to the east** (the east face). Side yard, East 8'-0": **does not comply,
   −2'-0"**, and lot coverage 25.7% also doesn't: one note, "2 items no longer comply".
7. **Undo.** Everything is back to the starting results.

### Harder tests

8. **A garage: `Box` 12 × 20 × 10 ft on the Default layer**, behind the house. "Objects on the lot not included"
   and Lot coverage need review: coverage counts every building on the lot. **Add to check…** puts it on the
   Building layer, and it is measured.
9. **Move one floor on its own** (Floor 2, 3 ft east). Stories needs review: "floors misaligned".
10. **The height bonus, done right:** raise the roof 3 ft (38'-0"), move the house 3 ft back, and pull each side
    wall 3 ft in. Every yard is then 3 ft larger, plus the 2 ft the tax map needs. Building height complies
    against 38'-6"; the Front yard row shows 28'-0" required, +2'-0".
11. **Delta in words:** after test 2 the Front yard row reads "+7'-0" to spare"; after test 3 the Rear yard row
    reads "−1'-4" short" (the same in the report).
12. **Corner lot:** Edit site… → Corner lot? Yes: two streets. The yards need review (which yard is the front is
    an open question for a corner lot).
13. **A survey:** with a surveyed lot, a new starting house goes exactly to the limits: 53'-0" × 30'-11", with
    side yards at 10'-0", at limit, complying.
14. **Other units:** start in a Millimeters, Meters or Inches template. The results are the same: Gordium works
    in feet and converts at Rhino's edge.

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
