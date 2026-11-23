namespace Gordium.Revit.Reading;

// The architect's marks (docs/revit/revit_interior_reading_design.md, section 3; Ben, 2026-11-19, decision 1):
// Gordium's shared parameters, added to a project by the add-in on first use (MarkSetup). Written here as data, so
// the Revit layer only copies them into Revit, and the tests read the same list.

/// <summary>What a mark holds (the Revit layer maps each to its <c>SpecTypeId</c>: <c>Boolean.YesNo</c>,
/// <c>String.Text</c>, <c>Length</c>, <c>Int.Integer</c>).</summary>
public enum MarkValueKind { YesNo, Text, Length, Integer }

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
        "The maker's net clear opening width, as the maker publishes it for egress. For a door, measured as R318.2 " +
        "measures it: between the face of the door open 90 degrees and the stop (never the door's size or its rough opening).");

    public static readonly MarkDefinition ClearHeight = new(
        "Gordium: Clear height", new("8a8a2307-84a5-4a36-9121-c21453707702"), MarkValueKind.Length, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear.height, doors[].stated_clear.height",
        "The maker's net clear opening height, as the maker publishes it for egress. For a door, measured as R318.2 " +
        "measures it: from the top of the threshold to the bottom of the stop.");

    public static readonly MarkDefinition ClearOffset = new(
        "Gordium: Clear offset", new("07f4d517-54a6-4e39-ba85-90c299137a28"), MarkValueKind.Length, MarkBinding.Type,
        [Windows], "openings[].stated_clear.bottom",
        "The height of the clear opening's bottom above the window's sill line (where Sill Height places it). Blank is not 0: no clear opening is sent.");

    public static readonly MarkDefinition ClearSource = new(
        "Gordium: Clear source", new("2bc7eaef-1770-4077-870b-450ed224adde"), MarkValueKind.Text, MarkBinding.Type,
        [Windows, Doors], "openings[].stated_clear.source, doors[].stated_clear.source",
        "The maker's publication the clear opening came from (catalogue, product line, hardware option).");

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
        "The building's number of stories as the City of Ithaca counts them (§325-3B STORY: from one floor level to the next floor or the roof; counted at the main entrance side, §325-8A Column 8). " +
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
        "The building's stories above grade plane as the NYS Residential Code counts them (R202 STORY ABOVE GRADE PLANE: a story whose floor is entirely above grade plane, or whose floor above is more than 6 ft above grade plane, more than 12 ft above the finished ground at any point, or more than 6 ft above the finished ground for more than half the perimeter; a habitable attic counts, R316.3). " +
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

    // ---- the dwelling's own facts which New York code needs (code_scope.py) and Ithaca's zoning reads too: sent as
    // the lot facts of the same names (host_core.facts.STATED_FACTS), each only when set (unset is not stated)

    /// <summary>The dwelling units on this lot (<c>facts.dwelling_units</c>), 1 or more.</summary>
    public static readonly MarkDefinition DwellingUnits = new(
        "Gordium: Dwelling units", new("aa32131a-e757-47a3-abf8-9deb81d7a09a"), MarkValueKind.Integer, MarkBinding.Instance,
        [ProjectInformation], "facts.dwelling_units",
        "The dwelling units on this lot (a building split along its party walls onto several lots: this lot's units only), an accessory dwelling unit not counted (Gordium: Accessory dwelling unit says it). A whole number, 1 or more. Blank: the use's own count (one for a detached one-family dwelling).");

    /// <summary>The dwelling units in the whole attached building, every lot it stands on (<c>facts.attached_units_in_building</c>).</summary>
    public static readonly MarkDefinition UnitsInAttachedBuilding = new(
        "Gordium: Units in the attached building", new("bccb088a-c087-475f-9ff9-53fd10133d0e"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.attached_units_in_building",
        "For an attached one-family dwelling (one_family_attached): the dwelling units in the whole attached building, every lot it stands on (§325-3B: three to six), 1 or more. It decides whether the building is a townhouse (RCNYS R202: three or more townhouse units). Blank: which code governs needs review.");

    /// <summary>Whether a home occupation is planned (<c>facts.home_occupation</c>).</summary>
    public static readonly MarkDefinition HomeOccupation = new(
        "Gordium: Home occupation", new("c6a7cf3a-28b8-4c18-98f2-cf34215901bf"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.home_occupation",
        "Yes when a home occupation is planned (§325-3B: a business, studio or office run by a resident in the dwelling unit); then which code governs needs a person's check (a live/work unit, BCNYS 508.5). No: none. Blank: Gordium assumes none and says so.");

    /// <summary>The rooms let for profit (<c>facts.rooms_let_for_profit</c>), 0 or more.</summary>
    public static readonly MarkDefinition RoomsLetForProfit = new(
        "Gordium: Rooms let for profit", new("2f038e8d-2d26-4e46-b92a-1c51d08bca87"), MarkValueKind.Integer,
        MarkBinding.Instance, [ProjectInformation], "facts.rooms_let_for_profit",
        "The rooms let for profit (to roomers) in the building, 0 or more; with any, the Residential Code covers it only when owner-occupied with five or fewer guestrooms and a sprinkler system (RCNYS R101.2 item 6). Blank: Gordium assumes none and says so.");

    /// <summary>Whether an accessory dwelling unit is on the lot (<c>facts.accessory_dwelling_unit</c>).</summary>
    public static readonly MarkDefinition AccessoryDwellingUnit = new(
        "Gordium: Accessory dwelling unit", new("6fcbf10d-a1c2-406a-b6c7-e726b4a695f2"), MarkValueKind.YesNo,
        MarkBinding.Instance, [ProjectInformation], "facts.accessory_dwelling_unit",
        "Yes when an accessory dwelling unit (§325-3B, §325-28) is on the lot, attached or detached; then say whether it is detached (Gordium: ADU detached). No: none. Blank: Gordium assumes none and says so.");

    /// <summary>The accessory dwelling units on the parcel (<c>facts.adus_on_parcel</c>), 1 or more.</summary>
    public static readonly MarkDefinition AdusOnParcel = new(
        "Gordium: ADUs on parcel", new("1fa82254-92d5-4f27-acef-924bfc047d7c"), MarkValueKind.Integer, MarkBinding.Instance,
        [ProjectInformation], "facts.adus_on_parcel",
        "With an accessory dwelling unit on the lot: the accessory dwelling units on the parcel, any already there included (§325-28C(1): one per parcel), 1 or more. More than one keeps which code governs at needs review (each may be one more of the building's units, RCNYS R202 DWELLING). Blank: Gordium assumes one, the one stated, and says so.");

    /// <summary>Whether the accessory dwelling unit is detached (<c>facts.adu_detached</c>).</summary>
    public static readonly MarkDefinition AduDetached = new(
        "Gordium: ADU detached", new("ebd07d28-ce47-4e7d-95e7-6e164d7d7bc8"), MarkValueKind.YesNo, MarkBinding.Instance,
        [ProjectInformation], "facts.adu_detached",
        "Yes when the accessory dwelling unit is in its own building; No when it is in or on the main building, where it is one more of the building's dwelling units (RCNYS R202 DWELLING: one or two). Blank, with an ADU on the lot: which code governs needs review.");

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
        CanBeLocked, PassThrough, Exit, Stories, NotOccupied,
        FollowsBuildingCode, StoriesAboveGradePlane, SeparateMeansOfEgress, TownhouseUnits, CareFacility, OccupancyGroups,
        SprinklerSystem, DwellingUnits, UnitsInAttachedBuilding, HomeOccupation, RoomsLetForProfit, AccessoryDwellingUnit,
        AduDetached, AdusOnParcel,
    ];

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
