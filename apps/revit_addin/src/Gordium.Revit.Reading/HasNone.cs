using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>One kind the architect can tick "this house has none of" (design note, sections 2 and 4; section 7, step 6).</summary>
/// <param name="Kind">The description's word for it: a list the format has itself (<c>stairs</c>, <c>doors</c>,
/// <c>guards</c>: sent as an empty list), or a kind of the format's <c>has_none</c> (<c>ramp</c>…: sent as a claim).</param>
/// <param name="Mark">Its tick on Project Information.</param>
/// <param name="Words">The plural, as the architect reads it ("ramps").</param>
/// <param name="IsList">True for a list the format has itself; false for a <c>has_none</c> claim.</param>
public sealed record NoneKind(string Kind, MarkDefinition Mark, string Words, bool IsList);

/// <summary>One tick, read: what the architect said, what drawn contradicts it, what could hide one, and what the reader
/// itself found (a proposal, shown only: never sent without the tick).</summary>
/// <param name="Kind">The kind ticked.</param>
/// <param name="Ticked">The tick: true (Yes), false (No) or null (not set: not stated, never No).</param>
/// <param name="Conflicts">What is drawn that the tick says isn't there (a stair in a house ticked "no stairs").</param>
/// <param name="Blockers">What could hide one: while any is there the tick isn't sent.</param>
/// <param name="Found">What the reader looked for and found none of ("no Ramp elements in the model"), or null when the
/// reader can't look for this kind (a basement, a patio cover: the architect's tick alone).</param>
public sealed record NoneTick(NoneKind Kind, bool? Ticked, IReadOnlyList<string> Conflicts, IReadOnlyList<string> Blockers, string? Found)
{
    /// <summary>Sent: ticked Yes, nothing drawn contradicts it, nothing could hide one.</summary>
    public bool Sent => Ticked is true && Conflicts.Count == 0 && Blockers.Count == 0;

    /// <summary>Where the claim comes from, as the format asks: who ticked it, and what the reader found.</summary>
    public string Source =>
        $"ticked by the architect ({Kind.Mark.Name}: Yes, on Project Information)" + (Found is null ? "" : "; " + Found);

    /// <summary>Why the kind isn't sent as none, in the architect's words (empty when it is sent).</summary>
    public IReadOnlyList<string> WhyNot =>
        Sent ? []
        : Ticked is not true ? [$"{Kind.Mark.Name} is {(Ticked is false ? "No" : "not set")} on Project Information"]
        : [.. Conflicts.Select(c => $"{Kind.Mark.Name} is Yes, but {c}: they disagree, so neither is read as none"),
           .. Blockers.Select(b => $"{Kind.Mark.Name} is Yes, but isn't sent while this could hide one: {b}")];
}

/// <summary>
/// What the house has none of (section 7, step 6 of docs/revit/revit_interior_reading_design.md): the architect's
/// ticks on Project Information, one per kind, read into the description only when ticked Yes, nothing of the kind is
/// drawn and nothing could hide one. The rules are the note's section 2: nothing found is never "none" (no tick, no
/// empty list); an unset tick is not stated, never No; a tick that contradicts what is drawn is never sent, and the
/// marking list puts it first. For a list the format has itself the claim is the empty list (<c>stairs: []</c>); for
/// every other kind, an entry of <c>has_none</c> whose source names the tick and what the reader found.
/// </summary>
public static class HasNone
{
    public static readonly NoneKind Stairs = new("stairs", Marks.NoStairs, "stairs", true);
    public static readonly NoneKind Doors = new("doors", Marks.NoDoors, "doors", true);
    public static readonly NoneKind Guards = new("guards", Marks.NoGuards, "guards", true);

    /// <summary>The format's <c>has_none</c> kinds, exactly <c>model_measurement.interior.has_none.KINDS</c> (a test
    /// reads them from Python).</summary>
    public static readonly IReadOnlyList<NoneKind> Claims =
    [
        new("basement", Marks.NoBasements, "basements", false),
        new("habitable_attic", Marks.NoHabitableAttics, "habitable attics", false),
        new("sleeping_loft", Marks.NoSleepingLofts, "sleeping lofts", false),
        new("ramp", Marks.NoRamps, "ramps", false),
        new("alternating_tread_device", Marks.NoAlternatingTreadDevices, "alternating tread devices", false),
        new("ships_ladder", Marks.NoShipLadders, "ship's ladders", false),
        new("patio_cover", Marks.NoPatioCovers, "patio covers", false),
        new("deck_porch_or_cantilever_over_escape_opening", Marks.NoProjectionOverEscapeOpening,
            "decks, porches or cantilevers over an escape opening", false),
    ];

    /// <summary>Every kind, the lists first, in the marks' order.</summary>
    public static readonly IReadOnlyList<NoneKind> All = [Stairs, Doors, Guards, .. Claims];

    public static bool? Tick(RevitModel model, NoneKind kind) =>
        Marks.YesNo(model.ProjectMarks.TryGetValue(kind.Mark.Guid, out var v) ? v : null);

