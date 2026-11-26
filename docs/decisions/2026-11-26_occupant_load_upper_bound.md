# The most people a story can hold, when the rooms' functions aren't stated (2026-11-26)

**Purpose:** why Gordium can decide a rule such as "three exits from 501 to 1,000 occupants" from a story's floor area alone, the law that proves the number is a true ceiling, and the facts it needs stated first.\
**For:** whoever changes `design_checker/occupant_load.py` or the rules that read an occupant load; the architects, for what each fact means.\
**Kept current by:** the PR that changes the occupant load factors (Table 1004.5), the ceiling, or the facts it needs.

## The problem

The egress UI audit ([finding 6](../revit/egress_ui_audit.md)) found the four-unit apartment asked to set each room's function for 1006.2.1.1 (three exits from 501 to 1,000 occupants). A 1,800 sq ft story can't hold 501 people, whatever its rooms are used for, so the question was noise. Gordium works out a room's occupant load from its function (Table 1004.5). With no function, it had no number at all.

## What Gordium does now

Where a space's or story's occupant load isn't worked out, Gordium gives it a **ceiling**: the most it can possibly be.

    ceiling = (story's floor area) / 5, rounded up to a whole person

- **Floor area:** the larger of two figures: the story's gross floor area (inside its exterior walls, 202 FLOOR AREA, GROSS), or its spaces' areas added together (in case a room is drawn past the walls). Every space's area must be measured.
- **5 sq ft per person:** the densest factor in Table 1004.5 (see below).
- **Rounded up:** an occupant load is a number of people. A computed 49.5 is 50 people, so a rule asking "fewer than 50" is never passed on it.

The ceiling is **proven** only where the building states every fact it needs:
- no area whose occupant load Table 1004.5 counts by something other than its floor area (fixed seats in any use, bowling lanes, a concentrated business use, a mall);
- no outdoor areas the occupants use;
- no mezzanine.

The occupancy groups don't matter: no group is taken as proof of what is inside it (review round 2).

Where any of these isn't stated, the ceiling is only what stating them would prove. A row it would settle asks for those facts first, before the rooms' functions. Where the building states one of them the other way, there is no ceiling at all.

A rule is decided on the ceiling only where the checker can prove the rule gives the same answer for every load from none up to the ceiling (`rule_format/parts.py`, `under_bounds`). Each of its formulas must move only one way as the load grows (`formula.truth_direction`), and give the same truth at none and at the ceiling. A rule whose formula the proof can't follow (an `if ... else`, an `==`) is left as it was. So the story rule 1006.3.3 ("2 exits if 500 or fewer, else 3"), written as an if-else, is not decided this way yet.

**On the apartment:** no function stated, and the three facts stated no. The ceiling is 1,800 / 5 = 360, so each apartment's 1006.2.1.1 row complies. With the mezzanine fact left blank, the rows ask "Say whether the building has a mezzanine", and nothing else, before the rooms' functions.

## Why it is a true ceiling (the law)

All quotes are from the 2025 Building Code of New York State. Nothing below is Gordium's own reading: each step is the law's words or a fact the building states.

1. **No factor is denser than 5 sq ft per person.** 1004.5: "For areas without fixed seating, the occupant load shall be not less than that number determined by dividing the floor area under consideration by the occupant load factor assigned to the function of the space as set forth in Table 1004.5."
   - The densest row of Table 1004.5 is "Standing space 5 net" (p.312).
   - The next densest are "Concentrated (chairs only—not fixed) 7 net" and "Gaming floors (keno, slots, etc.) 11 gross".
   - A test reads every factor from the frozen table (`occupant_load_factors.yaml`, each checked against the page's second reading) and checks that the fewest is 5.
   - 1004.5 also says: "Where an intended function is not listed in Table 1004.5, the building official shall establish a function based on a listed function". So every function takes one of these factors.
2. **The increase can't go past 5.** 1004.5.1 lets a design take more occupants than the table gives, but only while "the occupant load does not exceed one occupant per 7 square feet". That is sparser than 5, so it never raises a load past area / 5.
3. **Fewer is allowed, never more.** The 1004.5 exception ("although less than those determined by calculation") only lowers a load.
4. **The four rows with no factor are kept out by one fact the building states**, `loads_not_by_area: false` (Gordium: Loads not by area), whatever its groups:
   - **Fixed seats.** 1004.6: "For areas having fixed seats and aisles, the occupant load shall be determined by the number of fixed seats installed therein", in any use, not only assembly.
   - **Bowling centers.** "allow 5 persons for each lane including 15 feet of runway": counted by the lane, not the area.
   - **Concentrated business use.** NY's own 1004.8: "the actual occupant load as approved, but not less than one occupant per 50 square feet". No most is printed. It can sit in a Group R-2 building too (508.5.2: "Live/work units shall be classified as a Group R-2 occupancy").
   - **Malls.** "See Section 402.8.2".
   - A room whose stated function is one of these, or isn't one of the table's, leaves its story with no ceiling.
5. **Rooms people walk through add nothing from outside the story.** 1004.2.1 adds the loads of rooms whose occupants "egress from one or more rooms, areas or spaces through others". Those rooms are on the same story, so the story's area covers them. 1004.2.3: "Other than for the egress components designed for convergence in accordance with Section 1005.6, the occupant load from separate stories shall not be added." 1005.6 is about "the capacity of the means of egress from the point of convergence" for stairways and ramps. It sizes those components and adds no other story's people to a room's count.
6. **Mezzanines.** 1004.2.2: "That portion of the occupant load of a mezzanine with required egress through a room, area or space on an adjacent level shall be added to the occupant load of that room". That could be a room on this story or the next one. So the ceiling needs `mezzanines: false` (Gordium: Mezzanines) and never counts a share instead (review round 1).
7. **Outdoor areas.** 1004.7: "Where outdoor areas are to be used by persons in addition to the occupants of the building, and the path of egress travel from the outdoor areas passes through the building, means of egress requirements for the building shall be based on the sum". So the ceiling needs `occupied_outdoor_areas: false`.

A walk test checks the ceiling on the apartment. In 60 cases, every room gets any function with a factor, rooms are passed through or not, and the increase is taken or not. No load ever comes out over 360.

## The new facts

- `building.mezzanines` (yes/no): the building has a mezzanine (505.2). In Revit: **Gordium: Mezzanines**, a Yes/No on Project Information.
- `building.loads_not_by_area` (yes/no): any area's occupant load is counted by its seats, lanes or actual load (the four rows above). In Revit: **Gordium: Loads not by area**, a Yes/No on Project Information.

The pane's answer cards need every fact they ask to have its mark, so both come with one.

## Open

The story rules written as if-else (1006.3.3, Table 1006.3.4) could use the ceiling too, once the proof can follow an if-else whose branches only grow.
