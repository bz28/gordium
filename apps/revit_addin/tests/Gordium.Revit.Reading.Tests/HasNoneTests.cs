using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>What the house has none of, step 6 (docs/revit/revit_interior_reading_design.md, sections 2 and 4): the
/// architect's ticks on Project Information, read into the description only when ticked Yes, nothing of the kind is
/// drawn and nothing could hide one. Pinned on the hand-worked houses drawn as fake Revit records, one change at a
/// time: an unset tick is not stated (never No), a tick against what is drawn is never sent and is listed first, and
/// anything that could hide one holds it back.</summary>
public sealed class HasNoneTests
{
    private static readonly MarkValue Yes = new(true, 1);
    private static readonly MarkValue No = new(true, 0);
    private static readonly MarkValue Unset = new(false, 0);           // never set: Revit's AsInteger() gives 0

    private static NoneTick Tick(InteriorReadResult read, NoneKind kind) => read.Ticks.Single(t => t.Kind == kind);

    private static NoneKind Claim(string kind) => HasNone.Claims.Single(k => k.Kind == kind);

    [Fact]
    public void The_kinds_are_exactly_the_formats()
    {
        // the has_none kinds and the lists the measuring code reads, from its own tables (never retyped)
        var json = Env.RunCode(
            "import json; from model_measurement.interior import has_none as h; " +
            "print(json.dumps({'kinds': list(h.KINDS), 'listed': h.LISTED}))");
        using var doc = JsonDocument.Parse(json);
        Assert.Equal(doc.RootElement.GetProperty("kinds").EnumerateArray().Select(e => e.GetString()), HasNone.Claims.Select(k => k.Kind));
        var listed = doc.RootElement.GetProperty("listed").EnumerateObject().Select(p => p.Value.GetString()).ToHashSet();
        Assert.All(HasNone.All.Where(k => k.IsList), k => Assert.Contains(k.Kind, listed));
        Assert.DoesNotContain("rooms", HasNone.All.Select(k => k.Kind));        // rooms: [] is a house not drawn, never none
        Assert.Equal(HasNone.All.Select(k => k.Mark), Marks.All.Where(m => m.Name.StartsWith("Gordium: This house has no", StringComparison.Ordinal)));
        Assert.All(HasNone.All, k => Assert.Equal([Marks.ProjectInformation], k.Mark.Categories));
    }

    [Fact]
    public void A_tick_sends_the_empty_list_only_when_yes()
    {
        // house 1: no stairs, no guards, ticked so by the drawing
        var house = FakeHouse.Draw("1_ranch_compliant");
        var read = InteriorReader.Read(house.Model());
        Assert.Empty(read.Interior["stairs"]!.AsArray());
        Assert.Empty(read.Interior["guards"]!.AsArray());
        Assert.Empty(read.StairsNotRead);
        foreach (var value in new[] { Unset, No })
        {
            house.ProjectMarks[Marks.NoStairs.Guid] = value;
            house.ProjectMarks[Marks.NoGuards.Guid] = value;
            read = InteriorReader.Read(house.Model());
            Assert.Null(read.Interior["stairs"]);                         // nothing found is never "none"
            Assert.Null(read.Interior["guards"]);
            Assert.False(Tick(read, HasNone.Stairs).Sent);
        }
        Assert.True(Tick(read, HasNone.Stairs).Ticked is false);           // No reads as No (and unset as null, below)
        house.ProjectMarks.Remove(Marks.NoStairs.Guid);                   // not on Project Information at all
        Assert.Null(InteriorReader.Read(house.Model()).Interior["stairs"]);
        Assert.Null(Tick(InteriorReader.Read(house.Model()), HasNone.Stairs).Ticked);
    }

