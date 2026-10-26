# PR #15 checked in Rhino at d9d56ae: pass 2, and the street pick's words

**Purpose:** what pass 2 and the street pick's messages showed in Rhino 8 (Mac) on 2026-10-26 (claim 10's "so far — Enter when done", and Esc's "this pick wasn't kept").\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `pass2_in_rhino.py` as written (`pass2_results.json`, `corner.json`) | **26 of 26** |
| The street pick's Esc, driven by script (`bend_question_in_rhino.py` from the a31661e record; `bend_results.json`) | Esc behaves as it should; see below |

**Claim 10's words:** a click keeps the whole street and says how far the pick has got: "Ithaca Rd: 8 lot-line
pieces, 75'-10" so far — Enter when done", then "Street 2: 2 lot-line pieces, 91'-10 3/8" so far — Enter when
done". The side street's far corner is asked about once.

**Esc at the bend question:** the command line says "Esc: nothing changed — the street side is as it was; this pick
wasn't kept", and the street lines are as before. (The script's third claim reads as failed only because it was
written for a31661e's wording, "Esc: nothing changed (the street side is as it was)"; the new words are the ones
asked for.) Enter asks again ("Gordium needs a Yes or a No here …"); No keeps the side street without the bend.
