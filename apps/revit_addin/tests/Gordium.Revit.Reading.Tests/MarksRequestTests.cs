using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The trial's set-marks request (<see cref="MarksRequest"/>, docs/revit/revit_interior_reading_design.md
/// section 10): only the trial's own copies are written, each entry is written as given or refused with why, and the
/// marks written read back as the reader reads marks.</summary>
public sealed class MarksRequestTests
{
    private const string By = "eval assumption (Gordium, not the architect)";

    private static string Trial => Path.Combine(Path.GetTempPath(), "gordium_trial_test");

    [Fact]
    public void Only_a_model_under_the_trial_folder_is_opened_or_saved()
    {
        Assert.Null(MarksRequest.PathProblem(Path.Combine(Trial, "build", "model.rvt"), Trial));
        Assert.NotNull(MarksRequest.PathProblem(Path.Combine(Path.GetTempPath(), "architect", "model.rvt"), Trial));
        Assert.NotNull(MarksRequest.PathProblem(Path.Combine(Trial, "..", "model.rvt"), Trial));   // never out of it
        Assert.NotNull(MarksRequest.PathProblem(Trial + "_sibling" + Path.DirectorySeparatorChar + "model.rvt", Trial));
        Assert.NotNull(MarksRequest.PathProblem(Path.Combine(Trial, "model.json"), Trial));
        Assert.NotNull(MarksRequest.PathProblem(null, Trial));
    }

    private static JsonArray Entries(params JsonObject[] e) => new(e.Select(x => (JsonNode)x).ToArray());

    [Fact]
    public void Each_entry_is_written_as_given_or_refused_with_why()
    {
        var floor = new FakeFloor();
        floor.SetMark("C", Marks.Use, null);
        var plan = MarksRequest.Plan(Entries(
            new JsonObject { ["room"] = "C", ["mark"] = "Gordium: Use", ["value"] = "Corridor" },
            new JsonObject { ["door"] = "dA", ["mark"] = "Gordium: Exit", ["value"] = "Exterior door at discharge" },
            new JsonObject { ["room"] = "Z", ["mark"] = "Gordium: Use", ["value"] = "Other" },                      // no such room
            new JsonObject { ["room"] = "A", ["mark"] = "Gordium: Use", ["value"] = "Office" },                     // not a word
            new JsonObject { ["room"] = "A", ["mark"] = "Gordium: Pass through", ["value"] = "No" },                // not a Yes/No
            new JsonObject { ["door"] = "dA", ["mark"] = "Gordium: Use", ["value"] = "Other" },                     // not bound to doors
            new JsonObject { ["door"] = "dB", ["mark"] = "Gordium: Clear confirmed", ["value"] = "{}" },            // never the stamp alone
            new JsonObject { ["room"] = "B", ["mark"] = "Gordium: Can be locked", ["value"] = true },
            new JsonObject { ["room"] = "B", ["mark"] = "Gordium: Can be locked", ["value"] = false }),             // two values
            floor.Model(), By, "2026-11-21");
        Assert.Equal(2, plan.Writes.Count);
        Assert.Contains(plan.Writes, w => w.Element == FakeFloor.Uid("C") && w.Mark == Marks.Use && w.Value.Text == "Corridor");
        Assert.Contains(plan.Writes, w => w.Element == FakeFloor.Uid("dA") && w.Mark == Marks.Exit);
        Assert.Equal(6, plan.Refused.Count);
        Assert.Contains(plan.Refused, r => r.Contains("no room number Z"));
        Assert.Contains(plan.Refused, r => r.Contains("2 different values"));

        // a room number found twice is refused, never one of them picked
        floor.Marked[floor.MarkedIndex("B")] = floor.Marked[floor.MarkedIndex("B")] with { Number = "A" };
        Assert.Contains("which one is meant isn't known", MarksRequest.Plan(Entries(
            new JsonObject { ["room"] = "A", ["mark"] = "Gordium: Use", ["value"] = "Other" }), floor.Model(), By, "2026-11-21").Refused.Single());
    }

    [Fact]
    public void A_room_to_place_needs_its_level_a_point_a_name_and_a_number_no_room_has()
    {
        var floor = new FakeFloor();
        floor.Marked.Add(new MarkedElement { UniqueId = FakeFloor.Level, BuiltInCategory = Marks.Levels, Name = "Level 1" });
        JsonObject Place(string level, double x, string name, string number) => new()
        {
            ["level"] = level, ["at"] = new JsonArray(x, 28.0), ["name"] = name, ["number"] = number,
        };
        var (rooms, refused) = MarksRequest.Placements(new JsonArray(
            Place("Level 1", 25, "TOILET", "31"),
            Place("Level 2", 25, "TOILET", "32"),                 // no such level
            Place("Level 1", 25, "TOILET", "A"),                  // a number a Room has
            Place("Level 1", 26, "CLOSET", "31"),                 // a number placed already
            Place("Level 1", 27, "", "33"),                       // no name
            new JsonObject { ["level"] = "Level 1", ["name"] = "X", ["number"] = "34" }), floor.Model());   // no point
        var room = Assert.Single(rooms);
        Assert.Equal(new RoomToPlace(FakeFloor.Level, "Level 1", 25, 28, "TOILET", "31"), room);
        Assert.Equal(5, refused.Count);
        Assert.Contains(refused, r => r.Contains("no levels are named \"Level 2\""));
        Assert.Contains(refused, r => r.Contains("numbered A is already"));
    }

