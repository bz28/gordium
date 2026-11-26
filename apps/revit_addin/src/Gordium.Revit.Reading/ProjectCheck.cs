using System.Globalization;
using System.Text.Json.Nodes;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>The one check_site request "Check my project" sends: the site description (the outside), the lot facts
/// (the architect's marks on Project Information) and the interior description (the inside).</summary>
public sealed record ProjectRequest(JsonObject Site, JsonObject Facts, JsonObject Interior);

/// <summary>What "Check my project" read, ready to send, or why nothing is sent.</summary>
/// <param name="Request">The request, or null when a fact is missing (nothing is sent: principle 4).</param>
/// <param name="Missing">Exactly what the architect must fill in, in the architect's words (empty when sent).</param>
/// <param name="PhaseChecked">The phase checked (the last one), the same for the outside and the inside.</param>
/// <param name="OptionsChecked">Each design option set's option checked, the same for both.</param>
/// <param name="Inside">The interior read (its not-read lists for the dialog), or null when nothing was read.</param>
/// <param name="Street">The street line sent, in words ("the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)"), so
/// every result names the street it was checked against; null when nothing was sent.</param>
/// <param name="StreetRefused">Why the street edge kept wasn't sent, typed (<see cref="StreetEdges.NeedsNewPick"/>).</param>
public sealed record ProjectPrepared(ProjectRequest? Request, IReadOnlyList<string> Missing, string? PhaseChecked,
                                     IReadOnlyList<string> OptionsChecked, InteriorReadResult? Inside, string? Street = null,
                                     StreetRefusal StreetRefused = StreetRefusal.None)
{
    /// <summary>A check sent anyway (the Setup form's "Check now anyway"): the facts not set, or holding what Gordium
    /// can't read, that were left out, so the rules each decides need review (SetupWords.SentWithout says how).</summary>
    public IReadOnlyList<MarkDefinition> NotStated { get; init; } = [];
}

/// <summary>
/// "Check my project" without Revit (reading design note, section 9): the architect's own open project read outside
/// (<see cref="SiteReader"/>) and inside (<see cref="InteriorReader"/>), with the lot facts from Gordium's marks on
/// Project Information (<see cref="ProjectFacts"/>), as one check_site request. A fact missing, or a street edge that
/// isn't an edge of the lot read, and no request is made: the dialog lists what to fill in, never a check on a guess.
/// </summary>
public static class ProjectCheck
{
    /// <summary>Reads both models (the same document, read once by each Revit layer) into one request.
    /// <paramref name="outside"/> is RevitRead's model (elements, lot lines), <paramref name="inside"/> RevitInterior's
    /// (marks, Project Information, the interior records). Refused (<see cref="ReadRefusedException"/>) when the two
    /// don't name the same phases and design options: the outside and the inside must be the same design.</summary>
    /// <remarks><c>anyway</c>: the architect's "Check now anyway" (the Setup form): sent with what is stated, every
    /// fact not set (or holding what Gordium can't read) left out and listed (<see cref="ProjectPrepared.NotStated"/>), so
    /// each rule it decides needs review; never without the zone, which chooses the rules.</remarks>
    public static async Task<ProjectPrepared> PrepareAsync(RevitModel outside, RevitModel inside, ILeftOutAsker asker,
                                                           CancellationToken cancel = default, bool anyway = false)
    {
        ArgumentNullException.ThrowIfNull(outside);
        ArgumentNullException.ThrowIfNull(inside);
        ArgumentNullException.ThrowIfNull(asker);
        if (SameDesign(outside, inside) is { } differs)
            throw new ReadRefusedException("the outside and the inside weren't read in the same design (" + differs +
                                           "): nothing is sent; click Check project again");
        var read = ProjectFacts.Read(inside);
        var building = BuildingFacts.Read(inside);
        IReadOnlyList<string> missing = [.. read.Missing, .. building.Missing];
        if (missing.Count > 0 && !(anyway && read.Facts["zone"] is not null))
            return new ProjectPrepared(null, missing, null, [], null);
        // sent anyway: a building fact Gordium can't read goes as typed, so the code decision says it can't read it
        // (needs review), never takes it as not stated; it is listed with the facts left out
        IReadOnlyList<MarkDefinition> notStated = missing.Count > 0 ? [.. SetupFacts.NotSent(inside, read), .. building.NotRead] : [];

        // everything read from the records before the first await, on the caller's thread (Revit's: a lot line's
        // points call back into the API; SiteReader reads the lot before it asks the worker anything)
        var interior = InteriorReader.Read(inside);
        if (building.Building is { } said)       // which New York code governs: the architect's statements, as given
            interior.Interior["building"] = said;
        // sent anyway: only the lot facts whose mark holds a value Gordium couldn't send (a count under its least) are
        // named, so the code decision reads each as stated and unread, never as not stated (code_scope.py
        // facts_not_sent; review round 5); a mark simply not set (a blank Use) is not stated, and the decision asks for
        // it as such (review round 6)
        var unsent = notStated.Where(m => inside.ProjectMarks.TryGetValue(m.Guid, out var v) && v.HasValue)
                              .Select(m => m.Feeds).Where(f => f.StartsWith("facts.", StringComparison.Ordinal))
                              .Select(f => (JsonNode)f["facts.".Length..].Split(' ')[0].TrimEnd(',')).ToList();
        if (unsent.Count > 0)
        {
            var block = interior.Interior["building"] as JsonObject ?? new JsonObject();
            block["facts_not_sent"] = new JsonArray([.. unsent]);
            interior.Interior["building"] = block;
        }
        var site = await SiteReader.DescribeAsync(outside, read.Facts, asker, cancel).ConfigureAwait(false);
        var match = read.StreetEdges is { } kept ? StreetEdges.Match(kept, site.Site["lot"] as JsonObject, outside.InternalToShared) : null;
        // a kept edge no longer on the lot is asked for again, anyway too: anyway leaves out only what isn't set
        if (match is not null && match.StreetLine is null)
            return new ProjectPrepared(null, [match.Why!], site.PhaseChecked, site.OptionsChecked, null, StreetRefused: match.Reason);
        var facts = read.Facts.DeepClone().AsObject();
        if (match?.StreetLine is { } line)
            facts["street_line"] = line;
        return new ProjectPrepared(new ProjectRequest(site.Site, facts, interior.Interior), [], site.PhaseChecked,
                                   site.OptionsChecked, interior, match?.Words) { NotStated = notStated };
    }

