using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Change 14 of the UI design pass, Revit-free: which results mention an element selected in Revit. A result
/// mentions it when its own elements name it, or when a cause card holding it names the element as one of its rooms;
/// no row is ever dropped, each is listed once, in the pane's order, with its own status.</summary>
public sealed class SelectionResultsTests
{
    private static readonly DateTime At = new(2026, 11, 23, 14, 32, 0);

    private static (ResultModel Model, SelectionMap Map) Odyssey()
    {
        var model = UxAnswers.Model(UxAnswers.Odyssey());
        return (model, SelectionMap.Of(model, At));
    }

    /// <summary>The approved picture (13_selected_element_childcare_proposed.png): STORAGE (13) selected. The picture
    /// listed the 11 results of the "5 rooms have no route" card; STORAGE (13)'s own two rows are mentioned too (one of
    /// them is on that card), so 12, every one needs review.</summary>
    [Fact]
    public void Storage_13_is_mentioned_by_its_own_rows_and_the_rows_waiting_on_its_route()
    {
        var (model, map) = Odyssey();
        var storage = model.Causes.SelectMany(c => c.Rooms).First(r => r.Name == "STORAGE (13)");
        var answer = map.Answer([storage.Id], uid => uid == storage.Id ? "STORAGE (13)" : null);
        Assert.Equal("STORAGE (13)", answer.Title);
        Assert.Equal("12 results mention it · 12 need review", answer.Line);
        Assert.All(answer.Rows, r => Assert.Equal(PanelStatus.Review, r.Status));
        var card = model.Causes.Single(c => c.Rooms.Any(r => r.Id == storage.Id));
        Assert.Equal(11, card.Items.Count);
        var own = model.Groups.SelectMany(g => g.AllRows).Where(r => r.Elements.Contains(storage.Id)).Select(r => r.Id).ToList();
        Assert.Equal(2, own.Count);
        Assert.Equal(card.Items.Union(own).OrderBy(i => i, StringComparer.Ordinal), answer.Rows.Select(r => r.Row.Id).OrderBy(i => i, StringComparer.Ordinal));
    }

    /// <summary>The pin: every row naming an element is listed for that element; every row of a card naming a room is
    /// listed for that room; and nothing else is (the map is exactly the definition).</summary>
    [Fact]
    public void The_selection_map_never_drops_a_row()
    {
        foreach (var model in new[] { Odyssey().Model, Synthetic() })
        {
            var map = SelectionMap.Of(model, At);
            var placed = ResultList.Place(model);
            var expected = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
            void Expect(string uid, string row)
            {
                if (!expected.TryGetValue(uid, out var set))
                    expected[uid] = set = new HashSet<string>(StringComparer.Ordinal);
                set.Add(row);
            }
            foreach (var r in placed)
                foreach (var uid in r.Row.Elements)
                    Expect(uid, r.Row.Id);
            foreach (var c in model.Causes)
                foreach (var room in c.Rooms.Select(r => r.Id).Concat(c.Key.StartsWith("rooms:", StringComparison.Ordinal) ? c.Elements : []))
                    foreach (var id in c.Items)
                        Expect(room, id);
            Assert.NotEmpty(expected);
            Assert.Equal(expected.Keys.OrderBy(k => k, StringComparer.Ordinal), map.Elements.OrderBy(k => k, StringComparer.Ordinal));
            foreach (var (uid, rows) in expected)
                Assert.Equal(rows.OrderBy(i => i, StringComparer.Ordinal), map.For([uid]).Select(r => r.Row.Id).OrderBy(i => i, StringComparer.Ordinal));
            // every element at once: every row that names one, each once, in the pane's order
            var all = map.For(expected.Keys);
            Assert.Equal(expected.Values.SelectMany(s => s).Distinct().Count(), all.Count);
            Assert.Equal(placed.Where(p => all.Contains(p)).Select(p => p.Row.Id), all.Select(r => r.Row.Id));
        }
    }

    private static ResultModel Synthetic()
    {
        var items = new[]
        {
            UxAnswers.Item("cov", "does_not_comply", "Lot coverage", objects: ["bldg", "lot"]),
            UxAnswers.Item("front", "complies", "Front yard", objects: ["bldg", "lot"]),
            UxAnswers.Item("route", "needs_review", "Common path", objects: []),
            UxAnswers.Item("na", "not_applicable", "Ramps", objects: ["ramp"]),
        };
        items[2]["causes"] = new JsonArray(new JsonObject
        {
            ["key"] = "rooms:r1", ["rooms"] = new JsonArray(new JsonObject { ["id"] = "r1", ["name"] = "STORAGE (13)" }),
        });
        return UxAnswers.Model(UxAnswers.Parse(new JsonObject
        {
            ["view"] = new JsonObject
            {
                ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()), ["summary"] = "s", ["state"] = "does_not_comply",
                ["groups"] = new JsonArray(
                    UxAnswers.Group("fails", ["cov"]),
                    UxAnswers.Group("review", ["route"], new JsonObject
                    {
                        ["key"] = "rooms:r1", ["kind"] = "fix_model", ["words"] = "1 room has no route", ["items"] = new JsonArray("route"),
                        ["elements"] = new JsonArray("r1"),
                    }),
                    UxAnswers.Group("complies", ["front", "na"])),
            },
            ["report_error"] = null,
        }));
    }

    [Fact]
    public void Several_elements_list_each_result_once_worst_first_with_its_verdicts_counted()
    {
        var map = SelectionMap.Of(Synthetic(), At);
        var answer = map.Answer(["lot", "bldg", "ramp", "r1", "lot"], _ => null);
        Assert.Equal("4 elements", answer.Title);
        Assert.Equal(["cov", "route", "front", "na"], answer.Rows.Select(r => r.Row.Id));
        Assert.Equal("4 results mention them · 1 does not comply, 1 needs review, 1 complies, 1 not applicable", answer.Line);
        Assert.Equal("1 result mentions it · 1 not applicable", map.Answer(["ramp"], _ => "Ramp").Line);
    }

    /// <summary>An element no result names: said plainly, and that it is not a pass.</summary>
    [Fact]
    public void An_element_no_result_mentions_is_never_read_as_a_pass()
    {
        var answer = SelectionMap.Of(Synthetic(), At).Answer(["door-7"], _ => "Door D07");
        Assert.Equal("Door D07", answer.Title);
        Assert.Empty(answer.Rows);
        Assert.Equal("No result mentions it. That isn't a pass: Gordium may not read or check it yet.", answer.Line);
        Assert.Equal("1 element", SelectionMap.Of(Synthetic(), At).Answer(["door-7"], _ => null).Title);
    }

    /// <summary>Once the model changed: the same results, each with the stale clock, and the line says they were at the
    /// check, with no verdict counted as current.</summary>
    [Fact]
    public void A_stale_selection_lists_the_results_with_the_clock_and_no_verdicts()
    {
        var map = SelectionMap.Of(ResultRows.Stale(Synthetic(), At), At);
        var answer = map.Answer(["lot"], _ => "Lot");
        Assert.Equal(["cov", "front"], answer.Rows.Select(r => r.Row.Id));
        Assert.All(answer.Rows, r => Assert.Equal(PanelStatus.Stale, r.Status));
        Assert.Equal("2 results mentioned it at 14:32. The model changed since.", answer.Line);
    }
}
