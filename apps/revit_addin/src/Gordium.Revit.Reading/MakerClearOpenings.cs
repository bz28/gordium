using System.Globalization;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Gordium.Revit.Reading;

// Makers' clear-opening formulas (apps/revit_addin/data/maker_clear_openings.json; design note, section 3): a window
// type's net clear opening worked out from its frame size by the maker's own published formula, written into the
// type's Clear width, Clear height and Clear source as a DRAFT the architect still confirms. Never the confirmation
// stamp: the reader sends a clear opening only with it (ClearStamp), so a pre-fill alone never reaches the checker.

/// <summary>One maker's product line: which types it matches, its formula and where it holds.</summary>
public sealed record MakerFormula(
    string Id, string Maker, string ProductLine, string Operation, IReadOnlyList<string> Manufacturers,
    IReadOnlyList<string> WindowTypes, Guid WindowTypeParameter, string ModelCallNumber, Guid VentAreaParameter,
    double VentAreaTolerance, IReadOnlyList<string> WidthCns, IReadOnlyList<string> HeightCns,
    IReadOnlyList<double> FrameWidths, IReadOnlyList<double> FrameHeights,
    IReadOnlyList<double> RoughWidths, IReadOnlyList<double> RoughHeights, IReadOnlyList<double> MasonryWidths,
    IReadOnlyList<double> MasonryHeights, double WidthMinus, double HeightMinus, double FrameWidthMin,
    double FrameWidthMax, double FrameHeightMax, string Caveats, string Url, string FormulaPage, string FormulaQuote)
{
    /// <summary>The Model's width and height call numbers ("UCA3648": 36, 48), or null when it isn't a call number.</summary>
    public (string Width, string Height)? CallNumber(string? model) =>
        model is not null && Regex.Match(model.Trim(), ModelCallNumber, RegexOptions.CultureInvariant) is { Success: true } m
            ? (m.Groups[1].Value, m.Groups[2].Value) : null;

    /// <summary>The clear width and height, in inches, from a frame size in inches (the maker's formula only).</summary>
    public (double Width, double Height) Clear(double frameWidth, double frameHeight) =>
        (frameWidth - WidthMinus, frameHeight - HeightMinus);
}

/// <summary>A maker Gordium knows the clear-opening PDFs of (named in the marking list when no formula matches).</summary>
public sealed record KnownMaker(string Maker, IReadOnlyList<string> Manufacturers, IReadOnlyList<(string Title, string Url)> Pdfs);

/// <summary>The curated data file, embedded in this library (so the add-in installed reads the same file the tests do).</summary>
public static class MakerClearOpenings
{
    public const string Format = "gordium.maker_clear_openings/1";
    private const string Resource = "Gordium.Revit.Reading.maker_clear_openings.json";

    /// <summary>A size equal to a listed size: within 1/1000 in (Revit keeps a length as the number it was given).</summary>
    internal const double SameInches = 0.001;

    private static readonly Lazy<(string Version, IReadOnlyList<MakerFormula> Entries, IReadOnlyList<KnownMaker> Makers)> Data =
        new(() => Parse(Read()));

    public static string Version => Data.Value.Version;
    public static IReadOnlyList<MakerFormula> Entries => Data.Value.Entries;
    public static IReadOnlyList<KnownMaker> Makers => Data.Value.Makers;

    /// <summary>The embedded file's text.</summary>
    public static string Read()
    {
        using var s = typeof(MakerClearOpenings).Assembly.GetManifestResourceStream(Resource)
            ?? throw new InvalidOperationException($"{Resource} isn't embedded in {typeof(MakerClearOpenings).Assembly.GetName().Name}");
        using var r = new StreamReader(s);
        return r.ReadToEnd();
    }