    /// <summary>The one check_site: the site, the facts and the interior, together.</summary>
    public static Task<CheckResult> SendAsync(WorkerClient worker, ProjectRequest request, CancellationToken cancel = default,
                                              TimeSpan? silence = null, IProgress<string>? step = null)
    {
        ArgumentNullException.ThrowIfNull(worker);
        ArgumentNullException.ThrowIfNull(request);
        return worker.CheckSiteAsync(request.Site, request.Facts, interior: request.Interior, cancel: cancel, silence: silence, step: step,
                                     total: silence is { } s ? CheckFailures.Ceiling(s) : null);
    }

    /// <summary>Why the two reads aren't of the same design (phases, option sets, the option being edited), or null.</summary>
    internal static string? SameDesign(RevitModel a, RevitModel b)
    {
        if (!a.Phases.SequenceEqual(b.Phases))
            return "their phases differ";
        if (a.ActiveOption != b.ActiveOption)
            return "the design option being edited differs";
        static string Sets(RevitModel m) => string.Join("|", m.OptionSets.OrderBy(s => s.Id, StringComparer.Ordinal)
            .Select(s => s.Id + ":" + string.Join(",", s.Options.OrderBy(o => o.Id, StringComparer.Ordinal)
                .Select(o => o.Id + (o.IsPrimary ? "*" : "")))));
        return Sets(a) == Sets(b) ? null : "their design option sets differ";
    }
}

/// <summary>The interior description's <c>building</c> block, from the marks on Project Information that say which
/// New York code governs the building and what the Building Code's egress rules read (design_checker/code_scope.py
/// FACTS): each only when set, so an unset one is not stated. <see cref="Building"/> is null when none is set (the
/// description is then exactly as before). A word that isn't one of a mark's words, or a count under 1, is listed in
/// <see cref="Missing"/> and nothing is sent: never sent as something near it.</summary>
public sealed record BuildingFactsRead(JsonObject? Building, IReadOnlyList<string> Missing)
{
    /// <summary>The marks holding what Gordium can't read (each also in <see cref="Missing"/>, and in
    /// <see cref="Building"/> as typed, so a check sent anyway says it can't read it).</summary>
    public IReadOnlyList<MarkDefinition> NotRead { get; init; } = [];
}

/// <summary>Reads <see cref="BuildingFactsRead"/> from the marks.</summary>
public static class BuildingFacts
{
    private const string Where = " on Project Information (Manage > Project Information)";

    public static BuildingFactsRead Read(RevitModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        var missing = new List<string>();
        var notRead = new List<MarkDefinition>();
        var b = new JsonObject();
        MarkValue? Get(MarkDefinition m) => model.ProjectMarks.TryGetValue(m.Guid, out var v) ? v : null;
        foreach (var (mark, key) in new[] { (Marks.FollowsBuildingCode, "follows_building_code"),
                     (Marks.SeparateMeansOfEgress, "separate_means_of_egress"), (Marks.TownhouseUnits, "townhouse_units"),
                     (Marks.CareFacility, "care_facility"),
                     // what the Building Code's Chapter 10 rules read of the whole building (code_scope.FACTS)
                     (Marks.AssemblyFixedSeating, "assembly_fixed_seating"), (Marks.SpecialEgressSpaces, "special_egress_spaces"),
                     (Marks.MerchandisePads, "merchandise_pads"), (Marks.EgressBalconyIncrease, "egress_balcony_increase_taken"),
                     (Marks.Atrium, "building_has_atrium"),
                     // group 2's (Table 1006.3.4 note a): a Group R-2's escape openings per 1031
                     (Marks.EscapeOpenings1031, "emergency_escape_openings_1031"),
                     // group 3's: outdoor areas the occupants use (1004.7), and 1004.5.1's increased occupant load
                     (Marks.OccupiedOutdoorAreas, "occupied_outdoor_areas"), (Marks.OccupantLoadIncreased, "occupant_load_increased"),
                     // groups 4 and 5's: corridors (1020) and egress capacity (1005.3)
                     (Marks.OtherLevelsReachCorridors, "other_level_egress_into_corridors"),
                     (Marks.AmbulatoryCareFacility, "ambulatory_care_facility"),
                     (Marks.CorridorsWithinDwellingUnits, "corridors_within_dwelling_units"),
                     (Marks.EmergencyVoiceAlarm, "emergency_voice_alarm_system"),
                     // the occupant loads' ceiling: a mezzanine adds its occupants to the room below (1004.2.2)
                     (Marks.Mezzanines, "mezzanines"), (Marks.LoadsNotByArea, "loads_not_by_area") })
        {
            var v = Get(mark);
            if (Marks.YesNo(v) is { } yes)
                b[key] = yes;
            else if (v is { HasValue: true })
            {
                // set, but neither Yes nor No: asked again, never read as not stated; sent anyway as held, so the
                // check says it can't read it (code_scope._given: a yes/no fact that isn't one needs review)
                b[key] = v.Integer is { } n ? JsonValue.Create(n) : JsonValue.Create(v.Text ?? "not Yes or No");
                notRead.Add(mark);
                missing.Add($"{mark.Name} holds a value that isn't Yes or No: tick Yes or No, or leave it blank{Where}.");
            }
        }
        if (Marks.Count(Get(Marks.StoriesAboveGradePlane)) is { } stories)
        {
            if (stories < 1)
            {
                missing.Add($"{Marks.StoriesAboveGradePlane.Name} is {stories.ToString(CultureInfo.InvariantCulture)}: type " +
                            $"the stories above grade plane, 1 or more, or leave it blank{Where}.");
                notRead.Add(Marks.StoriesAboveGradePlane);
            }
            b["stories_above_grade_plane"] = stories;
        }
        if (Marks.Text(Get(Marks.OccupancyGroups)) is { } groups)
        {
            if (OccupancyGroupWords.Parse(groups) is { } parsed)
                b["occupancy_groups"] = new JsonArray([.. parsed.Select(g => (JsonNode)g)]);
            else
            {
                b["occupancy_groups"] = groups;
                notRead.Add(Marks.OccupancyGroups);
                missing.Add($"{Marks.OccupancyGroups.Name} is \"{groups}\": type the Building Code's groups separated by " +
                            $"commas ({OccupancyGroupWords.Listed}), or leave it blank{Where}.");
            }
        }
        // what a Group R-2's units are (Table 1006.3.4's notes b and c): all sleeping units true, all dwelling units
        // false, both nothing (not stated: both tables' rows need review); another word asked again, sent as typed
        if (Marks.Text(Get(Marks.R2SleepingUnits)) is { } units)
        {
            if (R2UnitWords.Table.Of(units) is { } word)
            {
                if (word != R2UnitWords.Both)
                    b["r2_sleeping_units"] = word == "true";
            }
            else
            {
                b["r2_sleeping_units"] = units;
                notRead.Add(Marks.R2SleepingUnits);
                missing.Add($"{Marks.R2SleepingUnits.Name} is \"{units}\": type one of {R2UnitWords.Table.Listed}, or leave it blank{Where}.");
            }
        }
        if (Marks.Text(Get(Marks.SprinklerSystem)) is { } system)
        {
            if (SprinklerWords.Table.Of(system) is { } word)
                b["sprinkler_system"] = word;
            else
            {
                b["sprinkler_system"] = system;
                notRead.Add(Marks.SprinklerSystem);
                missing.Add($"{Marks.SprinklerSystem.Name} is \"{system}\": type one of {SprinklerWords.Table.Listed}, or " +
                            $"leave it blank{Where}.");
            }
        }
        return new BuildingFactsRead(b.Count > 0 ? b : null, missing) { NotRead = notRead };
    }
}

