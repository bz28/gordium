using System.Diagnostics;
using System.Reflection;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The read's timings (<see cref="ReadSteps"/>, the trial log's <c>read_steps</c>): kept only while a read
/// has begun them on its thread, added up by name, written in one stable shape; never part of anything read or sent;
/// and the Revit layer's hooks pinned in its source (it builds only on Windows with Revit). That the request is the
/// same with them kept or not is <c>ProjectCheckTests</c>' (it needs the worker).</summary>
public sealed class ReadStepsTests
{
    private static string Addin(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file));

    [Fact]
    public void With_no_read_begun_nothing_is_kept_and_nothing_throws()
    {
        Assert.Null(ReadSteps.Current);
        using (ReadSteps.Step("outside"))
        {
        }
        ReadSteps.Count("outside.elements", 5);
        ReadSteps.Max("inside.over.candidates_per_room", 9);
        ReadSteps.Link("a link", 1, 2.0, 3);
        ReadSteps.CountGeometry("outside.fine", [new SolidItem([], [])]);
        Assert.Equal(42, ReadSteps.Time("outside", () => 42));
        var steps = new ReadSteps();
        Assert.Equal(Empty(), steps.ToLog());
    }

    private static Dictionary<string, object?> Empty() => new()
    {
        ["steps"] = new Dictionary<string, object>(), ["counts"] = new Dictionary<string, long>(),
        ["max"] = new Dictionary<string, long>(), ["links"] = new List<Dictionary<string, object>>(),
    };

    [Fact]
    public void Steps_counts_largest_and_links_are_added_up_by_name_while_begun()
    {
        var steps = new ReadSteps();
        using (ReadSteps.Begin(steps))
        {
            Assert.Same(steps, ReadSteps.Current);
            for (var i = 0; i < 3; i++)
                Assert.Equal(i, ReadSteps.Time("inside.room.over", () => i));
            ReadSteps.Count("inside.rooms", 2);
            ReadSteps.Count("inside.rooms", 3);
            ReadSteps.Count("inside.boolean_ops");
            ReadSteps.Max("inside.over.candidates_per_room", 4);
            ReadSteps.Max("inside.over.candidates_per_room", 11);
            ReadSteps.Max("inside.over.candidates_per_room", 7);
            ReadSteps.Link("Structure.rvt", 1, 1.23456, 812);
        }
        Assert.Null(ReadSteps.Current);
        ReadSteps.Count("inside.rooms", 100);                     // after the read: not kept
        var log = steps.ToLog();
        var timed = Assert.IsType<Dictionary<string, object>>(Assert.IsType<Dictionary<string, object>>(log["steps"])["inside.room.over"]);
        Assert.Equal(3L, timed["calls"]);
        Assert.InRange((double)timed["seconds"], 0, 5);
        Assert.Equal(new Dictionary<string, long> { ["inside.boolean_ops"] = 1, ["inside.rooms"] = 5 }, log["counts"]);
        Assert.Equal(new Dictionary<string, long> { ["inside.over.candidates_per_room"] = 11 }, log["max"]);
        var link = Assert.Single(Assert.IsType<List<Dictionary<string, object>>>(log["links"]));
        Assert.Equal(new Dictionary<string, object> { ["link"] = "Structure.rvt", ["depth"] = 1, ["seconds"] = 1.235, ["elements"] = 812 }, link);
    }

    [Fact]
    public void Seconds_are_kept_to_the_millisecond_and_names_written_in_order()
    {
        var steps = new ReadSteps();
        steps.Add("outside", (long)(Stopwatch.Frequency * 2.0004));
        steps.Add("outside", (long)(Stopwatch.Frequency * 1.0));
        steps.Add("inside", Stopwatch.Frequency / 2);
        var log = Assert.IsType<Dictionary<string, object>>(steps.ToLog()["steps"]);
        Assert.Equal(["inside", "outside"], log.Keys);
        Assert.Equal(new Dictionary<string, object> { ["seconds"] = 3.0, ["calls"] = 2L }, log["outside"]);
        Assert.Equal(new Dictionary<string, object> { ["seconds"] = 0.5, ["calls"] = 1L }, log["inside"]);
    }

    [Fact]
    public void A_step_that_throws_is_still_timed_and_the_throw_passes_on()
    {
        var steps = new ReadSteps();
        using (ReadSteps.Begin(steps))
            Assert.Throws<InvalidOperationException>(() => ReadSteps.Time<int>("inside.gross_areas", () => throw new InvalidOperationException("refused")));
        var timed = Assert.IsType<Dictionary<string, object>>(Assert.IsType<Dictionary<string, object>>(steps.ToLog()["steps"])["inside.gross_areas"]);
        Assert.Equal(1L, timed["calls"]);
    }

    [Fact]
    public void A_read_begun_inside_another_keeps_its_own_then_the_outer_one_is_kept_again()
    {
        var outer = new ReadSteps();
        var inner = new ReadSteps();
        using (ReadSteps.Begin(outer))
        {
            var scope = ReadSteps.Begin(inner);
            ReadSteps.Count("x");
            scope.Dispose();
            scope.Dispose();                                      // twice: still the outer one
            Assert.Same(outer, ReadSteps.Current);
            ReadSteps.Count("y");
        }
        Assert.Null(ReadSteps.Current);
        Assert.Equal(new Dictionary<string, long> { ["x"] = 1 }, inner.ToLog()["counts"]);
        Assert.Equal(new Dictionary<string, long> { ["y"] = 1 }, outer.ToLog()["counts"]);
    }

    [Fact]
    public void Another_thread_never_sees_the_read_s_steps()
    {
        var steps = new ReadSteps();
        using (ReadSteps.Begin(steps))
        {
            var seen = new Thread(() => ReadSteps.Count("elsewhere"));
            seen.Start();
            seen.Join();
            Assert.Same(steps, ReadSteps.Current);
        }
        Assert.Empty(Assert.IsType<Dictionary<string, long>>(steps.ToLog()["counts"]));
    }

    [Fact]
    public void Geometry_is_tallied_with_instances_items_included()
    {
        var face = new FaceRecord("PlanarFace", [], []);
        var edge = new EdgeRecord([], true);
        IReadOnlyList<GeometryItem> items =
        [
            new SolidItem([face, face], [edge]),
            new InstanceItem([new SolidItem([face], [edge, edge]), new InstanceItem(null), new MeshItem([], [], true)]),
            new LineworkItem(), new OtherItem("Profile"),
        ];
        Assert.Equal((2L, 3L, 3L, 1L), ReadSteps.Tally(items));
        Assert.Equal((0L, 0L, 0L, 0L), ReadSteps.Tally(null));
        var steps = new ReadSteps();
        using (ReadSteps.Begin(steps))
        {
            ReadSteps.CountGeometry("outside.fine", items);
            ReadSteps.CountGeometry("outside.fine", items);
        }
        Assert.Equal(new Dictionary<string, long>
        {
            ["outside.fine.edges"] = 6, ["outside.fine.faces"] = 6, ["outside.fine.meshes"] = 2, ["outside.fine.solids"] = 4,
        }, steps.ToLog()["counts"]);
    }

    // ---- never part of what is read or sent -------------------------------------------------------------------

    [Fact]
    public void No_record_or_request_holds_the_steps_and_no_reader_decision_reads_them()
    {
        // no type of the reader (records, the request, the prepared check) has a field or property of the steps' type
        foreach (var t in typeof(ReadSteps).Assembly.GetTypes().Where(t => t != typeof(ReadSteps) && t.DeclaringType != typeof(ReadSteps)))
        {
            const BindingFlags all = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
            Assert.DoesNotContain(t.GetFields(all), f => f.FieldType == typeof(ReadSteps));
            Assert.DoesNotContain(t.GetProperties(all), p => p.PropertyType == typeof(ReadSteps));
        }
        // and no file of the Revit-free layers names them but their own
        foreach (var dir in new[] { "Gordium.Revit.Reading", "Gordium.Worker" })
            foreach (var file in Directory.GetFiles(Path.Combine(Env.Repo, "apps", "revit_addin", "src", dir), "*.cs", SearchOption.AllDirectories))
                if (Path.GetFileName(file) != "ReadSteps.cs" && !file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}", StringComparison.Ordinal))
                    Assert.DoesNotContain("ReadSteps", File.ReadAllText(file), StringComparison.Ordinal);
    }

    // ---- the Revit layer's hooks (source text: it builds only with Revit) -------------------------------------

    [Fact]
    public void Check_project_keeps_the_steps_for_its_run_and_logs_them_beside_the_request_never_in_it()
    {
        var source = Addin("CheckProject.cs");
        Assert.Contains("using var keep = ReadSteps.Begin(steps);", source);
        Assert.Contains("ReadSteps.Time(\"outside\", () => RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance))", source);
        Assert.Contains("ReadSteps.Time(\"inside\", () => RevitInterior.Model(doc))", source);
        // PR 8: the worker is started on a pool thread before the read, and waited for on Revit's thread only when
        // the read asks it which objects are left out (the step worker_wait, inside prepare)
        Assert.DoesNotContain("worker_start", source);
        // (UI polish PR 5: the wait's failure is the checker's, WorkerUnavailableException; the step is still timed)
        Assert.Contains("client = ReadSteps.Time(\"worker_wait\", () => worker.GetAwaiter().GetResult());", source);
        Assert.Contains("return new WorkerLeftOut(client).AskAsync(", source);
        Assert.Contains("ReadSteps.Time(\"prepare\", () => ProjectCheck.PrepareAsync(outside, inside, new StartedLeftOut(worker), anyway: anyway).GetAwaiter().GetResult())", source);
        Assert.Contains("using (ReadSteps.Step(\"log_request\"))", source);
        // logged when nothing is sent, when it is, and on a failure (then rethrown)
        Assert.Equal(3, Count(source, "log[\"read_steps\"] = steps.ToLog();"));
        Assert.Contains("log[\"read_steps\"] = steps.ToLog();\n            throw;", source.Replace("\r\n", "\n"));
        // the request sent is the one prepared, as before: never with the steps
        // (sent off Revit's thread by CheckFlow.Send for the panel; on this thread for a check asked for by file)
        Assert.Contains("ProjectCheck.SendAsync(await Trial.WorkerAsync().ConfigureAwait(false), request)", source);
        Assert.Contains("ResultsPane.AfterInput(() => check.Send(request));", source);
        Assert.Contains("[\"site\"] = request.Site.DeepClone(), [\"facts\"] = request.Facts.DeepClone(), [\"interior\"] = request.Interior.DeepClone(),", source);
    }

    [Fact]
    public void Read_inside_and_record_houses_log_the_steps_of_their_read()
    {
        var source = Addin("RecordHouses.cs");
        Assert.Equal(2, Count(source, "using (ReadSteps.Begin(steps))"));
        Assert.Equal(2, Count(source, "model = ReadSteps.Time(\"inside\", () => RevitInterior.Model(doc));"));
        Assert.Equal(2, Count(source, "read = ReadSteps.Time(\"interior_reader\", () => InteriorReader.Read(model));"));
        Assert.Equal(2, Count(source, "log[\"read_steps\"] = steps.ToLog();"));
        Assert.DoesNotContain("[\"read_steps\"]", source.Split("var recording = new JsonObject")[1].Split("File.WriteAllText")[0]);
    }

    [Fact]
    public void The_outside_read_times_and_counts_each_step_reading_what_it_always_did()
    {
        var source = Addin("RevitRead.cs");
        foreach (var hook in new[]
                 {
                     "ReadSteps.Time(\"outside.collect\", () => new FilteredElementCollector(doc).WhereElementIsNotElementType().ToList())",
                     "ReadSteps.Count(\"outside.elements\", all.Count);",
                     "ReadSteps.Time(\"outside.get_geometry.fine\", () => e.get_Geometry(options))",
                     "ReadSteps.Time(\"outside.copy_geometry.fine\", () => Items(g))",
                     "ReadSteps.CountGeometry(\"outside.fine\", geometry);",
                     "ReadSteps.Count(\"outside.family_instances\");",
                     "ReadSteps.Time(\"outside.get_geometry.\" + at, () => e.get_Geometry(new Options { DetailLevel = level, IncludeNonVisibleObjects = false }))",
                     "ReadSteps.Time(\"outside.copy_geometry.\" + at, () => Items(other))",
                     "ReadSteps.CountGeometry(\"outside.\" + at, items);",
                     "ReadSteps.Link(li.Name, depth + 1, System.Diagnostics.Stopwatch.GetElapsedTime(started).TotalSeconds, read.Elements.Count);",
                     "using var rest = ReadSteps.Step(\"outside.element_rest\");",
                     "using var rest = ReadSteps.Step(\"outside.model_rest\");",
                     "ReadSteps.Time(\"outside.lot_lines\", () => LotLines(doc))",
                     // what is read, unchanged: Fine for every element, Medium and Coarse again for a family instance
                     "var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };",
                     "foreach (var level in new[] { ViewDetailLevel.Medium, ViewDetailLevel.Coarse })",
                     "linked is null || depth >= LinkDepth ? null : Model(linked, version, tolerance, depth + 1)",
                 })
            Assert.Contains(hook, source);
    }

    [Fact]
    public void The_inside_read_times_and_counts_each_step_reading_what_it_always_did()
    {
        var source = Addin("RevitInterior.cs");
        foreach (var hook in new[]
                 {
                     "ReadSteps.Time(\"inside.marks_model\", () => RevitMarks.Model(doc))",
                     "ReadSteps.Time(\"inside.internal_to_shared\", () => RevitRead.InternalToShared(doc))",
                     "ReadSteps.Time(\"inside.read\", () => Read(doc))",
                     "ReadSteps.Time(\"inside.rooms\", ",
                     "ReadSteps.Count(\"inside.rooms\", rooms.Count);",
                     "ReadSteps.Time(\"inside.openings\", ",
                     "ReadSteps.Count(\"inside.openings\", openings.Count);",
                     "ReadSteps.Time(\"inside.stairs\", () => StairsOf(doc, diagnostics))",
                     "ReadSteps.Time(\"inside.railings\", () => RailingsOf(doc, diagnostics))",
                     "ReadSteps.Time(\"inside.enclosed_areas\", () => Areas(doc, phase, diagnostics))",
                     "ReadSteps.Time(\"inside.links\", () => Links(doc))",
                     "ReadSteps.Time(\"inside.ramps\", () => RampsOf(doc, diagnostics))",
                     "ReadSteps.Time(\"inside.separation_lines\", () => SeparationLinesOf(doc, diagnostics))",
                     "ReadSteps.Time(\"inside.gross_areas\", () => GrossAreasOf(doc, phase, diagnostics))",
                     "ReadSteps.Count(\"inside.gross_areas.levels\");",
                     "ReadSteps.Time(\"inside.gross_areas.ring\",",
                     "using (ReadSteps.Step(\"inside.gross_areas.rollback\"))\n                    group.RollBack();",
                     "ReadSteps.Time(\"inside.gross_areas.lines_commit\", draw.Commit) != TransactionStatus.Committed",
                     "ReadSteps.Time(\"inside.gross_areas.topology\",",
                     "ReadSteps.Time(\"inside.gross_areas.room_commit\", place.Commit) != TransactionStatus.Committed",
                     "ReadSteps.Time(\"inside.enclosed_areas.topology\", () => doc.get_PlanTopology(level, phase))",
                     "using (ReadSteps.Step(\"inside.enclosed_areas.outline\"))",
                     "using (ReadSteps.Step(\"inside.enclosed_areas.rollback\"))\n                    t.RollBack();",
                     "ReadSteps.Count(\"inside.room.boundary_calls\");",
                     "using var timed = ReadSteps.Step(\"inside.room.boundary\");",
                     "ReadSteps.Time(\"inside.room.inside\", () => Inside(doc, room, loops, floor, level!))",
                     "ReadSteps.Time(\"inside.room.over\", () => Near(\"inside.over\", doc, room.Id, new Outline(new XYZ(x0, y0, floor), new XYZ(x1, y1, floor + 1000)), null,",
                     "ReadSteps.Time(\"inside.room.band_solid\", () => Band(x0, y0, x1, y1, floor))",
                     "ReadSteps.Count(\"inside.room.inside_hits\", hits.Count);",
                     "ReadSteps.Max(\"inside.room.inside_hits_per_room\", hits.Count);",
                     // each caller names its own steps (a stair run's and a railing's box never counted as a room's)
                     "ReadSteps.Time(\"inside.room.under\", () => Near(\"inside.under\", doc, room.Id,",
                     "ReadSteps.Time(\"inside.room.over\", () => Near(\"inside.over\", doc, room.Id,",
                     "near = Near(\"inside.stair_run.near\", doc, run.Id, new Outline(",
                     "near = Near(\"inside.railing.near\", doc, r.Id, new Outline(",
                     "private static List<NearbyElement>? Near(string step, Document doc, ElementId skip,",
                     "ReadSteps.Time(step + \".collect\",",
                     "ReadSteps.Count(step + \".candidates\", found.Count);",
                     "ReadSteps.Max(step + \".candidates_per_call\", found.Count);",
                     "ReadSteps.Time(step + \".faces\", () => Faces(e, options))",
                     "ReadSteps.Time(step + \".band\", () => InBand(e, band, bandBoxes, options))",
                     "ReadSteps.Count(step + \".read\", list.Count);",
                     "ReadSteps.Max(step + \".read_per_call\", list.Count);",
                     "ReadSteps.Count(\"inside.boolean_ops\");",
                     "using (ReadSteps.Step(\"inside.boolean_op\"))\n                            cut = BooleanOperationsUtils.ExecuteBooleanOperation(s, band, BooleanOperationsType.Intersect);",
                     "ReadSteps.Count(\"inside.open_shells\");",
                     "ReadSteps.Count(\"inside.faces\");",
                     "ReadSteps.Count(\"inside.faces_triangulated\");",
                     "ReadSteps.Time(\"inside.triangulate\", () => f.Triangulate()) is not { Vertices: { Count: > 0 } vertices }",
                     "ReadSteps.Time(\"inside.opening.faces\", () => Faces(fi, options))",
                     "ReadSteps.Time(\"inside.opening.cut\", () => Cut(wall, fi, options))",
                     // what is read, unchanged: the box over a room to +1000 ft, any category, with its band
                     "new XYZ(x1, y1, floor + 1000)), null,",
                 })
            Assert.Contains(hook, source.Replace("\r\n", "\n"));
        // the step never guessed from the band (a stair run's or railing's box, with none, was a room's under box)
        Assert.DoesNotContain("band is null ? \"inside.under\"", source);
        Assert.DoesNotContain("_per_room\", found.Count)", source);
        Assert.Equal(4, Count(source, "Near(\"inside."));
    }

    [Fact]
    public void What_is_inside_a_room_is_found_by_the_quick_box_first_then_the_exact_solid()
    {
        // Snowdon Towers: 300 of 408 s went to the solid test run on every element, per room (read_steps, 2026-11-22).
        // The padded box of the room's solid comes first, and the exact solid test still decides: same list, faster.
        var source = Addin("RevitInterior.cs");
        // (Collect runs Revit's box filter on the box index's candidates, then the solid test, as on the whole model)
        Assert.Contains("var hits = Collect(doc, Padded(solid, 1.0), new ElementIntersectsSolidFilter(solid))", source);
        var collect = source[source.IndexOf("private static List<Element> Collect(", StringComparison.Ordinal)..];
        foreach (var chain in new[] { "some.WherePasses(then)", "all.WherePasses(then)" })
        {
            var box = collect.IndexOf(".WherePasses(new BoundingBoxIntersectsFilter(box))", StringComparison.Ordinal);
            var exact = collect.IndexOf(chain, StringComparison.Ordinal);
            Assert.True(box >= 0, "the quick box filter is gone");
            Assert.True(exact > box, "the exact solid test must still run, after the box");
        }
        // the box is in model coordinates: all 8 corners through the solid box's own transform, padded on every side
        Assert.Contains("select box.Transform.OfPoint(new XYZ(x, y, z))", source);
        Assert.Contains("corners.Min(p => p.Z) - pad", source);
        Assert.Contains("corners.Max(p => p.Z) + pad", source);
        // each method keeps its own doc comment: Inside's directly above Inside, Padded's alone above Padded
        var inside = source.IndexOf("private static List<NearbyElement>? Inside(", StringComparison.Ordinal);
        Assert.EndsWith("Null when it can't be looked for.</summary>", source[..inside].TrimEnd());
        var padded = source.IndexOf("private static Outline Padded(", StringComparison.Ordinal);
        var before = source[..padded];
        Assert.Equal(1, Count(before[(before.LastIndexOf('}') + 1)..], "<summary>"));
    }

    [Fact]
    public void Each_elements_geometry_is_worked_out_once_per_read_and_only_before_the_model_changes()
    {
        // Snowdon Towers: an element over many rooms was read, triangulated and walked again for each (64,198 reads
        // of faces and of the band, read_steps 2026-11-22). Its faces and its walked geometry are kept by element and
        // geometry options for the rooms, openings, stairs and railings, and let go before the first step that
        // changes the model (a Room placed for the moment in the enclosed areas and the outer outlines).
        var source = Addin("RevitInterior.cs").Replace("\r\n", "\n");
        foreach (var hook in new[]
                 {
                     "private static (List<SurfaceRecord>? Faces, bool Failed) Faces(Element e, Options options) =>\n" +
                     "        FacesKept.Get(GeometryKey.Of(e, options), () => FacesRead(e, options));",
                     "ReadMemo<GeometryKey, (List<SurfaceRecord>? Faces, bool Failed)> FacesKept = new();",
                     "ReadMemo<GeometryKey, List<BandPiece>> BandPiecesKept = new();",
                     // each memo's hits and misses in the log
                     "ReadSteps.Count(name + \".hits\", hits);",
                     "ReadSteps.Count(name + \".misses\", misses);",
                     // every option get_Geometry reads is in the key, and the element
                     "new(e.Id.Value, o.DetailLevel, o.IncludeNonVisibleObjects, o.ComputeReferences, o.View?.Id.Value ?? -1)",
                     "var pieces = BandPiecesKept.Get(GeometryKey.Of(e, options), () => BandPieces(e, options));",
                     // a throw in the walk kept where it happened, thrown there again inside InBand's own catch
                     "pieces.Add(new BandPiece.Threw(ExceptionDispatchInfo.Capture(x)));",
                     "x.Throw();                               // where the walk threw: thrown here, as it was",
                     // what depends on the band is still worked out per band, as before
                     "cut = BooleanOperationsUtils.ExecuteBooleanOperation(s, band, BooleanOperationsType.Intersect);",
                     "corners.Max(c => c.Z) < bandMin.Z || corners.Min(c => c.Z) > bandMax.Z",
                 })
            Assert.Contains(hook, source);
        // FacesRead only through the memo; one walk of the geometry for the band, never in InBand itself
        Assert.Equal(1, Count(source, "() => FacesRead(e, options)"));
        Assert.Equal(1, Count(source, "() => BandPieces(e, options)"));
        var inBand = source.IndexOf("InBand(Element e, Solid band, BandBoxes boxes, Options options)", StringComparison.Ordinal);
        var pieces = source.IndexOf("private abstract record BandPiece", StringComparison.Ordinal);
        Assert.DoesNotContain("get_Geometry", source[inBand..pieces]);
        // the band's catch is the walk's own (Revit's three refusals), and the walk keeps every throw for it
        Assert.Contains("catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException\n" +
                        "                                       or Autodesk.Revit.Exceptions.ArgumentException)\n        {\n            return ([], true, 0);",
                        source[inBand..pieces]);
        // the scope: opened before the rooms, closed after the railings, before anything that changes the model
        Assert.Equal(5, Count(source, "Kept.Open("));
        var open = source.IndexOf("using (FacesKept.Open(Hits(\"inside.cache.faces\")))\n        using (BandPiecesKept.Open(Hits(\"inside.cache.band_pieces\")))\n" +
                                  "        using (NearKept.Open(Hits(\"inside.cache.near\")))\n        using (ModelKept.Open())\n        using (IndexKept.Open())\n        {",
                                  StringComparison.Ordinal);
        var rooms = source.IndexOf("ReadSteps.Time(\"inside.rooms\", ", StringComparison.Ordinal);
        var railings = source.IndexOf("ReadSteps.Time(\"inside.railings\", ", StringComparison.Ordinal);
        var close = source.IndexOf("}   // the geometry kept is let go here, before anything changes the model", StringComparison.Ordinal);
        Assert.True(open >= 0 && open < rooms && rooms < railings && railings < close, "the scope must hold the rooms to the railings");
        foreach (var changes in new[] { "() => Areas(doc, phase, diagnostics)", "() => GrossAreasOf(doc, phase, diagnostics)" })
        {
            Assert.Equal(1, Count(source, changes));
            Assert.True(source.IndexOf(changes, StringComparison.Ordinal) > close, $"{changes} changes the model: after the scope");
        }
        // nothing inside the scope starts a transaction (the methods that do are called only after it)
        Assert.DoesNotContain("Transaction", source[open..close]);
    }

    private static int Count(string text, string what)
    {
        var n = 0;
        for (var i = text.IndexOf(what, StringComparison.Ordinal); i >= 0; i = text.IndexOf(what, i + what.Length, StringComparison.Ordinal))
            n++;
        return n;
    }
}
