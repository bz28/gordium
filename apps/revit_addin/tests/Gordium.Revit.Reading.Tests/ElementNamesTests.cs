using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>An element named as the architect names it in the results (ElementNames): a room by its name and number,
/// a door or window by its Mark, anything else by its category and name; Revit's id only when nothing else names it.</summary>
public sealed class ElementNamesTests
{
    [Theory]
    [InlineData("Rooms", "CLOSET", "40", null, "CLOSET (40)")]
    [InlineData("Rooms", "KITCHEN 10", "10", null, "KITCHEN 10")]          // a name that already ends with its number
    [InlineData("Rooms", null, "13", null, "Room 13")]
    [InlineData("Rooms", "  ", null, null, "Room id 341207")]
    [InlineData("Doors", "36\" x 84\"", null, "D06", "Door D06")]
    [InlineData("Windows", "Casement", null, null, "Window: Casement")]
    [InlineData("Levels", "1st floor", null, null, "Level: 1st floor")]
    [InlineData(null, null, null, null, "Element id 341207")]
    [InlineData("Topography", "Surface", null, " ", "Topography: Surface")]
    public void An_element_is_named_as_the_architect_names_it(string? category, string? name, string? number, string? mark, string want) =>
        Assert.Equal(want, ElementNames.Of(category, name, number, mark, 341207));
}
