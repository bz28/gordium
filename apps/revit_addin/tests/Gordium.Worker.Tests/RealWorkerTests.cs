using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Worker.Tests;

/// <summary>The client against the real Python worker (<c>python -m design_checker serve</c>).</summary>
public sealed class RealWorkerTests(RealWorker worker) : IClassFixture<RealWorker>, IAsyncLifetime
{
    private WorkerClient Client => worker.Client;

    public Task InitializeAsync() => worker.EnsureRunningAsync();       // a stopped worker is started again

    public Task DisposeAsync() => Task.CompletedTask;

    // the status words the checker sends, mapped here on their own (not through the client's mapping)
    private static readonly Dictionary<string, Verdict> Word = new()
    {
        ["complies"] = Verdict.Complies,
        ["does_not_comply"] = Verdict.DoesNotComply,
        ["needs_review"] = Verdict.NeedsReview,
        ["not_checked"] = Verdict.NotChecked,
    };

    [Fact]
    public async Task The_shared_worker_is_started_again_once_a_test_has_stopped_it()
    {
        using (var p = Process.GetProcessById(Client.ProcessId))
        {
            p.Kill(entireProcessTree: true);
            p.WaitForExit(10_000);
        }
        var stopped = Client;
        await Assert.ThrowsAnyAsync<WorkerException>(() => stopped.HelloAsync());
        Assert.True(stopped.IsStopped);
        await worker.EnsureRunningAsync();              // what runs before the next test: a new worker for it
        Assert.NotSame(stopped, Client);
        Assert.False(Client.IsStopped);
        Assert.Equal(Client.About.Protocol, (await Client.HelloAsync()).Protocol);
    }

    [Fact]
    public void Hello_says_protocol_1_and_the_site_schema_with_fingerprints()
    {
        var about = Client.About;
        Assert.StartsWith("1.", about.Protocol);
        Assert.Equal("gordium.site/1", about.SiteSchema);
        Assert.Matches("^[0-9a-f]{64}$", about.WorkerFingerprint);
        Assert.Matches("^[0-9a-f]{64}$", about.Rulebook["new_york/ithaca_city"]);
    }

    public static TheoryData<string, string> Scenes()
    {
        var data = new TheoryData<string, string>();
        foreach (var c in SceneCase.All)
            data.Add(c.Scene, c.Step);
        return data;
    }

    [Fact]
    public void Every_conformance_scene_step_is_tested()
    {
        // 26 scenes, 3 with a step after the edit: the count the conformance README and the runbook give
        Assert.Equal(29, SceneCase.All.Count);
        Assert.Equal(26, SceneCase.All.Select(c => c.Scene).Distinct().Count());
    }

    [Theory]
    [MemberData(nameof(Scenes))]
    public async Task Check_site_gives_exactly_the_hand_worked_verdicts(string scene, string step)
    {
        var c = SceneCase.All.Single(x => x.Scene == scene && x.Step == step);
        var result = await Client.CheckSiteAsync(c.Site, c.Facts);
        var got = result.Items.ToDictionary(i => i.Id, i => i);
        // every expected row, with its status as the worker wrote it and as the client read it
        foreach (var (id, want) in c.Verdicts)
        {
            Assert.True(got.ContainsKey(id), $"{c}: no row {id} (expected {want})");
            Assert.Equal(want, got[id].Raw.GetProperty("status").GetString());
            Assert.Equal(Word[want], got[id].Status);
        }
        // and no row more
        Assert.Empty(got.Keys.Except(c.Verdicts.Keys));
        // the worker's groups, as the panel shows them: every row in exactly one
        Assert.Equal(got.Keys.Order(StringComparer.Ordinal), result.Groups.SelectMany(g => g.Items).Order(StringComparer.Ordinal));
        Assert.NotEmpty(result.Summary);
        Assert.Equal(Client.About.WorkerFingerprint, result.About.WorkerFingerprint);
    }

    [Fact]
    public async Task A_needs_review_scene_is_never_read_as_a_pass()
    {
        var c = SceneCase.All.Single(x => x.Scene == "02_curved_wall");
        var result = await Client.CheckSiteAsync(c.Site, c.Facts);
        Assert.Equal(Verdict.NeedsReview, result.State);
        Assert.Contains(result.Items, i => i.Status == Verdict.NeedsReview);
    }

