using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A door type's leaves (BCNYS 1010.1.1: where a door opening has two leaves without a mullion, one leaf gives
/// the 32 in): the type mark Gordium: Leaves, sent as <c>doors[].leaves</c> only as 1 or 2 (blank or another number is
/// said and not sent, so the door width rule needs review, never a pass on a pair's whole opening). Before it, every
/// door width result asked "Mark the door leaves in the model", a mark Revit didn't have: the check's ask now names the
/// field, and the pane's card opens this mark.</summary>
public sealed class DoorLeavesTests
{
    private static void SetTypeMark(FakeFloor floor, string id, MarkValue? value)
    {
        var i = floor.MarkedIndex(id);
        var type = new Dictionary<Guid, MarkValue>(floor.Marked[i].Type);
        if (value is null)
            type.Remove(Marks.DoorLeaves.Guid);
        else
            type[Marks.DoorLeaves.Guid] = value;
        floor.Marked[i] = floor.Marked[i] with { Type = type };
    }

    [Fact]
    public void The_mark_is_a_count_set_once_on_a_door_type_quoting_1010_1_1()
    {
        var m = Marks.DoorLeaves;
        Assert.Contains(m, Marks.All);
        Assert.Equal((MarkValueKind.Integer, MarkBinding.Type, "doors[].leaves"), (m.Kind, m.Binding, m.Feeds));
        Assert.Equal([Marks.Doors], m.Categories);
        Assert.Contains("\"Where this section requires a minimum clear opening width of 32 inches (813 mm) and a door opening includes two door leaves without a mullion, one leaf shall provide a minimum clear opening width of 32 inches (813 mm).\"",
                        m.Description, StringComparison.Ordinal);
        // a pair with a mullion: 1 only if the clear width given is one leaf's own (never a pair's whole opening as 1)
        // review round 2: the narrower leaf's, each opening of a mullioned pair needing the 32 in (1010.1)
        Assert.Contains("A pair with a mullion is two door openings, each needing the 32 in itself: give 1 only if this type's Gordium: Clear width is the narrower leaf's own opening, else 2.",
                        m.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void Leaves_are_sent_only_as_1_or_2_and_anything_else_is_said_never_sent()
    {
        var floor = new FakeFloor();
        SetTypeMark(floor, "dA", new(true, 1));
        SetTypeMark(floor, "dB", new(true, 2));
        SetTypeMark(floor, "dS", new(true, 3));                          // not a count Gordium reads
        SetTypeMark(floor, "dE", new(false, 0));                         // never set (Revit reads 0)
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal(1, FakeFloor.Part(read, "doors", "dA")!["leaves"]!.GetValue<int>());
        Assert.Equal(2, FakeFloor.Part(read, "doors", "dB")!["leaves"]!.GetValue<int>());
        foreach (var id in new[] { "dS", "dE", "dS2" })                  // dS2: no mark at all
            Assert.Null(FakeFloor.Part(read, "doors", id)!["leaves"]);
        var said = read.Notes.Where(n => n.Field == "doors.leaves").ToDictionary(n => n.Part, n => n.Why);
        Assert.Equal("Gordium: Leaves is 3 on its type, not 1 or 2", said[FakeFloor.Uid("dS")]);
        Assert.Equal("Gordium: Leaves is not set on its type", said[FakeFloor.Uid("dE")]);
    }

    /// <summary>The trial apartment's real answer (no door type's leaves marked): the door width results' ask names the
    /// field Gordium: Leaves answers, one card, never "Mark the door leaves in the model" (a mark Revit didn't have).</summary>
    [Fact]
    public void The_apartments_door_width_ask_is_one_card_opening_the_leaves_mark()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        var about = new WorkerAbout("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
        var model = ResultViews.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), about)));
        var cards = model.Fix.SelectMany(g => g.Cards).ToList();
        var card = Assert.Single(cards, c => c.Field == "doors[].leaves");
        Assert.Equal((FixKind.Mark, "Set each door type's leaves (a pair with a mullion: 1 only at the narrower leaf's clear width)"), (card.Kind, card.Headline));
        Assert.Equal(Marks.DoorLeaves, Marks.All.Single(k => k.Feeds == card.Field));
        Assert.DoesNotContain(cards, c => c.Headline.Contains("door leaves in the model", StringComparison.Ordinal));
        // the button selects the doors and opens Properties, where a type's mark is reached by Edit Type (review round
        // 1: "set Gordium: Leaves there" named a field the instance palette doesn't hold)
        var cause = Assert.Single(ResultRows.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), about)),
                                                   null, [], null).Causes, c => c.Fields.Contains("doors[].leaves"));
        var labels = cause.Elements.ToDictionary(e => e, e => "door " + e, StringComparer.Ordinal);   // the doors are in the model
        Assert.Equal(CardAction.ShowAndProperties, CauseCards.Action(cause, labels));
        Assert.Contains("Edit Type", CauseCards.Note(cause, labels), StringComparison.Ordinal);
        Assert.Contains("Edit Type", CauseCards.AfterProperties(cause, 10), StringComparison.Ordinal);
        // review rounds 2 and 3: Edit Type is greyed with more than one type selected, and picking a type in Properties'
        // Type Selector would retype every selected door: one element of a type, or the type in the Project Browser
        var after = CauseCards.AfterProperties(cause, 10);
        Assert.Contains("select one element of a type and click Edit Type", after, StringComparison.Ordinal);
        Assert.Contains("right-click the type in the Project Browser and choose Type Properties", after, StringComparison.Ordinal);
        Assert.DoesNotContain("type list", after, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Type Selector", after, StringComparison.Ordinal);
        var fix = Assert.Single(Fixes.Of([cause], labels));
        Assert.Contains("Edit Type", Fixes.Note(fix), StringComparison.Ordinal);
        // an element's own mark says nothing of types
        Assert.Equal("", CauseCards.OnType([Marks.ExitDoor]));
        // every card that asks for a mark's field has the mark that feeds it (no dead end)
        var fed = Marks.All.SelectMany(m => m.Feeds.Split(", ").Select(p => p.Split(' ')[0])).ToHashSet(StringComparer.Ordinal);
        Assert.All(cards.Where(c => c.Kind is FixKind.Mark or FixKind.Answer && c.Field is not null), c => Assert.Contains(c.Field!, fed));
    }
}
