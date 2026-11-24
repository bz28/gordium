namespace Gordium.Revit.Reading;

/// <summary>What the add-in does to one mark when it adds Gordium's marks to a project.</summary>
public enum MarkSetupAction
{
    /// <summary>Already bound as it should be: nothing to do.</summary>
    None,

    /// <summary>Not in the project: add it (<c>BindingMap.Insert</c>) to <see cref="MarkSetupStep.Categories"/>.</summary>
    Add,

    /// <summary>Bound, but not to every category it should be: bind it again (<c>BindingMap.ReInsert</c>) to
    /// <see cref="MarkSetupStep.Categories"/>, the categories it has kept and the missing ones.</summary>
    AddCategories,

    /// <summary>Can't be added as Gordium's mark (another parameter of its name, or bound the wrong way): nothing is
    /// changed, the marking list says why first, and the mark reads as not set wherever it isn't there.</summary>
    Conflict,
}

/// <summary>One mark's step: what to do, the categories to bind it to, and the words for a conflict.</summary>
public sealed record MarkSetupStep(MarkDefinition Mark, MarkSetupAction Action, IReadOnlyList<string> Categories, string? Words);

/// <summary>
/// Adding Gordium's marks to a project on first use (design note, section 3): for each mark, from the parameters
/// already bound in the project, whether to add it, extend it to a missing category, leave it, or refuse to touch
/// it. Decided here so it is tested; the Revit layer only does each step. Never removes or narrows a binding the
/// project has (an architect may have bound a mark to more categories, for their own schedules), and never binds a
/// mark over another parameter of the same name: a firm's own "Gordium: Sleeping room" isn't Gordium's, and the
/// reader reads marks by GUID only.
/// </summary>
public static class MarkSetup
{
    public static IReadOnlyList<MarkSetupStep> Plan(IReadOnlyList<BoundParameter> bound) =>
        Marks.All.Select(m => Step(m, bound)).ToList();

    private static MarkSetupStep Step(MarkDefinition m, IReadOnlyList<BoundParameter> bound)
    {
        var mine = bound.Where(b => b.Guid == m.Guid).ToList();
        var binding = m.Binding == MarkBinding.Instance ? "on each element" : "on each type";
        if (mine.Count == 0)
        {
            var clash = bound.FirstOrDefault(b => string.Equals(b.Name.Trim(), m.Name, StringComparison.OrdinalIgnoreCase));
            return clash is null
                ? new(m, MarkSetupAction.Add, m.Categories, null)
                : new(m, MarkSetupAction.Conflict, [],
                      $"the project already has a parameter named \"{clash.Name}\" that isn't Gordium's: rename or remove it, " +
                      "then click Set up again. Until then this mark is not read.");
        }
        var b = mine[0];
        if (mine.Count > 1 || b.Kind != m.Kind || b.IsInstance != (m.Binding == MarkBinding.Instance))
            return new(m, MarkSetupAction.Conflict, [],
                       $"\"{m.Name}\" is in the project but not as Gordium sets it ({m.Kind}, {binding}; found " +
                       $"{b.Kind?.ToString() ?? b.DataType}, {(b.IsInstance ? "on each element" : "on each type")}): " +
                       "remove it in Manage ▸ Project Parameters, then click Set up again. Until then this mark is not read.");
        var missing = m.Categories.Where(c => !b.Categories.Contains(c)).ToList();
        return missing.Count == 0
            ? new(m, MarkSetupAction.None, b.Categories, null)
            : new(m, MarkSetupAction.AddCategories, [.. b.Categories, .. missing], null);
    }
}