    [Fact]
    public void A_tick_against_what_is_drawn_is_never_sent_and_is_listed_first()
    {
        // house 2 has a stair: ticked "no stairs", its stair isn't read either (the two disagree)
        var house = FakeHouse.Draw("2_two_story_small_window");
        house.ProjectMarks[Marks.NoStairs.Guid] = Yes;
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains(read.StairsNotRead, w => w.StartsWith("Gordium: This house has no stairs is Yes, but stair", StringComparison.Ordinal));
        var list = MarkingList.Build(house.Model());
        Assert.Single(list.HasNoneConflicts);
        Assert.StartsWith("Conflict: Gordium: This house has no stairs is Yes, but stair", MarkingList.Text(list));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
        Assert.Contains(list.HasNoneLines, l => l.StartsWith("Gordium: This house has no stairs: Yes, but it disagrees", StringComparison.Ordinal));

        // house 1 has doors: "no doors" ticked is a conflict, its doors not read
        house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.NoDoors.Guid] = Yes;
        read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["doors"]);
        Assert.Equal(2, Tick(read, HasNone.Doors).Conflicts.Count);

        // house 4's loft guard is a railing on no stair
        house = FakeHouse.Draw("4_loft");
        house.ProjectMarks[Marks.NoGuards.Guid] = Yes;
        read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["guards"]);
        Assert.Contains("is drawn on no stair (a guard)", Assert.Single(Tick(read, HasNone.Guards).Conflicts));

        // "these are all the stairs: No" says a stair isn't drawn as one: against "no stairs"
        house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.AllStairs.Guid] = No;
        read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains("These are all the stairs is No", Assert.Single(Tick(read, HasNone.Stairs).Conflicts));
        // "all the guards and handrails: No" likewise against "no guards"
        house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.AllGuards.Guid] = No;
        Assert.Null(InteriorReader.Read(house.Model()).Interior["guards"]);
    }

    public static TheoryData<string> Hiding() => ["closed workset", "unloaded link", "nested link", "coordination model",
                                                 "generic model", "multistory stair", "stairs not read", "inside not read"];

    [Theory]
    [MemberData(nameof(Hiding))]
    public void Anything_that_could_hide_one_holds_the_tick_back(string what)
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var model = house.Model();
        switch (what)
        {
            case "closed workset": house.Worksets.Add(new WorksetRecord("w9", "Stair core", false)); break;
            case "unloaded link": house.Links.Add(new InteriorLink("l", "Core.rvt", false, null, 0, 0, false)); break;
            case "nested link": house.Links.Add(new InteriorLink("l", "Core.rvt", true, null, 0, 0, true)); break;
            case "coordination model": house.CoordinationModels = 1; break;
            case "generic model": house.StairCandidates.Add(new("gm", "OST_GenericModel", "Ladder", "an in-place family")); break;
            case "multistory stair": house.StairCandidates.Add(new("ms", "OST_MultistoryStairs", "Core", "a multistory stair")); break;
        }
        model = what switch
        {
            "stairs not read" => house.Model() with { Interior = house.Model().Interior! with { Stairs = null } },
            "inside not read" => house.Model() with { Interior = null },
            _ => house.Model(),
        };
        var read = InteriorReader.Read(model);
        Assert.Null(read.Interior["stairs"]);
        Assert.Null(read.Interior["guards"]);                              // the guards' blockers are the stairs' too
        var tick = Tick(read, HasNone.Stairs);
        Assert.True(tick.Ticked);
        Assert.NotEmpty(tick.Blockers);
        Assert.False(tick.Sent);
        Assert.All(read.StairsNotRead, w => Assert.StartsWith("Gordium: This house has no stairs is Yes, but isn't sent", w));
        if (what != "inside not read")                                   // then the list says it isn't checked yet
            Assert.Contains(MarkingList.Build(model).HasNoneLines, l => l.StartsWith("Gordium: This house has no stairs: Yes, but not read as none while", StringComparison.Ordinal));
    }

    [Fact]
    public void No_guards_needs_every_railing_on_a_stair_read_as_a_handrail()
    {
        // house 2: its handrail is a railing on its stair, read as a handrail beside a wall: "no guards" sent
        var house = FakeHouse.Draw("2_two_story_small_window");
        Assert.Empty(InteriorReader.Read(house.Model()).Interior["guards"]!.AsArray());
        // with the stairs not read, whether that railing is a handrail or a guard along the stair isn't known
        house.ProjectMarks.Remove(Marks.AllStairs.Guid);
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["guards"]);
        Assert.Contains(Tick(read, HasNone.Guards).Blockers, b => b.Contains("the stairs aren't read"));
    }

    [Fact]
    public void A_claim_is_sent_with_its_source_and_the_checker_takes_it()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.NoRamps.Guid] = Yes;
        house.ProjectMarks[Marks.NoPatioCovers.Guid] = Yes;
        house.ProjectMarks[Marks.NoShipLadders.Guid] = No;                // No: no claim, never "none"
        var read = InteriorReader.Read(house.Model());
        var entries = read.Interior["has_none"]!.AsArray().Select(e => e!.AsObject()).ToList();
        Assert.Equal(["ramp", "patio_cover"], entries.Select(e => e["kind"]!.GetValue<string>()));
        Assert.Equal("ticked by the architect (Gordium: This house has no ramps: Yes, on Project Information); no Ramp elements in the model",
                     entries[0]["source"]!.GetValue<string>());
        Assert.Equal("ticked by the architect (Gordium: This house has no patio covers: Yes, on Project Information)",
                     entries[1]["source"]!.GetValue<string>());
        Assert.True(read.Evidence["has_none"]!["ramp"]!["sent"]!.GetValue<bool>());

        // the measuring code takes both: ramps none, every escape opening not into a patio cover
        var path = Path.Combine(Path.GetTempPath(), $"gordium_has_none_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, read.Interior.ToJsonString());
        try
        {
            var got = JsonNode.Parse(Env.RunCode(
                "import json, sys; from model_measurement.interior import measure; m = measure(json.load(open(sys.argv[1]))); " +
                "print(json.dumps({'has_none': sorted(m['has_none']), 'ramp': m['parts']['ramp'], " +
                "'into': [p['measures'].get('opening_into_patio_cover') for p in m['parts']['emergency_escape_opening']]}))", path))!;
            Assert.Equal(["patio_cover", "ramp"], got["has_none"]!.AsArray().Select(n => n!.GetValue<string>()));
            Assert.Empty(got["ramp"]!.AsArray());
            Assert.All(got["into"]!.AsArray(), n => Assert.False(n!.GetValue<bool>()));
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void A_ramp_drawn_or_unread_holds_no_ramps_back()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.NoRamps.Guid] = Yes;
        house.Ramps!.Add(new RampRecord("ramp-1", "Ramp 1:12"));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["has_none"]);
        Assert.Equal(["ramp \"Ramp 1:12\" is drawn"], Tick(read, Claim("ramp")).Conflicts);
        Assert.Contains(MarkingList.Build(house.Model()).HasNoneConflicts, c => c.Contains("ramp \"Ramp 1:12\" is drawn"));

        house.Ramps[0] = house.Ramps[0] with { PhaseDemolished = FakeHouse.LastPhase };   // demolished by the last phase
        Assert.NotNull(InteriorReader.Read(house.Model()).Interior["has_none"]);

        house.Ramps = null;                                                 // the Revit layer couldn't list them
        Assert.Null(InteriorReader.Read(house.Model()).Interior["has_none"]);
        house.Ramps = [];
        house.Links.Add(new InteriorLink("l", "Site.rvt", true, null, 0, 0, false, Ramps: 1));
        Assert.Contains("holds 1 ramp(s)", Assert.Single(Tick(InteriorReader.Read(house.Model()), Claim("ramp")).Blockers));
    }

    [Fact]
    public void A_space_claim_needs_every_room_read()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        foreach (var k in new[] { "basement", "habitable_attic", "sleeping_loft" })
            house.ProjectMarks[Claim(k).Mark.Guid] = Yes;
        Assert.Equal(3, InteriorReader.Read(house.Model()).Interior["has_none"]!.AsArray().Count);
        var i = house.MarkedIndex("living");
        house.Marked[i] = house.Marked[i] with { Placement = RoomPlacement.Unplaced };      // a room not on the plan
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["has_none"]);
        Assert.Contains("1 Room is unplaced", Assert.Single(Tick(read, Claim("basement")).Blockers));
        // a patio cover isn't a room: only what could hide anything holds it back
        house.ProjectMarks[Marks.NoPatioCovers.Guid] = Yes;
        Assert.Equal("patio_cover", Assert.Single(InteriorReader.Read(house.Model()).Interior["has_none"]!.AsArray())!["kind"]!.GetValue<string>());
    }

    [Fact]
    public void The_marking_list_says_each_tick_and_proposes_only()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var list = MarkingList.Build(house.Model());
        Assert.Empty(list.HasNoneConflicts);
        Assert.Equal(HasNone.All.Count, list.HasNoneLines.Count);
        Assert.Equal("Gordium: This house has no stairs: Yes (on Project Information): read as a house with none.", list.HasNoneLines[0]);
        Assert.Equal("Gordium: This house has no ramps: not set on Project Information: not stated, never read as none. Gordium found " +
                     "no Ramp elements in the model: tick Yes if the house has none (Gordium never ticks it for you).",
                     list.HasNoneLines.Single(l => l.StartsWith("Gordium: This house has no ramps", StringComparison.Ordinal)));
        Assert.Equal("Gordium: This house has no basements: not set on Project Information: not stated, never read as none.",
                     list.HasNoneLines.Single(l => l.StartsWith("Gordium: This house has no basements", StringComparison.Ordinal)));
        house.ProjectMarks[Marks.NoBasements.Guid] = No;
        Assert.Contains("Gordium: This house has no basements: No (on Project Information): not stated as none, so the rules for basements need review.",
                        MarkingList.Build(house.Model()).HasNoneLines);
        Assert.Contains("Gordium: This house has no", MarkingList.Text(list));
        // the proposal is shown, never sent
        Assert.Null(InteriorReader.Read(house.Model()).Interior["has_none"]);
    }

    [Fact]
    public void A_list_ticked_no_says_read_as_drawn_only_when_that_kind_is_read()
    {
        // review round 1: house 1, "no stairs" No and "these are all the stairs" not set: no stair is read at all
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.ProjectMarks[Marks.NoStairs.Guid] = No;
        house.ProjectMarks.Remove(Marks.AllStairs.Guid);
        var line = MarkingList.Build(house.Model()).HasNoneLines[0];
        Assert.DoesNotContain("read as drawn", line);
        Assert.StartsWith("Gordium: This house has no stairs: No (on Project Information): not stated as none, so no stairs are " +
                          "read for egress (Gordium: These are all the stairs is not set", line);
        // house 2 with its stair read: "read as drawn" is true
        house = FakeHouse.Draw("2_two_story_small_window");
        house.ProjectMarks[Marks.NoStairs.Guid] = No;
        Assert.EndsWith("the stairs are read as drawn.", MarkingList.Build(house.Model()).HasNoneLines[0]);
    }

    [Fact]
    public void A_list_ticked_no_names_every_reason_that_kind_is_not_read()
    {
        // review round 2: the reasons were cut to 3 without a word; the architect fixing those 3 would think the guards read
        var house = FakeHouse.Draw("4_loft");
        house.ProjectMarks[Marks.NoGuards.Guid] = No;
        house.ProjectMarks.Remove(Marks.AllGuards.Guid);
        house.ProjectMarks.Remove(Marks.AllStairs.Guid);
        house.Worksets.Add(new WorksetRecord("w9", "Stair core", false));
        house.CoordinationModels = 1;
        var model = house.Model();
        var reasons = InteriorReader.Read(model).GuardsNotRead;
        Assert.True(reasons.Count > 3, $"the house must give more than 3 reasons, gave {reasons.Count}");
        var line = MarkingList.Build(model).HasNoneLines.Single(l => l.StartsWith("Gordium: This house has no guards", StringComparison.Ordinal));
        Assert.All(reasons, r => Assert.Contains(r, line));
    }

    [Fact]
    public void The_add_in_builds_the_marking_list_from_the_model_with_its_inside_read()
    {
        // review round 1: built from the marks alone, every Yes tick read "the model's inside wasn't read", no conflict
        // was listed and no proposal shown. The command builds it from RevitInterior.Model (the reader's own model)
        var command = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "RevitMarks.cs"));
        Assert.Contains("var model = RevitInterior.Model(doc);", command);    // read once: the list and the log's ids
        Assert.Contains("MarkingList.Build(model, plan, clearWriteFailed: failed)", command);   // (and a failed clear-opening write)
        Assert.DoesNotContain("MarkingList.Build(RevitMarks.Model(doc)", command);
        // and through that model a conflict is listed first (the Reading-layer seam the command calls)
        var house = FakeHouse.Draw("2_two_story_small_window");
        house.ProjectMarks[Marks.NoStairs.Guid] = Yes;
        Assert.StartsWith("Conflict: ", MarkingList.Text(MarkingList.Build(house.Model())));
        // without the inside read (any other caller), a tick isn't called held back: it says it isn't checked yet
        var bare = MarkingList.Build(house.Model() with { Interior = null });
        Assert.Empty(bare.HasNoneConflicts);
        Assert.Equal("Gordium: This house has no stairs: Yes on Project Information (not yet checked against the model: run Read " +
                     "inside to see whether it is read as none).", bare.HasNoneLines[0]);
        Assert.All(bare.HasNoneLines, l => Assert.DoesNotContain("wasn't read", l));
    }
}
