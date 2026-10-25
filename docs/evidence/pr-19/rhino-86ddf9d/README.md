# #19 start-box-lookup at 86ddf9d: checked in Rhino 8 (Mac), 2026-10-25 (RHINO_QUEUE 10)

**Purpose:** what the Rhino job's runs of item 10 showed.\
**For:** the coordinator, reviewers.\
**Kept current by:** never changed (a dated record).

| Part | Result |
|---|---|
| `pass2_in_rhino.py`, claim 6 (its box step, at this head): the empty file's start box says "no lot yet: draw it, or pick a closed outline on the Site layer", with no Use my survey… or Change… until a lot exists; claim 11's wording as well (`claim6_results.json`, `6_box_no_lot.png`) | **3 of 3** |
| The R-2a box, the real start box driven through its own controls (`r2a/`) | **9 of 9** |

The R-2a box runs used the lookup's recorded answers for 106 Ithaca Rd, with the City map's zone set in the answer
for each case:
- **R-2a** (`r2a_single.json`, screenshots 1–4): no district preselected, and the row reads "not set". The amber line
  reads "The City map says R-2a; Gordium doesn't have R-2a's rules yet: pick a district only if you know it
  applies." Draw is off, with "Pick the district to continue." Picking R-1b makes the source "entered by you" at
  once. Ticking "This is the lot's district" turns Draw on with an empty reason line. After Draw and reopen:
  R-1b, still "entered by you".
- **Two zones, R-2a and R-1b** (`r2a_two.json`, screenshot 5): nothing preselected, and the doubt is said once (on the
  district row only).
- **R-1b found** (`r2a_suggested.json`, screenshots 6–7): "suggested by Gordium · City zoning map says R-1b (checked
  <date>)". The Street side reads "Ithaca Road" before Draw and still "Ithaca Road" after Draw and reopen.

The first R-2a command of the day was stopped before it started (nothing hung in Rhino). The driver also looked for
the district tick by its old words ("I confirm"); this head says "This is the lot's district". Both were fixed in
the driver, which accepts either wording, and every wait is time-limited.