/// <summary>The lot facts as Gordium's marks on Project Information give them.</summary>
/// <param name="Facts">The facts to send (jurisdiction, zone, use, lot_surveyed, and corner_lot, grade_from and
/// stories when set); street_line is added once the lot is read (<c>StreetEdges.Match</c>).</param>
/// <param name="StreetEdges">The street edges picked (Revit's internal coordinates), or null when not set.</param>
/// <param name="Missing">What to fill in; empty when every required fact is stated.</param>
public sealed record ProjectFactsRead(JsonObject Facts, IReadOnlyList<KeptEdge>? StreetEdges, IReadOnlyList<string> Missing);

/// <summary>The lot facts from the marks. Gordium checks the City of Ithaca only (CLAUDE.md: first city), so the
/// jurisdiction is fixed. Every required fact (the checker's own list, host_core.facts.REQUIRED: zone, use,
/// street_line, lot_surveyed) unset, and it is listed as missing; an unset optional one (corner lot, the ground, the
/// stories) is not sent, so the rows it decides need review.</summary>
public static class ProjectFacts
{
    public const string Jurisdiction = "regulations/jurisdictions/new_york/ithaca_city";

    private const string Where = " on Project Information (Manage > Project Information)";

    /// <summary>The street edge not set, as the panel lists it.</summary>
    public static readonly string StreetNotSet = $"{Marks.StreetEdge.Name}: click the lot edge along the street when Check " +
                                                 "project asks (in a plan or site view; with no property line drawn, draw it first).";

    public static ProjectFactsRead Read(RevitModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        var missing = new List<string>();
        var facts = new JsonObject { ["jurisdiction"] = Jurisdiction };
        MarkValue? Get(MarkDefinition m) => model.ProjectMarks.TryGetValue(m.Guid, out var v) ? v : null;

        if (Marks.Text(Get(Marks.Zone)) is { } zone)
            facts["zone"] = zone;
        else
            missing.Add($"{Marks.Zone.Name}: type the lot's zoning district as the City's zoning map writes it (R-1b, R-2a...){Where}.");
        if (Marks.Text(Get(Marks.Use)) is { } use)
            facts["use"] = use;
        else
            missing.Add($"{Marks.Use.Name}: type what the building is used for, in Gordium's word (one_family_detached...){Where}.");
        if (Marks.YesNo(Get(Marks.LotSurveyed)) is { } surveyed)
            facts["lot_surveyed"] = surveyed;
        else
            missing.Add($"{Marks.LotSurveyed.Name}: tick Yes if the property line is drawn from a survey, No if from the tax map{Where}.");
        if (Marks.YesNo(Get(Marks.CornerLot)) is { } corner)
            facts["corner_lot"] = corner;
        var ground = Marks.Text(Get(Marks.GroundFrom));
        if (ground is not null)
        {
            var word = Marks.GroundWords.FirstOrDefault(w => string.Equals(w.Word, ground, StringComparison.OrdinalIgnoreCase));
            if (word.Word is null)
                missing.Add($"{Marks.GroundFrom.Name} is \"{ground}\": type one of " +
                            string.Join(" or ", Marks.GroundWords.Select(w => w.Word)) + $", or leave it blank{Where}.");
            else
                facts["grade_from"] = word.GradeFrom;
        }
        // the architect's count of stories (optional): sent as their statement, which the measuring keeps only within
        // what the drawing allows; a count under 1 is no count of stories, and is asked again, never sent
        if (Marks.Count(Get(Marks.Stories)) is { } stories)
        {
            if (stories < 1)
                missing.Add($"{Marks.Stories.Name} is {stories.ToString(CultureInfo.InvariantCulture)}: type the number " +
                            $"of stories, 1 or more, or leave it blank{Where}.");
            else
                facts["stories"] = stories;
        }
        // the dwelling's own facts (optional; which New York code governs reads them, and Ithaca's zoning): each sent
        // as stated, a count under its least asked again, never sent
        foreach (var (mark, key, least) in new[] { (Marks.DwellingUnits, "dwelling_units", 1),
                     (Marks.UnitsInAttachedBuilding, "attached_units_in_building", 1), (Marks.RoomsLetForProfit, "rooms_let_for_profit", 0),
                     (Marks.AdusOnParcel, "adus_on_parcel", 1) })
            if (Marks.Count(Get(mark)) is { } n)
            {
                if (n < least)
                    missing.Add($"{mark.Name} is {n.ToString(CultureInfo.InvariantCulture)}: type {least} or more, or leave it blank{Where}.");
                else
                    facts[key] = n;
            }
        foreach (var (mark, key) in new[] { (Marks.HomeOccupation, "home_occupation"),
                     (Marks.AccessoryDwellingUnit, "accessory_dwelling_unit"), (Marks.AduDetached, "adu_detached") })
            if (Marks.YesNo(Get(mark)) is { } yes)
                facts[key] = yes;
        // the house's own facts Ithaca's zoning reads (UI design change 20): each sent as stated; blank is not stated
        // (its rows need review, never No or 0); a value Gordium can't read, or under its least, is said and not sent
        foreach (var (mark, problem) in HouseFacts(model, facts))
            missing.Add($"{mark.Name} {problem}{Where}.");
        IReadOnlyList<KeptEdge>? edges = null;
        var street = Marks.Text(Get(Marks.StreetEdge));
        if (street is null)
            missing.Add(StreetNotSet);
        else if ((edges = StreetEdges.Parse(street)) is null)
            missing.Add($"{Marks.StreetEdge.Name} holds \"{street}\", which isn't an edge Gordium wrote: clear it, then " +
                        "click the lot edge along the street when Check project asks.");
        return new ProjectFactsRead(facts, edges, missing);
    }