    /// <summary>The file read; refused (an exception) when its format isn't this one or an entry lacks a field: a
    /// formula half read is never used.</summary>
    public static (string Version, IReadOnlyList<MakerFormula> Entries, IReadOnlyList<KnownMaker> Makers) Parse(string json)
    {
        var root = JsonNode.Parse(json) as JsonObject ?? throw new FormatException("not a JSON object");
        if (Str(root, "format") != Format)
            throw new FormatException($"not {Format}");
        var entries = new List<MakerFormula>();
        foreach (var e in Arr(root, "entries").Cast<JsonObject>())
        {
            var match = Obj(e, "match");
            var sizes = Obj(e, "standard_sizes");
            var formula = Obj(e, "formula");
            var valid = Obj(e, "valid");
            var source = Obj(Obj(e, "sources"), Str(formula, "source"));
            List<double> Col(string axis, string what) => Arr(sizes, axis).Select(x => Num((JsonObject)x!, what)).ToList();
            List<string> Cns(string axis) => Arr(sizes, axis).Select(x => Str((JsonObject)x!, "cn")).ToList();
            var check = Obj(e, "cross_check");
            _ = Regex.Match("", Str(match, "model_call_number"));                // a pattern that doesn't parse is refused here
            entries.Add(new(
                Str(e, "id"), Str(e, "maker"), Str(e, "product_line"), Str(e, "operation"), Strs(match, "manufacturer"),
                Strs(match, "window_type"), Guid.Parse(Str(match, "window_type_parameter")), Str(match, "model_call_number"),
                Guid.Parse(Str(check, "vent_area_parameter")), Num(check, "tolerance_ft2"), Cns("width"), Cns("height"),
                Col("width", "frame"), Col("height", "frame"), Col("width", "rough"),
                Col("height", "rough"), Col("width", "masonry"), Col("height", "masonry"),
                Num(Obj(formula, "clear_width"), "frame_width_minus"), Num(Obj(formula, "clear_height"), "frame_height_minus"),
                Num(valid, "frame_width_min"), Num(valid, "frame_width_max"), Num(valid, "frame_height_max"),
                Str(e, "caveats"), Str(source, "url"), Str(source, "formula_page"), Str(source, "formula_quote")));
        }
        var makers = Arr(root, "known_makers").Cast<JsonObject>().Select(m => new KnownMaker(
            Str(m, "maker"), Strs(m, "manufacturer"),
            Arr(m, "clear_opening_pdfs").Cast<JsonObject>().Select(p => (Str(p, "title"), Str(p, "url"))).ToList())).ToList();
        return (Str(root, "version"), entries, makers);
    }

    private static string Str(JsonObject o, string key) =>
        o[key] is JsonValue v && v.TryGetValue<string>(out var s) && !string.IsNullOrWhiteSpace(s) ? s
        : throw new FormatException($"no {key}");

    private static double Num(JsonObject o, string key) =>
        o[key] is JsonValue v && v.TryGetValue<double>(out var d) && double.IsFinite(d) ? d : throw new FormatException($"no {key}");

    private static JsonObject Obj(JsonObject o, string key) => o[key] as JsonObject ?? throw new FormatException($"no {key}");

    private static JsonArray Arr(JsonObject o, string key) => o[key] as JsonArray ?? throw new FormatException($"no {key}");

    private static List<string> Strs(JsonObject o, string key) =>
        Arr(o, key).Select(x => x is JsonValue v && v.TryGetValue<string>(out var s) ? s : throw new FormatException($"no {key}")).ToList();

    private static bool Same(string? a, IEnumerable<string> any) =>
        a is not null && any.Any(x => string.Equals(x.Trim(), a.Trim(), StringComparison.OrdinalIgnoreCase));

    /// <summary>The entry whose Manufacturer equals the type's (trimmed, case-insensitive) and whose Window Type equals
    /// the type's shared Window Type, or whose call-number pattern the type's Model is; null otherwise.</summary>
    public static MakerFormula? Match(string? manufacturer, string? windowType, string? model) =>
        Entries.FirstOrDefault(e => Same(manufacturer, e.Manufacturers) && (Same(windowType, e.WindowTypes) || e.CallNumber(model) is not null));