    [Fact]
    public async Task A_real_check_whose_zoning_complies_waits_on_egress()
    {
        // the box house with every question the common rows ask answered: the worker's state is "complies", and the
        // client's own check (the rows must back it) accepts it. Since PR 82 (the headline waits on the facts) a row
        // still waiting keeps the whole check at needs review, so the facts the model can't show are given too: the
        // bedrooms and parking spaces (R-1b's parking rule) and PR 84's overlays finding (an address lookup that
        // found no overlay on exactly this lot, the day before the check's own day; the overlays row goes only then)
        var c = SceneCase.All.Single(x => x.Scene == "01_box_house");
        var facts = c.Facts.DeepClone().AsObject();
        foreach (var (k, v) in Json.Obj("""
            {"stream_near_lot": false, "accessory_dwelling_unit": false, "garage_cars": 0, "home_occupation": false,
             "unrelated_persons": 0, "owner_occupied": true, "rooms_let_for_profit": 0,
             "sleeping_rooms": 3, "parking_spaces": 2, "address": "106 Ithaca Rd, Ithaca, NY 14850",
             "overlays_none_found": {"value": true, "lot_outline": [[0, 0], [60, 0], [60, 120], [0, 120]],
               "address": "106 Ithaca Rd, Ithaca, NY 14850", "date": "2026-11-11",
               "source": "address lookup: FEMA flood maps, the City's historic, gorge and zoning maps and parcel record, every one answering none"}}
            """).ToList())
            facts[k] = v!.DeepClone();
        var result = await Client.CheckSiteAsync(c.Site, facts, today: "2026-11-12");
        // zoning complies; since egress was switched on (PR 106) the state's egress rules wait for rooms, which no
        // host sends yet, so the whole check holds at needs review (never "complies" with egress unchecked) and the
        // client reads that, with the zoning section complying and the egress section waiting
        Assert.Equal(Verdict.NeedsReview, result.State);
        var sections = result.Raw.GetProperty("sections");
        Assert.Equal("zoning", sections[0].GetProperty("key").GetString());
        Assert.Equal("complies", sections[0].GetProperty("state").GetString());
        Assert.Equal("waiting", sections[1].GetProperty("state").GetString());
        Assert.Contains(result.Items, i => i.Id == "egress.waiting" && i.Status == Verdict.NotChecked);
        // without the day of the check the finding's age can't be told: the overlays row stays, never a pass
        var undated = await Client.CheckSiteAsync(c.Site, facts);
        Assert.Equal(Verdict.NeedsReview, undated.State);
        Assert.Equal("needs_review", undated.Raw.GetProperty("sections")[0].GetProperty("state").GetString());
    }

    [Fact]
    public async Task An_unknown_command_is_refused_and_the_worker_keeps_serving()
    {
        var e = await Assert.ThrowsAsync<WorkerRefusedException>(() => Client.SendAsync("no_such_command"));
        Assert.Equal("unknown command 'no_such_command'", e.Error);
        Assert.False(Client.IsStopped);
        Assert.Equal(Client.About.Protocol, (await Client.HelloAsync()).Protocol);
    }

    [Fact]
    public async Task Bad_facts_are_refused_with_the_workers_words()
    {
        var c = SceneCase.All.Single(x => x.Scene == "01_box_house");
        var facts = c.Facts.DeepClone().AsObject();
        facts["zone"] = "R-99";
        var e = await Assert.ThrowsAsync<WorkerRefusedException>(() => Client.CheckSiteAsync(c.Site, facts));
        Assert.Contains("R-99", e.Error);
        Assert.False(Client.IsStopped);
    }

    [Fact]
    public async Task Start_site_answers_for_the_box_house_lot()
    {
        var c = SceneCase.All.Single(x => x.Scene == "01_box_house");
        var answer = await Client.StartSiteAsync(c.Site, c.Facts);
        Assert.Equal(JsonValueKind.Object, answer.Result.ValueKind);
        Assert.Equal("gordium.site/1", answer.About.SiteSchema);
    }

    [Fact]
    public async Task A_session_constant_is_always_given()
    {
        var answer = await Client.SessionAsync("session.undo", new JsonObject());
        Assert.Equal(JsonValueKind.Object, answer.Get("words").ValueKind);
        Assert.Throws<AnswerMissingException>(() => answer.Get("recheck"));   // its fields weren't sent
    }

    [Fact]
    public async Task A_refused_part_is_an_error_and_the_other_parts_still_answer()
    {
        var answer = await Client.SessionAsync("facts.validate", Json.Obj("""{"kind": "number", "text": "abc"}"""));
        var e = Assert.Throws<PartRefusedException>(() => answer.Get("value"));
        Assert.Equal("value", e.Answer);
        Assert.NotEmpty(e.Words);
        Assert.Equal(JsonValueKind.String, answer.Get("problem").ValueKind);
    }

    [Fact]
    public async Task Want_asks_for_one_answer()
    {
        var answer = await Client.SessionAsync("session.freshness",
            Json.Obj("""{"begun_at": 5.0, "dirty_at": 3.0}"""), ["still"]);
        Assert.Equal(JsonValueKind.True, answer.Get("still").ValueKind);
    }

