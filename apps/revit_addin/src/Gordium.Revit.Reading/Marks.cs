namespace Gordium.Revit.Reading;

// The architect's marks (docs/revit/revit_interior_reading_design.md, section 3; Ben, 2026-11-19, decision 1):
// Gordium's shared parameters, added to a project by the add-in on first use (MarkSetup). Written here as data, so
// the Revit layer only copies them into Revit, and the tests read the same list.

/// <summary>What a mark holds (the Revit layer maps each to its <c>SpecTypeId</c>: <c>Boolean.YesNo</c>,
/// <c>String.Text</c>, <c>Length</c>).</summary>
public enum MarkValueKind { YesNo, Text, Length }

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

    public const string GenericModels = "OST_GenericModel";
    public const string StairsCategory = "OST_Stairs";

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

    /// <summary>Every mark, in the design note's order.</summary>
    public static readonly IReadOnlyList<MarkDefinition> All =
    [
        SleepingRoom, EscapeOpening, ExitDoor, Operation, ClearWidth, ClearHeight, ClearOffset, ClearSource,
        ClearConfirmed, TopRailIsHandrail, AllStairs, AllGuards,
        NoStairs, NoDoors, NoGuards, NoBasements, NoHabitableAttics, NoSleepingLofts, NoRamps, NoAlternatingTreadDevices,
        NoShipLadders, NoPatioCovers, NoProjectionOverEscapeOpening, NoRoomsOnLevel, NotAStair,
    ];

    // ---- reading a mark: an unset mark is "not stated", never a default (principle 4) -----------------------------

    /// <summary>A Yes/No mark: true or false only when Revit says it has a value (<c>Parameter.HasValue</c>) stored as
    /// 1 or 0; anything else (not on the element, never set, another storage) is null: not stated.</summary>
    public static bool? YesNo(MarkValue? v) =>
        v is { HasValue: true, Integer: 1 } ? true : v is { HasValue: true, Integer: 0 } ? false : null;

    /// <summary>A text mark, trimmed; null when not stated or blank.</summary>
    public static string? Text(MarkValue? v) =>
        v is { HasValue: true, Text: { } t } && !string.IsNullOrWhiteSpace(t) ? t.Trim() : null;

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
