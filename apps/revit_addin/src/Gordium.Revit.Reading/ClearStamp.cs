using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>What a window type's clear opening is, as its marks give it now (design note, section 3): the values the
/// <c>Gordium: Clear confirmed</c> stamp records, read from the type's marks and its size.</summary>
/// <param name="Type">The type's <c>UniqueId</c>.</param>
/// <param name="Width">The type's own Width (<see cref="OpeningRecord.TypeWidth"/>).</param>
/// <param name="Height">The type's own Height.</param>
/// <param name="Operation">The <c>Gordium: Operation</c> text, trimmed, as typed.</param>
/// <param name="ClearWidth">The <c>Gordium: Clear width</c>.</param>
/// <param name="ClearHeight">The <c>Gordium: Clear height</c>.</param>
/// <param name="ClearOffset">The <c>Gordium: Clear offset</c> (blank is not 0: null).</param>
/// <param name="Source">The <c>Gordium: Clear source</c>.</param>
/// <param name="MappedName">A maker's family parameter the clear opening was copied from, or null.</param>
/// <param name="MappedValue">That parameter's value.</param>
/// <param name="Door">A door type's clear opening (step 5): the width and height R318.2 measures, with no offset (a
/// door's clear opening has no bottom in the description); the stamp says it was made for a door, and a door is
/// confirmed only by a door's stamp.</param>
public sealed record ClearValues(string? Type, double? Width, double? Height, string? Operation, double? ClearWidth,
                                 double? ClearHeight, double? ClearOffset, string? Source, string? MappedName = null,
                                 double? MappedValue = null, bool Door = false);

/// <summary>The confirmation stamp (<c>Gordium: Clear confirmed</c>): written by the add-in only when the architect
/// confirms a window type's clear opening, it records exactly what was confirmed, who and when. The reader sends a
/// clear opening only when every value read now equals the stamp's (design note, sections 3 and 4): a duplicated or
/// resized type, or any value edited since, leaves the window unconfirmed. Lengths are compared to a billionth of a
/// foot (Revit keeps a length as the number it was given), text exactly.</summary>
public static class ClearStamp
{
    public const string Format = "gordium.clear_confirmed/1";
    private const double Same = 1e-9;

    /// <summary>The stamp's text for the values confirmed; refused (an <see cref="ArgumentException"/>) when any value
    /// the stamp must record is missing: nothing is ever confirmed half way.</summary>
    public static string Make(ClearValues v, string by, string at)
    {
        if (Missing(v) is { } what)
            throw new ArgumentException($"a clear opening can't be confirmed without {what}");
        if (string.IsNullOrWhiteSpace(by) || string.IsNullOrWhiteSpace(at))
            throw new ArgumentException("a confirmation says who confirmed it and when");
        var stamp = new JsonObject
        {
            ["stamp"] = Format,
            ["for"] = v.Door ? "door" : "window",
            ["type"] = v.Type,
            ["width"] = v.Width,
            ["height"] = v.Height,
            ["operation"] = v.Operation,
            ["clear_width"] = v.ClearWidth,
            ["clear_height"] = v.ClearHeight,
            ["clear_offset"] = v.Door ? null : v.ClearOffset,
            ["source"] = v.Source,
            ["mapped"] = v.MappedName is null ? null : new JsonObject { ["name"] = v.MappedName, ["value"] = v.MappedValue },
            ["by"] = by,
            ["at"] = at,
        };
        return stamp.ToJsonString();
    }

    /// <summary>What a confirmation needs and these values don't have, in words; null when nothing is missing.</summary>
    public static string? Missing(ClearValues v)
    {
        var missing = new List<string>();
        if (string.IsNullOrWhiteSpace(v.Type)) missing.Add("the type's id");
        if (v.Width is null || v.Height is null) missing.Add("the type's own Width and Height");
        if (string.IsNullOrWhiteSpace(v.Operation)) missing.Add(Marks.Operation.Name);
        if (v.ClearWidth is null) missing.Add(Marks.ClearWidth.Name);
        if (v.ClearHeight is null) missing.Add(Marks.ClearHeight.Name);
        if (v.ClearOffset is null && !v.Door) missing.Add(Marks.ClearOffset.Name + " (blank is not 0)");
        if (string.IsNullOrWhiteSpace(v.Source)) missing.Add(Marks.ClearSource.Name);
        if (v.MappedName is not null && v.MappedValue is null) missing.Add($"the maker's parameter {v.MappedName}'s value");
        return missing.Count == 0 ? null : string.Join(", ", missing);
    }