    [Fact]
    public void A_clear_opening_written_with_its_stamp_reads_back_as_the_doors_clear_width()
    {
        var floor = new FakeFloor();
        foreach (var d in new[] { "dA", "dB" })                               // no clear opening confirmed yet
            floor.Marked[floor.MarkedIndex(d)] = floor.Marked[floor.MarkedIndex(d)] with { Type = new Dictionary<Guid, MarkValue>() };
        Assert.Null(FakeFloor.Part(InteriorReader.Read(floor.Model()), "doors", "dA")!["plan"]);
        var clear = new JsonObject { ["width_in"] = 34, ["height_in"] = 80, ["operation"] = "Side-hinged door", ["source"] = "eval assumption: a 36-in leaf at 34 in clear" };
        var plan = MarksRequest.Plan(Entries(new JsonObject { ["door"] = "dA", ["clear"] = clear.DeepClone() }), floor.Model(), By, "2026-11-21");
        Assert.Empty(plan.Refused);
        Assert.Equal(5, plan.Writes.Count);
        Assert.All(plan.Writes, w => Assert.True(w.OnType));
        // written as the Revit layer writes them (on the type), then read as any model is
        var i = floor.MarkedIndex("dA");
        floor.Marked[i] = floor.Marked[i] with { Type = plan.Writes.ToDictionary(w => w.Mark.Guid, w => w.Value) };
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal(34.0 / 12, FakeFloor.Part(read, "doors", "dA")!["plan"]!["clear_width"]!.GetValue<double>(), 12);
        Assert.Contains(By, plan.Writes.Single(w => w.Mark == Marks.ClearConfirmed).Value.Text);   // the stamp says who stood in

        // a clear opening wider than the door, or two of one type's doors given different ones: refused
        Assert.Single(MarksRequest.Plan(Entries(new JsonObject
        {
            ["door"] = "dA", ["clear"] = new JsonObject { ["width_in"] = 40, ["height_in"] = 80, ["operation"] = "Side-hinged door", ["source"] = "x" },
        }), floor.Model(), By, "2026-11-21").Refused);
        floor.Marked[floor.MarkedIndex("dB")] = floor.Marked[floor.MarkedIndex("dB")] with { TypeUniqueId = "type-dA" };
        var two = MarksRequest.Plan(Entries(
            new JsonObject { ["door"] = "dA", ["clear"] = clear.DeepClone() },
            new JsonObject { ["door"] = "dB", ["clear"] = new JsonObject { ["width_in"] = 32, ["height_in"] = 80, ["operation"] = "Side-hinged door", ["source"] = "x" } }),
            floor.Model(), By, "2026-11-21");
        Assert.DoesNotContain(two.Writes, w => w.Mark == Marks.ClearWidth);
    }

    [Fact]
    public void A_window_is_found_by_its_Mark_and_its_type_marked_once()
    {
        // the New York eval (test_data/real_houses/orangetown_ny_80_south_william/eval_marks.yaml): each window's escape
        // mark and its type's operation, by the window's Mark (WN01...), as a door is found by its Mark
        var floor = new FakeFloor();
        foreach (var id in new[] { "WN01", "WN02" })
            floor.Marked.Add(new MarkedElement
            {
                UniqueId = FakeFloor.Uid(id), BuiltInCategory = Marks.Windows, Name = "36 x 54", Number = id, Family = "Fixed",
                TypeUniqueId = "type-3046", PhaseCreated = FakeFloor.Phase,
            });
        var plan = MarksRequest.Plan(Entries(
            new JsonObject { ["window"] = "WN01", ["mark"] = "Gordium: Escape opening", ["value"] = true },
            new JsonObject { ["window"] = "WN01", ["mark"] = "Gordium: Operation", ["value"] = "Double hung" },
            new JsonObject { ["window"] = "WN02", ["mark"] = "Gordium: Operation", ["value"] = "Double hung" },
            new JsonObject { ["window"] = "WN03", ["mark"] = "Gordium: Escape opening", ["value"] = true },         // no such window
            new JsonObject { ["window"] = "dA", ["mark"] = "Gordium: Escape opening", ["value"] = true },           // a door's Mark
            new JsonObject { ["window"] = "WN02", ["mark"] = "Gordium: Exit door", ["value"] = true }),             // not bound to windows
            floor.Model(), By, "2026-11-21");
        Assert.Contains(plan.Writes, w => w.Element == FakeFloor.Uid("WN01") && w.Mark == Marks.EscapeOpening && w.Value.Integer == 1);
        // the two windows share a type: its operation written once, on the type
        Assert.Single(plan.Writes, w => w.Mark == Marks.Operation && w.OnType && w.Element == "type-3046" && w.Value.Text == "Double hung");
        Assert.Equal(2, plan.Writes.Count);
        Assert.Contains(plan.Refused, r => r.Contains("no window Mark WN03"));
        Assert.Contains(plan.Refused, r => r.Contains("no window Mark dA"));
        Assert.Contains(plan.Refused, r => r.Contains("Gordium: Exit door isn't bound to OST_Windows"));
        Assert.Equal(3, plan.Refused.Count);
    }
}
