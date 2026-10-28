# Gordium in Rhino: the user guide

**Purpose:** what an architect sees and does in Rhino, in plain words, as the screens are on the `rhino-ui` branch.\
**For:** architects using Gordium.\
**Kept current by:** any PR that changes what an architect sees updates this guide in the same PR. A test
(`packages/design_checker/tests/test_guide.py`) fails when a button, tick box, command or prompt in the code is
missing here, or named here but gone from the code. The set-up steps are in [QUICKSTART.md](QUICKSTART.md).

Gordium checks your massing against the City of Ithaca zoning rules while you design (residential districts, one
lot at a time). Every item gets one answer: **Complies**, **Does not comply**, **Needs review** or **Not
checked**. It never says "Complies" when it is not sure: a missing fact or an unclear rule gives "Needs review".

## The commands

Type a command's name in Rhino's command line.

| Command | What it does |
|---|---|
| `GordiumStart` | Starts a new project: the start box (below), then draws the lot and the largest legal house. |
| `GordiumCheck` | Checks the model now, shows the result in the panel and writes the zoning report. On an empty model it does what `GordiumStart` does; if facts are missing it opens the start box first. It also turns live checking on. |
| `GordiumLive` | Turns live checking on or off. On, every edit is re-checked by itself. |
| `GordiumFacts` | Opens the start box (the same as **Edit site…**) on the project's facts, to correct them, then checks again. |
| `GordiumOff` | Turns Gordium off for this Rhino session: live checking stops, its hooks are removed, the panel closes and its overlay is cleared. Your model is untouched. |
| `GordiumPanel` | Only makes the panel available to Rhino (it does not show it). `GordiumStart` and `GordiumCheck` show it, docked beside the viewports; Rhino's own Panels menu also lists it. |

## 1. Start a project

