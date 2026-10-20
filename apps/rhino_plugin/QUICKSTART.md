# Gordium in Rhino: from scratch

For an architect who has just opened Rhino. About 10 minutes the first time, then 1 minute per project.

Gordium checks your massing against the City of Ithaca zoning rules (R-1b, one-family houses, for now) while
you design. Every item is **✓ complies**, **✕ does not comply**, **? needs review** or **– not checked**. It
never says "complies" unless it is sure (see [What "needs review" means](#what-needs-review-means)).

## What you need (once)

1. **Rhino 8** (tested on a Mac; Windows should work but hasn't been tried).
2. **This repository** on your computer, with its Python environment. In Terminal, from the repository folder:

   ```
   python3.12 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

   Gordium's checking runs in this `.venv` Python, in the background; Rhino only draws what it says. No AI
   runs while you design.

## Install in Rhino (once)

1. Open Rhino.
2. Type this in Rhino's command line, with your repository's folder in place of `<repo>`, and press Enter:

   ```
   _-RunPythonScript "<repo>/apps/rhino_plugin/install.py"
   ```

   Or: **ScriptEditor** → open `apps/rhino_plugin/install.py` → **Run**.
3. The command line says `Gordium: GordiumStart -> gordium_start.py`, and the same for `GordiumCheck`,
   `GordiumLive`, `GordiumFacts` and `GordiumOff`. These are now Rhino commands, kept between sessions.

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
   - **Ground**: "flat at the lot level · as drawn", or your spot grades or terrain. **Place spot grades…**,
     **Pick terrain…**, or **I'll regrade: set finished ground…**.
   - **No regrading near the house**: tick it if the ground shown is the finished ground. Then height is checked.
     Unticked, height and stories need review, because the code measures height from *finished* grade.
   - An amber line appears when the box can't decide something itself, with what to do (for example "This lot
     faces two streets: pick the front").

   Any button that picks something closes the box, lets you pick in the model, and opens it again.
4. **Draw.** You see:
   - the lot's property line with each edge's length (in Top view);
   - the buildable envelope, see-through blue: the space every yard and the height limit leave;
   - the largest legal starting building: three floor blocks (11'-8" floor to floor), one group, on the
     `Gordium::Massing` layer. **Hide starting house** in the panel hides it (it is still checked);
   - top right, the **status box**: one line such as "? 6 need review · 4 comply · 2 not checked";
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
7. **Zoning report…** writes `<your model>_gordium_report.xlsx` next to the model (in Documents if the model
   isn't saved yet), with the same statuses as the panel.

## The other commands

| Command | What it does |
|---|---|
| `GordiumCheck` | Check the model now: your own design, or (on an empty file) the start flow. Writes the report. |
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

## Troubleshooting

- **"no .venv found above …"**: the repository's Python environment is missing. Run the two Terminal lines in
  [What you need](#what-you-need-once) from the repository folder, then the command again.
- **Nothing happens / the commands aren't found**: run the install step again. If the ScriptEditor hasn't been
  opened in this Rhino session, open it once (Tools → ScriptEditor). That starts Rhino's Python.
- **I can't see the panel**: it is a floating window and may be behind Rhino or on another desktop (Mission
  Control). Run `GordiumCheck` again to bring it back.
- **"Gordium: ⚠ couldn't … (it was skipped; details in …gordium_errors.log)"**: one drawing or panel step failed
  and was skipped; the check itself is unaffected. Please send that log file.
- **Rhino closed unexpectedly**: please send
  1. the newest `Rhinoceros-….ips` in `~/Library/Logs/DiagnosticReports/`;
  2. `gordium_errors.log` and `gordium_worker.log` from your temporary folder (in Terminal: `open $TMPDIR`);
  3. what you were doing just before.

  Your model is in Rhino's autosave (File → Open Recent, or the recovered file Rhino offers on restart).
