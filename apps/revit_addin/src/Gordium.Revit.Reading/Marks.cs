namespace Gordium.Revit.Reading;

// The architect's marks (docs/revit/revit_interior_reading_design.md, section 3; Ben, 2026-11-19, decision 1):
// Gordium's shared parameters, added to a project by the add-in on first use (MarkSetup). Written here as data, so
// the Revit layer only copies them into Revit, and the tests read the same list.

/// <summary>What a mark holds (the Revit layer maps each to its <c>SpecTypeId</c>: <c>Boolean.YesNo</c>,
/// <c>String.Text</c>, <c>Length</c>, <c>Int.Integer</c>, <c>Area</c>; a length held in feet, an area in square feet,
/// Revit's internal units).</summary>
public enum MarkValueKind { YesNo, Text, Length, Integer, Area }

/// <summary>Whether a mark is set on each element (<c>InstanceBinding</c>) or once on its type (<c>TypeBinding</c>).</summary>
public enum MarkBinding { Instance, Type }

/// <summary>One Gordium shared parameter.</summary>
/// <param name="Name">Its name in Revit, as the design note writes it.</param>
/// <param name="Guid">Its shared-parameter GUID. <b>Never changed</b>: the GUID is what makes it the same parameter in
/// every project, schedule and tag; a new GUID would be a different parameter and every mark set on the old one
/// would read as not set. The reader reads a mark by its GUID only, never by name, so a firm's own parameter of
/// the same name is never read as Gordium's.</param>
/// <param name="Kind">What it holds.</param>
/// <param name="Binding">On each element, or once on its type.</param>
/// <param name="Categories">The categories it is bound to, by built-in name.</param>
/// <param name="Feeds">The interior description's field it feeds (for the architect's tooltip and the tests).</param>
/// <param name="Description">The tooltip Revit shows the architect.</param>
public sealed record MarkDefinition(string Name, Guid Guid, MarkValueKind Kind, MarkBinding Binding,
                                    IReadOnlyList<string> Categories, string Feeds, string Description);

/// <summary>Gordium's marks, exactly the design note's section 3 table.</summary>
public static class Marks
{
    public const string Rooms = "OST_Rooms";
    public const string Windows = "OST_Windows";
    public const string Doors = "OST_Doors";
    public const string Railings = "OST_StairsRailing";
    public const string ProjectInformation = "OST_ProjectInformation";
    public const string Levels = "OST_Levels";

    /// <summary>The group the parameters are written under in the shared-parameter file Gordium makes.</summary>
    public const string Group = "Gordium";

    public static readonly MarkDefinition SleepingRoom = new(
        "Gordium: Sleeping room", new("938333c3-b268-495a-8835-5c667a514122"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Rooms], "rooms[].sleeping",
        "Yes for a room used or meant for sleeping (a bedroom). Every room needs Yes or No: one left blank and no room is read for egress.");

    public static readonly MarkDefinition EscapeOpening = new(
        "Gordium: Escape opening", new("04893afb-a562-4d71-b5c9-28c4e9541060"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Windows, Doors], "openings[].escape",
        "Yes for the window or door that is its room's emergency escape and rescue opening. Every window and door needs Yes or No: one left blank and no opening is read for egress.");

    public static readonly MarkDefinition ExitDoor = new(
        "Gordium: Exit door", new("ba0a9f39-5bce-4e05-98f9-15b639b9eb2a"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Doors], "doors[].exit",
        "Yes for the dwelling's required exit door. Every door needs Yes or No: one left blank and no door is read for egress.");

    public static readonly MarkDefinition Operation = new(
        "Gordium: Operation", new("7b1e6d97-1774-458d-8f46-90002a1881c0"), MarkValueKind.Text, MarkBinding.Type,
        [Windows, Doors], "openings[].operation, doors[].operation",
        "How this type opens, one of: " + string.Join(", ", Operations.Words) + ".");

    public static readonly MarkDefinition ClearWidth = new(
        "Gordium: Clear width", new("8cb5d70c-116d-4621-9876-fd15c4c55f5c"), MarkValueKind.Length, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear.width, doors[].stated_clear.width",
        "A length, in this project's length units (Manage > Project Units: 3 typed is 3 ft in a feet project, 3 mm in a millimeter one): the maker's net clear opening width, as the maker publishes it for egress. For a door, measured as R318.2 " +
        "measures it: between the face of the door open 90 degrees and the stop (never the door's size or its rough opening).");

    public static readonly MarkDefinition ClearHeight = new(
        "Gordium: Clear height", new("8a8a2307-84a5-4a36-9121-c21453707702"), MarkValueKind.Length, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear.height, doors[].stated_clear.height",
        "A length, in this project's length units (Manage > Project Units: 3 typed is 3 ft in a feet project, 3 mm in a millimeter one): the maker's net clear opening height, as the maker publishes it for egress. For a door, measured as R318.2 " +
        "measures it: from the top of the threshold to the bottom of the stop.");

    public static readonly MarkDefinition ClearOffset = new(
        "Gordium: Clear offset", new("07f4d517-54a6-4e39-ba85-90c299137a28"), MarkValueKind.Length, MarkBinding.Type,
        [Windows], "openings[].stated_clear.bottom",
        "A length, in this project's length units (Manage > Project Units: 3 typed is 3 ft in a feet project, 3 mm in a millimeter one): the height of the clear opening's bottom above the window's sill line (where Sill Height places it). Blank is not 0: no clear opening is sent.");

    public static readonly MarkDefinition ClearSource = new(
        "Gordium: Clear source", new("2bc7eaef-1770-4077-870b-450ed224adde"), MarkValueKind.Text, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear.source, doors[].stated_clear.source",
        "The maker's publication the clear opening came from (catalogue, product line, hardware option).");

    /// <summary>How many leaves a door type's opening has (<c>doors[].leaves</c>, BCNYS 1010.1.1): 1, or 2 for a pair
    /// with no mullion between them, set once on the type (Type Properties), like its clear opening. Blank, or another
    /// number: not sent, so the door width rule needs review for every door of the type (never a pass).</summary>
    public static readonly MarkDefinition DoorLeaves = new(
        "Gordium: Leaves", new("f23ad40b-e048-4b61-a92a-b7963e64d4cf"), MarkValueKind.Integer, MarkBinding.Type,
        [Doors], "doors[].leaves",
        "A count: how many leaves this door type's opening has: 1 for a single leaf; 2 for a pair with no mullion between them. A pair with a mullion is two door openings, each needing the 32 in itself: give 1 only if this type's Gordium: Clear width is the narrower leaf's own opening, else 2. " +
        "BCNYS 1010.1.1: \"Where this section requires a minimum clear opening width of 32 inches (813 mm) and a door opening includes two door leaves without a mullion, one leaf shall provide a minimum clear opening width of 32 inches (813 mm).\" " +
        "1: the door's clear width is checked against 32 in. 2: one leaf of the pair must give the 32 in, which the maker's clear opening of the whole pair doesn't show, so a person checks. Blank or any other number: the door width needs review.");

    public static readonly MarkDefinition ClearConfirmed = new(
        "Gordium: Clear confirmed", new("66ced3f6-2dd7-4aa7-a0ce-89d086652103"), MarkValueKind.Text, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear, doors[].stated_clear (the confirmation stamp)",
        "Written by Gordium when the architect confirms this type's clear opening. Don't type in it: any change leaves the type unconfirmed.");

    public static readonly MarkDefinition TopRailIsHandrail = new(
        "Gordium: Top rail is handrail", new("8f09dc9e-0975-42ba-8a4b-43e43b393578"), MarkValueKind.YesNo, MarkBinding.Type,
        [Railings], "stairs[].handrails",
        "Yes when this railing type's top rail is also the stair's handrail (34 to 38 in up).");

