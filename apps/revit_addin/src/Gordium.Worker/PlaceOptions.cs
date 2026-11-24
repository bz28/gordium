using System.Text.Json;

namespace Gordium.Worker;

/// <summary>One use a district's chart lists (design_checker check.use_choices): Gordium's word for it, its name as
/// the chart writes it, whether the chart permits it by right (null when the district has no use rule to say), and
/// the chart's words when it doesn't (a special permit, with the chart's page).</summary>
public sealed record UseChoice(string Id, string Name, bool? Permitted, string? Note);

/// <summary>What the older <c>options</c> command answers (<see cref="WorkerClient.OptionsAsync"/>): the place's
/// districts that have a rulebook, the city's use words with their names, and each district's uses, all read from the
/// rulebooks and the city's uses file by the worker, never kept by hand here. The add-in's Setup form offers them as
/// its Zone and Use choices.</summary>
/// <param name="Zones">The districts with a rulebook, in the worker's order.</param>
/// <param name="Uses">Every use word of the city and its name, in the file's order.</param>
/// <param name="DistrictUses">Each district's uses, permitted first, as its chart lists them.</param>
public sealed record PlaceOptions(IReadOnlyList<string> Zones, IReadOnlyList<(string Id, string Name)> Uses,
                                  IReadOnlyDictionary<string, IReadOnlyList<UseChoice>> DistrictUses)
{
    /// <summary>The uses whose buildings the Building Code covers whatever else is stated (check.building_code_uses:
    /// New York's code choice by the use alone), where the place's laws split buildings between books; empty
    /// elsewhere, and from a worker that doesn't send them. The Setup form then requires the occupancy group and the
    /// sprinkler system (Ben, 2026-11-23).</summary>
    public IReadOnlyList<string> BuildingCodeUses { get; init; } = [];

    /// <summary>Reads the answer strictly: a field missing or of another kind is refused (the worker is then stopped
    /// by the client, as for any answer it can't read). Fields the form doesn't use (follow_ups, implied) are left.</summary>
    internal static PlaceOptions Parse(JsonElement result)
    {
        const string where = "options";
        var zones = StrictJson.Field(result, "zones", where);
        if (zones.ValueKind != JsonValueKind.Array)
            throw new WorkerProtocolException($"{where}.zones is {StrictJson.Kind(zones)}, not a list");
        var zoneList = zones.EnumerateArray().Select((z, i) => z.ValueKind == JsonValueKind.String && z.GetString()!.Length > 0
            ? z.GetString()! : throw new WorkerProtocolException($"{where}.zones[{i}] is {StrictJson.Kind(z)}, not a district")).ToList();
        var uses = new List<(string, string)>();
        foreach (var p in StrictJson.Object(result, "uses", where).EnumerateObject())
            uses.Add((p.Name, p.Value.ValueKind == JsonValueKind.String
                ? p.Value.GetString()! : throw new WorkerProtocolException($"{where}.uses[\"{p.Name}\"] is {StrictJson.Kind(p.Value)}, not a name")));
        var district = new Dictionary<string, IReadOnlyList<UseChoice>>(StringComparer.Ordinal);
        foreach (var d in StrictJson.Object(result, "district_uses", where).EnumerateObject())
        {
            if (d.Value.ValueKind != JsonValueKind.Array)
                throw new WorkerProtocolException($"{where}.district_uses[\"{d.Name}\"] is {StrictJson.Kind(d.Value)}, not a list");
            district[d.Name] = d.Value.EnumerateArray().Select((u, i) =>
            {
                var at = $"{where}.district_uses[\"{d.Name}\"][{i}]";
                if (u.ValueKind != JsonValueKind.Object)
                    throw new WorkerProtocolException($"{at} is {StrictJson.Kind(u)}, not a use");
                var permitted = StrictJson.Field(u, "permitted", at);
                return new UseChoice(StrictJson.String(u, "id", at, nonEmpty: true), StrictJson.String(u, "name", at),
                    permitted.ValueKind switch
                    {
                        JsonValueKind.True => true,
                        JsonValueKind.False => false,
                        JsonValueKind.Null => (bool?)null,
                        _ => throw new WorkerProtocolException($"{at}.permitted is {StrictJson.Kind(permitted)}, not true, false or null"),
                    },
                    StrictJson.StringOrNull(u, "note", at));
            }).ToList();
        }
        // optional (an older worker sends none): a list of use words, anything else refused
        var building = new List<string>();
        if (result.TryGetProperty("building_code_uses", out var bc))
        {
            if (bc.ValueKind != JsonValueKind.Array)
                throw new WorkerProtocolException($"{where}.building_code_uses is {StrictJson.Kind(bc)}, not a list");
            building.AddRange(bc.EnumerateArray().Select((u, i) => u.ValueKind == JsonValueKind.String && u.GetString()!.Length > 0
                ? u.GetString()! : throw new WorkerProtocolException($"{where}.building_code_uses[{i}] is {StrictJson.Kind(u)}, not a use")));
        }
        return new PlaceOptions(zoneList, uses, district) { BuildingCodeUses = building };
    }
}