    /// <summary>Why the stamp doesn't confirm these values (null when it does): no stamp, one that can't be read, or
    /// the first value that differs from what was confirmed.</summary>
    public static string? Why(string? stamp, ClearValues now, IReadOnlyDictionary<string, double> typeLengths)
    {
        if (string.IsNullOrWhiteSpace(stamp))
            return "its type's clear opening isn't confirmed (no " + Marks.ClearConfirmed.Name + ")";
        JsonObject s;
        try
        {
            s = JsonNode.Parse(stamp, documentOptions: new JsonDocumentOptions { AllowTrailingCommas = false }) as JsonObject
                ?? throw new JsonException("not an object");
        }
        catch (JsonException)
        {
            return Marks.ClearConfirmed.Name + " can't be read (typed over?): confirm the clear opening again";
        }
        if (Text(s, "stamp") != Format)
            return Marks.ClearConfirmed.Name + " isn't Gordium's stamp: confirm the clear opening again";
        if (Missing(now) is { } missing)
            return "its type has no " + missing;
        // a door is confirmed only by a stamp made for a door (its width and height, no offset); a window by one made
        // for a window (step 3's stamps say nothing: they were all made for windows)
        if ((Text(s, "for") ?? (s["for"] is null ? "window" : null)) != (now.Door ? "door" : "window"))
            return $"the stamp wasn't made for a {(now.Door ? "door" : "window")}: confirm this type's clear opening";
        if (Text(s, "type") != now.Type)
            return "the stamp was made on another type (a duplicated or copied type): confirm this type's clear opening";
        var differs = new List<string>();
        void Length(string key, double? value, string what)
        {
            if (Number(s, key) is not { } was || value is not { } v || Math.Abs(was - v) > Same)
                differs.Add(what);
        }
        Length("width", now.Width, "the type's Width");
        Length("height", now.Height, "the type's Height");
        if (Text(s, "operation") != now.Operation)
            differs.Add(Marks.Operation.Name);
        Length("clear_width", now.ClearWidth, Marks.ClearWidth.Name);
        Length("clear_height", now.ClearHeight, Marks.ClearHeight.Name);
        if (!now.Door)
            Length("clear_offset", now.ClearOffset, Marks.ClearOffset.Name);
        if (Text(s, "source") != now.Source)
            differs.Add(Marks.ClearSource.Name);
        if (s["mapped"] is JsonObject mapped)
        {
            var name = Text(mapped, "name");
            if (name is null || !typeLengths.TryGetValue(name, out var current) || Number(mapped, "value") is not { } was
                || Math.Abs(was - current) > Same)
                differs.Add($"the maker's parameter {name ?? "(unnamed)"}");
        }
        else if (s["mapped"] is not null)
            differs.Add("the stamp's maker's parameter");
        if (Text(s, "by") is null || Text(s, "at") is null)
            differs.Add("who confirmed it and when");
        return differs.Count == 0 ? null
            : "changed since its clear opening was confirmed (" + string.Join(", ", differs) + "): confirm it again";
    }

    private static string? Text(JsonObject o, string key) =>
        o[key] is JsonValue v && v.TryGetValue<string>(out var t) ? t : null;

    private static double? Number(JsonObject o, string key) =>
        o[key] is JsonValue v && v.TryGetValue<double>(out var d) && double.IsFinite(d) ? d : null;

    /// <summary>A length in inches, for the words.</summary>
    internal static string Inches(double feet) => (feet * 12).ToString("0.###", CultureInfo.InvariantCulture) + " in";
}