    /// <summary>The project-wide tick that the stairs found are all the house's stairs (design note, sections 2 and 3:
    /// a Yes/No on Project Information; unset is not stated). Without Yes, no stair is read: a stair missed would go
    /// unchecked.</summary>
    public static readonly MarkDefinition AllStairs = new(
        "Gordium: These are all the stairs", new("90205a68-1eaf-4ca2-a350-0cb24012986c"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "stairs (sent only when Yes)",
        "Yes once every stair of the house is drawn as a Revit stair (not a generic model or an in-place family). Blank or No: no stair is read for egress.");

    /// <summary>The project-wide tick that the railings found are all the house's guards and handrails (design note,
    /// sections 2 and 3; step 5): without Yes no guard is read (a guard drawn as a low wall would go unchecked) and no
    /// stair's handrails are (a handrail drawn as a wall sweep would leave the width at the handrail read too wide).</summary>
    public static readonly MarkDefinition AllGuards = new(
        "Gordium: These are all the guards and handrails", new("80055f84-3feb-492a-b581-331ff692a2a9"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "guards and stairs[].handrails (sent only when Yes)",
        "Yes once every guard and handrail of the house is drawn as a Revit railing (not a wall, a wall sweep or a generic model). Blank or No: no guard or handrail is read for egress.");

    // ---- the lot facts "Check my project" sends (reading design note, section 9): on Project Information, typed by
    // the architect (the street edge picked by Gordium). Unset is not stated: a required one unset and nothing is sent.

    /// <summary>The zoning district, as the architect confirms it (never an address lookup's suggestion).</summary>
    public static readonly MarkDefinition Zone = new(
        "Gordium: Zone", new("7c0c478b-5959-44fd-bf53-ca89d9302bf0"), MarkValueKind.Text, MarkBinding.Instance,
        [ProjectInformation], "facts.zone",
        "The lot's zoning district exactly as the City of Ithaca's zoning map writes it (R-1b, R-2a, R-3a...). Typed by you, so confirmed: Gordium never fills it from an address lookup.");

    /// <summary>The use: on Project Information the building's, in the checker's own word (one_family_detached...); on
    /// a Room the room's (escape routes, docs/revit/revit_interior_reading_design.md section 10), one of
    /// <see cref="RoomUses.Words"/>. One parameter for both (the same GUID, bound to both categories): Gordium can't add
    /// a second parameter of the same name (MarkSetup refuses a name another parameter has), and which use it is
    /// follows from the element it is on.</summary>
    public static readonly MarkDefinition Use = new(
        "Gordium: Use", new("0a732869-f46a-4fbd-bab9-4d60735d96f3"), MarkValueKind.Text, MarkBinding.Instance,
        [ProjectInformation, Rooms], "facts.use (on Project Information), rooms[].use (on a Room)",
        "On Project Information: what the building is used for, in Gordium's word for the use (one_family_detached, one_family_semi_detached...); a word the district doesn't list needs review, never a pass. " +
        "On a Room: what the room is, one of: " + string.Join(", ", RoomUses.Words) + ". Blank: an escape route never passes through the room.");

    /// <summary>Whether a room can be locked (<c>rooms[].lockable</c>): a route never passes through one that can.
    /// Blank is not stated: the room is end-only.</summary>
    public static readonly MarkDefinition CanBeLocked = new(
        "Gordium: Can be locked", new("5b0d7c3e-2f41-4a8e-9c63-1e7a4f2b9d05"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Rooms], "rooms[].lockable",
        "Yes when the room can be locked against the people passing through it (then no escape route passes through it); No when it can't. Blank: an escape route never passes through the room.");

    /// <summary>Whether the architect states a room is one an exit route may pass through (<c>rooms[].pass_through</c>,
    /// IBC 1014.2 item 1). Blank is not stated: the room is end-only.</summary>
    public static readonly MarkDefinition PassThrough = new(
        "Gordium: Pass through", new("c2e94a61-7d3b-4f5e-8a10-6b9d3e2f4c87"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Rooms], "rooms[].pass_through",
        "Yes when an escape route may pass through this room: it is accessory to the rooms it serves, with a discernible path to an exit (IBC 1014.2 item 1). No when it may not. A corridor needs Yes or No too. Blank: an escape route never passes through the room.");

    /// <summary>Which exit a door is (<c>doors[].exit_kind</c>), in IBC 1016.1's own list, one of
    /// <see cref="ExitKinds.Words"/>. Blank: not an exit (exits are marked, never guessed).</summary>
    public static readonly MarkDefinition Exit = new(
        "Gordium: Exit", new("e7a3c519-04d2-4b86-b1f5-93c8d6a2e470"), MarkValueKind.Text, MarkBinding.Instance,
        [Doors], "doors[].exit_kind, doors[].exit_id",
        "For a door that is an exit of the building, which kind, one of: " + ExitKinds.Listed + ". Every door into one stair enclosure is the same exit. Blank: not an exit (Gordium never guesses one).");

    /// <summary>Whether the architect states nobody occupies a room (<c>rooms[].not_occupied</c>, route note decision 1b):
    /// an abandoned space, a room whose door is permanently fixed shut, a shaft. Yes: NFPA 101's travel and common path
    /// aren't measured from its points (7.6.1(1): "starting from the most remote point subject to occupancy"), each such
    /// figure naming it; the IBC's still are (1016.1: "the most remote point within a story"). Never makes a room
    /// crossable or not. Refused on a sleeping room or a day-care room. Blank or No: occupied, measured.</summary>
    public static readonly MarkDefinition NotOccupied = new(
        "Gordium: Not occupied", new("306bccbe-b2f7-4a73-9169-6be76fb46202"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Rooms], "rooms[].not_occupied",
        "Yes when nobody occupies this space: abandoned, its door permanently fixed shut, a shaft or chase (not a room visited for storage, maintenance, testing or inspection, NFPA 101 A.3.3.21.6). " +
        "Then NFPA 101's travel distance and common path aren't measured from it (7.6.1: from points subject to occupancy), each saying so; the IBC's still are (1016.1). Blank or No: occupied, measured.");

    /// <summary>A room's function as BCNYS Table 1004.5 lists them (<c>rooms[].function</c>), one of
    /// <see cref="RoomFunctions.Words"/>: the Building Code's occupant loads are worked out from it (its factor, gross or
    /// net). Stated by the architect, never guessed: the Setup form may suggest one from the room's name, written only
    /// when the architect accepts it. Blank: not stated, and the room's occupant load (and its story's) needs review; a
    /// word not in the list: sent as typed, which the checker says and reads as needs review, never as no function.</summary>
    public static readonly MarkDefinition RoomFunction = new(
        "Gordium: Function", new("de595662-5386-4cab-9245-600eefb9462d"), MarkValueKind.Text, MarkBinding.Instance,
        [Rooms], "rooms[].function",
        "The room's function as the 2025 Building Code of New York State's Table 1004.5 lists them (its occupant load factor is read from it), one of: " +
        RoomFunctions.Listed + ". Leave it blank on an exit stair enclosure or exit passageway and on a room whose Gordium: Use is Corridor, Closet or Toilet. " +
        "Blank on any other room, or a word not in the list (sent as typed, and said): the room's occupant load and its story's need review.");

    public static readonly MarkDefinition LotSurveyed = new(
        "Gordium: Lot surveyed", new("133d30e3-832f-4956-88c3-6b48989ac3f7"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.lot_surveyed",
        "Yes when the property line is drawn from a survey; No when it is traced from the tax map (its measures then carry the map's 2 ft accuracy). Blank: nothing is checked.");

    public static readonly MarkDefinition CornerLot = new(
        "Gordium: Corner lot", new("b37e1302-284e-4440-bc43-a44309ea8991"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.corner_lot",
        "Yes when the lot is on two streets. Blank: the yards need review until you answer.");

    /// <summary>The lot edges along the street, written by Gordium when the architect clicks them (StreetEdges).</summary>
    public static readonly MarkDefinition StreetEdge = new(
        "Gordium: Street edge", new("260b3e70-6b9b-45d2-8137-a5c18db9ccf5"), MarkValueKind.Text, MarkBinding.Instance,
        [ProjectInformation], "facts.street_line",
        "Written by Gordium when you click the lot edge along the street (Pick on plan, in Gordium's Setup). Don't type in it: an edge it can't find on the lot is asked for again.");

    /// <summary>Which of Gordium's spot-grade markers the ground is read from (<c>grade_from</c>).</summary>
    public static readonly MarkDefinition GroundFrom = new(
        "Gordium: Ground from", new("aa4ea7e3-5a41-48da-b6a8-979f3dfb3e5c"), MarkValueKind.Text, MarkBinding.Instance,
        [ProjectInformation], "facts.grade_from",
        "Which of Gordium's spot-grade markers give the ground: " + string.Join(" or ", GroundWords.Select(w => w.Word)) +
        ". Blank: no ground is sent, so building height and stories need review (a Toposolid isn't read yet).");

    /// <summary>The number of stories the architect states for the whole building (<c>facts.stories</c>): optional,
    /// never required, a whole number 1 or more, sent as the architect's statement. The measuring keeps it only within
    /// what the drawing allows (never fewer than the floors drawn, never more than the walls could hold at 7 ft a
    /// story: places/ithaca_city/measure.py _stories_whole), and the panel shows it as "stated by the architect" (CheckItem.Stated). Its
    /// words are Ithaca's own STORY (§325-3B), so the count is the one the law means. Blank: not stated, the count is
    /// read from the drawing, and where the drawing allows more than one count the row needs review.</summary>
    public static readonly MarkDefinition Stories = new(
        "Gordium: Stories", new("bf758947-8ee4-490c-a499-dee706a6f1e7"), MarkValueKind.Integer, MarkBinding.Instance,
        [ProjectInformation], "facts.stories",
        "A count: the building's number of stories as the City of Ithaca counts them (§325-3B STORY: from one floor level to the next floor or the roof; counted at the main entrance side, §325-8A Column 8). " +
        "A basement counts when the floor above it is more than 6 ft above the grade plane or more than 12 ft above the finished ground at any point; a cellar never counts; " +
        "a mezzanine doesn't; an attic doesn't when unfinished and without human occupancy. A whole number, 1 or more: kept only within what the drawing allows. " +
        "Blank: the count is read from the drawing, and needs review where the drawing allows more than one.");

    // ---- which New York code governs the building (design_checker/code_scope.py; docs/decisions/2026-11-22_which_ny_code.md):
    // on Project Information, the architect's statements, sent as the interior description's `building` block. Each is
    // optional; blank is not stated, and where the decision needs one it says which to fill in (never a guess).

    /// <summary>R101.2's exception, the architect's one real choice of code: Yes applies the Building Code of New York
    /// State to a house the Residential Code covers (<c>building.follows_building_code</c>).</summary>
    public static readonly MarkDefinition FollowsBuildingCode = new(
        "Gordium: Follows the Building Code", new("01405f95-7061-47e2-b2a3-7706747c0817"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.follows_building_code",
        "Yes when this building is designed to the 2025 Building Code of New York State although the Residential Code covers it. RCNYS R101.2 exception: \"Application of the provisions of the Building Code of New York State to the construction, alteration, movement, enlargement, replacement, repair, equipment, use and occupancy, location, removal and demolition of the buildings and structures listed in Section R101.2 is permitted, provided that all applicable provisions of the Building Code of New York State are applied.\" " +
        "Blank or No: Gordium picks the code from the building (a house of three stories or fewer above grade plane: the Residential Code; anything else: the Building Code).");

    /// <summary>The building's stories above grade plane as New York counts them (<c>building.stories_above_grade_plane</c>).</summary>
    public static readonly MarkDefinition StoriesAboveGradePlane = new(
        "Gordium: Stories above grade plane", new("3f5ba80f-f877-49d9-bc47-a86de4a87a19"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "building.stories_above_grade_plane",
        "A count: the building's stories above grade plane as the NYS Residential Code counts them (R202 STORY ABOVE GRADE PLANE: a story whose floor is entirely above grade plane, or whose floor above is more than 6 ft above grade plane, more than 12 ft above the finished ground at any point, or more than 6 ft above the finished ground for more than half the perimeter; a habitable attic counts, R316.3). " +
        "It decides which code governs (R101.2: not more than three). A whole number, 1 or more. Blank: Gordium: Stories stands in where nothing is drawn below the ground.");

    /// <summary>Whether each dwelling unit has a separate means of egress (<c>building.separate_means_of_egress</c>).</summary>
    public static readonly MarkDefinition SeparateMeansOfEgress = new(
        "Gordium: Separate means of egress", new("489999a0-b6a0-4d36-a186-a7874e8e78ff"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.separate_means_of_egress",
        "For a building of two dwelling units: Yes when each unit has a separate means of egress (RCNYS R101.2 item 2: \"Detached two-family dwellings in which each dwelling unit has a separate means of egress.\"); No when they share one (then the Building Code governs). Blank: which code governs needs review.");

    /// <summary>Whether every unit of an attached building is a townhouse unit (<c>building.townhouse_units</c>).</summary>
    public static readonly MarkDefinition TownhouseUnits = new(
        "Gordium: Townhouse units", new("81480188-21b7-4786-b2b3-c3da847439c2"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.townhouse_units",
        "For three or more attached units: Yes when every unit is a townhouse unit (RCNYS R202: \"A single-family dwelling unit in a townhouse that extends from foundation to roof, that has a yard or public way on not less than two sides, and has a separate means of egress.\"). Blank: which code governs needs review.");

    /// <summary>Whether people outside the household receive care in the building (<c>building.care_facility</c>).</summary>
    public static readonly MarkDefinition CareFacility = new(
        "Gordium: Care facility", new("58d76f42-7618-4c1c-8765-3af6c45b31d2"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.care_facility",
        "Yes when people outside the household receive custodial, medical or personal care, or day care, in the building (BCNYS 308.2.4, 310.4.1: five or fewer in a dwelling may stay under the Residential Code with a sprinkler system). Yes: which code governs needs review. Blank or No: none.");

    /// <summary>The building's occupancy groups (BCNYS Chapter 3), comma separated (<c>building.occupancy_groups</c>).</summary>
    public static readonly MarkDefinition OccupancyGroups = new(
        "Gordium: Occupancy groups", new("ea50d05c-05a2-46b3-aafc-6cbb22bf19ac"), MarkValueKind.Text,
        MarkBinding.Instance, [ProjectInformation], "building.occupancy_groups",
        "The building's occupancy groups as the 2025 Building Code of New York State classifies them (Chapter 3), separated by commas: " +
        OccupancyGroupWords.Listed + ". The Building Code's egress rules read it (Group I-4 has its own limits). Blank: the rules that turn on the group need review.");

    /// <summary>The building's automatic sprinkler system (<c>building.sprinkler_system</c>).</summary>
    public static readonly MarkDefinition SprinklerSystem = new(
        "Gordium: Sprinkler system", new("4b542577-d04e-463a-87fa-019dbc102374"), MarkValueKind.Text,
        MarkBinding.Instance, [ProjectInformation], "building.sprinkler_system",
        "The automatic sprinkler system the building is equipped with throughout, one of: " + SprinklerWords.Table.Listed +
        " (BCNYS 903.3.1.1 NFPA 13, 903.3.1.2 NFPA 13R, 903.3.1.3 NFPA 13D). Blank: the limits that change with a sprinkler system need review.");

    // ---- what the Building Code's Chapter 10 egress rules read of the whole building (code_scope.FACTS, the BCNYS
    // rulebook's proposed_measures.yaml): each a Yes/No on Project Information, sent only when set. Yes leaves the limits
    // the fact changes to a person (Gordium doesn't measure them yet); No is the architect's statement that the general
    // limits apply; blank is not stated, and every rule that reads it needs review (never read as No).

    /// <summary>Whether any room or space is used for assembly with fixed seating (<c>building.assembly_fixed_seating</c>,
    /// BCNYS Table 1006.2.1 note c, 1030.8).</summary>
    public static readonly MarkDefinition AssemblyFixedSeating = new(
        "Gordium: Fixed assembly seating", new("717d4f32-6264-46b4-95e7-ffd7668518c4"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.assembly_fixed_seating",
        "Yes when any room or space of the building is used for assembly purposes with fixed seating, in any group (BCNYS Table 1006.2.1 note c: \"c. For a room or space used for assembly purposes having fixed seating, see Section 1030.8.\"). " +
        "Yes: a person checks the exits, common path and travel such a room changes (1030.7 measures its travel along the aisles, never over or on the seats; 1030.8 limits its common path from any seat). No: there is none. Blank: the rules that turn on it need review.");

    /// <summary>Whether the building holds a space the Building Code gives its own exits or travel limit
    /// (<c>building.special_egress_spaces</c>, BCNYS 1006.2.2, Table 1017.2 note a).</summary>
    public static readonly MarkDefinition SpecialEgressSpaces = new(
        "Gordium: Special egress spaces", new("8efde5e2-df14-4f88-b8ce-da46285b930d"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.special_egress_spaces",
        "Yes when the building holds any space the Building Code gives its own exits or exit access travel limit: a covered or open mall (402.8), a Group I-2 care suite (407.4.4), a special amusement area (411), an aircraft manufacturing facility (412.6), " +
        "a boiler, incinerator or furnace room, a refrigeration machinery room, a refrigerated room or an electrical room (1006.2.2.1 to 1006.2.2.4), a vehicular ramp (1006.2.2.5), a temporary structure (3103.4) or a pedestrian walkway (3104.9). " +
        "BCNYS 1006.2.2: \"The numbers, configuration and types of components of exits or access to exits shall be provided in the uses described in Sections 1006.2.2.1 through 1006.2.2.6.\" " +
        "Yes: a person checks the limits those spaces change. No: the building has none of them. Blank: the rules that turn on it need review.");

    /// <summary>Whether a Group M store has merchandise pads (<c>building.merchandise_pads</c>, BCNYS 1018.4).</summary>
    public static readonly MarkDefinition MerchandisePads = new(
        "Gordium: Merchandise pads", new("90d6a3a4-6f52-487c-b98b-21ea864dee45"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.merchandise_pads",
        "Yes when a Group M store in the building has merchandise pads (areas of display elements with aisle accessways among them). BCNYS 1018.4: \"The common path of egress travel shall not exceed 30 feet (9144 mm) from any point in the merchandise pad.\" (75 ft for not more than 50 occupants). " +
        "Yes: a person checks that common path (the pads aren't marked in the model). No: there are none. Blank: the rules that turn on it need review.");

    /// <summary>Whether the design takes the exterior egress balcony increase (<c>building.egress_balcony_increase_taken</c>,
    /// BCNYS 1017.2.1).</summary>
    public static readonly MarkDefinition EgressBalconyIncrease = new(
        "Gordium: Egress balcony increase", new("3f260842-2450-44da-902d-3e066984a521"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.egress_balcony_increase_taken",
        "Yes when the design relies on BCNYS 1017.2.1's exterior egress balcony increase: up to 100 ft more exit access travel where the last portion of the exit access leading to the exit is on an exterior egress balcony. " +
        "Yes: a travel distance over the table's limit but within the increase is checked by a person. No: the design doesn't take it, so Table 1017.2's limits apply as they are. Blank: the rules that turn on it need review.");

    /// <summary>Whether the building's Group R-2 consists of sleeping units, not dwelling units
    /// (<c>building.r2_sleeping_units</c>, BCNYS Tables 1006.3.4(1) and (2), notes b and c).</summary>
    /// Three words, never a Yes/No (review round 3: a Yes/No once set can't be cleared back to blank, so a building of
    /// both kinds, which neither table fits, had no answer to give): see <see cref="R2UnitWords"/>.
    public static readonly MarkDefinition R2SleepingUnits = new(
        "Gordium: R-2 sleeping units", new("b8d986fc-ae44-428a-8740-0937a6a8197a"), MarkValueKind.Text,
        MarkBinding.Instance, [ProjectInformation], "building.r2_sleeping_units",
        "For a Group R-2 building, what its Group R-2 units are, one of: " + R2UnitWords.Table.Listed + ". It chooses which table limits a Group R-2 story with one exit: All sleeping units (a dormitory, a boarding house), Table 1006.3.4(2); All dwelling units (apartments), Table 1006.3.4(1); Both: neither table fits every story, so both tables' one-exit rows need review. " +
        "BCNYS Table 1006.3.4(1) note b: \"This table is used for Group R-2 occupancies consisting of dwelling units. For Group R-2 occupancies consisting of sleeping units, use Table 1006.3.4(2).\" " +
        "Blank: the one-exit rows for Group R-2 need review, under both tables.");

    /// <summary>Whether the building has emergency escape and rescue openings per BCNYS 1031
    /// (<c>building.emergency_escape_openings_1031</c>, Tables 1006.3.4(1) and (2) note a).</summary>
    public static readonly MarkDefinition EscapeOpenings1031 = new(
        "Gordium: 1031 escape openings", new("298cd307-3a3f-4c2f-a12d-e8fe3d31b4f6"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.emergency_escape_openings_1031",
        "For a Group R-2 building: Yes only when it is provided with emergency escape and rescue openings in accordance with Section 1031 (every sleeping room and basement the section asks for has one that complies with it; Gordium doesn't check them under the Building Code). " +
        "BCNYS Table 1006.3.4(1) note a: \"Buildings classified as Group R-2 equipped throughout with an automatic sprinkler system in accordance with Section 903.3.1.1 or 903.3.1.2 and provided with emergency escape and rescue openings in accordance with Section 1031.\" " +
        "Yes: a Group R-2 story may then have one exit within the table's limits. No: it may not under that row. Blank: those rows need review.");

    /// <summary>Whether the building has outdoor areas its occupants use (<c>building.occupied_outdoor_areas</c>,
    /// BCNYS 1004.7).</summary>
    public static readonly MarkDefinition OccupiedOutdoorAreas = new(
        "Gordium: Occupied outdoor areas", new("5be49bb1-7c0f-4eea-a360-c6b47d2e9dad"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.occupied_outdoor_areas",
        "Yes when the building has yards, patios, occupiable roofs, courts or similar outdoor areas its occupants can reach and use. " +
        "BCNYS 1004.7: \"Yards, patios, occupiable roofs, courts and similar outdoor areas accessible to and usable by the building occupants shall be provided with means of egress as required by this chapter.\" " +
        "Yes: their means of egress and the occupant load the building official assigns them are a person's check (outdoor areas aren't drawn for Gordium). No: there are none. Blank: that check needs review.");

    /// <summary>Whether the design takes BCNYS 1004.5.1's increased occupant load (<c>building.occupant_load_increased</c>).</summary>
    public static readonly MarkDefinition OccupantLoadIncreased = new(
        "Gordium: Occupant load increased", new("64b5a6c7-d4ae-4424-b7e1-2c041b09d02a"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.occupant_load_increased",
        "Yes when the design takes BCNYS 1004.5.1's increased occupant load: more occupants than Table 1004.5's factors give, every other requirement met for that number, at most one occupant per 7 sq ft of occupiable floor space. " +
        "No: the design takes no increase, so each room's occupant load is Table 1004.5's alone. Yes or blank: each room's larger reading is at least its area / 7 (the most 1004.5.1 allows), so a rule an increase could fail needs review or fails, never passes.");

    // ---- groups 4 and 5's (corridors, 1020; egress capacity, 1005.3): what the corridor rules read of the building

    /// <summary>Whether another level's occupants reach the building's corridors (<c>building.other_level_egress_into_corridors</c>;
    /// BCNYS 1004.2.2, 1004.2.3, 1005.6): read by the occupant loads (occupant_load.py), never a rule's own measure.</summary>
    public static readonly MarkDefinition OtherLevelsReachCorridors = new(
        "Gordium: Other levels reach corridors", new("63ce1aaf-5fb8-4af6-9c71-730392b78bb4"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.other_level_egress_into_corridors",
        "Yes when any other level's occupants reach a corridor of the building: an unenclosed stairway or ramp, a mezzanine (BCNYS 1004.2.2 adds its occupants to the space below), or stairs converging or discharging into it (1004.2.3, 1005.6). " +
        "Yes: a corridor's occupant load is worked out by hand (the story's doesn't bound it). No: none does, so each corridor's load lies between none and its whole story's. Blank: worked out by hand, as for Yes.");

    /// <summary>Whether the building is or holds an ambulatory care facility (<c>building.ambulatory_care_facility</c>,
    /// BCNYS 202, Section 422, Tables 1020.2 and 1020.3).</summary>
    public static readonly MarkDefinition AmbulatoryCareFacility = new(
        "Gordium: Ambulatory care facility", new("2a31e2c4-cf29-4ac4-9c57-a41ca85748b3"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.ambulatory_care_facility",
        "Yes when the building is or holds an ambulatory care facility (BCNYS 202 AMBULATORY CARE FACILITY, Section 422: outpatient care where patients may be rendered incapable of self-preservation, Group B). " +
        "Table 1020.3 asks 72 in for its corridors and areas serving stretcher traffic, which the model doesn't show; Section 422 asks its fire partition from adjacent corridors (422.2) and its smoke compartments (422.3). Yes: Section 422's flags, a Group B corridor under 72 in and an unrated Group B corridor (Table 1020.2) are a person's check. No: none of them. Blank: those checks need review.");

    /// <summary>Whether any corridor is inside a dwelling or sleeping unit (<c>building.corridors_within_dwelling_units</c>,
    /// BCNYS 1020.2 exception 2, Table 1020.3).</summary>
    public static readonly MarkDefinition CorridorsWithinDwellingUnits = new(
        "Gordium: Corridors within dwelling units", new("a61d6738-cc50-4a7a-bf34-eb258e6b55d7"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.corridors_within_dwelling_units",
        "Yes when any corridor of the building is inside a dwelling unit or sleeping unit. BCNYS 1020.2 exception 2: \"A fire-resistance rating is not required for corridors contained within a dwelling unit or sleeping unit in an occupancy in Groups I-1 and R.\" (Table 1020.3 also asks only 36 in within a dwelling unit.) " +
        "Yes: a corridor short of the rating or the width is a person's check (which corridors are inside a unit isn't shown). No: none is, so the table's rating and width apply to every corridor, and a door onto a corridor gets none of BCNYS 1010.1.1's exceptions for doors inside a dwelling unit (exceptions 1, 4, 6, 7: its width and height are held to the full size). Blank: those checks need review.");

    /// <summary>Whether the building has an emergency voice/alarm communication system per BCNYS 907.5.2.2
    /// (<c>building.emergency_voice_alarm_system</c>; 1005.3.1 and 1005.3.2 exception 1).</summary>
    public static readonly MarkDefinition EmergencyVoiceAlarm = new(
        "Gordium: Emergency voice/alarm system", new("f4184d32-275e-4423-90c6-66a2e4d247ee"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.emergency_voice_alarm_system",
        "Yes only when the building is equipped throughout with an emergency voice/alarm communication system in accordance with BCNYS Section 907.5.2.2. A system in only part of the building: No. " +
        "With an automatic sprinkler system throughout too (NFPA 13; NFPA 13R in Group R only, elsewhere a person checks), BCNYS 1005.3.1 and 1005.3.2 exception 1 lower the egress capacity factors (other than Groups H and I-2): 0.15 in per occupant for corridors and other components, 0.2 in for stairways. " +
        "No: the full factors (0.2 in and 0.3 in). Blank: a capacity met only at the lower factor needs review.");

    /// <summary>Whether the building is a high-rise or more than 420 ft in building height (<c>building.high_rise_building</c>,
    /// BCNYS 202 HIGH-RISE BUILDING, Section 403: 403.2.2, 403.5.2).</summary>
    public static readonly MarkDefinition HighRiseBuilding = new(
        "Gordium: High-rise building", new("50749eaa-b331-40c1-af60-c1bf02acbc28"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.high_rise_building",
        "Yes when the building is a high-rise, or more than 420 ft in building height. BCNYS 202: \"A building with an occupied floor or occupiable roof located more than 75 feet (22 860 mm) above the lowest level of fire department vehicle access.\" " +
        "The model can't show where fire trucks reach the building, so Gordium never decides it; its question may give the model's height over the lowest finished ground as a hint. " +
        "Yes: Section 403's requirements are a person's check, and outside Group R-2 a story with no more exits than 1006.3 asks needs review (403.5.2: one more interior exit stairway over 420 ft). No: neither. Blank: as for Yes.");

    /// <summary>Whether a floor level used for human occupancy is more than 30 ft below the lowest level of exit
    /// discharge (<c>building.underground_building</c>, BCNYS 405.1, 405.7.1).</summary>
    public static readonly MarkDefinition UndergroundBuilding = new(
        "Gordium: Underground building", new("0b116213-0d7e-4e3c-b03b-e71a9f387d05"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.underground_building",
        "Yes when a floor level used for human occupancy is more than 30 ft below the finished floor of the lowest level of exit discharge. BCNYS 405.1: \"The provisions of Sections 405.2 through 405.9 apply to building spaces having a floor level used for human occupancy more than 30 feet (9144 mm) below the finished floor of the lowest level of exit discharge.\" " +
        "Yes: Section 405's requirements are a person's check, and a story with one exit needs review (405.7.1: two exits on each floor level). No: none. Blank: as for Yes.");

    /// <summary>Whether the building has an atrium (<c>building.building_has_atrium</c>, BCNYS 1017.3.2.3).</summary>
    public static readonly MarkDefinition Atrium = new(
        "Gordium: Atrium", new("8c3211a5-546b-463e-8d8c-b70fd753c1b6"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "building.building_has_atrium",
        "Yes when the building has an atrium (BCNYS 202 ATRIUM: an opening connecting two or more stories, closed at the top) that a path of egress travel passes through or that areas open to. BCNYS 1017.3.2.3: \"Where the path of egress travel is not at the level of exit discharge from the atrium, that portion of the total permitted exit access travel distance that occurs within the atrium shall be not greater than 200 feet (60 960 mm).\" " +
        "Yes: a travel distance over 200 ft is checked by a person. No: there is none. Blank: the rules that turn on it need review.");

    // ---- the lot facts the worker asks the architect for that no other mark stated (Ithaca's zoning: §325-3B,
    // §325-8B(1), §325-19E, §325-28): sent as the lot facts of the same names (host_core.facts.STATED_FACTS) only when
    // set, so a blank one is not stated and its rows need review; a value Gordium can't read is said, never sent

    /// <summary>Whether R-1a or R-1b land abuts the lot (<c>facts.abuts_r1_district</c>, §325-19E).</summary>
    public static readonly MarkDefinition AbutsR1 = new(
        "Gordium: Abuts R-1 land", new("e03a7668-69f3-4286-b79e-7e2fedd51174"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.abuts_r1_district",
        "For a use other than a one- or two-family dwelling in R-3a or R-3b: Yes when any R-1a or R-1b land touches the lot (even at a corner) or is across a street, alley, creek or other waterway, railroad or other right-of-way from it. " +
        "§325-19E: \"Development in R-3 Districts which abut R-1 Districts.\" (its lot size, height, coverage and yards change). Gordium reads its test (land that directly abuts) the cautious way, across a street included, as a reading to confirm. No: none. Blank: the rules that turn on it need review.");

    /// <summary>Whether the building is a conversion, not new construction (<c>facts.conversion</c>, §325-3B).</summary>
    public static readonly MarkDefinition Conversion = new(
        "Gordium: Conversion", new("b4ae661a-9d9d-4e7b-addf-cb674911fc28"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.conversion",
        "Yes when the building is made by converting an existing building, not new construction. §325-3B: \"CONVERSION — The changing of use or occupancy by alteration, addition or by other reorganization.\" No: new construction. Blank: the rules that turn on it need review.");

    /// <summary>How many primary buildings stand on the lot (<c>facts.primary_buildings</c>, 1 or more).</summary>
    public static readonly MarkDefinition PrimaryBuildings = new(
        "Gordium: Primary buildings", new("99739cee-bd25-46a2-9ed4-f552654d1209"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.primary_buildings",
        "A count: the primary buildings on the lot, the main one included: each separate building holding a home or another permitted primary use, never a garage, shed or accessory dwelling unit. " +
        "§325-3B: \"PRIMARY STRUCTURE — A single structure (located on a parcel) containing a use permitted in the zoning district in which it is located.\" A whole number, 1 or more. Blank: read from the drawing, and where the drawing allows more than one count the rows it changes need review.");

    /// <summary>Whether every primary building holds the lot's use (<c>facts.primary_buildings_same_use</c>, §325-8B(1)).</summary>
    public static readonly MarkDefinition PrimaryBuildingsSameUse = new(
        "Gordium: Primary buildings same use", new("8c4cda53-f475-42ff-ad64-b7ba1f85979e"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.primary_buildings_same_use",
        "With more than one primary building: Yes when every one holds the use given for the lot (Gordium: Use), so each needs that use's lot area. " +
        "§325-8B(1): \"For minimum lot size requirements stated in Column 6, Area in Square Feet, for all residential use districts, each square-footage requirement applies separately to the initial permitted primary use and to each additional permitted primary use located in a separate building on the property in question (e.g., in R-2b Districts, an area of 3,000 square feet is required for a one family house or a two-family house, and an additional area of 3,000 square feet is required for each additional one-family house or two-family house on the property).\" No: they hold other uses. Blank: the lot size needs review.");

    /// <summary>The home occupation's indoor floor area (<c>facts.home_occupation_area</c>, sq ft, §325-3B).</summary>
    public static readonly MarkDefinition HomeOccupationArea = new(
        "Gordium: Home occupation area", new("78decf20-6a2b-49f3-910c-c09c2e63d90d"), MarkValueKind.Area,
        MarkBinding.Instance, [ProjectInformation], "facts.home_occupation_area",
        AreaWords + " (Manage > Project Units: 300 typed is 300 sq ft in a square-feet project, 300 m² in a square-meters one): with a home occupation planned, the indoor floor area it uses, its accessory structures included, as typed (never rounded). " +
        "§325-3B HOME OCCUPATION (1)(f): \"The occupation occupies no more than 25% of the dwelling unit and no more than a total of 500 indoor square feet, including accessory structures.\" 0 or more. Blank: the rule needs review.");

    /// <summary>The floor area of the dwelling unit the home occupation is in (<c>facts.home_occupation_unit_area</c>).</summary>
    public static readonly MarkDefinition HomeOccupationUnitArea = new(
        "Gordium: Home occupation unit area", new("2b6debca-6222-4c69-a0b0-c6d754ef4f0d"), MarkValueKind.Area,
        MarkBinding.Instance, [ProjectInformation], "facts.home_occupation_unit_area",
        AreaWords + " (Manage > Project Units: 300 typed is 300 sq ft in a square-feet project, 300 m² in a square-meters one): with a home occupation planned, the floor area of the dwelling unit it is in, as typed (never rounded). " +
        "§325-3B HOME OCCUPATION (1)(f): \"The occupation occupies no more than 25% of the dwelling unit and no more than a total of 500 indoor square feet, including accessory structures.\" 0 or more. Blank: the rule needs review.");

    /// <summary>Whether a detached ADU is in an existing accessory building (<c>facts.adu_existing_building</c>).</summary>
    public static readonly MarkDefinition AduExistingBuilding = new(
        "Gordium: ADU in existing building", new("acd7b1f8-d8f1-4001-8a07-362db5e75524"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.adu_existing_building",
        "For a detached accessory dwelling unit: Yes when it is in an accessory building that already exists; No when it is new construction (§325-28C(7)(b) and (c), its size, and (8)(b), its setbacks, differ). " +
        "§325-28C(7)(b)[1]: \"An existing accessory building may be altered or expanded, provided that it does not exceed the size limitations for new construction.\" Blank: the rules that turn on it need review.");

    /// <summary>The bedrooms in the accessory dwelling unit (<c>facts.adu_bedrooms</c>, §325-28C(3)).</summary>
    public static readonly MarkDefinition AduBedrooms = new(
        "Gordium: ADU bedrooms", new("019161da-e9c1-4219-8cfc-01dbd1071761"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.adu_bedrooms",
        "A count: the bedrooms in the accessory dwelling unit. §325-28C(3): \"An ADU may have a maximum of two bedrooms.\" A whole number, 0 or more. Blank: the rule needs review.");

    /// <summary>The floor area of an attached ADU (<c>facts.adu_floor_area</c>, sq ft, §325-28C(7)(a)).</summary>
    public static readonly MarkDefinition AduFloorArea = new(
        "Gordium: ADU floor area", new("41c8f63d-368d-4ea9-b371-85828b769d6a"), MarkValueKind.Area,
        MarkBinding.Instance, [ProjectInformation], "facts.adu_floor_area",
        AreaWords + " (Manage > Project Units: 300 typed is 300 sq ft in a square-feet project, 300 m² in a square-meters one): for an attached accessory dwelling unit, its floor area, as typed (never rounded). " +
        "§325-28C(7)(a): \"The ADU shall not exceed 40% of the floor area of the primary structure.\" 0 or more. Blank: the rule needs review.");

    /// <summary>The floor area of the main building an attached ADU is in (<c>facts.primary_floor_area</c>).</summary>
    public static readonly MarkDefinition MainBuildingFloorArea = new(
        "Gordium: Main building floor area", new("f237131b-5e7e-4c8e-94df-a8538de16954"), MarkValueKind.Area,
        MarkBinding.Instance, [ProjectInformation], "facts.primary_floor_area",
        AreaWords + " (Manage > Project Units: 300 typed is 300 sq ft in a square-feet project, 300 m² in a square-meters one): for an attached accessory dwelling unit, the floor area of the whole main building it is in, the ADU included, as typed (never rounded). " +
        "§325-28C(7)(a): \"The ADU shall not exceed 40% of the floor area of the primary structure.\" (whether the 40% is of the whole structure or of the rest of it is an open question, so a close result needs review). 0 or more. Blank: the rule needs review.");

    // ---- the dwelling's own facts which New York code needs (code_scope.py) and Ithaca's zoning reads too: sent as
    // the lot facts of the same names (host_core.facts.STATED_FACTS), each only when set (unset is not stated)

    /// <summary>The dwelling units on this lot (<c>facts.dwelling_units</c>), 1 or more.</summary>
    public static readonly MarkDefinition DwellingUnits = new(
        "Gordium: Dwelling units", new("aa32131a-e757-47a3-abf8-9deb81d7a09a"), MarkValueKind.Integer, MarkBinding.Instance,
        [ProjectInformation], "facts.dwelling_units",
        "A count: the dwelling units on this lot (a building split along its party walls onto several lots: this lot's units only), an accessory dwelling unit not counted (Gordium: Accessory dwelling unit says it). A whole number, 1 or more. Blank: the use's own count (one for a detached one-family dwelling).");

    /// <summary>The dwelling units in the whole attached building, every lot it stands on (<c>facts.attached_units_in_building</c>).</summary>
    public static readonly MarkDefinition UnitsInAttachedBuilding = new(
        "Gordium: Units in the attached building", new("bccb088a-c087-475f-9ff9-53fd10133d0e"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.attached_units_in_building",
        "A count: for an attached one-family dwelling (one_family_attached): the dwelling units in the whole attached building, every lot it stands on (§325-3B: three to six), 1 or more. It decides whether the building is a townhouse (RCNYS R202: three or more townhouse units). Blank: which code governs needs review.");

    /// <summary>Whether a home occupation is planned (<c>facts.home_occupation</c>).</summary>
    public static readonly MarkDefinition HomeOccupation = new(
        "Gordium: Home occupation", new("c6a7cf3a-28b8-4c18-98f2-cf34215901bf"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.home_occupation",
        "Yes when a home occupation is planned (§325-3B: a business, studio or office run by a resident in the dwelling unit); then which code governs needs a person's check (a live/work unit, BCNYS 508.5). No: none. Blank: Gordium assumes none and says so.");

    /// <summary>The rooms let for profit (<c>facts.rooms_let_for_profit</c>), 0 or more.</summary>
    public static readonly MarkDefinition RoomsLetForProfit = new(
        "Gordium: Rooms let for profit", new("2f038e8d-2d26-4e46-b92a-1c51d08bca87"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.rooms_let_for_profit",
        "A count: the rooms let for profit (to roomers) in the building, 0 or more; with any, the Residential Code covers it only when owner-occupied with five or fewer guestrooms and a sprinkler system (RCNYS R101.2 item 6). Blank: Gordium assumes none and says so.");

    /// <summary>Whether an accessory dwelling unit is on the lot (<c>facts.accessory_dwelling_unit</c>).</summary>
    public static readonly MarkDefinition AccessoryDwellingUnit = new(
        "Gordium: Accessory dwelling unit", new("6fcbf10d-a1c2-406a-b6c7-e726b4a695f2"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.accessory_dwelling_unit",
        "Yes when an accessory dwelling unit (§325-3B, §325-28) is on the lot, attached or detached; then say whether it is detached (Gordium: ADU detached). No: none. Blank: Gordium assumes none and says so.");

    /// <summary>The accessory dwelling units on the parcel (<c>facts.adus_on_parcel</c>), 1 or more.</summary>
    public static readonly MarkDefinition AdusOnParcel = new(
        "Gordium: ADUs on parcel", new("1fa82254-92d5-4f27-acef-924bfc047d7c"), MarkValueKind.Integer, MarkBinding.Instance,
        [ProjectInformation], "facts.adus_on_parcel",
        "A count: with an accessory dwelling unit on the lot, the accessory dwelling units on the parcel, any already there included (§325-28C(1): one per parcel), 1 or more. More than one keeps which code governs at needs review (each may be one more of the building's units, RCNYS R202 DWELLING). Blank: Gordium assumes one, the one stated, and says so.");

    /// <summary>Whether the accessory dwelling unit is detached (<c>facts.adu_detached</c>).</summary>
    public static readonly MarkDefinition AduDetached = new(
        "Gordium: ADU detached", new("ebd07d28-ce47-4e7d-95e7-6e164d7d7bc8"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.adu_detached",
        "Yes when the accessory dwelling unit is in its own building; No when it is in or on the main building, where it is one more of the building's dwelling units (RCNYS R202 DWELLING: one or two). Blank, with an ADU on the lot: which code governs needs review.");

    // ---- the house's own facts Ithaca's zoning reads and no drawing shows (UI design change 20): sent as the lot facts
    // of the same names (host_core.facts.STATED_FACTS), each only when set, so an unset one is not stated and its rows
    // need review (never No or 0); a value Gordium can't read is said, never sent, and its rows need review

    /// <summary>Whether a stream or inlet is within 20 ft of the lot (<c>facts.stream_near_lot</c>, §325-26).</summary>
    public static readonly MarkDefinition StreamNearLot = new(
        "Gordium: Stream within 20 ft", new("17620cff-9a18-449f-900b-cd66e0ed1b82"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.stream_near_lot",
        "Yes when any inlet wall, or the bank of an inlet channel or stream (at average water level), is within 20 ft of the lot; then give the distance (Gordium: Distance from stream). " +
        "§325-26: \"No new structure shall be located nearer than 20 feet to an inlet wall or to the bank of an inlet channel or stream, measured at an average water level, except for those structures directly connected with marine or public or commercial recreation activities.\" No: none. Blank: the rule needs review.");

    /// <summary>The least distance from a new structure to that wall or bank (<c>facts.stream_distance</c>, feet).</summary>
    public static readonly MarkDefinition StreamDistance = new(
        "Gordium: Distance from stream", new("6b203698-192c-4814-b27c-4e5968fa8111"), MarkValueKind.Length,
        MarkBinding.Instance, [ProjectInformation], "facts.stream_distance",
        "A length, in this project's length units (Manage > Project Units: 3 typed is 3 ft in a feet project, 3 mm in a millimeter one): with a stream or inlet within 20 ft of the lot, the least horizontal distance from any new structure (house, addition, garage, deck, fence; not a patio or terrace) to the inlet wall or the stream's bank, at average water level, as typed (never rounded). " +
        "§325-26: \"No new structure shall be located nearer than 20 feet to an inlet wall or to the bank of an inlet channel or stream, measured at an average water level, except for those structures directly connected with marine or public or commercial recreation activities.\" §325-3B: \"Structures shall not include patios or terraces.\" 0 or more. Blank: the rule needs review.");

    /// <summary>The most people in any one dwelling unit not related to its family (<c>facts.unrelated_persons</c>).</summary>
    public static readonly MarkDefinition UnrelatedPersons = new(
        "Gordium: Unrelated people per unit", new("74a581ac-f1c6-4062-a97f-0504955d2175"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.unrelated_persons",
        "A count: the most people in any one dwelling unit not related by blood, marriage or adoption to its household's family, minor dependent children in a parent's or relative's care left out. " +
        "§325-3B DWELLING, ONE-FAMILY: \"A dwelling unit occupied exclusively for residential purposes by an individual or family and not more than one unrelated individual or a functional family unit. In the R-1 Zones, occupancy by an individual or a family and not more than two unrelated individuals is permitted if the dwelling is owner-occupied.\" " +
        "A whole number, 0 or more. Blank: the occupancy rule needs review.");

    /// <summary>Whether the owner lives in the one-family dwelling itself (<c>facts.owner_occupied</c>).</summary>
    public static readonly MarkDefinition OwnerOccupied = new(
        "Gordium: Owner-occupied", new("489c2902-38ec-430f-aa5e-47675cb48eff"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.owner_occupied",
        "Yes when the dwelling is owner-occupied: its owner, exactly as §325-3B defines OWNER below (who holds the property, and how, both count), maintains his or her principal residence in it. " +
        "With an accessory dwelling unit on the lot, whether an owner living only in the ADU counts is an open question: a person checks it. " +
        "§325-3B: \"In the R-1 Zones, occupancy by an individual or a family and not more than two unrelated individuals is permitted if the dwelling is owner-occupied.\" " +
        "OWNER (§325-3B, where owner-occupancy is required): \"A person who maintains his/her principal residence in property for more than six months of each calendar year and who is: (1) The sole owner of record of the property, as reflected in a deed recorded in the Tompkins County Clerk's Office; (2) A tenant by the entirety or joint tenant with right of survivorship, as reflected in a deed recorded in the Tompkins County Clerk's Office; or (3) A tenant in common of at least a 50% interest in the property, as reflected in a deed recorded in the Tompkins County Clerk's Office, provided that such interest was acquired: (a) For full market value, paid to the grantor; or (b) By descent or devise following the death of the former owner.\" " +
        "No: not owner-occupied. Blank: the occupancy rule needs review where it matters.");

    /// <summary>Whether the household is to be shown to the City to be a functional family unit (<c>facts.functional_family_unit</c>).</summary>
    public static readonly MarkDefinition FunctionalFamilyUnit = new(
        "Gordium: Functional family unit", new("868efeab-7254-4c46-bf04-564a4c853946"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.functional_family_unit",
        "Yes when the household is to be shown to the City to be a functional family unit (the City's finding: Gordium then says a person checks it). " +
        "§325-3B FUNCTIONAL FAMILY UNIT: \"A group of individuals living together in a single dwelling unit and functioning as a family with respect to those characteristics that are consistent with the purposes of zoning restrictions in residential neighborhoods. (1) In determining whether or not a group of unrelated individuals is a functional family unit under the definition set forth above, the following criteria must be present: (a) The occupants must share the entire dwelling unit. A unit in which the various occupants act as separate roomers cannot be deemed to be occupied by a functional family unit. (b) The household must have stability with respect to the purpose of this chapter. Evidence of such stability may include the following: [1] The presence of minor dependent children regularly residing in the household. [2] Proof of the sharing of expenses for food, rent or ownership costs, utilities and other household expenses and sharing in the preparation, storage and consumption of food. [3] Whether or not different members of the household have the same address for the purposes of: [a] Voter registration. [b] Drivers' licenses. [c] Motor vehicle registration. [d] Summer or other residences. [e] The filing of taxes. [4] Common ownership of furniture and appliances among the members of the household. [5] Enrollment of dependent children in local schools. [6] Employment of householders in the local area. [7] A showing that the household has been living together as a unit for a year or more, whether in the current dwelling unit or other dwelling units. [8] Any other factor reasonably related to whether or not the group or persons is the functional equivalent of a family. (2) A group of individuals living in the same dwelling unit shall be presumed not to be a functional family unit, as defined in this section, if such dwelling unit contains four or more college students over the age of 16 years. (a) A college student is a person who attends, at least half time, any college, university or other institution authorized to confer degrees by the State of New York. (b) For the purpose of this presumption, minor dependent children of any other member of the household shall be excluded in calculating the number of college students in the household. (3) A group of individuals living together in the same dwelling unit shall be presumed not to be a functional family unit, as defined in this section, if the dwelling unit is occupied by four or more unrelated adults over the age of 18 years and is not occupied by minor dependent children. (4) The presumptions set forth in Subsections (2) and (3) of this definition may be rebutted by sufficient evidence of the characteristics set forth in Subsection (1) of this definition.\" " +
        "No: not one. Blank: the occupancy rule needs review where it matters.");

    /// <summary>The cars all the lot's private garages hold together (<c>facts.garage_cars</c>).</summary>
    public static readonly MarkDefinition GarageCars = new(
        "Gordium: Garage cars", new("08e37847-735e-417a-85fa-fb945a28276f"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.garage_cars",
        "A count: the cars the lot's private garages hold, all together: every private garage as §325-3B defines it below, attached or detached; 0 if there is none (a carport isn't enclosed). " +
        "Zoning chart, Private garage, note 6: \"For not more than three cars.\" §325-3B GARAGE, PRIVATE: \"An enclosed space for the storage of one or more motor vehicles, provided that no business, occupation or service is conducted for profit therein.\" " +
        "A whole number, 0 or more. Blank: the garage rule needs review.");

    /// <summary>The private garages on the lot (<c>facts.private_garages</c>), asked only once the cars are over three.</summary>
    public static readonly MarkDefinition PrivateGarages = new(
        "Gordium: Private garages", new("92d7674d-e182-407c-a43b-2acb0146265b"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.private_garages",
        "A count: with more than three garage cars, the private garages on the lot, an attached garage counted. " +
        "Zoning chart, Private garage, note 6: \"For not more than three cars.\" Whether that limits each garage or all of them together is an open question, so cars spread over garages of three or fewer each need a person's check. A whole number, 1 or more. Blank: the garage rule needs review when the cars are over three.");

    /// <summary>The <see cref="GroundFrom"/> words and the <c>grade_from</c> each sends.</summary>
    public static IReadOnlyList<(string Word, string GradeFrom)> GroundWords => [("Spot grades", "spot"), ("Finished spot grades", "finished_spots")];
    /// <summary>A level the architect says has no rooms at all (a roof, a turret's top: Revit finds enclosed areas
    /// there between walls and parapets). Yes: its enclosed areas with no Room aren't sent as spaces whose use isn't
    /// known; a Room drawn on it disagrees, and is listed first as a conflict (the tick then doesn't count). Blank or
    /// No: its enclosed areas with no Room are each sent so, and every sleeping-room rule needs review.</summary>
    public static readonly MarkDefinition NoRoomsOnLevel = new(
        "Gordium: No rooms on this level", new("c8cc09e8-00ce-4e4b-a27a-4c2d23410a02"), MarkValueKind.YesNo, MarkBinding.Instance,
        [Levels], "unknown_spaces (an enclosed area with no Room on a level ticked Yes isn't one)",
        "Yes for a level with no rooms at all (a roof, the top of a turret). Its enclosed areas with no Room are then not treated as rooms nobody drew; a Room drawn on it is listed as a conflict. Blank or No: each enclosed area with no Room on it keeps every sleeping-room rule needing review.");

    // ---- step 6: what the house has none of (design note, sections 2 and 4; HasNone) ------------------------------
    // One Yes/No on Project Information per kind: the three kinds the description lists itself (an empty list says
    // none) and every kind of the format's has_none (model_measurement.interior.has_none.KINDS). Yes is sent only when
    // nothing of that kind is drawn and nothing could hide one; No or unset: not stated, that kind not read.

    private static MarkDefinition NoneTick(string name, string guid, string feeds, string what) => new(
        "Gordium: This house has no " + name, new(guid), MarkValueKind.YesNo, MarkBinding.Instance, [ProjectInformation], feeds,
        $"Yes when the house has no {what} at all (however drawn). Sent only when nothing of the kind is drawn and nothing " +
        "could hide one. Blank or No: not stated, so its egress rules need review.");

    public static readonly MarkDefinition NoStairs = NoneTick("stairs", "a1f4e4bd-612e-4ac3-8f40-29734e304311", "stairs: []", "stairs");
    public static readonly MarkDefinition NoDoors = NoneTick("doors", "06f6906a-a8b1-4ca9-81bc-f073346c5bad", "doors: []", "doors");
    public static readonly MarkDefinition NoGuards = NoneTick("guards", "8ba873c3-cea1-4adc-b301-52e61ba9c1a4", "guards: []",
                                                               "guards (at a floor's edge or along a stair)");
    public static readonly MarkDefinition NoBasements = NoneTick("basements", "a96ef278-0a0e-4787-b2ed-0f5e3fd4e693",
                                                                  "has_none: basement", "basement");
    public static readonly MarkDefinition NoHabitableAttics = NoneTick("habitable attics", "bccc5c23-d42d-47cf-bd62-0c45311db280",
                                                                        "has_none: habitable_attic", "habitable attic");
    public static readonly MarkDefinition NoSleepingLofts = NoneTick("sleeping lofts", "348c128f-c23b-40af-a0ea-2b1acaa45d46",
                                                                      "has_none: sleeping_loft", "sleeping loft");
    public static readonly MarkDefinition NoRamps = NoneTick("ramps", "6aad2ebe-4051-49b2-bae3-e531d9d620f4", "has_none: ramp", "ramp");
    public static readonly MarkDefinition NoAlternatingTreadDevices = NoneTick(
        "alternating tread devices", "3e807c15-9890-4ed0-9f16-98ee891af0f1", "has_none: alternating_tread_device",
        "alternating tread device");
    // no apostrophe in a parameter's name: "ship ladders" (the format's "ship's ladders")
    public static readonly MarkDefinition NoShipLadders = NoneTick("ship ladders", "0249580f-f83a-431e-9e59-9e9e5a542066",
                                                                    "has_none: ships_ladder", "ship's ladder");
    public static readonly MarkDefinition NoPatioCovers = NoneTick("patio covers", "0b28269f-ee8a-4939-b3ed-2ac97d6b44d1",
                                                                    "has_none: patio_cover", "patio cover");
    public static readonly MarkDefinition NoProjectionOverEscapeOpening = NoneTick(
        "deck or porch or cantilever over an escape opening", "820cd2d1-5b6d-416d-afa8-01cb1f0c4515",
        "has_none: deck_porch_or_cantilever_over_escape_opening", "deck, porch or cantilever over any escape opening");
    public const string Floors = "OST_Floors";

    /// <summary>What a site slab is (reading design note, section 1, "Site slabs"): on a Floor under none of the
    /// house's walls or roofs, which Revit can't tell from a porch. Read only on such a floor (<see cref="SiteSlabs"/>);
    /// unset, the rows it could change need review.</summary>
    public static readonly MarkDefinition SiteSlab = new(
        "Gordium: Site slab is", new("56113427-6ae6-430d-95dd-2472fbefff71"), MarkValueKind.Text, MarkBinding.Instance,
        [Floors], "buildings (a porch...) or left_out[].slab",
        "For a floor outside the house (under none of its walls or roofs), what it is, one of: " +
        string.Join(", ", SlabKinds.Words) + ". A porch, deck, landing or ramp counts in lot coverage and the yards; " +
        "a patio, terrace or walk (less than 18 in above grade, no roof) and parking or a driveway don't count in lot " +
        "coverage. Blank: lot coverage and the yards need review.");

    public const string GenericModels = "OST_GenericModel";
    public const string StairsCategory = "OST_Stairs";

    /// <summary>The categories a structure standing apart from the house is drawn in when it isn't drawn as the building
    /// (a freestanding deck, a landing, a shed drawn as a Generic Model, a family or an in-place family): what
    /// <see cref="SiteObject"/> is bound to. Every one is a model category that takes bound parameters in Revit 2025 to
    /// 2027 (to check on the trial: "Mark for egress" binds them). An element of another category standing apart keeps
    /// the yards needing review, unmarked (it can't be cleared); Planting and Entourage need no mark
    /// (<see cref="SiteReader.NotStructures"/>).</summary>
    public static readonly IReadOnlyList<string> SiteObjectCategories =
    [
        GenericModels, "OST_SpecialityEquipment", "OST_Site", "OST_Mass", "OST_Furniture", "OST_Casework",
        "OST_StructuralFraming", "OST_StructuralFoundation", "OST_Parking",
        // review round 1: an AC condenser or a site light standing apart holds every yard; the architect can clear it
        "OST_MechanicalEquipment", "OST_LightingFixtures",
    ];

    /// <summary>An element the architect says is not a stair, a stair's part or a guard (Ben, 2026-11-20, Q2: a real
    /// model's wall niches, corbels and trim drawn as Generic Models; Pacific Continental has 19). Yes: that element no
    /// longer stops the stairs (and guards) being read, and each one cleared is listed in the marking list and the Read
    /// inside log. Bound to every category whose other elements could be a stair (Generic Models, Stairs, Railings),
    /// but it never clears a Revit Stair, Railing or multistory stair: Yes on one is a conflict, listed first, and the
    /// element is read as what it is. Blank or No: not stated, so it still stops the stairs being read.</summary>
    public static readonly MarkDefinition NotAStair = new(
        "Gordium: Not a stair", new("6f527562-6b18-467b-9e86-5a2c5489dbc2"), MarkValueKind.YesNo, MarkBinding.Instance,
        [GenericModels, StairsCategory, Railings], "stairs and guards (a cleared element doesn't stop them being read)",
        "Yes for a generic model or family that is not a stair, a stair's part or a guard (a wall niche, a corbel, trim): " +
        "it then doesn't stop the stairs being read, and is listed as cleared by you. Never clears a Revit Stair or Railing. " +
        "Blank or No: it could be a stair drawn another way, so no stair is read for egress.");

    /// <summary>What an object on the lot that isn't the building is (reading design note, section 1, "Objects standing
    /// apart"): a freestanding deck, porch, landing or ramp drawn as a Generic Model or a family is "part of the
    /// building in both the determination of required yards and lot coverage" (§325-18A), and no other building or
    /// structure may occupy a yard (§325-3B YARD), so one standing apart from the house keeps the yards needing review
    /// until it says what it is. Its words (<see cref="SiteObjectKinds"/>): a porch, deck, landing or ramp, or a garage,
    /// shed or carport (an accessory building, §325-25), each measured as a building; or "Not a structure" (STRUCTURE:
    /// "Anything constructed or erected on the ground"; a bench, a sculpture set on the lawn). Never the slab words
    /// (review round 1): a patio or a driveway leaves every check, so those are read on Floors only (site slabs), where
    /// the shape is a slab; a garage drawn as a Generic Model and marked "Parking" must never vanish from the
    /// check.</summary>
    public static readonly MarkDefinition SiteObject = new(
        "Gordium: Site object is", new("2f1ba96f-363b-4bdb-a03c-832fad615857"), MarkValueKind.Text, MarkBinding.Instance,
        SiteObjectCategories, "buildings (a porch, a garage...) or left_out[].could_be_building",
        "For a generic model or family on the lot that isn't part of the house's walls, floors or roof, what it is, one of: " +
        SiteObjectKinds.Listed + ". A porch, deck, landing or ramp, or a garage, shed or carport, is measured as a " +
        "building (lot coverage and the yards); not a structure keeps no yard waiting. A patio, walk or driveway is a " +
        "floor's word (Gordium: Site slab is), not read here. Blank: one standing apart from the house keeps the yards " +
        "needing review.");

    /// <summary>Every mark, in the design note's order.</summary>
    public static readonly IReadOnlyList<MarkDefinition> All =
    [
        SleepingRoom, EscapeOpening, ExitDoor, Operation, ClearWidth, ClearHeight, ClearOffset, ClearSource,
        ClearConfirmed, TopRailIsHandrail, AllStairs, AllGuards, Zone, Use, LotSurveyed, CornerLot, StreetEdge, GroundFrom,
        NoStairs, NoDoors, NoGuards, NoBasements, NoHabitableAttics, NoSleepingLofts, NoRamps, NoAlternatingTreadDevices,
        NoShipLadders, NoPatioCovers, NoProjectionOverEscapeOpening, NoRoomsOnLevel, NotAStair, SiteSlab, SiteObject,
        CanBeLocked, PassThrough, Exit, Stories, NotOccupied, RoomFunction,
        FollowsBuildingCode, StoriesAboveGradePlane, SeparateMeansOfEgress, TownhouseUnits, CareFacility, OccupancyGroups,
        SprinklerSystem, AssemblyFixedSeating, SpecialEgressSpaces, MerchandisePads, EgressBalconyIncrease, R2SleepingUnits,
        EscapeOpenings1031, Atrium, OccupiedOutdoorAreas, OccupantLoadIncreased, OtherLevelsReachCorridors,
        AmbulatoryCareFacility, CorridorsWithinDwellingUnits, EmergencyVoiceAlarm, HighRiseBuilding, UndergroundBuilding,
        DwellingUnits, UnitsInAttachedBuilding, HomeOccupation, RoomsLetForProfit, AccessoryDwellingUnit,
        AduDetached, AdusOnParcel,
        StreamNearLot, StreamDistance, UnrelatedPersons, OwnerOccupied, FunctionalFamilyUnit, GarageCars, PrivateGarages,
        AbutsR1, Conversion, PrimaryBuildings, PrimaryBuildingsSameUse, HomeOccupationArea, HomeOccupationUnitArea,
        AduExistingBuilding, AduBedrooms, AduFloorArea, MainBuildingFloorArea,
        DoorLeaves,
    ];

    /// <summary>What a number typed in a mark means, said before it is typed, true wherever it is read: "count" for a
    /// whole number; "length" for a length, typed in the project's length units in Revit's dialogs and the Setup form
    /// alike (the form's label names the unit: <see cref="LengthUnits"/>); null for a mark that takes no number.</summary>
    public static string? Unit(MarkDefinition m) => m.Kind switch
    {
        MarkValueKind.Length => "length",
        MarkValueKind.Area => "area",
        MarkValueKind.Integer => "count",
        _ => null,
    };

    /// <summary>The words every length mark's tooltip opens with: in Revit's own dialogs a number is read in the
    /// project's length units, so the tooltip never names one unit (review round 2 of change 20: "In feet" was false in
    /// a meters project, where 15 typed is 15 m).</summary>
    public const string LengthWords = "A length, in this project's length units";

    /// <summary>The words every area mark's tooltip opens with: in Revit's own dialogs an area is read in the project's
    /// area units, so the tooltip never names one unit.</summary>
    public const string AreaWords = "An area, in this project's area units";

    // ---- reading a mark: an unset mark is "not stated", never a default (principle 4) -----------------------------

    /// <summary>A Yes/No mark: true or false only when Revit says it has a value (<c>Parameter.HasValue</c>) stored as
    /// 1 or 0; anything else (not on the element, never set, another storage) is null: not stated.</summary>
    public static bool? YesNo(MarkValue? v) =>
        v is { HasValue: true, Integer: 1 } ? true : v is { HasValue: true, Integer: 0 } ? false : null;

    /// <summary>A text mark, trimmed; null when not stated or blank.</summary>
    public static string? Text(MarkValue? v) =>
        v is { HasValue: true, Text: { } t } && !string.IsNullOrWhiteSpace(t) ? t.Trim() : null;

    /// <summary>A whole-number mark (Revit's Integer); null when not stated. Never 0 for blank: an unset Integer
    /// parameter's AsInteger() is 0 with HasValue false.</summary>
    public static int? Count(MarkValue? v) => v is { HasValue: true, Integer: { } n } ? n : null;

    /// <summary>A length mark (feet); null when not stated or not a finite number. Never 0 for blank.</summary>
    public static double? Length(MarkValue? v) =>
        v is { HasValue: true, Number: { } d } && double.IsFinite(d) ? d : null;

    /// <summary>An area mark (square feet, Revit's internal unit); null when not stated or not a finite number. Never 0
    /// for blank.</summary>
    public static double? Area(MarkValue? v) => Length(v);
}

/// <summary>The architect-facing operation list (the <c>Gordium: Operation</c> mark), each word through a fixed table
/// to the interior description's own word: the openings list and the doors list use different words
/// (docs/interior/interior_description_format.md). A word not in the table is not stated, never a near guess.</summary>
public static class Operations
{
    /// <summary>Architect's word → (the opening's word, the door's word or null when it isn't a door's operation).</summary>
    private static readonly (string Word, string Opening, string? Door)[] Table =
    [
        ("Casement", "casement", null),
        ("Double hung", "double_hung", null),
        ("Single hung", "single_hung", null),
        ("Horizontal slider", "horizontal_slider", null),
        ("Awning", "awning", null),
        ("Hopper", "hopper", null),
        ("Pivot", "pivot", null),
        ("Tilt-turn", "tilt_turn", null),
        ("Fixed", "fixed", null),
        ("Side-hinged door", "side_hinged_door", "side_hinged"),
        ("Sliding door", "sliding_door", "sliding"),
        // the openings list has no folding or pocket word: "other", which needs the maker's clear opening
        ("Folding door", "other", "folding"),
        ("Pocket door", "other", "pocket"),
        ("Other", "other", "other"),
    ];

    /// <summary>The words the architect may type, in the list's order.</summary>
    public static IReadOnlyList<string> Words { get; } = Table.Select(t => t.Word).ToList();

    private static int Find(string? word) =>
        word is null ? -1 : Array.FindIndex(Table, t => string.Equals(t.Word, word.Trim(), StringComparison.OrdinalIgnoreCase));

    /// <summary>The opening's operation (<c>openings[].operation</c>) for the architect's word, or null.</summary>
    public static string? ForOpening(string? word) => Find(word) is var i and >= 0 ? Table[i].Opening : null;

    /// <summary>The opening's operation for a window (any word in the list) or a door (a door's word only: a window's
    /// word on a door, "Casement", is not stated, never a window's operation, which would read the door as not a
    /// door). The one rule the reader and the marking list both use.</summary>
    public static string? ForOpening(string? word, bool isDoor) =>
        isDoor && ForDoor(word) is null ? null : ForOpening(word);

    /// <summary>The door's operation (<c>doors[].operation</c>), or null (a window's word on a door is not a door's
    /// operation: not stated).</summary>
    public static string? ForDoor(string? word) => Find(word) is var i and >= 0 ? Table[i].Door : null;
}

/// <summary>A fixed table from the architect's word to the interior description's own (trimmed, any case): a word not
/// in it is not stated, never a near guess. The room uses and the exit kinds (escape routes).</summary>
public sealed class WordTable(params (string Word, string Described)[] table)
{
    /// <summary>The words the architect may type, in the list's order.</summary>
    public IReadOnlyList<string> Words { get; } = table.Select(t => t.Word).ToList();

    /// <summary>The words as the architect reads them in a sentence.</summary>
    public string Listed => string.Join(", ", Words);

    /// <summary>The description's word for the architect's, or null.</summary>
    public string? Of(string? word) =>
        word is null ? null
        : Array.FindIndex(table, t => string.Equals(t.Word, word.Trim(), StringComparison.OrdinalIgnoreCase)) is var i and >= 0
            ? table[i].Described : null;

    /// <summary>The architect's word for the description's.</summary>
    public string WordFor(string described) => table.First(t => t.Described == described).Word;
}

/// <summary>A room's use (<c>Gordium: Use</c> on a Room) → <c>rooms[].use</c> (the route code's <c>USES</c>).</summary>
public static class RoomUses
{
    public static WordTable Table { get; } = new(
        ("Corridor", "corridor"), ("Lobby", "lobby"), ("Day care", "day_care"), ("Accessory storage", "accessory_storage"),
        ("Kitchen", "kitchen"), ("Toilet", "toilet"), ("Closet", "closet"), ("Workroom", "workroom"), ("Other", "other"));

    public static IReadOnlyList<string> Words => Table.Words;
}

/// <summary>A room's function (<c>Gordium: Function</c> on a Room) → <c>rooms[].function</c>: BCNYS Table 1004.5's rows
/// in its order (the BCNYS rulebook's records/occupant_load_factors.yaml <c>functions</c>, each with its factor), each
/// in words close to the table's own.</summary>
public static class RoomFunctions
{
    public static WordTable Table { get; } = new(
        ("Accessory storage or mechanical equipment room", "accessory_storage_mechanical"), ("Agricultural building", "agricultural"),
        ("Aircraft hangar", "aircraft_hangar"), ("Airport baggage claim", "airport_baggage_claim"),
        ("Airport baggage handling", "airport_baggage_handling"), ("Airport concourse", "airport_concourse"),
        ("Airport waiting area", "airport_waiting"), ("Gaming floor", "gaming_floor"),
        ("Exhibit gallery or museum", "exhibit_gallery_museum"), ("Assembly with fixed seats", "assembly_fixed_seats"),
        ("Assembly concentrated (chairs only, not fixed)", "assembly_concentrated"), ("Assembly standing space", "assembly_standing"),
        ("Assembly unconcentrated (tables and chairs)", "assembly_unconcentrated"), ("Bowling center", "bowling_center"),
        ("Business area", "business"), ("Concentrated business use area", "concentrated_business"),
        ("Courtroom (other than fixed seating)", "courtroom"), ("Day care", "day_care"), ("Dormitory", "dormitory"),
        ("Classroom", "classroom"), ("Shop or vocational room", "vocational_shop"), ("Exercise room", "exercise_room"),
        ("Group H-5 fabrication or manufacturing area", "h5_fabrication"), ("Industrial area", "industrial"),
        ("Information technology equipment facility", "information_technology"), ("Inpatient treatment area", "inpatient_treatment"),
        ("Outpatient area", "outpatient"), ("Institutional sleeping area", "institutional_sleeping"),
        ("Commercial kitchen", "commercial_kitchen"), ("Library reading room", "library_reading_room"),
        ("Library stack area", "library_stack"), ("Locker room", "locker_room"), ("Mall building (covered or open)", "mall"),
        ("Mercantile", "mercantile"), ("Storage, stock or shipping area", "storage_stock_shipping"),
        ("Parking garage", "parking_garage"), ("Residential", "residential"), ("Rink or pool", "rink_pool"),
        ("Rink or pool deck", "pool_deck"), ("Stage or platform", "stage_platform"), ("Warehouse", "warehouse"));

    public static IReadOnlyList<string> Words => Table.Words;

    /// <summary>The row a typed word names: one of the words, or the row's own id ("business", "day_care"), in any case;
    /// null for anything else. The id is read as its row (review round 8: sent as typed, the checker matched it to its
    /// row while the add-in said it wasn't one, and "Business" in capitals didn't match), and always sent as the id.</summary>
    public static string? Of(string? word) =>
        Table.Of(word) ?? (word is null ? null
            : Table.Words.Select(w => Table.Of(w)!).FirstOrDefault(id => string.Equals(id, word.Trim(), StringComparison.OrdinalIgnoreCase)));

    /// <summary>The words in a sentence: separated by semicolons, since some hold a comma.</summary>
    public static string Listed => string.Join("; ", Table.Words);
}

/// <summary>The occupancy groups <c>Gordium: Occupancy groups</c> takes (BCNYS Chapter 3; code_scope.GROUPS).</summary>
public static class OccupancyGroupWords
{
    public static IReadOnlyList<string> Words { get; } =
        ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2", "I-3",
         "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"];

    public static string Listed => string.Join(", ", Words);

    /// <summary>The groups typed, each as the book writes it, or null when any word isn't a group (nothing sent).</summary>
    public static IReadOnlyList<string>? Parse(string text)
    {
        var got = text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(p => Words.FirstOrDefault(w => string.Equals(w, p, StringComparison.OrdinalIgnoreCase))).ToList();
        return got.Count > 0 && got.All(g => g is not null) ? got.Select(g => g!).Distinct().ToList() : null;
    }
}

/// <summary>What a Group R-2's units are (<c>Gordium: R-2 sleeping units</c>) → <c>building.r2_sleeping_units</c>: all
/// sleeping units sends true, all dwelling units false, both sends nothing (not stated: both tables' rows need review).</summary>
public static class R2UnitWords
{
    public const string Both = "both";

    public static WordTable Table { get; } = new(
        ("All sleeping units", "true"), ("All dwelling units", "false"), ("Both", Both));
}

/// <summary>The sprinkler systems <c>Gordium: Sprinkler system</c> takes → <c>building.sprinkler_system</c>.</summary>
public static class SprinklerWords
{
    public static WordTable Table { get; } = new(
        ("None", "none"), ("NFPA 13", "nfpa_13"), ("NFPA 13R", "nfpa_13r"), ("NFPA 13D", "nfpa_13d"));
}

/// <summary>Which exit a door is (<c>Gordium: Exit</c>) → <c>doors[].exit_kind</c>, IBC 2009 1016.1's own list (the
/// route code's <c>EXIT_KINDS</c>).</summary>
public static class ExitKinds
{
    public const string Discharge = "exterior_at_discharge";
    public const string Enclosure = "exit_enclosure";
    public const string Passageway = "exit_passageway";
    public const string Horizontal = "horizontal_exit";
    public const string OutsideStair = "exterior_stair_or_ramp";

    public static WordTable Table { get; } = new(
        ("Exterior door at discharge", Discharge), ("Exit stair enclosure", Enclosure), ("Exit passageway", Passageway),
        ("Horizontal exit", Horizontal), ("Exterior exit stair or ramp", OutsideStair));

    public static IReadOnlyList<string> Words => Table.Words;

    public static string Listed => Table.Listed;
}

/// <summary>What a site slab is, as Chapter 325 sorts it (§325-3B BUILDING AREA, §325-18A, TERRACE OR PATIO).</summary>
public enum SlabKind
{
    /// <summary>A porch, deck, landing or ramp: "part of the building in both the determination of required yards and
    /// lot coverage" (§325-18A), so read as a building.</summary>
    Building,

    /// <summary>A patio, terrace or walk: "exempt from total lot coverage requirements", but one "above grade" may not
    /// be in a required yard (§325-3B). A walk is read as one: §325-3B has no walk, and TERRACE OR PATIO is "a level
    /// plane or surfaced patio ... less than 18 inches above grade, without a roof" (GREEN SPACE names "sidewalks or
    /// patios" together).</summary>
    Patio,

    /// <summary>A parking area, parking space or driveway: building area "shall not include parking areas and parking
    /// spaces" (§325-3B).</summary>
    Parking,
}

/// <summary>The words the architect may type in <c>Gordium: Site slab is</c>, each to its kind through a fixed table:
/// a word not in it is not stated, never a near guess.</summary>
public static class SlabKinds
{
    private static readonly (string Word, SlabKind Kind)[] Table =
    [
        ("Porch", SlabKind.Building), ("Deck", SlabKind.Building), ("Landing", SlabKind.Building), ("Ramp", SlabKind.Building),
        ("Patio", SlabKind.Patio), ("Terrace", SlabKind.Patio), ("Walk", SlabKind.Patio),
        ("Parking", SlabKind.Parking), ("Driveway", SlabKind.Parking),
    ];

    /// <summary>The words, in the list's order.</summary>
    public static IReadOnlyList<string> Words { get; } = Table.Select(t => t.Word).ToList();

    /// <summary>The kind for the architect's word (trimmed, any case), or null.</summary>
    public static SlabKind? Of(string? word) =>
        word is null ? null
        : Array.FindIndex(Table, t => string.Equals(t.Word, word.Trim(), StringComparison.OrdinalIgnoreCase)) is var i and >= 0
            ? Table[i].Kind : null;

    /// <summary>The site description's word for a slab left out (<c>left_out[].slab</c>): null for a building.</summary>
    public static string? Described(SlabKind? kind) => kind switch
    {
        null => "unmarked",
        SlabKind.Patio => "patio",
        SlabKind.Parking => "parking",
        _ => null,
    };
}

/// <summary>What <c>Gordium: Site object is</c> says an element is (review round 1: never a slab kind, which would let
/// a garage marked "Parking" leave every check).</summary>
public enum SiteObjectKind
{
    /// <summary>A porch, deck, landing or ramp (part of the building, §325-18A), or a garage, shed or carport (an
    /// accessory building, §325-25): measured as a building.</summary>
    Building,

    /// <summary>Not "constructed or erected on the ground" (§325-3B STRUCTURE): no yard waits on it; still an object
    /// on the lot not measured.</summary>
    NotAStructure,
}

/// <summary>The words the architect may type in <c>Gordium: Site object is</c>, through a fixed table: a word not in it
/// (a slab's "Patio" or "Driveway" too: read on Floors only) is not stated, never a near guess.</summary>
public static class SiteObjectKinds
{
    public const string NotAStructureWord = "Not a structure";
    public const string AccessoryWord = "Garage, shed or carport";

    private static readonly (string Word, SiteObjectKind Kind)[] Table =
    [
        ("Porch", SiteObjectKind.Building), ("Deck", SiteObjectKind.Building), ("Landing", SiteObjectKind.Building),
        ("Ramp", SiteObjectKind.Building), (AccessoryWord, SiteObjectKind.Building),
        (NotAStructureWord, SiteObjectKind.NotAStructure),
    ];

    /// <summary>The words, in the list's order.</summary>
    public static IReadOnlyList<string> Words { get; } = Table.Select(t => t.Word).ToList();

    /// <summary>The words as the architect reads them in a sentence (one of them holds commas).</summary>
    public static string Listed { get; } = string.Join(" / ", Table.Select(t => t.Word));

    /// <summary>The kind for the architect's word (trimmed, any case), or null.</summary>
    public static SiteObjectKind? Of(string? word) =>
        word is null ? null
        : Array.FindIndex(Table, t => string.Equals(t.Word, word.Trim(), StringComparison.OrdinalIgnoreCase)) is var i and >= 0
            ? Table[i].Kind : null;
}