    /// <summary>The house's own facts Ithaca's zoning reads and no drawing shows (UI design change 20), each with the
    /// lot fact it sends and the least it takes (a length: 0 or more feet).</summary>
    public static IReadOnlyList<(MarkDefinition Mark, string Key, int Least)> HouseFactMarks { get; } =
    [
        (Marks.StreamNearLot, "stream_near_lot", 0), (Marks.StreamDistance, "stream_distance", 0),
        (Marks.UnrelatedPersons, "unrelated_persons", 0), (Marks.OwnerOccupied, "owner_occupied", 0),
        (Marks.FunctionalFamilyUnit, "functional_family_unit", 0), (Marks.GarageCars, "garage_cars", 0),
        (Marks.PrivateGarages, "private_garages", 1),
        // the lot facts the worker's cards asked for with no mark to set (an area in square feet, a count, a yes/no)
        (Marks.AbutsR1, "abuts_r1_district", 0), (Marks.Conversion, "conversion", 0),
        (Marks.PrimaryBuildings, "primary_buildings", 1), (Marks.PrimaryBuildingsSameUse, "primary_buildings_same_use", 0),
        (Marks.HomeOccupationArea, "home_occupation_area", 0), (Marks.HomeOccupationUnitArea, "home_occupation_unit_area", 0),
        (Marks.AduExistingBuilding, "adu_existing_building", 0), (Marks.AduBedrooms, "adu_bedrooms", 0),
        (Marks.AduFloorArea, "adu_floor_area", 0), (Marks.MainBuildingFloorArea, "primary_floor_area", 0),
    ];

    /// <summary>Adds each house fact set to <paramref name="facts"/>, and returns the ones holding what Gordium can't
    /// send, each with why in plain words: a value of another kind than the mark's (a Yes/No that isn't 1 or 0, text in
    /// a number), a count under its least, a length or an area under 0 or not a number. A blank one is neither: not
    /// stated.</summary>
    public static IReadOnlyList<(MarkDefinition Mark, string Problem)> HouseFacts(RevitModel model, JsonObject? facts = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        var problems = new List<(MarkDefinition, string)>();
        var unit = LengthUnits.Of(model.DisplayUnits);          // a length's messages in the project's units, as it is typed
        var areaUnit = AreaUnits.Of(model.AreaDisplayUnits);    // an area's, likewise
        foreach (var (mark, key, least) in HouseFactMarks)
        {
            if (!model.ProjectMarks.TryGetValue(mark.Guid, out var v) || !v.HasValue)
                continue;                                         // not stated
            switch (mark.Kind)
            {
                case MarkValueKind.YesNo when Marks.YesNo(v) is { } yes:
                    if (facts is not null) facts[key] = yes;
                    break;
                case MarkValueKind.YesNo:
                    problems.Add((mark, "holds a value that isn't Yes or No: tick Yes or No, or leave it blank"));
                    break;
                case MarkValueKind.Integer when Marks.Count(v) is { } n && n >= least:
                    if (facts is not null) facts[key] = n;
                    break;
                case MarkValueKind.Integer when Marks.Count(v) is { } n:
                    problems.Add((mark, $"is {n.ToString(CultureInfo.InvariantCulture)}: type {least} or more, or leave it blank"));
                    break;
                case MarkValueKind.Integer:
                    problems.Add((mark, "holds a value that isn't a whole number: type a whole number, or leave it blank"));
                    break;
                case MarkValueKind.Length when Marks.Length(v) is { } feet && feet >= 0:
                    if (facts is not null) facts[key] = feet;
                    break;
                case MarkValueKind.Length when Marks.Length(v) is { } feet:
                    problems.Add((mark, $"is {LengthUnits.Shown(feet, unit)} {unit.Symbol}: type a length of 0 {unit.Symbol} or more, or leave it blank"));
                    break;
                // an area: square feet as Revit holds it (its internal unit), sent as is, never rounded
                case MarkValueKind.Area when Marks.Area(v) is { } squareFeet && squareFeet >= 0:
                    if (facts is not null) facts[key] = squareFeet;
                    break;
                case MarkValueKind.Area when Marks.Area(v) is { } squareFeet:
                    problems.Add((mark, $"is {LengthUnits.Shown(squareFeet, areaUnit)} {areaUnit.Symbol}: type an area of 0 {areaUnit.Symbol} or more, or leave it blank"));
                    break;
                case MarkValueKind.Area:
                    problems.Add((mark, $"holds a value that isn't an area: type an area in {areaUnit.Words}, or leave it blank"));
                    break;
                default:
                    problems.Add((mark, $"holds a value that isn't a length: type a length in {unit.Words}, or leave it blank"));
                    break;
            }
        }
        return problems;
    }