    /// <summary>One tick, read. <paramref name="stairs"/> is what the flights made of the railings beside them (null
    /// when the stairs weren't read): a railing on a stair counts as a handrail only when read so (the guards').</summary>
    public static NoneTick Read(RevitModel model, NoneKind kind, StairReader.RailingUse? stairs = null)
    {
        var tick = Tick(model, kind);
        var conflicts = new List<string>();
        var blockers = new List<string>();
        string? found = null;
        var records = model.Interior;
        if (records is null)
            return new(kind, tick, [], ["the model's inside wasn't read"], null);
        bool InDesign(string? demolished, string? option) => SiteReader.InDesignChecked(model, demolished, option);
        switch (kind.Kind)
        {
            case "stairs":
                if (records.Stairs is null)
                    blockers.Add("the stairs couldn't be read");
                foreach (var s in (records.Stairs ?? []).Where(s => InDesign(s.PhaseDemolished, s.DesignOption)))
                    conflicts.Add($"stair \"{s.Name ?? s.UniqueId}\" is drawn");
                if (MarkReading.AllStairs(model) is false)
                    conflicts.Add($"{Marks.AllStairs.Name} is No (a stair not drawn as a Revit stair)");
                blockers.AddRange(StairReader.Blockers(model));
                found = "no Revit stair in the model";
                break;
            case "doors":
                foreach (var d in MarkReading.Doors(model))
                    conflicts.Add($"door {Label(model, d.Id)} is drawn");
                blockers.AddRange(InteriorReader.OpeningsNotRead(model));
                blockers.AddRange(Hidden(model));
                found = "no door in the model";
                break;
            case "guards":
                if (records.Railings is null)
                    blockers.Add("the railings couldn't be read");
                foreach (var r in (records.Railings ?? []).Where(r => InDesign(r.PhaseDemolished, r.DesignOption)))
                    if (!(records.Stairs ?? []).Any(s => StairReader.OnStair(s, r)))
                        conflicts.Add($"railing \"{r.Name ?? r.UniqueId}\" is drawn on no stair (a guard)");
                if (MarkReading.AllGuards(model) is false)
                    conflicts.Add($"{Marks.AllGuards.Name} is No (a guard or handrail not drawn as a railing)");
                // a railing on a stair not read as a handrail beside a wall may be a guard along the stair
                blockers.AddRange(GuardReader.Blockers(model, stairs));
                found = "no railing off a stair in the model";
                break;
            case "ramp":
                if (records.Ramps is null)
                    blockers.Add("the ramps couldn't be read");
                foreach (var r in (records.Ramps ?? []).Where(r => InDesign(r.PhaseDemolished, r.DesignOption)))
                    conflicts.Add($"ramp \"{r.Name ?? r.UniqueId}\" is drawn");
                foreach (var link in records.Links.Where(l => l.Loaded && l.Ramps > 0))
                    blockers.Add($"linked model \"{link.Name}\" holds {link.Ramps} ramp(s): a linked model's ramps aren't read");
                // a ramp, a ladder or a device drawn as a generic model, an in-place family or in a link
                blockers.AddRange(StairReader.Blockers(model));
                found = "no Ramp elements in the model";
                break;
            case "alternating_tread_device" or "ships_ladder":
                blockers.AddRange(StairReader.Blockers(model));
                break;
            case "basement" or "habitable_attic" or "sleeping_loft":
                // a space: every room must be read, so the checker can hold the claim against them (a room within
                // another's height refuses "no sleeping lofts"; a floor below the ground, "no basements")
                blockers.AddRange(InteriorReader.RoomsNotRead(model));      // its closed worksets and links too
                blockers.AddRange(Hidden(model, worksetsAndLinks: false));
                break;
            default:                                        // a patio cover; a deck, porch or cantilever over an opening
                blockers.AddRange(Hidden(model));
                break;
        }
        return new(kind, tick, conflicts.Distinct().ToList(), blockers.Distinct().ToList(), found);
    }

    /// <summary>Every tick, read (the lists, then the claims).</summary>
    public static IReadOnlyList<NoneTick> ReadAll(RevitModel model, StairReader.RailingUse? stairs = null) =>
        All.Select(k => Read(model, k, stairs)).ToList();

    /// <summary>The <c>has_none</c> entries to send (the claims ticked and sent), or null when there are none.</summary>
    public static JsonArray? Entries(IEnumerable<NoneTick> ticks) =>
        ticks.Where(t => !t.Kind.IsList && t.Sent).Select(t => (JsonNode)new JsonObject
        {
            ["kind"] = t.Kind.Kind, ["source"] = t.Source,
        }).ToArray() is { Length: > 0 } entries ? new JsonArray(entries) : null;

    /// <summary>The tick's record for the evidence (what was ticked, sent, contradicted or in the way).</summary>
    public static JsonObject Evidence(NoneTick t) => new()
    {
        ["ticked"] = t.Ticked,
        ["sent"] = t.Sent,
        ["found"] = t.Found,
        ["conflicts"] = new JsonArray(t.Conflicts.Select(c => (JsonNode?)c).ToArray()),
        ["blockers"] = new JsonArray(t.Blockers.Select(b => (JsonNode?)b).ToArray()),
    };

    /// <summary>What could hide anything: a closed workset, an unloaded link, a link's own links (unless
    /// <paramref name="worksetsAndLinks"/> is false: the caller lists them itself), a coordination model.</summary>
    private static IEnumerable<string> Hidden(RevitModel model, bool worksetsAndLinks = true)
    {
        foreach (var w in model.UserWorksets.Where(w => worksetsAndLinks && !w.IsOpen))
            yield return $"Workset \"{w.Name}\" is closed: one could be in it (open it)";
        foreach (var link in worksetsAndLinks ? model.Interior?.Links ?? [] : [])
        {
            if (!link.Loaded)
                yield return $"Linked model \"{link.Name}\" isn't loaded: one could be in it";
            else if (link.HasLinks)
                yield return $"Linked model \"{link.Name}\" holds links of its own, which aren't read: one could be in one";
        }
        if (model.Interior is { CoordinationModels: > 0 } r)
            yield return $"{r.CoordinationModels} coordination model(s) linked: what is in one isn't read";
    }

    private static string Label(RevitModel model, string id) =>
        model.Marked.FirstOrDefault(e => e.UniqueId == id) is { } e ? $"\"{MarkingList.Label(e)}\"" : id;
}
