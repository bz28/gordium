# envelope_builder

The largest building the rules allow on a lot: the lot shrunk by every required yard, up to the height limit.
Plain code reading the zone's rules; no AI.

- **Where the numbers come from:** every comparison in a rule that applies, `<yard> >= <limit>` or
  `building_height <= <limit>`, whose limit depends only on the lot (area, width, depth), never on the design.
  The R-1b rear yard `max(min(0.25 × lot_depth, 50), 20)` counts; the height bonus's yards (which grow with the
  design's height) don't, so the plain 35 ft limit stands.
- **Cautious everywhere:** each lot line is pushed in by the largest yard it could need under every reading of
  the lot (a jog as a side or a rear line, each reading of the lot depth); the height is the lowest limit. Rounded
  corners are drawn 0.001 ft further in than needed, so no point of the envelope is ever inside a required yard.
- **Not drawn, with a note saying why:** a corner lot (its yards are an open question), no corner-lot answer, no
  street side, or a limit that can't be worked out for this lot.
- **Not a shape:** lot coverage comes back as numbers: allowed, have, and how far over.

Tested by `tests/test_envelope.py`: the 106 Ithaca Rd lot gives front 25, sides 10, rear 22.5 and 35 ft; no point
is inside a yard (a jog, an inside corner); rules that don't apply and flags add nothing; the envelope doesn't
change with the design.