    /// <summary>Every maker's shared type parameter the Revit layer reads by GUID (a Window Type, a Vent Area).</summary>
    public static IReadOnlyList<Guid> SharedParameters =>
        Entries.SelectMany(e => new[] { e.WindowTypeParameter, e.VentAreaParameter }).Distinct().ToList();

    /// <summary>The known maker whose Manufacturer equals the type's, or null.</summary>
    public static KnownMaker? MakerOf(string? manufacturer) => Makers.FirstOrDefault(m => Same(manufacturer, m.Manufacturers));

    internal static bool Listed(double inches, IEnumerable<double> sizes) => sizes.Any(s => Math.Abs(s - inches) <= SameInches);

    internal static string In(double inches) => inches.ToString("0.###", CultureInfo.InvariantCulture) + " in";
}

/// <summary>What Gordium does with one window type's clear opening.</summary>
public enum PrefillState
{
    /// <summary>Its three marks are empty and the formula holds: fill them (a draft).</summary>
    Fill,

    /// <summary>Its three marks hold exactly what Gordium would fill now: the draft, still to confirm.</summary>
    Filled,

    /// <summary>Its Clear source is Gordium's but the values aren't what it would fill now (resized, or edited).</summary>
    Differs,

    /// <summary>A product line matched but the formula can't be used (its size): nothing filled.</summary>
    NotFilled,

    /// <summary>Its Manufacturer is a maker Gordium knows, but no product line matched: nothing filled.</summary>
    KnownMakerOnly,
}

/// <summary>One window type's pre-fill: the values to write (feet, the marks' internal unit) only for
/// <see cref="PrefillState.Fill"/>, and the marking list's line.</summary>
public sealed record ClearPrefill(string TypeId, string Label, PrefillState State, string Line, double? ClearWidth = null,
                                  double? ClearHeight = null, string? Source = null);

/// <summary>Which window types get the maker's clear opening as a draft (design note, section 3). Only a window type
/// whose Gordium: Clear width, Clear height and Clear source are all empty is filled (never over a value the
/// architect typed, never half of one), never one with a Clear confirmed stamp, and never the stamp itself.</summary>
public static class ClearPrefills
{
    /// <summary>Every Clear source Gordium writes starts with this: how a later read knows the draft is Gordium's.</summary>
    public const string SourcePrefix = "Gordium filled from ";

    private const double SameFeet = 1e-9;

    /// <summary>A line per window type in the design checked that a maker's data concerns (no line for the others).</summary>
    public static IReadOnlyList<ClearPrefill> Plan(RevitModel model)
    {
        var plans = new List<ClearPrefill>();
        foreach (var e in MarkReading.InDesign(model).Where(e => MarkReading.KindOf(e) == MarkedKind.Window && e.TypeUniqueId is not null)
                     .GroupBy(e => e.TypeUniqueId!).Select(g => g.First()))
            if (For(e) is { } p)
                plans.Add(p);
        return plans.OrderBy(p => p.Label, StringComparer.OrdinalIgnoreCase).ThenBy(p => p.TypeId, StringComparer.Ordinal).ToList();
    }

    /// <summary>The type's label: its family and type name.</summary>
    private static string Label(MarkedElement e) =>
        string.Join(": ", new[] { e.Family, e.Name }.Where(s => !string.IsNullOrWhiteSpace(s))) is { Length: > 0 } l ? l : e.TypeUniqueId!;

