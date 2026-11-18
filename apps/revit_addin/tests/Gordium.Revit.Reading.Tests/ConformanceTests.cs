using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The strongest proof on the Mac: each conformance scene a Revit model can draw, drawn as fake Revit records
/// (SceneDrawing), read by the reader with the real worker deciding what is left out, must give the description the
/// suite expects and exactly the scene's hand-worked verdicts. Checked twice, by two routes: the conformance
/// suite's own <c>recording_problems</c> (the description, then check_site in Python), and the worker's
/// <c>check_site</c> from C#, row by row.</summary>
public sealed class ConformanceTests(RealWorker worker) : IClassFixture<RealWorker>
{
    public static TheoryData<string> Scenes()
    {
        var d = new TheoryData<string>();
        foreach (var s in SceneDrawing.All)
            d.Add(s.Name);
        return d;
    }

    /// <summary>The scenes that are descriptions only (a top-level <c>site:</c>, no drawing to read): 13 and 14, checked
    /// for their verdicts by the worker client's tests. Every other scene is drawn here: the design note (section 7)
    /// names no drawn scene Revit can't draw, so none is left out, least of all because it was hard.</summary>
    private static readonly string[] DescriptionsOnly = ["13_no_lot_and_no_reason", "14_nothing_sent_and_inventory_incomplete"];

    [Fact]
    public void Every_drawn_scene_is_drawn_here()
    {
        // read from the scene files themselves, not from scene_data.py, so a scene it skipped would be caught: the
        // 26 scenes less the 2 descriptions, 24 drawn (01 to 12, 15 to 26)
        var dir = Path.Combine(Env.Repo, "test_data", "host_conformance", "scenes");
        var every = Directory.GetFiles(dir, "*.yaml").Select(Path.GetFileNameWithoutExtension).Order(StringComparer.Ordinal).ToList();
        var descriptions = every.Where(n => File.ReadLines(Path.Combine(dir, n + ".yaml")).Any(l => l.StartsWith("site:", StringComparison.Ordinal))).ToList();
        Assert.Equal(DescriptionsOnly, descriptions);
        Assert.Equal(every.Except(DescriptionsOnly), SceneDrawing.All.Select(s => s.Name).Order(StringComparer.Ordinal));
        Assert.Equal(24, SceneDrawing.All.Count);
    }

    [Theory]
    [MemberData(nameof(Scenes))]
    public async Task A_scene_drawn_in_Revit_passes_the_conformance_suite(string name) =>
        await Passes(SceneDrawing.Named(name), 0, "revit_fake");

    /// <summary>The same with shared coordinates turned a quarter turn as well as moved (design note, section 3: every
    /// point turned once, in one place): the description must still be the scene's, to a millionth of a foot. A
    /// quarter turn keeps Revit's own boxes exact; a 30° turn grows them (ReaderTests).</summary>
    [Theory]
    [InlineData("01_box_house")]
    [InlineData("10_survey_coordinates")]
    [InlineData("15_objects_left_out_touching_on_context_and_a_block")]
    [InlineData("17_curved_rear_lot_line")]
    public async Task A_scene_drawn_with_shared_coordinates_turned_passes_too(string name) =>
        await Passes(SceneDrawing.Named(name), Math.PI / 2, "revit_fake_turned");

    private async Task Passes(SceneDrawing scene, double turn, string host)
    {
        var client = await worker.RunningAsync();
        var steps = new JsonObject();
        foreach (var step in scene.Steps)
        {
            var read = await SiteReader.DescribeAsync(scene.Model(step, turn), scene.Facts, new WorkerLeftOut(client));
            steps[step] = read.Site;

            // route 1: the worker's check_site, from C#, gives every hand-worked row and no other
            var result = await client.CheckSiteAsync(read.Site, scene.Facts);
            // the status as the worker wrote it (a word the client doesn't know is read as needs review, so its
            // reading alone could hide one), and the client's reading of it the same
            var got = result.Items.ToDictionary(i => i.Id, i => i.StatusWord);
            Assert.All(result.Items, i => Assert.Equal(i.StatusWord, Verdicts.Word(i.Status)));
            Assert.Equal(scene.Verdicts(step).OrderBy(p => p.Key, StringComparer.Ordinal),
                         got.OrderBy(p => p.Key, StringComparer.Ordinal));
        }

        // route 2: the conformance suite's own check of a recording (description, then verdicts)
        var recording = new JsonObject
        {
            ["host"] = host, ["scene"] = scene.Name,
            ["recorded"] = new JsonObject { ["by"] = "Gordium.Revit.Reading.Tests", ["tool"] = "fake Revit records" },
            ["ids"] = new JsonObject(scene.Ids().Select(p => KeyValuePair.Create(p.Key, (JsonNode?)p.Value))),
            ["steps"] = steps,
        };
        var path = Path.Combine(Path.GetTempPath(), $"gordium_{host}_{scene.Name}_{Environment.ProcessId}.json");
        File.WriteAllText(path, recording.ToJsonString());
        try
        {
            var problems = JsonSerializer.Deserialize<List<string>>(Env.RunPython("check_recording.py", path))!;
            Assert.True(problems.Count == 0, string.Join("\n", problems));   // every reason, not the first's start
        }
        finally
        {
            File.Delete(path);
        }
    }
}