    [Fact]
    public async Task Left_out_objects_are_decided_by_the_worker_a_missing_linked_file_counts_as_touching()
    {
        // a 60 x 120 ft lot, the house at x 15..45, y 30..80; a linked shed whose file isn't found (Rhino gives it one
        // label: a point box), a shed on the lot apart from the house, one against its west wall, one far away
        var lot = Json.Obj("""{"ring": [[0, 0], [60, 0], [60, 120], [0, 120]], "box": [0, 0, 60, 120]}""");
        var objects = JsonNode.Parse("""
            [{"id": "linked", "box": [52, 94, 4, 52, 94, 4], "points": [[52, 94]], "definition": "shed"},
             {"id": "apart", "box": [48, 90, 0, 56, 98, 8], "points": [[48, 90], [56, 90], [56, 98], [48, 98]]},
             {"id": "against", "box": [7, 40, 0, 15, 48, 8], "points": [[7, 40], [15, 40], [15, 48], [7, 48]]},
             {"id": "far", "box": [500, 0, 0, 510, 10, 8], "points": [[500, 0], [510, 0], [510, 10], [500, 10]]}]
            """)!.AsArray();
        var definitions = Json.Obj("""{"shed": {"status": "LinkedFileNotFound", "parts": [{"box": [52, 94, 4, 52, 94, 4]}]}}""");
        var answer = await Client.LeftOutAsync(lot, objects, new JsonArray(new JsonArray(15, 30, 0, 45, 80, 20)), definitions);
        Assert.Equal([true, true, true, false], answer.Get("left_out").EnumerateArray().Select(o => o.GetProperty("left_out").GetBoolean()));
        Assert.Equal(["contents_not_known", "on_lot", "on_lot", "far_from_lot"],
                     answer.Get("left_out").EnumerateArray().Select(o => o.GetProperty("why").GetString()));
        Assert.Equal([JsonValueKind.Null, JsonValueKind.False, JsonValueKind.True, JsonValueKind.False],
                     answer.Get("touching").EnumerateArray().Select(o => o.GetProperty("touching").ValueKind));
        Assert.Equal("contents_not_known", answer.Get("no_box")[0].GetProperty("why").GetString());
    }

    [Fact]
    public async Task A_left_out_object_with_a_field_the_worker_doesnt_read_is_refused_never_guessed()
    {
        var objects = JsonNode.Parse("""[{"id": "x", "box": [0, 0, 0, 1, 1, 1], "points": [[0, 0]], "category": "Walls"}]""")!.AsArray();
        var answer = await Client.LeftOutAsync(null, objects, []);
        var e = Assert.Throws<PartRefusedException>(() => answer.Get("left_out"));
        Assert.Contains("no field category", e.Words);
    }

    [Fact]
    public async Task A_field_the_command_doesnt_read_is_refused()
    {
        var e = await Assert.ThrowsAsync<WorkerRefusedException>(() => Client.SessionAsync("session.freshness",
            Json.Obj("""{"begun_at": 5.0, "dirty_at": 3.0, "bogus": 1}""")));
        Assert.Contains("doesn't read bogus", e.Error);
    }
}

/// <summary>A real worker that dies: each test starts its own.</summary>
public sealed class RealWorkerDiesTests
{
    [Fact]
    public async Task A_worker_killed_mid_session_gives_a_clear_error_never_a_hang_or_an_answer()
    {
        var c = SceneCase.All.Single(x => x.Scene == "01_box_house");
        using var client = await WorkerClient.StartAsync(Env.Real());
        Assert.NotEmpty((await client.CheckSiteAsync(c.Site, c.Facts)).Items);
        using (var p = Process.GetProcessById(client.ProcessId))
        {
            p.Kill(entireProcessTree: true);
            p.WaitForExit(10_000);
        }
        var clock = Stopwatch.StartNew();
        var e = await Assert.ThrowsAsync<WorkerExitedException>(() => client.CheckSiteAsync(c.Site, c.Facts));
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(15), $"took {clock.Elapsed}");
        Assert.Contains("stopped", e.Message);
        Assert.True(client.IsStopped);
        await Assert.ThrowsAsync<WorkerStoppedException>(() => client.CheckSiteAsync(c.Site, c.Facts));
    }

    [Fact]
    public async Task A_worker_killed_while_checking_gives_an_error_or_its_one_full_answer()
    {
        var c = SceneCase.All.Single(x => x.Scene == "01_box_house");
        using var client = await WorkerClient.StartAsync(Env.Real());
        var check = client.CheckSiteAsync(c.Site, c.Facts);
        using (var p = Process.GetProcessById(client.ProcessId))
            p.Kill(entireProcessTree: true);
        try
        {
            // the check may have finished just before the kill: then it is the whole, real answer
            var result = await check;
            Assert.Equal(c.Verdicts.Count, result.Items.Count);
        }
        catch (WorkerExitedException) { }
        await Assert.ThrowsAnyAsync<WorkerException>(() => client.CheckSiteAsync(c.Site, c.Facts));
    }

    [Fact]
    public async Task A_python_that_isnt_there_is_a_clear_error()
    {
        var options = new WorkerOptions { PythonPath = Path.Combine(Env.Repo, "no_such_python"), WorkingDirectory = Env.Repo };
        var e = await Assert.ThrowsAsync<WorkerExitedException>(() => WorkerClient.StartAsync(options));
        Assert.Contains("couldn't be started", e.Message);
    }
}