    internal static ClearPrefill? For(MarkedElement e)
    {
        if (Marks.Text(MarkReading.Value(e, Marks.ClearConfirmed)) is not null)
            return null;                                     // confirmed by the architect: Gordium proposes nothing
        var label = Label(e);
        var windowType = Shared(e, MakerClearOpenings.Entries.Select(x => x.WindowTypeParameter)) is { } wt ? Marks.Text(wt) : null;
        var entry = MakerClearOpenings.Match(e.TypeManufacturer, windowType, e.TypeModel);
        if (entry is null)
        {
            if (MakerClearOpenings.MakerOf(e.TypeManufacturer) is not { } maker)
                return null;
            return new(e.TypeUniqueId!, label, PrefillState.KnownMakerOnly,
                $"{label}: made by {maker.Maker}, but its Window Type ({Quote(windowType)}) and Model ({Quote(e.TypeModel)}) " +
                "aren't a product line Gordium has a " +
                $"formula for, so its clear opening isn't filled: take it from {maker.Maker}'s clear-opening tables (" +
                string.Join("; ", maker.Pdfs.Select(p => $"{p.Title}: {p.Url}")) + ") into " + Marks.ClearWidth.Name + ", " +
                Marks.ClearHeight.Name + " and " + Marks.ClearSource.Name + ".");
        }
        double? width = Marks.Length(MarkReading.Value(e, Marks.ClearWidth)), height = Marks.Length(MarkReading.Value(e, Marks.ClearHeight));
        var source = Marks.Text(MarkReading.Value(e, Marks.ClearSource));
        var vent = Shared(e, [entry.VentAreaParameter]) is { HasValue: true, Number: { } a } && double.IsFinite(a) ? a : (double?)null;
        var (fill, why) = Compute(entry, e.TypeWidth, e.TypeHeight, e.TypeModel, vent);
        if (width is null && height is null && source is null)
        {
            if (fill is not { } f)
                return new(e.TypeUniqueId!, label, PrefillState.NotFilled,
                    $"{label}: {entry.Maker} {entry.ProductLine}, but its clear opening isn't filled: {why}. Take it from " +
                    $"{entry.Maker}'s tables ({entry.Url}).");
            return new(e.TypeUniqueId!, label, PrefillState.Fill, FilledLine(label, entry), f.Width, f.Height, f.Source);
        }
        if (source is null || !source.StartsWith(SourcePrefix, StringComparison.Ordinal))
            return null;                                     // the architect's own values: kept, nothing to say
        if (fill is { } now && width is { } w && height is { } h && Math.Abs(w - now.Width) <= SameFeet
            && Math.Abs(h - now.Height) <= SameFeet && source == now.Source)
            return new(e.TypeUniqueId!, label, PrefillState.Filled, FilledLine(label, entry));
        return new(e.TypeUniqueId!, label, PrefillState.Differs,
            $"{label}: its {Marks.ClearSource.Name} says Gordium filled it, but its clear opening isn't what Gordium would " +
            $"fill now ({(fill is null ? why : "the type was resized, or a value edited since")}): check all three against " +
            $"{entry.Maker}'s tables ({entry.Url}) before confirming, or empty them for Gordium to fill again.");
    }

    /// <summary>The dialog's first words when types were just filled (empty when none were).</summary>
    public static string Head(int filled) => filled == 0 ? ""
        : $"Gordium filled the maker's clear opening of {(filled == 1 ? "1 window type" : $"{filled} window types")} " +
          "as a draft: confirm each (Mark for egress lists them); none is sent before.\n\n";

    private static string FilledLine(string label, MakerFormula entry) =>
        $"{label}: Gordium filled the clear opening from {entry.Maker} {entry.FormulaPage}: confirm it (check the hinge/hardware: " +
        $"{entry.Caveats}). It is a draft until you confirm it: no clear opening is sent before. {Marks.ClearOffset.Name} is " +
        "yours to set (the maker's formula doesn't give it).";

    /// <summary>The type's maker's shared parameter (the first of these GUIDs it has), or null.</summary>
    private static MarkValue? Shared(MarkedElement e, IEnumerable<Guid> guids) =>
        guids.Select(g => e.TypeShared.TryGetValue(g, out var v) ? v : null).FirstOrDefault(v => v is not null);

