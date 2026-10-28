# PR #15 checked in Rhino at a31661e: the bend question needs a Yes or a No

**Purpose:** what the street side's bend question did in Rhino 8 (Mac) on 2026-10-26 (RHINO_QUEUE 15), driven by script, and pass 2 in full at this head.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## The bend question (`bend_question_in_rhino.py`, `bend_results.json`): 4 of 4

The sample, Corner lot? Yes, the street side picked again (Change…): one Ithaca Rd piece clicked, then the side
street. The plugin's own question about the side street's far corner was answered through a stand-in for Rhino's
GetOption prompt (the answers scripted in the plugin's own input call; nothing typed into Rhino, no interactive
command):

| Step | Result |
|---|---|
| Asked: "Past there the lot line turns 89° over short pieces, a corner or a bend (2 more lot-line pieces, 69'-9"). Is that on Street 2 too? (Yes or No)" | pass |
| Enter: asked again, starting "Gordium needs a Yes or a No here (Esc: nothing changes): kept as street, a line that isn't can pass lot width; left out, a line that is can pass the front yard. …" | pass |
| Esc: the command line says "Esc: nothing changed (the street side is as it was)"; the street lines as before (8, Ithaca Rd) | pass (`A_after_esc_street_as_before.png`: the blue line along Ithaca Rd only) |
| The same picks again, No: "Street 2: 2 lot-line pieces, 91'-10 3/8" of frontage"; 10 lines kept, the bend left out | pass (`B_after_no.png`: blue along Ithaca Rd and up the side street to its corner, nothing along the rear) |

One wording point: in the Esc run the command line first says "Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage"
(the first click), then "Esc: nothing changed (the street side is as it was)". It reads as if something were kept,
then nothing.

What is left for a person: the same steps with the real keyboard (Enter and Esc at Rhino's own prompt). The script
replaced only the source of the answers, the plugin's GetOption, not what the plugin does with them.

## Pass 2 at a31661e (`pass2_results.json`): 26 of 26

Every step, including the corner step (claims 10 and 12) and the empty file's box (claim 6).