    /// <summary>Every write of a Gordium mark (the street pick's and a request file's) goes through here:
    /// <paramref name="set"/> is Revit's Parameter.Set, which says false when it didn't set the value; then it throws
    /// naming the mark, so nothing is checked or logged as set on a mark the project doesn't hold.</summary>
    public static void Write(MarkDefinition mark, string value, Func<bool> set)
    {
        ArgumentNullException.ThrowIfNull(mark);
        ArgumentNullException.ThrowIfNull(set);
        if (!set())
            throw new InvalidOperationException($"Revit didn't set {mark.Name} to {value}: nothing was checked");
    }

    /// <summary>A mark's value in a request file (check_project_request.json's "marks"), as Revit's Parameter.Set
    /// takes it: a Yes/No mark needs true or false (1 or 0), a whole-number mark a whole number (the Integer it is
    /// set to, returned where a Yes/No's 1 or 0 is), a text mark text. Anything else is refused naming the
    /// mark, never set as something near it: a check made on a mark the request didn't mean.</summary>
    public static (int? YesNo, string? Text) RequestValue(MarkDefinition mark, JsonNode? value)
    {
        ArgumentNullException.ThrowIfNull(mark);
        var v = value as JsonValue;
        switch (mark.Kind)
        {
            case MarkValueKind.YesNo when v is not null && v.TryGetValue<bool>(out var yes):
                return (yes ? 1 : 0, null);
            // a whole number given as a JSON number (never true, "3" or 3.5), set as Revit's Integer is set: AsInteger
            case MarkValueKind.Integer when v is not null && v.GetValueKind() == System.Text.Json.JsonValueKind.Number &&
                                            v.TryGetValue<int>(out var count):
                return (count, null);
            case MarkValueKind.Text when v is not null && v.TryGetValue<string>(out var text):
                return (null, text);
            default:
                throw new InvalidOperationException(
                    $"{mark.Name} is a {mark.Kind switch { MarkValueKind.YesNo => "Yes/No mark: give true or false", MarkValueKind.Text => "text mark: give text", MarkValueKind.Integer => "whole-number mark: give a whole number", _ => "length mark, which a request can't set" }}, " +
                    $"not {value?.ToJsonString() ?? "null"}: nothing was checked");
        }
    }
}

/// <summary>A lot edge picked as the street: its ends (internal coordinates), whether it is straight, and its length
/// (along the curve for a curved one); Mid, a point on it, halfway along (internal coordinates): with IsLine, what tells an arc
/// from its chord, or two arcs on the same ends, apart (review round 4).</summary>
public sealed record PickedEdge(Xyz A, Xyz B, bool IsLine, double Length, Xyz? Mid = null);

/// <summary>A street edge as the mark keeps it: its ends and, when Gordium wrote them (from round 4), whether it is
/// straight and its point halfway along. An older mark has the ends alone (<see cref="IsLine"/> null).</summary>
public sealed record KeptEdge(Xyz A, Xyz B, bool? IsLine = null, Xyz? Mid = null);

/// <summary>Whether "Check my project" asks for the street edge by a click now (<see cref="StreetEdges.Ask"/>).</summary>
public enum StreetAsk
{
    /// <summary>Kept and usable: nothing to ask.</summary>
    NotNeeded,
    /// <summary>Asked for now: every other fact is set and the view shows a property line.</summary>
    Pick,
    /// <summary>Not asked: other facts are missing (the panel lists them first).</summary>
    OtherFactsFirst,
    /// <summary>Not asked: the active view can't show the property line (the panel says to open a site plan).</summary>
    OpenAPlan,
    /// <summary>Not asked: the project being checked isn't the active one (the architect switched projects after
    /// clicking Check): a click would land in another project, so none is asked for (the panel says to switch).</summary>
    NotActive,
}

/// <summary>Why a kept street edge wasn't sent as a lot edge.</summary>
public enum StreetRefusal
{
    None,
    /// <summary>No lot edge has its ends (and kind and middle): the property line was changed.</summary>
    NoLongerAnEdge,
    /// <summary>More than one lot edge matches what was kept (an older mark with its ends alone, on a lot with an arc
    /// and its chord): which was meant can't be told.</summary>
    Ambiguous,
}

/// <summary>What <see cref="StreetEdges.Match(IReadOnlyList{KeptEdge}, JsonObject?, Transform3)"/> gives: the street
/// line to send, or why not (in words, and typed).</summary>
public sealed record StreetMatch(JsonArray? StreetLine, string? Why, StreetRefusal Reason)
{
    /// <summary>The street line sent, in words: each the lot edge matched, by its own points (a curved one by its
    /// length along them); a kept edge sent with no lot read, without a length.</summary>
    public string? Words { get; init; }

    public void Deconstruct(out JsonArray? streetLine, out string? why) => (streetLine, why) = (StreetLine, Why);
}

/// <summary>The street edges: picked by the architect on the property line (<see cref="Nearest"/>), kept in the
/// <see cref="Marks.StreetEdge"/> mark as their ends in Revit's internal coordinates (they don't move when the shared
/// coordinates are set again), and sent as the lot's own edges (<c>Match</c>): an edge the lot no longer has
/// (the property line redrawn) is asked for again, never sent as a street line no lot edge is.</summary>
public static class StreetEdges
{
    /// <summary>How near a picked point must be to an edge (ft): Revit puts the pick on the line itself.</summary>
    public const double PickReach = 1.0;

    /// <summary>How near a kept edge's ends must be to a lot edge's (ft).</summary>
    public const double Tolerance = 0.01;

    /// <summary>How near a kept edge's middle must be to a lot edge's (ft): a curved lot edge is sent as points
    /// <see cref="LotReader.ArcStep"/> apart, so its middle is found to within that.</summary>
    public const double MidTolerance = LotReader.ArcStep;

    private static string R(double v) => v.ToString("R", CultureInfo.InvariantCulture);

    /// <summary>The kept edges as the mark's text, "; " between (feet, internal): "x1 y1 x2 y2 line mx my" or
    /// "x1 y1 x2 y2 arc mx my" (its kind and its point halfway along); an edge with no middle known, the ends alone.</summary>
    public static string Format(IEnumerable<KeptEdge> edges) =>
        string.Join("; ", edges.Select(e => string.Join(" ", new[] { e.A.X, e.A.Y, e.B.X, e.B.Y }.Select(R))
            + (e.IsLine is { } line && e.Mid is { } m ? $" {(line ? "line" : "arc")} {R(m.X)} {R(m.Y)}" : "")));

