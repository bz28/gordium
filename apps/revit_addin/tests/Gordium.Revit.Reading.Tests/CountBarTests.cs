using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The compact count bar (CountBar): one line per law with its most important counts, every failure always
/// shown, the rest behind "+N more" and in the tooltip, nothing recounted or lost.</summary>
public sealed class CountBarTests
{
    private static CountChip Fails(string w) => new(w, Tone.Fails);
    private static CountChip Review(string w) => new(w, Tone.Review);
    private static CountChip Pass(string w) => new(w, Tone.Complies);

    /// <summary>The Revit trial's counts (106 Ithaca Rd, 2026-11-22): 6 lines of chips at the docked pane before.</summary>
    private static readonly CountLine Zoning = new("Zoning (City of Ithaca)",
        [Fails("1 does not comply"), Review("9 need review"), Pass("10 comply"), Review("1 to answer"),
         Review("1 not checked in this release"), Review("2 use details to answer")]);

    private static readonly CountLine Egress = new("Egress (NY State Residential Code 2025)",
        [Review("8 to review"), Review("8 parts not read yet"), Review("86 sections not checked yet")]);

    [Fact]
    public void Each_law_shows_its_most_important_counts_and_the_rest_behind_more()
    {
        var z = CountBar.Row(Zoning);
        Assert.Equal("Zoning", z.Title);
        Assert.Equal(["1 does not comply", "9 need review"], z.Shown.Select(c => c.Words));
        Assert.Equal(("+4", "4 more counts"), (z.More, z.MoreWords));
        var e = CountBar.Row(Egress);
        Assert.Equal(["8 to review", "8 parts not read yet"], e.Shown.Select(c => c.Words));
        Assert.Equal(("+1", "1 more count"), (e.More, e.MoreWords));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Every_count_is_reachable_in_the_workers_order_and_none_is_made(bool open)
    {
        foreach (var line in new[] { Zoning, Egress })
        {
            var row = CountBar.Row(line, open);
            Assert.Equal(line.Chips, row.Shown.Concat(row.Hidden).OrderBy(c => line.Chips.ToList().IndexOf(c)));
            Assert.Equal(line.Chips.Count, row.Shown.Count + row.Hidden.Count);
            Assert.Equal(string.Join("\n", [line.Title!, .. line.Chips.Select(c => c.Words)]), row.Tooltip);
        }
    }

    [Fact]
    public void Opened_every_count_is_on_the_line()
    {
        var z = CountBar.Row(Zoning, open: true);
        Assert.Equal(Zoning.Chips, z.Shown);
        Assert.Null(z.More);
    }

    [Fact]
    public void A_failure_is_never_hidden_whatever_the_room()
    {
        var line = new CountLine("Egress (x)", [Review("2 to review"), Fails("3 do not comply"), Fails("Windows: 1 does not comply"), Pass("4 comply")]);
        var row = CountBar.Row(line);
        Assert.Equal(["3 do not comply", "Windows: 1 does not comply"], row.Shown.Select(c => c.Words));
        Assert.All(row.Hidden, c => Assert.NotEqual(Tone.Fails, c.Tone));
        Assert.Contains(CountBar.Row(line, keep: 0).Shown, c => c.Tone == Tone.Fails);
    }

    [Fact]
    public void Two_counts_in_the_same_words_are_each_kept()
    {
        var line = new CountLine(null, [Review("1 to answer"), Review("1 to answer"), Review("1 to answer")]);
        var row = CountBar.Row(line);
        Assert.Equal((2, 1), (row.Shown.Count, row.Hidden.Count));
        Assert.Null(row.Title);
    }

    [Fact]
    public void The_whole_summarys_line_has_no_title()
    {
        var row = CountBar.Row(new CountLine(null, [Review("2 need review")]));
        Assert.Equal("2 need review", row.Tooltip);
        Assert.Null(row.More);
    }
}
