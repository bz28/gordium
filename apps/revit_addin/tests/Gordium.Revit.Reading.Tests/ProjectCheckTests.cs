using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>"Check my project" without Revit (reading design note, section 9): conformance scene 01 (the box house)
/// as the outside and a hand-worked interior house as the inside, both fake Revit records, with the lot facts as
/// Gordium's marks on Project Information, made into one check_site request and checked by the real worker. The
/// outside's rows must be the scene's hand-worked verdicts, the inside's the house's; a fact missing sends nothing; a
/// project with no lot never complies.</summary>
public sealed class ProjectCheckTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly SceneDrawing Scene = SceneDrawing.Named("01_box_house");

    /// <summary>Scene 01 as the project's outside, with Gordium spot-grade markers at the middle of each wall at 0 (the
    /// scene states its ground flat at 0 instead, which no mark sends: the spots give the same ground), in the
    /// inside's phases (one document: both reads see the same phases).</summary>
    internal static RevitModel Outside(RevitModel inside)
    {
        var model = Scene.Model(Scene.Steps[0]);
        var f = new FakeRevit(model.InternalToShared);
        var spots = new[] { (30.0, 30.0), (45.0, 55.0), (30.0, 80.0), (15.0, 55.0) }.Select((p, k) => new RevitElement
        {
            UniqueId = $"uid-spot-{k}", BuiltInCategory = "OST_GenericModel", Category = "Generic Models",
            Mark = GordiumMark.SpotGrade, Location = f.Place(p.Item1, p.Item2, 0),
        });
        return model with { Elements = [.. model.Elements, .. spots], Phases = inside.Phases };
    }

    /// <summary>The south lot edge (the scene's street) as Gordium writes it when the architect clicks it.</summary>
    internal static string SouthEdge(RevitModel outside)
    {
        var c = outside.LotLines[0].Curves.Single(c => Math.Abs(c.Start.Y - c.End.Y) < 1e-9 && Math.Min(c.Start.Y, c.End.Y) < 1);
        return StreetEdges.Format([(c.Start, c.End)]);
    }

    /// <summary>The scene's hand-worked zoning verdicts (its <c>egress.waiting</c> row is the one a check with no
    /// inside gives: here the inside is sent).</summary>
    private static IEnumerable<KeyValuePair<string, string>> Outside(SceneDrawing scene) =>
        scene.Verdicts(scene.Steps[0]).Where(p => !p.Key.StartsWith("egress.", StringComparison.Ordinal));

    private static void Mark(FakeHouse house, MarkDefinition m, MarkValue v) => house.ProjectMarks[m.Guid] = v;

    /// <summary>The scene's facts as marks: R-1b, one family detached, surveyed, not a corner, ground from the spots,
    /// the south edge picked.</summary>
    private static (FakeHouse House, RevitModel Outside) Project(string house)
    {
        var h = FakeHouse.Draw(house);
        var outside = Outside(h.Model());
        Mark(h, Marks.Zone, new(true, Text: "R-1b"));
        Mark(h, Marks.Use, new(true, Text: "one_family_detached"));
        Mark(h, Marks.LotSurveyed, new(true, 1));
        Mark(h, Marks.CornerLot, new(true, 0));
        Mark(h, Marks.GroundFrom, new(true, Text: "Spot grades"));
        Mark(h, Marks.StreetEdge, new(true, Text: SouthEdge(outside)));
        return (h, outside);
    }

    private async Task<(ProjectPrepared Prepared, CheckResult Result)> Check(FakeHouse house, RevitModel outside)
    {
        var client = await worker.RunningAsync();
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
        Assert.Empty(prepared.Missing);
        return (prepared, await ProjectCheck.SendAsync(client, prepared.Request!));
    }

    /// <summary>The read's timings (the log's <c>read_steps</c>) never reach the worker: the same project prepared with
    /// the steps kept, as Check project keeps them (begun on this thread, the prepare waited for on it), and without,
    /// gives the same request, byte for byte, and no step's name is in it.</summary>
    [Fact]
    public async Task The_request_is_byte_for_byte_the_same_with_the_read_steps_kept_or_not()
    {
        var (house, outside) = Project("1_ranch_compliant");
        var client = await worker.RunningAsync();
        static string Sent(ProjectRequest r) => new JsonObject
        {
            ["site"] = r.Site.DeepClone(), ["facts"] = r.Facts.DeepClone(), ["interior"] = r.Interior.DeepClone(),
        }.ToJsonString();
        var plain = Sent((await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client))).Request!);
        var steps = new ReadSteps();
        string kept;
        using (ReadSteps.Begin(steps))
        {
            ReadSteps.Count("outside.elements", 7);
            ReadSteps.Link("Structure.rvt", 1, 0.5, 3);
            kept = ReadSteps.Time("prepare", () => Sent(ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client))
                                                      .GetAwaiter().GetResult().Request!));
        }
        Assert.Equal(plain, kept);
        foreach (var name in new[] { "read_steps", "outside.elements", "Structure.rvt", "\"seconds\"", "\"calls\"" })
            Assert.DoesNotContain(name, kept, StringComparison.Ordinal);
        Assert.Contains("prepare", Assert.IsType<Dictionary<string, object>>(steps.ToLog()["steps"]).Keys);
    }

    [Fact]
    public async Task The_box_house_with_a_compliant_ranch_inside_gives_the_scenes_verdicts_and_egress_rows()
    {
        var (house, outside) = Project("1_ranch_compliant");
        var (prepared, result) = await Check(house, outside);

        // one request: the site, the facts as the marks state them (the street the lot's own south edge), the inside
        var facts = prepared.Request!.Facts;
        Assert.Equal(ProjectFacts.Jurisdiction, facts["jurisdiction"]!.GetValue<string>());
        Assert.Equal("R-1b", facts["zone"]!.GetValue<string>());
        Assert.Equal("spot", facts["grade_from"]!.GetValue<string>());
        Assert.Equal("[[[0,0],[60,0]]]", facts["street_line"]!.ToJsonString());
        Assert.Equal("gordium.interior/1", prepared.Request.Interior["format"]!.GetValue<string>());
        Assert.Equal(FakeHouse.LastPhase, prepared.PhaseChecked);
        // the street the check was sent with, named in every result (review round 1)
        Assert.Equal("the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)", prepared.Street);
        Assert.Contains("; street line: the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0).",
                        ResultText.Format(result, "phase 2", prepared.OptionsChecked, prepared.Inside, street: prepared.Street).Checked,
                        StringComparison.Ordinal);

        var got = result.Items.ToDictionary(i => i.Id, i => i.StatusWord);
        foreach (var (id, word) in Outside(Scene))
            Assert.True(got.TryGetValue(id, out var mine) && mine == word, $"{id}: the scene says {word}, the check {(mine ?? "no row")}");
        Assert.DoesNotContain("egress.waiting", got.Keys);          // the inside went with it: egress isn't waiting
        // the inside was checked too: the ranch's escape windows' clear width complies (26 and 30 in wide, 20 needed)
        var widths = result.Items.Where(i => i.Id.StartsWith("general.r319_2_2_escape_opening_min_net_clear_width@", StringComparison.Ordinal)).ToList();
        Assert.Equal(2, widths.Count);
        Assert.All(widths, i => Assert.Equal(Verdict.Complies, i.Status));
        Assert.DoesNotContain(result.Items, i => i.Status == Verdict.DoesNotComply);
        Assert.NotEqual(Verdict.Complies, result.State);        // the use details and the egress still to review
    }

    [Fact]
    public async Task A_basement_window_too_small_fails_in_the_same_check()
    {
        var (house, outside) = Project("5_basement_window_well");
        var (_, result) = await Check(house, outside);
        Assert.Equal(Verdict.DoesNotComply, result.State);
        var area = result.Items.Where(i => i.Id.StartsWith("general.r319_2_1_escape_opening_min_net_clear_area@", StringComparison.Ordinal)).ToList();
        Assert.Contains(area, i => i.Status == Verdict.DoesNotComply);
        // and the outside's rows are still the scene's
        var got = result.Items.ToDictionary(i => i.Id, i => i.StatusWord);
        foreach (var (id, word) in Outside(Scene))
            Assert.Equal(word, got[id]);
    }

    [Fact]
    public async Task With_no_lot_nothing_complies()
    {
        var (house, outside) = Project("1_ranch_compliant");
        var client = await worker.RunningAsync();
        var prepared = await ProjectCheck.PrepareAsync(outside with { LotLines = [] }, house.Model(), new WorkerLeftOut(client));
        Assert.Empty(prepared.Missing);                         // sent: the check says why there is no lot
        Assert.Null(prepared.Request!.Site["lot"]);
        var result = await ProjectCheck.SendAsync(client, prepared.Request);
        Assert.NotEqual(Verdict.Complies, result.State);
        // only what needs no lot may comply: the use, and the building's own height and stories (from the ground)
        Assert.Equal(["R-1b.height", "R-1b.stories", "R-1b.use"],
                     result.Items.Where(i => i.Group is "site" or "building" && i.Status == Verdict.Complies).Select(i => i.Id).Order(StringComparer.Ordinal));
        foreach (var id in new[] { "R-1b.lot_area_one_family_detached", "R-1b.front_yard", "R-1b.rear_yard", "R-1b.lot_coverage" })
            Assert.Contains(result.Items, i => i.Id == id && i.Status == Verdict.NeedsReview);
    }

    /// <summary>An asker that fails the test if asked: nothing may be read or sent.</summary>
    private sealed class NeverAsked : ILeftOutAsker
    {
        public Task<IReadOnlyList<LeftOutDecision>> AskAsync(JsonObject? lot, JsonArray objects, JsonArray buildings,
                                                             JsonObject definitions, CancellationToken cancel = default) =>
            throw new InvalidOperationException("the worker was asked although a fact is missing");
    }

    [Theory]
    [InlineData("zone", "Gordium: Zone")]
    [InlineData("use", "Gordium: Use")]
    [InlineData("lot_surveyed", "Gordium: Lot surveyed")]
    [InlineData("street_line", "Gordium: Street edge")]
    public async Task A_required_fact_missing_sends_nothing_and_says_what_to_fill_in(string fact, string mark)
    {
        var (house, outside) = Project("1_ranch_compliant");
        var m = Marks.All.Single(x => x.Name == mark);
        Assert.Contains(fact, m.Feeds);
        house.ProjectMarks[m.Guid] = m.Kind == MarkValueKind.YesNo ? new MarkValue(false, 0) : new MarkValue(true, Text: "  ");   // never set; blank
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new NeverAsked());
        Assert.Null(prepared.Request);
        Assert.StartsWith(mark + ":", Assert.Single(prepared.Missing), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Marks_never_added_list_every_required_fact()
    {
        var (house, outside) = Project("1_ranch_compliant");
        foreach (var m in new[] { Marks.Zone, Marks.Use, Marks.LotSurveyed, Marks.CornerLot, Marks.StreetEdge, Marks.GroundFrom })
            house.ProjectMarks.Remove(m.Guid);
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new NeverAsked());
        Assert.Null(prepared.Request);
        Assert.Equal(["Gordium: Zone", "Gordium: Use", "Gordium: Lot surveyed", "Gordium: Street edge"],
                     prepared.Missing.Select(w => w[..w.IndexOf(':', "Gordium: ".Length)]));
    }

    /// <summary>The architect's count of stories (Gordium: Stories, optional): sent as <c>facts.stories</c> only when
    /// stated; blank (Revit's unset Integer reads 0 with HasValue false) is never sent as 0; a count under 1 is asked
    /// again, never sent.</summary>
    [Fact]
    public void A_stories_count_is_sent_only_when_stated_and_one_or_more()
    {
        var (house, _) = Project("1_ranch_compliant");
        Assert.False(ProjectFacts.Read(house.Model()).Facts.ContainsKey("stories"));      // never marked: not sent
        Mark(house, Marks.Stories, new(false, 0));                                          // unset: AsInteger() 0
        var unset = ProjectFacts.Read(house.Model());
        Assert.False(unset.Facts.ContainsKey("stories"));
        Assert.DoesNotContain(unset.Missing, w => w.StartsWith(Marks.Stories.Name, StringComparison.Ordinal));  // never required
        Mark(house, Marks.Stories, new(true, 3));
        var three = ProjectFacts.Read(house.Model());
        Assert.Equal(3, three.Facts["stories"]!.GetValue<int>());
        Assert.DoesNotContain(three.Missing, w => w.StartsWith(Marks.Stories.Name, StringComparison.Ordinal));
        foreach (var n in new[] { 0, -2 })
        {
            Mark(house, Marks.Stories, new(true, n));
            var bad = ProjectFacts.Read(house.Model());
            Assert.False(bad.Facts.ContainsKey("stories"));
            Assert.Contains($"{Marks.Stories.Name} is {n}: type the number of stories, 1 or more, or leave it blank",
                            Assert.Single(bad.Missing, w => w.StartsWith(Marks.Stories.Name, StringComparison.Ordinal)),
                            StringComparison.Ordinal);
        }
    }

    /// <summary>The count reaches the check as the architect's statement, kept only within what the drawing allows:
    /// the box house is drawn as two floor blocks (its stories read, 2: complies with R-1b's 3), so a count of 2 agrees
    /// and still complies, and a count of 1, fewer than the floors drawn, is refused by the measuring ("the stories
    /// typed (1) are fewer than the floor blocks drawn (2)"), never a pass on it.</summary>
    [Fact]
    public async Task A_stated_stories_count_reaches_the_check_and_is_kept_only_within_the_drawing()
    {
        var (house, outside) = Project("1_ranch_compliant");
        var (_, before) = await Check(house, outside);
        Assert.Equal(Verdict.Complies, Assert.Single(before.Items, i => i.Id == "R-1b.stories").Status);
        Mark(house, Marks.Stories, new(true, 2));
        var (prepared, agrees) = await Check(house, outside);
        Assert.Equal(2, prepared.Request!.Facts["stories"]!.GetValue<int>());
        Assert.Equal(Verdict.Complies, Assert.Single(agrees.Items, i => i.Id == "R-1b.stories").Status);
        Mark(house, Marks.Stories, new(true, 1));
        var (_, refused) = await Check(house, outside);
        var row = Assert.Single(refused.Items, i => i.Id == "R-1b.stories");
        Assert.Equal(Verdict.NeedsReview, row.Status);
        Assert.Contains("the stories typed (1) are fewer than the floor blocks drawn (2)", row.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_ground_word_not_known_is_asked_never_read_as_no_ground()
    {
        var (house, outside) = Project("1_ranch_compliant");
        Mark(house, Marks.GroundFrom, new(true, Text: "Toposolid"));
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new NeverAsked());
        Assert.Null(prepared.Request);
        Assert.Contains("\"Toposolid\"", Assert.Single(prepared.Missing), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_street_edge_the_lot_no_longer_has_is_asked_again_never_sent()
    {
        var (house, outside) = Project("1_ranch_compliant");
        Mark(house, Marks.StreetEdge, new(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(30, 0, 0))])));   // half the edge
        var client = await worker.RunningAsync();
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
        Assert.Null(prepared.Request);
        Assert.StartsWith("Gordium: Street edge: the street edge picked is no longer an edge of the lot", Assert.Single(prepared.Missing), StringComparison.Ordinal);
        // and text Gordium didn't write is asked for again too
        Mark(house, Marks.StreetEdge, new(true, Text: "the front"));
        prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new NeverAsked());
        Assert.Contains("isn't an edge Gordium wrote", Assert.Single(prepared.Missing), StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_outside_and_inside_read_in_different_designs_are_refused()
    {
        var (house, outside) = Project("1_ranch_compliant");
        await Assert.ThrowsAsync<ReadRefusedException>(() => ProjectCheck.PrepareAsync(outside with { Phases = ["phase-1"] }, house.Model(), new NeverAsked()));
        await Assert.ThrowsAsync<ReadRefusedException>(() => ProjectCheck.PrepareAsync(outside with { ActiveOption = "opt-2" }, house.Model(), new NeverAsked()));
        var sets = new[] { new OptionSet("set-1", "Porch", [new DesignOptionRecord("opt-1", "Deep", true), new DesignOptionRecord("opt-2", "Shallow", false)]) };
        await Assert.ThrowsAsync<ReadRefusedException>(() => ProjectCheck.PrepareAsync(outside with { OptionSets = sets }, house.Model(), new NeverAsked()));
    }

    // ---- the street edge picked --------------------------------------------------------------------------------

    [Fact]
    public void A_click_on_an_edge_keeps_that_edge_and_a_click_at_a_corner_or_off_the_line_keeps_none()
    {
        var line = Scene.Model(Scene.Steps[0]).LotLines[0];
        var (edge, why) = StreetEdges.Nearest(line, new Xyz(20, 0.2, 0));
        Assert.Null(why);
        var kept = StreetEdges.Parse(StreetEdges.Format([new KeptEdge(edge!.A, edge.B, edge.IsLine, edge.Mid)]))!;
        Assert.Equal(new KeptEdge(edge.A, edge.B, true, new Xyz(30, 0, 0)), Assert.Single(kept));      // its kind and middle kept
        Assert.Equal(new KeptEdge(edge.A, edge.B), Assert.Single(StreetEdges.Parse(StreetEdges.Format([(edge.A, edge.B)]))!));   // an older mark still reads
        Assert.Equal(0, edge.A.Y + edge.B.Y);
        Assert.Equal(60, Math.Abs(edge.A.X - edge.B.X));
        Assert.Contains("corner", StreetEdges.Nearest(line, new Xyz(0, 0, 0)).Why, StringComparison.Ordinal);
        // review round 1: a click just past the corner, nearer the side edge, or on the street edge within 2 ft of the
        // corner, could keep either edge: refused (the old 0.01 ft band kept the side edge and the street edge)
        Assert.Contains("corner", StreetEdges.Nearest(line, new Xyz(0.05, 0.3, 0)).Why, StringComparison.Ordinal);
        Assert.Contains("corner", StreetEdges.Nearest(line, new Xyz(1.5, 0, 0)).Why, StringComparison.Ordinal);
        Assert.Contains("corner", StreetEdges.Nearest(line, new Xyz(58.7, 0.1, 0)).Why, StringComparison.Ordinal);
        Assert.Equal(edge, StreetEdges.Nearest(line, new Xyz(3, 0, 0)).Edge);                    // past the corner band
        // said back to the architect before it is kept
        Assert.Equal("the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)", StreetEdges.Describe(edge, Transform3.Identity));
        Assert.Contains("wasn't on an edge", StreetEdges.Nearest(line, new Xyz(30, 60, 0)).Why, StringComparison.Ordinal);
        // a property line holding a curve with no ends (a full circle): its lot is never read, so no edge of it is
        // kept, even a click right on one of its straight edges
        var (none, noEnds) = StreetEdges.Nearest(line with { Unbound = 1 }, new Xyz(20, 0.2, 0));
        Assert.Null(none);
        Assert.Contains("a curve with no ends", noEnds, StringComparison.Ordinal);
    }

    /// <summary>Review round 2: a curved street edge is said by its length along the curve (47.1 ft), never its
    /// chord (40 ft), when it is confirmed and when the result names it.</summary>
    [Fact]
    public void A_curved_street_edge_is_said_by_its_length_along_the_curve()
    {
        // an arc from (0, 0) to (40, 0), 47.1 ft along, bulging south; the lot closed by three straight lines
        const double len = 47.1;
        double lo = 20.01, hi = 1000;                                      // the radius whose 47.1 ft arc spans a 40 ft chord
        for (var k = 0; k < 200; k++)
        {
            var mid = (lo + hi) / 2;
            if (2 * mid * Math.Sin(len / (2 * mid)) < 40) lo = mid; else hi = mid;
        }
        var r = (lo + hi) / 2;
        double half = len / (2 * r), h = r * Math.Cos(half);              // the centre (20, h), north of the chord
        Xyz At(double t)
        {
            var ang = -Math.PI / 2 - half + 2 * half * t;
            return new Xyz(20 + r * Math.Cos(ang), h + r * Math.Sin(ang), 0);
        }
        Assert.Equal(0, At(0).DistanceTo(new Xyz(0, 0, 0)), 9);
        Assert.Equal(0, At(1).DistanceTo(new Xyz(40, 0, 0)), 9);
        var arc = new LotCurve(new Xyz(0, 0, 0), new Xyz(40, 0, 0), false, len, At);
        var line = new LotLineElement("pl-arc", true,
            [arc, new LotCurve(new Xyz(40, 0, 0), new Xyz(40, 100, 0), true), new LotCurve(new Xyz(40, 100, 0), new Xyz(0, 100, 0), true),
             new LotCurve(new Xyz(0, 100, 0), new Xyz(0, 0, 0), true)]);
        var (edge, why) = StreetEdges.Nearest(line, At(0.5));
        Assert.Null(why);
        Assert.False(edge!.IsLine);
        Assert.Equal("the curved 47.1 ft lot edge from (0.0, 0.0) to (40.0, 0.0)", StreetEdges.Describe(edge, Transform3.Identity));
        // the result's words, from the lot's own points along the arc
        var lot = new JsonObject
        {
            ["edges"] = new JsonArray(new JsonObject
            {
                ["curved"] = true,
                ["points"] = new JsonArray(Enumerable.Range(0, 201).Select(k => At(k / 200.0)).Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray()),
            }),
        };
        // the arc as the mark keeps it: its ends, its kind and its middle (review round 4)
        var arcKept = Assert.Single(StreetEdges.Parse(StreetEdges.Format([new KeptEdge(edge.A, edge.B, edge.IsLine, edge.Mid)]))!);
        Assert.Equal(false, arcKept.IsLine);
        var match = StreetEdges.Match([arcKept], lot, Transform3.Identity);
        Assert.Equal("the curved 47.1 ft lot edge from (0.0, 0.0) to (40.0, 0.0)", match.Words);

        // review round 3: with no lot read, no length is said (the chord would contradict the 47.1 ft confirmed)
        Assert.Equal("the street edge from (0.0, 0.0) to (40.0, 0.0), not matched to a lot (none was read)",
                     StreetEdges.Match([arcKept], null, Transform3.Identity).Words);

        // review round 4: a lot bounded by the arc and its chord (two edges with the same ends, the chord run back from
        // (40, 0) to (0, 0)). The arc kept sends the arc, its own way round; the chord kept, the chord; never each other
        lot["edges"]!.AsArray().Add(new JsonObject { ["points"] = new JsonArray(new JsonArray(40.0, 0.0), new JsonArray(0.0, 0.0)) });
        match = StreetEdges.Match([arcKept], lot, Transform3.Identity);
        Assert.Equal("[[[0,0],[40,0]]]", Rounded(match.StreetLine!));
        Assert.Equal("the curved 47.1 ft lot edge from (0.0, 0.0) to (40.0, 0.0)", match.Words);
        var chordKept = new KeptEdge(new Xyz(0, 0, 0), new Xyz(40, 0, 0), true, new Xyz(20, 0, 0));
        match = StreetEdges.Match([chordKept], lot, Transform3.Identity);
        Assert.Equal("[[[40,0],[0,0]]]", Rounded(match.StreetLine!));
        Assert.Equal("the 40.0 ft lot edge from (40.0, 0.0) to (0.0, 0.0)", match.Words);
        // each test on its own: the kind, for an arc so flat its middle is within 0.25 ft of the chord's; the middle,
        // for two arcs on the same ends bulging either way
        JsonObject Curved(Func<double, Xyz> at) => new()
        {
            ["curved"] = true,
            ["points"] = new JsonArray(Enumerable.Range(0, 201).Select(k => at(k / 200.0)).Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray()),
        };
        var flat = new JsonObject { ["edges"] = new JsonArray(Curved(t => new Xyz(40 * t, -0.4 * t * (1 - t), 0)),
            new JsonObject { ["points"] = new JsonArray(new JsonArray(40.0, 0.0), new JsonArray(0.0, 0.0)) }) };
        Assert.Equal("[[[40,0],[0,0]]]", Rounded(StreetEdges.Match([chordKept], flat, Transform3.Identity).StreetLine!));
        var twoArcs = new JsonObject { ["edges"] = new JsonArray(Curved(At), Curved(t => At(t) with { Y = -At(t).Y })) };
        match = StreetEdges.Match([arcKept], twoArcs, Transform3.Identity);
        Assert.Equal(StreetRefusal.None, match.Reason);
        Assert.Equal(-1, Math.Sign(arcKept.Mid!.Value.Y));                                   // the arc kept bulges south
        // an older mark, its ends alone: which was meant can't be told, so nothing is sent, and its typed reason is
        // one the button asks a new pick for (never read from the words)
        var (both, why2) = StreetEdges.Match([(edge.A, edge.B)], lot, Transform3.Identity);
        Assert.Null(both);
        Assert.Contains("Check project asks you to click the lot edge along the street again", why2, StringComparison.Ordinal);
        Assert.Equal(StreetRefusal.Ambiguous, StreetEdges.Match([(edge.A, edge.B)], lot, Transform3.Identity).Reason);
        var prepared = new ProjectPrepared(null, [why2!], null, [], null, StreetRefused: StreetRefusal.Ambiguous);
        Assert.True(StreetEdges.NeedsNewPick(prepared));
        Assert.True(StreetEdges.NeedsNewPick(prepared with { StreetRefused = StreetRefusal.NoLongerAnEdge }));
        Assert.False(StreetEdges.NeedsNewPick(prepared with { StreetRefused = StreetRefusal.None }));
    }

    /// <summary>A street line with each coordinate to a millionth of a foot (an arc's end a hair off 0 reads 0).</summary>
    private static string Rounded(JsonArray line) =>
        "[" + string.Join(",", line.Select(e => "[" + string.Join(",", e!.AsArray().Select(p =>
            "[" + string.Join(",", p!.AsArray().Select(v => (Math.Round(v!.GetValue<double>(), 6) + 0.0)
                .ToString(System.Globalization.CultureInfo.InvariantCulture))) + "]")) + "]")) + "]";

    /// <summary>Review round 2: every mark write goes through one helper; a Set Revit refuses throws naming the mark,
    /// and the street edge is never logged as kept.</summary>
    [Fact]
    public void A_street_edge_revit_wont_set_throws_naming_the_mark_and_logs_nothing()
    {
        var edge = new PickedEdge(new Xyz(0, 0, 0), new Xyz(60, 0, 0), true, 60);
        var log = new Dictionary<string, object?>();
        string? given = null;
        var e = Assert.Throws<InvalidOperationException>(() => StreetEdges.Keep([edge], t => { given = t; return false; }, log));
        Assert.StartsWith("Revit didn't set Gordium: Street edge to ", e.Message, StringComparison.Ordinal);
        Assert.Equal("0 0 60 0", given);
        Assert.False(log.ContainsKey("street_edge"));
        StreetEdges.Keep([edge], _ => true, log);
        Assert.Equal("0 0 60 0", log["street_edge"]);
        Assert.Throws<InvalidOperationException>(() => ProjectFacts.Write(Marks.Zone, "\"R-1b\"", () => false));
    }

    /// <summary>Review round 1: a request file's mark is set by the mark's own kind; another kind is refused naming
    /// the mark (it was set as text, or Revit's Set refused it unseen, and the check ran on a mark not meant).</summary>
    [Fact]
    public void A_request_files_mark_of_the_wrong_kind_is_refused_naming_the_mark()
    {
        Assert.Equal((1, null), ProjectFacts.RequestValue(Marks.LotSurveyed, JsonValue.Create(true)));
        Assert.Equal((0, null), ProjectFacts.RequestValue(Marks.CornerLot, JsonNode.Parse("false")));
        Assert.Equal((null, "R-1b"), ProjectFacts.RequestValue(Marks.Zone, JsonNode.Parse("\"R-1b\"")));
        Assert.Equal((3, null), ProjectFacts.RequestValue(Marks.Stories, JsonNode.Parse("3")));      // set as Revit's Integer
        foreach (var (m, v) in new (MarkDefinition, string)[] { (Marks.LotSurveyed, "\"yes\""), (Marks.LotSurveyed, "1"), (Marks.Zone, "true"),
                                                                 (Marks.Use, "null"), (Marks.ClearWidth, "3.0"),
                                                                 (Marks.Stories, "\"3\""), (Marks.Stories, "true"), (Marks.Stories, "3.5") })
        {
            var e = Assert.Throws<InvalidOperationException>(() => ProjectFacts.RequestValue(m, JsonNode.Parse(v)));
            Assert.StartsWith(m.Name + " is a ", e.Message, StringComparison.Ordinal);
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData("1 2 3")]
    [InlineData("1 2 3 x")]
    [InlineData("1 2 1 2")]
    [InlineData("1 2 3 NaN")]
    [InlineData("1 2 3 4;")]
    public void Text_gordium_didnt_write_is_no_street_edge(string text) => Assert.Null(StreetEdges.Parse(text));

    [Fact]
    public void A_kept_edge_is_sent_as_the_lots_own_points_in_shared_coordinates()
    {
        var lot = JsonNode.Parse("""{"edges": [{"points": [[100, 200], [160, 200]]}, {"points": [[160, 200], [160, 320]]}]}""")!.AsObject();
        var toShared = Transform3.Translation(new Xyz(100, 200, 0));
        // kept reversed, a hair off: sent as the lot's own edge, its own way round
        var (line, why) = StreetEdges.Match([(new Xyz(60.004, 0, 0), new Xyz(0, 0.003, 0))], lot, toShared);
        Assert.Null(why);
        Assert.Equal("[[[100,200],[160,200]]]", line!.ToJsonString());
        Assert.NotNull(StreetEdges.Match([(new Xyz(60.02, 0, 0), new Xyz(0, 0, 0))], lot, toShared).Why);
    }
}