    /// <summary>Ends alone (a lot line's own ends, as the log lists them; an older mark).</summary>
    public static string Format(IEnumerable<(Xyz A, Xyz B)> edges) => Format(edges.Select(e => new KeptEdge(e.A, e.B)));

    /// <summary>The mark's text as edges (an older mark's ends alone still read), or null when it isn't text
    /// <see cref="Format(IEnumerable{KeptEdge})"/> wrote.</summary>
    public static IReadOnlyList<KeptEdge>? Parse(string text)
    {
        var edges = new List<KeptEdge>();
        foreach (var part in text.Split(';'))
        {
            var v = part.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (v.Length != 4 && !(v.Length == 7 && v[4] is "line" or "arc"))
                return null;
            var idx = v.Length == 4 ? new[] { 0, 1, 2, 3 } : new[] { 0, 1, 2, 3, 5, 6 };
            var n = new double[7];
            foreach (var i in idx)
                if (!double.TryParse(v[i], NumberStyles.Float, CultureInfo.InvariantCulture, out n[i]) || !double.IsFinite(n[i]))
                    return null;
            if (n[0] == n[2] && n[1] == n[3])
                return null;
            edges.Add(v.Length == 4
                ? new KeptEdge(new Xyz(n[0], n[1], 0), new Xyz(n[2], n[3], 0))
                : new KeptEdge(new Xyz(n[0], n[1], 0), new Xyz(n[2], n[3], 0), v[4] == "line", new Xyz(n[5], n[6], 0)));
        }
        return edges.Count > 0 ? edges : null;
    }

    /// <summary>What PickObject's status bar says while the street edge is asked for.</summary>
    public const string PickPrompt = "Click the lot edge along the street (Esc to skip)";

    /// <summary>The words listed in the panel when the street edge is needed but the active view can't show it.</summary>
    public static readonly string OpenAPlan = $"{Marks.StreetEdge.Name}: open a site plan (or a floor plan) that shows the " +
                                              "property line, then click Check again: it asks you to click the lot edge along the street.";

    /// <summary>The same, said where Pick on plan was pressed in the Setup form: the next step is that button again.</summary>
    public static readonly string OpenAPlanFromSetup = $"{Marks.StreetEdge.Name}: open a site plan (or a floor plan) that " +
                                                       "shows the property line, then press Pick on plan again.";

    /// <summary>The title of the street edge pick's own dialogs (its confirmation, a click refused), wherever it was
    /// asked from (Check project or the Setup form's Pick on plan).</summary>
    public const string PickTitle = "Gordium: street edge";

    /// <summary>Whether to ask for the street edge now (Revit trial, 2026-11-20: asked from a sheet view, the pick
    /// waited with no prompt where no property line could be clicked). Only when the street edge is the one fact
    /// still to give (<paramref name="needed"/>: not set, or kept but no longer a lot edge) and every other fact is
    /// set, and only in a view that shows a property line (<paramref name="viewShowsPropertyLine"/>: a plan view
    /// with one visible). <see cref="StreetAsk.OpenAPlan"/>: the panel lists <see cref="OpenAPlan"/> instead.
    /// <paramref name="active"/>: whether the project being checked is the active one; when it isn't, never
    /// <see cref="StreetAsk.Pick"/> (<see cref="StreetAsk.NotActive"/>: a pick, and the mark it writes, would be in
    /// another project).</summary>
    public static StreetAsk Ask(ProjectFactsRead read, bool needed, bool viewShowsPropertyLine, bool active)
    {
        ArgumentNullException.ThrowIfNull(read);
        if (!needed)
            return StreetAsk.NotNeeded;
        if (read.Missing.Any(m => !m.StartsWith(Marks.StreetEdge.Name, StringComparison.Ordinal)))
            return StreetAsk.OtherFactsFirst;
        if (!active)
            return StreetAsk.NotActive;
        return viewShowsPropertyLine ? StreetAsk.Pick : StreetAsk.OpenAPlan;
    }

    /// <summary>What the panel lists for the street edge when the project checked wasn't the active one.</summary>
    public static readonly string SwitchToIt = $"{Marks.StreetEdge.Name}: this project wasn't the active one when " +
        "Gordium asked for its street edge (a click would have landed in another project): switch to it, open a site " +
        "plan that shows the property line, and click Check again.";

    // ---- the same refusals said where Pick on plan was pressed in the Setup form: the next step is that button ------

    /// <summary><see cref="SwitchToIt"/> from the Setup form's Pick on plan.</summary>
    public static readonly string SwitchToItFromSetup = $"{Marks.StreetEdge.Name}: this project isn't the active one (a " +
        "click would land in another project): switch to it, open a site plan that shows the property line, and press " +
        "Pick on plan again.";

    /// <summary>The project has no property line to pick, from the Setup form's Pick on plan.</summary>
    public static readonly string NoPropertyLineFromSetup = $"{Marks.StreetEdge.Name}: this project has no property line " +
        "to pick: draw it (Massing & Site > Property Line), then press Pick on plan again.";

    /// <summary>Esc pressed before any edge was kept, from the Setup form's Pick on plan.</summary>
    public const string NonePickedFromSetup = "No street edge was picked: press Pick on plan again to pick it.";

    /// <summary>Every message the Setup form's Pick on plan path can show before an edge is picked (the pick's own
    /// per-click words, <see cref="Nearest"/>'s, name no button): each names Pick on plan as the next step.</summary>
    public static IReadOnlyList<string> FromSetup => [OpenAPlanFromSetup, SwitchToItFromSetup, NoPropertyLineFromSetup, NonePickedFromSetup];