    /// <summary>The draft for a type size (feet), or why there is none. The size is accepted only when it is the
    /// maker's standard frame size on both axes (a rough or masonry opening, or a custom size, is ambiguous: none);
    /// a Model that is a call number must be that frame's; a maker's Vent Area (sq ft) must agree with the formula's
    /// area.</summary>
    public static ((double Width, double Height, string Source)? Fill, string? Why) Compute(
        MakerFormula entry, double? widthFeet, double? heightFeet, string? model = null, double? ventArea = null)
    {
        if (widthFeet is not { } wf || heightFeet is not { } hf)
            return (null, "its type has no Width and Height of its own (a family sized per window)");
        double w = wf * 12, h = hf * 12;
        bool frameW = MakerClearOpenings.Listed(w, entry.FrameWidths), frameH = MakerClearOpenings.Listed(h, entry.FrameHeights);
        if (!frameW || !frameH)
        {
            var rough = MakerClearOpenings.Listed(w, entry.RoughWidths) && MakerClearOpenings.Listed(h, entry.RoughHeights);
            var masonry = MakerClearOpenings.Listed(w, entry.MasonryWidths) && MakerClearOpenings.Listed(h, entry.MasonryHeights);
            var size = $"{MakerClearOpenings.In(w)} by {MakerClearOpenings.In(h)}";
            return (null, rough ? $"its Width and Height ({size}) are {entry.Maker}'s rough opening, not the frame the formula needs"
                : masonry ? $"its Width and Height ({size}) are {entry.Maker}'s masonry opening, not the frame the formula needs"
                : $"its Width and Height ({size}) aren't one of {entry.Maker}'s standard frame sizes, so Gordium can't tell " +
                  "whether they are the frame or the rough opening");
        }
        if (w < entry.FrameWidthMin - MakerClearOpenings.SameInches || w > entry.FrameWidthMax + MakerClearOpenings.SameInches
            || h > entry.FrameHeightMax + MakerClearOpenings.SameInches)
            return (null, $"its frame ({MakerClearOpenings.In(w)} by {MakerClearOpenings.In(h)}) is outside where Gordium uses the " +
                          $"formula ({MakerClearOpenings.In(entry.FrameWidthMin)} to {MakerClearOpenings.In(entry.FrameWidthMax)} " +
                          $"wide, up to {MakerClearOpenings.In(entry.FrameHeightMax)} high)");
        if (entry.CallNumber(model) is { } cn)
        {
            var wi = entry.WidthCns.ToList().IndexOf(cn.Width);
            var hi = entry.HeightCns.ToList().IndexOf(cn.Height);
            if (wi < 0 || hi < 0 || Math.Abs(entry.FrameWidths[wi] - w) > MakerClearOpenings.SameInches
                || Math.Abs(entry.FrameHeights[hi] - h) > MakerClearOpenings.SameInches)
                return (null, $"its Model ({model!.Trim()}) is a call number whose frame isn't its Width and Height " +
                              $"({MakerClearOpenings.In(w)} by {MakerClearOpenings.In(h)}): a mulled unit, or a resized type");
        }
        var (cw, ch) = entry.Clear(w, h);
        if (ventArea is { } vent && Math.Abs(cw * ch / 144 - vent) > entry.VentAreaTolerance + 1e-9)
            return (null, $"the formula's clear area ({(cw * ch / 144).ToString("0.00", CultureInfo.InvariantCulture)} sq ft) " +
                          $"disagrees with the family's own Vent Area ({vent.ToString("0.00", CultureInfo.InvariantCulture)} sq ft) " +
                          $"by more than {entry.VentAreaTolerance.ToString("0.00", CultureInfo.InvariantCulture)} sq ft");
        var source = $"{SourcePrefix}{entry.Maker} {entry.ProductLine}, {entry.FormulaPage} ({entry.Url}): " +
                     $"clear width = frame width - {MakerClearOpenings.In(entry.WidthMinus)}, clear height = frame height - " +
                     $"{MakerClearOpenings.In(entry.HeightMinus)}; frame {MakerClearOpenings.In(w)} by {MakerClearOpenings.In(h)} (the type's Width " +
                     "and Height). A draft until the architect confirms it.";
        return ((cw / 12, ch / 12, source), null);
    }

    private static string Quote(string? s) => string.IsNullOrWhiteSpace(s) ? "not set" : $"\"{s.Trim()}\"";
}
