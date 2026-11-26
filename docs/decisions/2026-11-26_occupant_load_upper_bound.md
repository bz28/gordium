# The most people a story can hold, when the rooms' functions aren't stated (2026-11-26)

**Purpose:** why Gordium can decide a rule such as "three exits from 501 to 1,000 occupants" from a story's floor area alone, the law that proves the number is a true ceiling, and the facts it needs stated first.\
**For:** whoever changes `design_checker/occupant_load.py` or the rules that read an occupant load; the architects, for the readings marked below.\
**Kept current by:** the PR that changes the occupant load factors (Table 1004.5), the ceiling, or the facts it needs.

## The problem

The egress UI audit ([finding 6](../revit/egress_ui_audit.md)) found the four-unit apartment asked to set each room's function for 1006.2.1.1 (three exits from 501 to 1,000 occupants). A 1,800 sq ft story can't hold 501 people, whatever its rooms are used for, so the question was noise. Gordium works out a room's occupant load from its function (Table 1004.5); with no function it had no number at all.

## What Gordium does now

Where a space's or story's occupant load isn't worked out, Gordium gives it a **ceiling**: the most it can possibly be.

    ceiling = (story's floor area) x (1 + mezzanine share) / 5, rounded up to a whole person

- **Floor area:** the larger of the story's gross floor area (inside its exterior walls, 202 FLOOR AREA, GROSS) and its spaces' areas added together (in case a room is drawn past the walls). Every space's area must be measured.
- **5 sq ft per person:** the densest factor in Table 1004.5 (below).
- **Mezzanine share:** 0 where the building states it has no mezzanine; otherwise the most 505.2.1 allows (below).
- **Rounded up:** an occupant load is a number of people. A computed 49.5 is 50 people, so a rule asking "fewer than 50" is never passed on it.

A rule is decided on the ceiling only where the checker can prove the rule gives the same answer for every load from none up to the ceiling (`rule_format/parts.py`, `under_bounds`): each of its formulas must move only one way as the load grows (`formula.truth_direction`), and give the same truth at none and at the ceiling. A rule whose formula the proof can't follow (an `if ... else`, an `==`) is left as it was. Example: "2 exits if 500 or fewer, else 3" is written as an if-else, so the story rule 1006.3.3 is not decided this way yet.

On the apartment (no function stated, Group R-2, no fixed assembly seating, no outdoor areas the occupants use): with no sprinkler system the ceiling is 1,800 x 4/3 / 5 = 480, so each apartment's 1006.2.1.1 row complies. With an NFPA 13R system a mezzanine could be half the room (505.2.1 exception 3): 1,800 x 1.5 / 5 = 540, over 500. Then Gordium asks the one fact that would settle it ("Say whether the building has a mezzanine"), before the rooms' functions. Stated "no", the ceiling is 360 and the row complies.

## Why it is a true ceiling (the law)

All quotes are from the 2025 Building Code of New York State.

1. **No factor is denser than 5 sq ft per person.** 1004.5: "For areas without fixed seating, the occupant load shall be not less than that number determined by dividing the floor area under consideration by the occupant load factor assigned to the function of the space as set forth in Table 1004.5." The densest row of Table 1004.5 is "Standing space 5 net" (p.312). The next densest are "Concentrated (chairs only—not fixed) 7 net" and "Gaming floors (keno, slots, etc.) 11 gross". A test reads every factor from the frozen table (`occupant_load_factors.yaml`, each checked against the page's second reading) and checks the fewest is 5. "Where an intended function is not listed in Table 1004.5, the building official shall establish a function based on a listed function" (1004.5), so every function takes one of these factors.
2. **The increase can't pass it.** 1004.5.1 lets a design take more occupants than the table gives, but only so long as "the occupant load does not exceed one occupant per 7 square feet". That is sparser than 5, so it never raises a load past area / 5.
3. **Fewer is allowed, never more.** The 1004.5 exception ("although less than those determined by calculation") only lowers a load.
4. **The four functions with no factor are kept out:**
   - Fixed seats (1004.6: "the occupant load shall be determined by the number of fixed seats installed"; benches at "one person for each 18 inches"). Seats can be packed tighter than 5 sq ft each, so the ceiling needs the building to state no fixed assembly seating (`assembly_fixed_seating: false`), and no Group A.
   - Bowling centers ("allow 5 persons for each lane including 15 feet of runway"): counted by the lane, not the area, so no Group A. *Gordium's reading:* a bowling space kept as part of another occupancy (303.1.2: under 750 sq ft) can't beat 5 sq ft each either: 5 people on 15 ft of a lane about 3.5 ft wide is about 10 sq ft each.
   - Concentrated business use (NY's own 1004.8: "the actual occupant load as approved, but not less than one occupant per 50 square feet"): no most is printed, so no Group B.
   - Malls ("See Section 402.8.2"): no Group M.
   - A room whose stated function is one of these, or isn't one of the table's, leaves its story with no ceiling.
5. **Rooms people walk through add nothing outside the story.** 1004.2.1 adds the loads of rooms whose occupants "egress from one or more rooms, areas or spaces through others". Those rooms are on the same story, so the story's area covers them. 1004.2.3: "Other than for the egress components designed for convergence in accordance with Section 1005.6, the occupant load from separate stories shall not be added." *Gordium's reading:* 1005.6 sets only the capacity (width) of stairs and the means of egress where flows from above and below meet ("the capacity of the means of egress from the point of convergence"); it adds no other story's people to a room's own count for 1006.2.
6. **Mezzanines add their own people.** 1004.2.2: "That portion of the occupant load of a mezzanine with required egress through a room, area or space on an adjacent level shall be added to the occupant load of that room". 505.2 counts a mezzanine as "a portion of the story below", and its floor isn't in the story's floor area. 505.2.1 caps it: "not greater than one-third of the floor area of that room or space in which they are located", one-half with an NFPA 13 system and Type I or II construction (exception 2) or within a dwelling unit with NFPA 13 or 13R (exception 3), two-thirds for a special industrial occupancy (exception 1). Gordium doesn't know the construction type, so it takes the largest share the stated facts allow: 2/3 if any group is F, H or S (or groups aren't stated), 1/2 with NFPA 13 or 13R (or no sprinkler system stated), else 1/3. A level bigger than this isn't a mezzanine. It is a story, and 1004.2.3 adds nothing from it.
7. **Outdoor areas can add people.** 1004.7: "Where outdoor areas are to be used by persons in addition to the occupants of the building, and the path of egress travel from the outdoor areas passes through the building, means of egress requirements for the building shall be based on the sum". So the ceiling needs `occupied_outdoor_areas: false`.

A walk test checks the ceiling on the apartment: for 60 cases of a function (any with a factor) on every room, rooms passed through or not, the increase taken or not, no load comes out over 360.

## The new fact

`building.mezzanines` (yes/no): the building has a mezzanine (505.2). Revit has no mark for it yet. It is on the Revit-fields queue as **Gordium: Mezzanines** (Project Information, Yes/No).

## Open

- The two readings above (bowling inside another occupancy; convergence adds no people to a room's count) are Gordium's, for the architects to confirm.
- The story rules written as if-else (1006.3.3, Table 1006.3.4) could use the ceiling too, once the proof can follow an if-else whose branches only grow.