    /// <summary>What to fill in, as the panel lists it: when the view couldn't show the property line, the street
    /// edge's "click when Check project asks" replaced by <see cref="OpenAPlan"/> (a kept edge's own reason kept,
    /// <see cref="OpenAPlan"/> after it).</summary>
    public static IReadOnlyList<string> MissingAsShown(IReadOnlyList<string> missing, StreetAsk ask)
    {
        ArgumentNullException.ThrowIfNull(missing);
        if (ask is not (StreetAsk.OpenAPlan or StreetAsk.NotActive))
            return missing;
        var words = ask == StreetAsk.OpenAPlan ? OpenAPlan : SwitchToIt;     // NotActive: switch to it
        var shown = missing.Where(m => m != ProjectFacts.StreetNotSet).ToList();
        if (!shown.Contains(words))
            shown.Add(words);
        return shown;
    }

    /// <summary>Whether the refusal's fix is a new pick (the button then asks for the edge again).</summary>
    public static bool NeedsNewPick(ProjectPrepared prepared)
    {
        ArgumentNullException.ThrowIfNull(prepared);
        return prepared.Request is null && prepared.StreetRefused is StreetRefusal.NoLongerAnEdge or StreetRefusal.Ambiguous;
    }

    /// <summary>How near a corner a click is refused (ft): a click this near an end the edge shares with another can
    /// land on either edge (Revit highlights the whole property line, not the edge hit). A quarter of a shorter edge's
    /// length, so every edge keeps a middle that can be clicked.</summary>
    public const double CornerReach = 2.0;

    /// <summary>The edge of the property line nearest the point picked on it (plan distance, internal coordinates):
    /// its two ends, or why none: the pick off every edge; or at a corner (the two nearest edges within half
    /// <see cref="PickReach"/> of each other, or the click within <see cref="CornerReach"/> of an end the edge shares
    /// with another), where a click meant for one edge can keep the other; or a property line holding a curve with no
    /// ends, whose lot is never read.</summary>
    public static (PickedEdge? Edge, string? Why) Nearest(LotLineElement line, Xyz picked)
    {
        ArgumentNullException.ThrowIfNull(line);
        if (line.Unbound > 0)            // its lot is never read (LotReader.UnboundPropertyLine): no edge of it is kept
            return (null, "this property line has a curve with no ends (a full circle or ellipse drawn as one curve), " +
                          "which Gordium can't read as lot edges: redraw it as arcs, then pick the street edge");
        var near = line.Curves.Select(c => (Curve: c, D: PlanDistance(LotReader.Points(c), picked)))
                              .OrderBy(x => x.D).ToList();
        if (near.Count == 0 || near[0].D > PickReach)
            return (null, "the click wasn't on an edge of the property line: click on the edge along the street");
        const string corner = "the click was too near a corner, where it could be on either edge: click nearer the middle of the edge along the street";
        if (near.Count > 1 && near[1].D - near[0].D < PickReach / 2)
            return (null, corner);
        var c0 = near[0].Curve;
        var reach = Math.Min(CornerReach, (c0.IsLine ? Plan(c0.Start, c0.End) : c0.Length) / 4);
        foreach (var end in new[] { c0.Start, c0.End })
            if (Plan(end, picked) < reach && line.Curves.Any(c => !ReferenceEquals(c, c0)
                    && (Plan(c.Start, end) <= Tolerance || Plan(c.End, end) <= Tolerance)))
                return (null, corner);
        // its point halfway along: a line's midpoint; a curve's at half its normalised parameter (Curve.Evaluate)
        var mid = c0.IsLine || c0.PointAt is null ? 0.5 * (c0.Start + c0.End) : c0.PointAt(0.5);
        return (new PickedEdge(new Xyz(c0.Start.X, c0.Start.Y, 0), new Xyz(c0.End.X, c0.End.Y, 0), c0.IsLine,
                               c0.IsLine ? Plan(c0.Start, c0.End) : c0.Length, new Xyz(mid.X, mid.Y, 0)), null);
    }