1. Open an empty Rhino file (any unit; Gordium converts) and type `GordiumStart`. The **start box** opens empty: the
   lot rows say `Look up an address to fill these in`, and **Draw** stays off with
   `Look up the address first. It finds the lot, zoning district and neighbourhood.`
   To try Gordium, look up 106 Ithaca Rd. With no lookup possible (a lot the maps don't know), press
   **Enter the site by hand…**: you draw the lot, pick the district and the street side, all "entered by you";
   no neighbourhood is drawn (only a lookup finds one).
2. Read each row:
   - **Address**: the project's address. **Look up** asks the City's and the State's maps about that address and fills in what they give (the lot, its district); each row says where its answer came from.
   - **Zoning district**: the district and where it came from ("entered by you"); **Change** picks another. Tick **This is the lot's
     district** to confirm it. Nothing is drawn until you do: a district nobody confirmed is never trusted.
   - **Use**: the kind of building (one-family dwelling, detached, for now). **Change** picks another.
   - **Lot**: the lot's area and where it came from. **Use my survey…** replaces the tax-map lot with your own
     surveyed lot lines (tax-map lines can be about 2 ft off; Gordium says so and keeps its answers safe).
     In a new file, after **Look up** finds an address, this row and the street row below show the *found* lot's
     area and street marked `· after Draw` (nothing is drawn until you press Draw; a failed or new lookup never
     leaves another address's numbers behind). Once a lot is drawn, they describe the drawing.
   - **Front lot line (on the street)**: which lot line is on the street; Gordium measures the front yard from it.
     **Change…** lets you click it. **Corner lot?** is never guessed: **Not answered**, **No: one street** or
     **Yes: two streets**.
   Until the district is ticked the box says `Confirm the district to continue.` and **Draw** stays off.
3. Press **Draw**. Gordium draws the lot, the **buildable envelope** (the see-through blue volume where a building
   complies), and the largest legal house, the **starting house**, one block per floor. Then it checks it.

`GordiumStart` begins from a model with no building in it (an empty file, or a lot you drew with no building yet: it
uses that lot's facts). If the model already has a building, Gordium says (in a message and on the command line)
`This model already has a building. To start over on another address, use Edit site… in the Gordium panel: Look up the new address and press Draw (the lot and starting house are drawn again for it). To check the building you have, use GordiumCheck.`
From **Edit site…** (and `GordiumFacts`) the same box opens with its last button reading **Check** instead of **Draw**: it re-checks with the changed facts; a new address looked up there is drawn clean (Gordium asks once before removing anything you drew).
**Cancel** closes the box without drawing anything new; the command line says nothing was started.

## 2. The panel

The panel lists every item, worst news first, each with what your design has, what the rule requires, and the
margin. The groups are Does not comply, Needs review, Complies, Not checked and "Not checked yet" (rules Gordium
does not cover yet: check those by hand). **Complies** and "Not checked yet" start folded. Click a row to see it;
press **Zoom to** to look at the part of the model it is about: it selects those objects and switches to the Top
view (the Front view for height and stories). It is off when nothing is selected or the results are out of date,
and says so when nothing is drawn to zoom to.

Buttons along the panel:

- **Edit site…**: reopen the start box to change the facts.
- **Pick survey lot lines…**: choose your surveyed lot lines in the model. Shown while the lot is the tax map's.
- **Main building…** and **Pick the main building…**: when the file holds several buildings, say which one is the
  house being checked. **Main building…** is in the header only then.
- **Add to check…** and **This is the ground**: on the row for an object Gordium left out, to include it or to say
  it is the ground. **Not the ground** is in the Site facts, when nothing is selected, if Gordium took an object
  for the ground because you marked it.
- **Zoning report…**: writes the report in the architects' spreadsheet format, opens it and says where it saved it.
- **?**: the legend (what the marks and colours mean, and which version of the law was checked).
- **Retry**: shown only when a check failed, to try it again.

Tick boxes:

- **Hide starting house**: hides the starting house's layers. Hidden, it is still checked.
- **Show on-screen labels**: labels each yard and lot edge in the model, off by default.
- **Show buildable envelope**: shows or hides the blue envelope.

In the model, **red** is the part of the building that does not comply; **amber** is the part a rule that needs
review is about. A small notice names a rule an edit has just broken ("Rear yard no longer complies").

## 3. Edit and watch

Move a wall, raise the roof, add a garage: the panel and the colours update by themselves: live checking is on after `GordiumStart` and `GordiumCheck`
(`GordiumLive` turns it off and on again). Undo puts the model back (Rhino's own Undo) and Gordium re-checks it.

## What Gordium asks you in the command line

Questions come in the command line (the line at the top or bottom of Rhino). What **Esc** does is said where it
differs.

Picking the street side (**Change…** on the start box). On a one-street lot, Esc or Enter leaves it as it was:

- `Click the lot line on the street` on a one-street lot; on a corner lot,
  `Click each lot line on a street (`, then how many are picked, then `); Enter when done`. Click any piece:
  Gordium takes the whole street it is on. On a corner lot, Enter keeps the lines clicked; Esc changes nothing.
- `Which street is this lot line on? (Enter leaves it unnamed)`: Esc here changes nothing (the line you clicked isn't kept).
- When Gordium cannot tell whether the lot line bends along one street or turns a corner it asks a **Yes** or
  **No** question. It needs a real answer: Enter asks again, with
  `Gordium needs a Yes or a No here (Esc: nothing changes)`, because a guess could pass a lot that does not comply.

Picking other things:

- `Click the surveyed lot outline (Site layer); Enter keeps the one outlined` (**Pick survey lot lines…**)
- `Click your surveyed lot outline (a closed curve on the Site layer); Enter keeps it` (**Use my survey…**)
- `Click the main building (a solid on the Building layer), or choose one; Enter keeps it`

The next two are asked only when the **Ground** row is on (see "Not shown in this version"):

- `Click the terrain surface or mesh`
- `Click a spot grade at a wall (Enter when done)` and
  `Click the finished ground you'll grade to, at each wall (Enter when done)`

A row's **Enter** button (for example "Enter bedrooms and parking spaces") asks the facts that row waits for, one
at a time: `Bedrooms`, `Off-street parking spaces`, `Dwelling units`, `Rooms let for profit`, `Stories of the whole building`, and
`Made by converting an existing building, not new construction? (§325-3B)`. Each ends with `(Enter to skip)`:
skipping leaves the fact unset, so its rule keeps waiting (never 0 or No).

## Not shown in this version

Two parts of the start box exist in the code but are switched off while the ground is assumed flat: the **Ground**
row (**Place spot grades…**, **Pick terrain…**, **I'll regrade: set finished ground…**, and the tick **No
regrading near the house**) and the **Advanced** section with **Design buffer**. The panel's **Set grade…** button (tell Gordium the ground level) is switched off with it. They will be described
here when they come back.

## What "Needs review" means

Gordium found a fact it could not prove: a tax-map line that might be 2 ft off, ground it has to assume flat, a
rule it reads two ways. The row says what it needs. Where it waits for facts you can state (bedrooms, parking...), it has an **Enter** button
for them; otherwise its hint says what to do (for example **Pick survey lot lines…** in the header). Check those
by hand until then.
