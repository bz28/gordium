# envelope_builder

The largest building the rules allow on a lot: the lot shrunk by every required yard, up to the height limit.
Plain code reading the zone's rules; no AI.

- **Where the numbers come from:** each rule that applies is read for the limits a building must meet
  everywhere: every part of an `and`; for an `or`, the first alternative whose limits can all be read and whose
  other conditions are known true for this lot. A limit is `<yard> >= <limit>` or `building_height <= <limit>`
  (either way round), where the limit depends only on the lot (area, width, depth), never on the design. The
  R-1b rear yard `max(min(0.25 × lot_depth, 50), 20)` counts; the height bonus's yards grow with the design's
  height, so that alternative isn't readable and the plain 35 ft limit stands.
- **Cautious everywhere:** each lot line is pushed in by the largest yard it could need under every reading of
  the lot (a jog as a side or a rear line, each reading of the lot depth); the height is the lowest limit. Rounded
  corners are drawn 0.001 ft further in than needed, so no point of the envelope is ever inside a required yard.
- **Not drawn, with a note saying why:** a corner lot (its yards are an open question), no corner-lot answer, no
  street side, ground not confirmed flat (the height is measured from the ground), a yard, height or area limit
  written in a form it can't read (two yards added together, a yard that depends on the height), or a limit
  that can't be worked out for this lot.
- **Not a shape:** lot coverage comes back as numbers: allowed, have, and how far over; none until the lot
  area is known (a surveyed lot).

Tested by `tests/test_envelope.py`: the 106 Ithaca Rd lot gives front 25, sides 10, rear 22.5 and 35 ft; no point
is inside a yard (a jog, an inside corner); rules that don't apply and flags add nothing; the envelope doesn't
change with the design.

## The starting building (`start.py`, GordiumStart)

`largest_legal_building(site, facts, measured, rules)`: the building an architect starts designing from, as
**stacked floor blocks, one per story**.

- **Footprint:** a rectangle square to the street, set right at the front yard line, as wide as the side yards
  allow, then as deep as the lot-coverage limit and the rear yard allow (inside the envelope above). So growing it
  on any side breaks a rule: the front yard, a side yard, or in depth the coverage limit or the rear yard.
- **Unequal side yards** (R-2b: `side_yard_smaller >= 5 and side_yard_larger >= 10`): the envelope keeps the larger
  yard on both sides (`side_split` says the two minimums), but the starting house takes it on one side only: both
  ways are tried and the larger house wins; a tie goes to the left as seen from the street (on a corner lot it will
  be the side away from the side street, once corner lots get an envelope: today they get none). A side yard rule
  with two ways to comply (an `or`) is never split. `larger_side="left"|"right"` asks for a side (Switch side yards in Rhino). Each
  is proven like any other house; one that would break a rule is never returned (then the larger yard on both
  sides). On the 35 ft lot: 35 − 10 − 5 = 20 ft wide, not 15.
- **Height and stories:** up to the height limit, split into the story limit (`stories <= N`) evenly; the top
  floor's top sits exactly on the limit.
- **Every number from the rules,** never typed in the code: another zone's rules give that zone's building.
- **A lot not yet surveyed:** coverage is sized from the lot as drawn, and a note says so; the check still says
  NEEDS REVIEW for coverage until the survey is confirmed.
- **Can't be drawn** (no buildable area, no height limit or ground level): no floors, and the notes say why.
- **Proven before it is returned, on any lot shape:** the building found is measured and checked with the
  checker's own rules (`measure`, then `outcome`). If it would break any rule the lot itself doesn't already
  break, nothing is placed and the note says "Gordium can't generate a starting building on this lot shape yet;
  draw one and Gordium will check it". Plain four-sided lots (the R-1b kind) always get one; a flag lot or a
  narrow neck, where the side yards close the frontage, gets the note. Never a wrong building.

Tested by `tests/test_start.py`: on a rectangle, a tilted lot, a wide lot, a jogged lot and 106 Ithaca Rd, the
building passes every outside rule of the real R-1b rulebook; growing any side by 1 ft makes a rule fail; its
floor blocks measure as 3 stories and 35 ft; numbers changed in a copy of the rules change the building. Over 60 random lot shapes (convex or not), every building
placed breaks no rule; a search forced to return a rectangle too deep is refused; doubling a lot's depth at
most about doubles the search (counted, not timed).
