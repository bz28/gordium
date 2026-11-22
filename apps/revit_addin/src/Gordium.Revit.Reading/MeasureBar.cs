using System.Text.Json;

namespace Gordium.Revit.Reading;

/// <summary>Which side of the limit a rule wants: at least it (≥), at most it (≤), or not said.</summary>
public enum LimitSide { AtLeast, AtMost, Unsaid }

/// <summary>
/// The measured-vs-limit bar of a result's detail (docs/revit/ui_design_pass.md section 2.4, PR 6), drawn only from
/// two lengths the worker sent as numbers in one unit: its <c>limit_length</c> (the remoteness ratio's limit as a
/// length: exits 187.16 ft apart against 71 ft). The figures shown are the worker's own words (<see cref="Words"/>);
/// the numbers only place the two marks along the bar (a drawing, never a figure shown). Its colour is the row's
/// status (never green for a row that needs review, the clock's hatching once stale): the bar never says a row passes.
/// </summary>
/// <param name="Measured">The length found, the worker's number.</param>
/// <param name="Limit">The limit as a length, the worker's number.</param>
/// <param name="Unit">Their one unit ("ft").</param>
/// <param name="Side">Which side of the limit the rule wants, from the worker's words ("needs ≥").</param>
/// <param name="Words">The worker's words for both ("exits 187.16 ft apart, needs ≥ 71 ft (1/3 of the 212.99 ft diagonal)").</param>
public sealed record MeasureBar(double Measured, double Limit, string Unit, LimitSide Side, string Words)
{
    /// <summary>Where the measured mark is along the bar, 0 to 1: the longer of the two lengths spans the bar.</summary>
    public double MeasuredAt => Measured / Math.Max(Measured, Limit);

    /// <summary>Where the limit's mark is along the bar, 0 to 1.</summary>
    public double LimitAt => Limit / Math.Max(Measured, Limit);

    /// <summary>The bar from a row's <c>limit_length</c>, or null unless it holds a measured length and a limit as
    /// finite numbers, not both zero and neither negative, in one unit (its <c>unit</c>, or <c>measured_unit</c> and
    /// <c>limit_unit</c> the same), and the worker's words for them. Never a bar from anything else: a zoning figure
    /// ("28.3%") or an egress reason's words are text, and the panel never reads numbers out of them.</summary>
    public static MeasureBar? Of(JsonElement row)
    {
        if (row.ValueKind != JsonValueKind.Object || !row.TryGetProperty("limit_length", out var l) || l.ValueKind != JsonValueKind.Object)
            return null;
        if (Number(l, "measured") is not { } measured || Number(l, "limit") is not { } limit || ResultRows.Text(l, "words") is not { } words)
            return null;
        var unit = ResultRows.Text(l, "unit");
        if (unit is null && ResultRows.Text(l, "measured_unit") is { } mu && ResultRows.Text(l, "limit_unit") == mu)
            unit = mu;
        if (unit is null || (ResultRows.Text(l, "measured_unit") is { } m2 && m2 != unit) || (ResultRows.Text(l, "limit_unit") is { } l2 && l2 != unit))
            return null;
        if (measured < 0 || limit < 0 || measured + limit <= 0)
            return null;
        var side = words.Contains("needs ≥", StringComparison.Ordinal) ? LimitSide.AtLeast
                 : words.Contains("needs ≤", StringComparison.Ordinal) ? LimitSide.AtMost : LimitSide.Unsaid;
        return new MeasureBar(measured, limit, unit, side, words);
    }

    private static double? Number(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var d) && double.IsFinite(d) ? d : null;
}
