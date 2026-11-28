# Revit marks for the building facts New York's egress rules ask: the plan (2026-11-28)

**Purpose:** which building facts that Chapters 4, 7, 9 and 10 of the 2025 Building Code of New York State ask about become Revit marks, on which Revit element, with which values, which rules each settles, which facts are left out and why, and the order of the PRs.\
**For:** engineers adding marks to `apps/revit_addin` and facts to `design_checker/code_scope.py`; Ben (scope, order); reviewers of each PR.\
**Kept current by:** the engineer who builds a PR of this plan, in that same branch (its status line below).

Each chapter's plan keeps a list of facts the model can't show, so its rules can't use them yet (the "Revit-fields queue"): [Chapter 4's](2026-11-26_ny_building_chapter_4_egress.md) part f, [Chapter 7's](2026-11-26_ny_building_chapter_7.md) "Rules that new facts would allow", [Chapter 9's](2026-11-27_ny_building_chapter_9.md) parts c to e, and [Chapter 10's](2026-11-23_ny_building_egress_all_occupancies.md) section group 9h. Today the architect answers those questions in the pane, one check at a time. A mark puts the answer in the Revit model, where it stays with the project and is read on every check.

## Rules for every mark

1. **Blank means not stated.** A mark never set sends nothing, so every rule reading the fact needs review: never a pass, never "not applicable". A value that isn't one of the mark's words is asked again (the Setup form lists it as not read) and sent as typed, so the check says it can't read it; it is never read as something near it.
2. **"No" only from the architect.** Gordium never sends No for a mark left blank, and never works a No out from the model: a model may hold only some floors, or put the rest in a linked model (memory: "No only from a stated fact").
3. **Derive before asking.** A fact the model can show (levels, rooms, windows and doors and their sizes, the ground, devices placed in the model) is measuring code, tested on real models. A mark is only for what the model can't show for certain. A mark that would let a person claim something Gordium could measure, or would measure wrongly, is left out (below).
4. **Each mark quotes the law.** Its tooltip says what Yes, No (or each word) and Blank do, quoting the section that defines it.
5. **Same plumbing as the marks before it** (the Chapter 4 marks, `ChapterFourFactsTests.cs`): `Marks.cs` (a fixed GUID, never changed), `Marks.All`, `BuildingFacts.Read` (`ProjectCheck.cs`), the Setup form (from `Marks.All`, no change), the pane's card opening Project Information on the mark (`CauseCards.MarksOf`, from the mark's `Feeds`), `code_scope.MARK` (the asks name the mark exactly), and `docs/revit/revit_interior_reading_design.md`'s table.

## The marks, by element and PR

### PR A: Project Information, the four facts the rules already read

These four are already stated facts (`code_scope.FACTS`, each in `proposed_measures.yaml`); only the Revit mark is missing, so the pane asks them by name. No rule changes.

| Mark | Values | Fact | What it settles |
|---|---|---|---|
| `Gordium: Assembly spaces` | Yes / No / blank | `building.assembly_spaces` | Section 1030's flags (assembly) show where Yes or blank, and outside Group A are set aside on No (with fixed assembly seating stated No too); Yes also makes seating possible on every story where no room shows an assembly use (occupant_load.py), so the rows of Tables 1006.2.1, 1006.3.4 and 1017.2 that turn on seating need review. A room whose `Gordium: Function` is a Table 1004.5 Assembly row makes it Yes whatever the mark says; a room that may be assembly (a courtroom, a pool, a stage) turns a No into not stated (`code_scope.assembly_spaces_from_rooms`, already built). |
| `Gordium: Stages or platforms` | Yes / No / blank | `building.stages_or_platforms` | 410.5's flags; the band holding Table 1006.2.1's 125 ft rows (Groups R-2, R-3, R-4) at 410.5.3.3's 100 ft common path. A room whose `Gordium: Function` is Table 1004.5's "Stages and platforms" makes it Yes whatever the mark says (`code_scope.ROOM_SHOWS`, this PR's review round 1). |
| `Gordium: Aircraft-related occupancy` | Yes / No / blank | `building.aircraft_related_occupancy` | Section 412's flags; 905.3.5's helistop standpipes; the band on Table 1006.2.1's Group U row (412.4.2's two means of egress). A room whose `Gordium: Function` is Table 1004.5's "Aircraft hangars" makes it Yes whatever the mark says (`code_scope.ROOM_SHOWS`). |
| `Gordium: Service corridors` | Yes / No / blank | `building.service_corridors` | 415.11.3.3's and 415.11.3.4's flags and 1020.3's capacity band, in Group H-5 or a building of two or more groups; in Group H-5, the bands on Table 1017.2's travel, Table 1006.3.4(2)'s one exit, Table 1020.3's width and 1020.5's dead ends. |