    private static double Plan(Xyz a, Xyz b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    /// <summary>An edge as the architect confirms it: "the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)"; a curved
    /// one by its length along the curve, never its chord: "the curved 47.1 ft lot edge from ...". The coordinates
    /// as given (shared, for what is sent and shown); <paramref name="curvedLength"/> null for a straight edge.</summary>
    public static string Describe((double X, double Y) a, (double X, double Y) b, double? curvedLength = null) =>
        string.Create(CultureInfo.InvariantCulture,
            $"the {(curvedLength is null ? "" : "curved ")}{curvedLength ?? Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y)):0.0} ft lot edge from ({N(a.X)}, {N(a.Y)}) to ({N(b.X)}, {N(b.Y)})");

    /// <summary>A coordinate to a tenth, never "-0.0" (a point a hair below 0).</summary>
    private static string N(double v) => (Math.Round(v, 1) + 0.0).ToString("0.0", CultureInfo.InvariantCulture);

    /// <summary>A picked edge (internal coordinates) described in the shared coordinates the check uses.</summary>
    public static string Describe(PickedEdge edge, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(edge);
        ArgumentNullException.ThrowIfNull(toShared);
        Xyz a = toShared.Apply(edge.A), b = toShared.Apply(edge.B);
        return Describe((a.X, a.Y), (b.X, b.Y), edge.IsLine ? null : edge.Length);
    }

    /// <summary>The lot edge matched, in words: by its own points (a curved edge by its length along them).</summary>
    private static string Words(List<(double X, double Y)> pts, bool curved) =>
        curved ? Describe(pts[0], pts[^1], pts.Zip(pts.Skip(1), (p, q) => Math.Sqrt((p.X - q.X) * (p.X - q.X) + (p.Y - q.Y) * (p.Y - q.Y))).Sum())
               : Describe(pts[0], pts[^1]);

    /// <summary>A street edge sent as kept, matched to no lot edge: no length said (never the chord of an arc).</summary>
    private static string Unmatched((double X, double Y) a, (double X, double Y) b) => string.Create(CultureInfo.InvariantCulture,
        $"the street edge from ({N(a.X)}, {N(a.Y)}) to ({N(b.X)}, {N(b.Y)}), not matched to a lot (none was read)");

    /// <summary>Keeps the picked edges in the <see cref="Marks.StreetEdge"/> mark through <paramref name="set"/> (Revit's
    /// Parameter.Set, which says false when it didn't), and logs them only once set: never a street edge logged that
    /// the project doesn't hold.</summary>
    public static void Keep(IEnumerable<PickedEdge> edges, Func<string, bool> set, IDictionary<string, object?> log)
    {
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentNullException.ThrowIfNull(log);
        var text = Format(edges.Select(e => new KeptEdge(e.A, e.B, e.Mid is null ? null : e.IsLine, e.Mid)));
        ProjectFacts.Write(Marks.StreetEdge, text, () => set(text));
        log["street_edge"] = text;
    }

    /// <summary>The kept edges as the facts' <c>street_line</c>: each the lot's own edge whose ends they are (turned
    /// into the shared coordinates), sent with the lot edge's exact first and last points; or why not (an edge the
    /// lot doesn't have). With no lot read, the kept edges are sent turned as they are: the check then says there is
    /// no lot, so nothing complies. A kept edge with its kind and middle (from round 4) matches only the lot edge
    /// whose ends, kind and middle all agree, so an arc and its chord never match each other; an older mark's ends
    /// alone matching more than one lot edge is refused (<see cref="StreetRefusal.Ambiguous"/>).</summary>
    public static StreetMatch Match(IReadOnlyList<(Xyz A, Xyz B)> edges, JsonObject? lot, Transform3 toShared) =>
        Match(edges.Select(e => new KeptEdge(e.A, e.B)).ToList(), lot, toShared);

    public static StreetMatch Match(IReadOnlyList<KeptEdge> edges, JsonObject? lot, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentNullException.ThrowIfNull(toShared);
        static JsonArray Pt(double x, double y) => new(x, y);
        static (double X, double Y) P(JsonNode? p) => (p![0]!.GetValue<double>(), p[1]!.GetValue<double>());
        var line = new JsonArray();
        var words = new List<string>();
        foreach (var kept in edges)
        {
            Xyz sa = toShared.Apply(kept.A), sb = toShared.Apply(kept.B);
            Xyz? sm = kept.Mid is { } m ? toShared.Apply(m) : null;
            if (lot is null)
            {
                line.Add(new JsonArray(Pt(sa.X, sa.Y), Pt(sb.X, sb.Y)));
                words.Add(Unmatched((sa.X, sa.Y), (sb.X, sb.Y)));
                continue;
            }
            JsonArray? found = null;
            List<(double X, double Y)>? foundPts = null;
            var foundCurved = false;
            var matches = 0;
            foreach (var e in lot["edges"]!.AsArray())
            {
                var pts = e!["points"]!.AsArray();
                var (f, l) = (pts[0]!.AsArray(), pts[^1]!.AsArray());
                double fx = f[0]!.GetValue<double>(), fy = f[1]!.GetValue<double>();
                double lx = l[0]!.GetValue<double>(), ly = l[1]!.GetValue<double>();
                bool Near(Xyz p, double x, double y) => Math.Abs(p.X - x) <= Tolerance && Math.Abs(p.Y - y) <= Tolerance;
                if (!(Near(sa, fx, fy) && Near(sb, lx, ly) || Near(sa, lx, ly) && Near(sb, fx, fy)))
                    continue;
                if (kept.IsLine is { } isLine && sm is { } want)
                {
                    if (isLine != (e["curved"]?.GetValue<bool>() != true))
                        continue;                                    // an arc kept never matches a straight edge, nor a line an arc
                    var (mx, my) = Middle(pts.Select(P).ToList());
                    if (Math.Abs(want.X - mx) > MidTolerance || Math.Abs(want.Y - my) > MidTolerance)
                        continue;                                    // another curve on the same ends
                }
                if (found is null)
                {
                    found = new JsonArray(Pt(fx, fy), Pt(lx, ly));
                    foundPts = pts.Select(P).ToList();
                    foundCurved = e["curved"]?.GetValue<bool>() == true;
                }
                matches++;
            }
            // what will happen is said: the button asks for the edge again at once; a request file has no pick
            const string again = " Check project asks you to click the lot edge along the street again (from a request " +
                                 "file: give the Gordium: Street edge mark again); nothing is checked until then.";
            if (matches > 1)
                return new(null, $"{Marks.StreetEdge.Name}: the street edge kept matches more than one lot edge (two share its " +
                                 "ends, an arc and its chord: it was kept before Gordium noted which)." + again, StreetRefusal.Ambiguous);
            if (found is null)
                return new(null, $"{Marks.StreetEdge.Name}: the street edge picked is no longer an edge of the lot (the " +
                                 "property line was changed)." + again, StreetRefusal.NoLongerAnEdge);
            line.Add(found);
            words.Add(Words(foundPts!, foundCurved));
        }
        return new(line, null, StreetRefusal.None) { Words = string.Join(" and ", words) };
    }

    /// <summary>The point halfway along a run of points (by length).</summary>
    private static (double X, double Y) Middle(List<(double X, double Y)> pts)
    {
        var lengths = pts.Zip(pts.Skip(1), (p, q) => Math.Sqrt((p.X - q.X) * (p.X - q.X) + (p.Y - q.Y) * (p.Y - q.Y))).ToList();
        var half = lengths.Sum() / 2;
        for (var i = 0; i < lengths.Count; i++)
        {
            if (half <= lengths[i] && lengths[i] > 0)
            {
                var t = half / lengths[i];
                return (pts[i].X + t * (pts[i + 1].X - pts[i].X), pts[i].Y + t * (pts[i + 1].Y - pts[i].Y));
            }
            half -= lengths[i];
        }
        return pts[^1];
    }

    private static double PlanDistance(List<Xyz> pts, Xyz p)
    {
        var best = double.PositiveInfinity;
        for (var i = 0; i + 1 < pts.Count; i++)
        {
            double ax = pts[i].X, ay = pts[i].Y, dx = pts[i + 1].X - ax, dy = pts[i + 1].Y - ay;
            var len2 = dx * dx + dy * dy;
            var t = len2 == 0 ? 0 : Math.Clamp(((p.X - ax) * dx + (p.Y - ay) * dy) / len2, 0, 1);
            best = Math.Min(best, Math.Sqrt(Math.Pow(p.X - ax - t * dx, 2) + Math.Pow(p.Y - ay - t * dy, 2)));
        }
        return best;
    }
}
