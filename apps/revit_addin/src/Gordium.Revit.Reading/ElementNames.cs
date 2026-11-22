using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>
/// An element as an architect names it in the results (docs/revit/ui_design_pass.md section 2.4, a result's detail:
/// "CLOSET (40)", "Door D06", never "Rooms id 341207"): a room by its name and number as the room tag shows them, a
/// door or a window by its category and Mark as the door schedule does, anything else by its category and name. Revit's
/// element id is kept apart, never in the name: the panel carries it beside the name (PanelContent.Ids) and shows it in
/// each element's Show tooltip in a result's detail ("Revit id 341207, for Select by ID"); <see cref="Id"/> names an
/// element by it only when nothing else names it.
/// </summary>
public static class ElementNames
{
    /// <summary>The name an architect knows the element by.</summary>
    /// <param name="category">Revit's category name ("Rooms", "Doors", "Levels"), or null.</param>
    /// <param name="name">The element's name (a room's Name parameter, a level's name, a door's type name), or null.</param>
    /// <param name="number">A room's Number, or null.</param>
    /// <param name="mark">A door's or window's Mark, or null.</param>
    /// <param name="id">Revit's element id: named by it only when nothing else names the element.</param>
    public static string Of(string? category, string? name, string? number, string? mark, long id)
    {
        var one = One(category);
        name = Clean(name);
        number = Clean(number);
        mark = Clean(mark);
        if (category == "Rooms" || category == "Spaces" || category == "Areas")
            return (name, number) switch
            {
                ({ } n, { } k) when !EndsWithWord(n, k) => $"{n} ({k})",
                ({ } n, _) => n,
                (null, { } k) => $"{one} {k}",
                _ => Id(one, id),
            };
        if (mark is not null)
            return $"{one} {mark}";
        return name is not null ? $"{one}: {name}" : Id(one, id);
    }

    /// <summary>"Door id 341207": an element nothing else names, by Revit's id (Select by ID finds it).</summary>
    public static string Id(string? category, long id) =>
        $"{One(category)} id {id.ToString(CultureInfo.InvariantCulture)}";

    /// <summary>A category in the singular, as one element of it is named ("Doors" → "Door"); an unknown one as it is.</summary>
    internal static string One(string? category) => Clean(category) switch
    {
        null => "Element",
        "Doors" => "Door",
        "Windows" => "Window",
        "Rooms" => "Room",
        "Spaces" => "Space",
        "Areas" => "Area",
        "Levels" => "Level",
        "Walls" => "Wall",
        "Floors" => "Floor",
        "Stairs" => "Stair",
        "Railings" => "Railing",
        "Property Lines" => "Property line",
        "Generic Models" => "Generic model",
        "Mass" => "Mass",
        { } c => c,
    };

    /// <summary>Whether <paramref name="name"/> already ends with the number as a word of its own ("BEDROOM 2" and
    /// "2", "STORAGE-13" and "13"), never as the end of a longer number ("OFFICE 112" and "12" is not).</summary>
    private static bool EndsWithWord(string name, string number) =>
        name == number || name.EndsWith(number, StringComparison.Ordinal) && !char.IsLetterOrDigit(name[^(number.Length + 1)]);

    private static string? Clean(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();
}