The model never rules one out (a building may hold only some of its floors in the model, a hangar may be Group U and a tower Group B, a service corridor looks like any corridor), so No is the architect's alone; a room the model states a stage, a hangar or an assembly use can only add a Yes.

### PR B: Project Information, the fire alarm system and the standpipes (Chapter 9 parts c to e)

New stated facts, each building-wide; the rules that read them are changed in the same PR (the law PR's checks: every rule walked over each fact three ways against an oracle written from the law, the coverage report, publish). Two marks, so the law change stays one section family per PR (the speed rules).

| Mark | Values | Fact | What it settles |
|---|---|---|---|
| `Gordium: Manual fire alarm system` | Yes / No / blank | `building.manual_fire_alarm_system` | Yes: the building is equipped throughout with a manual fire alarm system that activates the occupant notification system per 907.5. The sections whose only requirement is that system (907.2.1, 907.2.2, 907.2.4, 907.2.7.1, 907.2.8.1, 907.2.9.1, 907.2.10.1) pass on Yes; No or blank needs review (where each applies turns on loads, floors and units the model may not hold, and a No may be a system whose boxes an exception leaves out). In a building of two or more groups, 907.2.1 also asks Group E's system for Group E's assembly portions (907.2.3: an emergency voice/alarm system), so there it passes only with `emergency_voice_alarm_system` stated too. 907.2.3 (Group E: the system initiates its signal through an emergency voice/alarm system, and sprinklers and detectors are connected to it), 907.2.5 (Group H: smoke detection too) and 907.2.6 (Group I: smoke detection too) stay flags: a manual system alone doesn't meet them. The system's design (907.5, NFPA 72) stays the architect's statement, as the sprinkler system is. |
| `Gordium: Standpipe system` | None / Class I / Class II / Class III / blank | `building.standpipe_system` | None sets aside the flags that bind a standpipe system provided (905.3.7, 905.4, 905.4.1, 905.4.2). 905.3.1 (its rule keeps 905.3's exceptions for Group R-3 and Group R-2 townhouses): Class III passes; None or Class II fails where four or more stories are stated above grade plane (each exception allows Class I, none allows no system); Class I needs review (the exceptions), and so does any value where the stories aren't stated (905.3.1 counts stories above or below grade plane, and heights above fire department access the model can't show). 905.3.2 (Class I automatic wet) stays a flag: the kind of Class I system isn't asked. |

### PR C: Project Information, smokeproof enclosures and the fire command center (Chapter 9 part e, 1023.12)

| Mark | Values | Fact | What it settles |
|---|---|---|---|
| `Gordium: Smokeproof enclosures` | Yes / No / blank | `building.smokeproof_enclosures` | Yes: every interior exit stairway and ramp is a smokeproof enclosure per 909.20. No: none is. 1023.12's requirement (403.5.4, 405.7.2, 412.2.2.1) passes on Yes; No sets aside only the 909.20 flags that bind a smokeproof enclosure alone (909.20.4's pressurized stairways, and what it reaches, stay: 1023.3.1 reaches them too). Some but not all: leave it blank (every flag shows). |
| `Gordium: Fire command center` | Yes / No / blank | `building.fire_command_center` | 911.1 in a building stated a high-rise: No fails (911.1: "in buildings classified as high-rise buildings ... a fire command center ... shall be provided"). Yes leaves 911.1's flag (911.1.1 to 911.1.7's location, separation, size and features are a person's check); a building not stated a high-rise keeps the flag (other sections, F-1 and S-1 footprints). |

### PR D: rooms and doors (Chapter 7's queue)

Planned in outline; its own PR settles the details against the law, as Chapter 7's plan asks.

| Mark | Element | Values | What it settles |
|---|---|---|---|
| `Gordium: Enclosure rating minutes` | Room (an interior exit stairway's or exit passageway's enclosure) | a count of minutes / blank | 1023.2 (707.3.2, 713.4): 120 or more passes (none asks more); under 60 fails where 1023.2's exceptions are ruled out; between, it needs both the stories the enclosure connects (from the levels where the model holds every floor, else review) and the rating of the floor assemblies it penetrates (1023.2: "not less than the floor assembly penetrated, but need not exceed 2 hours"), so under four stories it passes only where the floors are stated rated no more than the enclosure; else review. Like the corridor's `Gordium: Corridor rating minutes`. |
| (no mark) a door's fire protection rating | Door type | Revit's own Fire Rating parameter, read where it is a duration ("20 min", "1 hr", "1-1/2 hr"); anything else not stated | Table 716.1(2) for a door in an exit enclosure wall (against the enclosure's stated rating) and in a rated corridor wall (1/3 hour, 716.2.2.1's smoke and draft control a person's check). No Gordium mark: the model already holds it, so a second place to type it could disagree. Whether a family's shipped value should count as stated is settled in PR D. |
| `Gordium: Closer` | Door | Self-closing / Automatic on smoke detection / None / blank | 716.2.6.1 once Chapter 7 part b2 brings it in; 909.20.2.1 for a smokeproof enclosure's doors; 710.5.2.3 on a corridor whose walls are stated smoke partitions. Built after part b2. |

## Left out, and why

- **Smoke alarms (907.2.11) and an automatic smoke detection system (907.2.x).** The law asks where each one is (each sleeping room, outside each sleeping area, each story, corridors, habitable spaces), and alarms and detectors are elements a Revit model can hold (Fire Alarm Devices, often in a linked MEP model). A building-wide Yes would claim locations Gordium can measure and can't say where. On the measuring queue: read the devices from the model and its links; until then the flags stay a person's check.
- **A story's exterior wall openings (903.2.11.1).** The openings' sizes and places, their walls and the ground outside each are in the model (the window and door readers, `GroundReader`), so it is measuring code, not a mark.
- **The stories an exit enclosure connects (1023.2, 713.4).** Read from the levels where the model holds every floor (`2026-11-25_story_facts_from_the_model.md`); never typed.
- **Whether a Class I standpipe is automatic wet (905.3.2), and whether occupant notification activates on sprinkler water flow (907.2's exceptions).** Each loosens one flag only; the flag stays a person's check.
- **The high-rise and underground marks, the emergency voice/alarm system** are already marks (Chapter 4's marks PR; section group 5a).

## Status

- **PR A**, branch `feat/marks-building-facts-a` (PR #289): built 2026-11-28. Review round 1 found a stated No beating a room the model states a stage or a hangar (fixed: `code_scope.ROOM_SHOWS`), three tooltips' effects misdescribed (fixed), and three places where PR B's and D's plans as first written could pass falsely: 907.2.5's and 907.2.6's smoke detection and 907.2.3's connections, and 1023.2's floor assemblies (fixed above).
- **PR B**, branch `feat/marks-building-facts-b` (stacked on A): building.
- **PR C** and **PR D**: planned; D's closer after Chapter 7 part b2.
