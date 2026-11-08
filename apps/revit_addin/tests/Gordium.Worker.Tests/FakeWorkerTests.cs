using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Worker.Tests;

/// <summary>Each way a worker's answer can go wrong, given on purpose by the stand-in worker (fake_worker.py).
/// Every one must be an error, never a result: Gordium's rule is never a false pass.</summary>
public sealed class FakeWorkerTests
{
    private static readonly JsonObject Site = Json.Obj("""{"schema": "gordium.site/1"}""");
    private static readonly JsonObject Facts = Json.Obj("""{"zone": "R-1b"}""");

    private static async Task<WorkerClient> Start(string mode, TimeSpan? timeout = null) =>
        await WorkerClient.StartAsync(Env.Fake(mode, timeout: timeout));

    [Fact]
    public async Task A_well_formed_answer_is_read()
    {
        using var client = await Start("ok");
        var result = await client.CheckSiteAsync(Site, Facts);
        Assert.Equal(Verdict.Complies, Assert.Single(result.Items).Status);
        Assert.Equal("R-1b.height", result.Items[0].Id);
        Assert.Equal("1 complies", result.Summary);
        Assert.Null(result.ReportError);
    }

    // ---- hello: the versions ----

    [Fact]
    public async Task A_worker_reporting_protocol_2_is_refused()
    {
        var e = await Assert.ThrowsAsync<WorkerVersionException>(() => Start("hello_2"));
        Assert.Contains("protocol 2.0", e.Message);
    }

    [Theory]
    [InlineData("hello_other_schema", typeof(WorkerVersionException))]
    [InlineData("hello_no_schema", typeof(WorkerProtocolException))]
    [InlineData("hello_bad_version", typeof(WorkerProtocolException))]
    public async Task A_hello_that_isnt_protocol_1_and_site_1_is_refused(string mode, Type error)
    {
        var e = await Assert.ThrowsAnyAsync<WorkerProtocolException>(() => Start(mode));
        Assert.IsType(error, e);
    }

    [Fact]
    public async Task Every_answer_is_checked_for_its_version_not_only_hello()
    {
        using var client = await Start("about_2");
        await Assert.ThrowsAsync<WorkerVersionException>(() => client.CheckSiteAsync(Site, Facts));
        Assert.True(client.IsStopped);
    }

    [Fact]
    public async Task A_worker_that_crashes_at_start_says_so_with_its_log()
    {
        var e = await Assert.ThrowsAsync<WorkerExitedException>(() => Start("hello_crash"));
        Assert.Equal(7, e.ExitCode);
        Assert.Contains("no module named shapely", e.Message);
    }

    [Fact]
    public async Task A_worker_that_never_says_hello_times_out()
    {
        var options = Env.Fake("hello_hang");
        options = new WorkerOptions
        {
            PythonPath = options.PythonPath, WorkingDirectory = options.WorkingDirectory,
            Arguments = options.Arguments, StartTimeout = TimeSpan.FromSeconds(2),
        };
        var clock = Stopwatch.StartNew();
        await Assert.ThrowsAsync<WorkerTimeoutException>(() => WorkerClient.StartAsync(options));
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(20), $"took {clock.Elapsed}");
    }

    // ---- a check's answer that can't be trusted ----

    [Theory]
    [InlineData("unknown_status")]
    [InlineData("missing_status")]
    [InlineData("null_status")]
    [InlineData("missing_id")]
    [InlineData("missing_reason")]
    [InlineData("reason_not_text")]
    [InlineData("empty_row_id")]
    [InlineData("missing_name")]
    [InlineData("missing_group")]
    [InlineData("missing_summary")]
    [InlineData("state_unknown")]
    [InlineData("report_error_not_text")]
    [InlineData("about_other_schema")]
    [InlineData("about_empty_fingerprint")]
    [InlineData("about_rulebook_not_text")]
    [InlineData("about_rulebook_empty")]
    [InlineData("refused_error_not_text")]
    [InlineData("duplicate_key")]
    [InlineData("duplicate_status")]
    [InlineData("nan")]
    [InlineData("empty_items")]
    [InlineData("items_not_a_list")]
    [InlineData("row_twice")]
    [InlineData("missing_state")]
    [InlineData("missing_view")]
    [InlineData("missing_report_error")]
    [InlineData("no_about")]
    [InlineData("no_result")]
    [InlineData("no_ok")]
    [InlineData("ok_text")]
    [InlineData("refused_no_error")]
    [InlineData("wrong_id")]
    [InlineData("id_as_text")]
    [InlineData("null_id")]
    [InlineData("not_json")]
    [InlineData("progress_line")]
    [InlineData("not_utf8")]
    public async Task An_answer_that_cant_be_trusted_is_an_error_and_stops_the_worker(string mode)
    {
        using var client = await Start(mode);
        await Assert.ThrowsAnyAsync<WorkerProtocolException>(() => client.CheckSiteAsync(Site, Facts));
        Assert.True(client.IsStopped);
        // and never an answer afterwards: a later line could be this request's, read as the next one's
        await Assert.ThrowsAsync<WorkerStoppedException>(() => client.CheckSiteAsync(Site, Facts));
    }

    [Fact]
    public async Task A_refusal_gives_the_workers_words_and_the_worker_keeps_serving()
    {
        using var client = await Start("refused");
        var e = await Assert.ThrowsAsync<WorkerRefusedException>(() => client.CheckSiteAsync(Site, Facts));
        Assert.Equal("facts: zone is missing", e.Error);
        Assert.Equal("Traceback ...", e.Trace);
        Assert.False(client.IsStopped);
    }

    [Fact]
    public async Task A_worker_that_dies_before_answering_is_a_clear_error()
    {
        using var client = await Start("die");
        var e = await Assert.ThrowsAsync<WorkerExitedException>(() => client.CheckSiteAsync(Site, Facts));
        Assert.Equal(3, e.ExitCode);
        Assert.True(client.IsStopped);
    }

    [Fact]
    public async Task A_worker_that_hangs_times_out_and_is_stopped()
    {
        using var client = await Start("hang", TimeSpan.FromSeconds(2));
        var pid = client.ProcessId;
        var clock = Stopwatch.StartNew();
        await Assert.ThrowsAsync<WorkerTimeoutException>(() => client.CheckSiteAsync(Site, Facts));
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(20), $"took {clock.Elapsed}");
        Assert.True(client.IsStopped);
        Assert.True(Exited(pid), "the hung worker was not stopped");
    }

    [Fact]
    public async Task A_cancelled_request_stops_the_worker()
    {
        using var client = await Start("hang");
        using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(300));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.CheckSiteAsync(Site, Facts, cancel: cancel.Token));
        Assert.True(client.IsStopped);
        await Assert.ThrowsAsync<WorkerStoppedException>(() => client.CheckSiteAsync(Site, Facts));
    }

    private static bool Exited(int pid)
    {
        try
        {
            using var p = Process.GetProcessById(pid);
            return p.WaitForExit(10_000);
        }
        catch (ArgumentException)
        {
            return true;            // gone already
        }
    }

    // ---- session answers ----

    [Theory]
    [InlineData("session_refused_and_answered", "facts.validate", null)]
    [InlineData("session_refused_unknown_part", "facts.validate", null)]
    [InlineData("session_refused_words_not_text", "facts.validate", null)]
    [InlineData("session_half_a_part", "box.pick", null)]
    [InlineData("session_wanted_not_given", "facts.validate", "value")]
    public async Task A_session_answer_that_cant_be_trusted_is_an_error(string mode, string command, string? want)
    {
        using var client = await Start(mode);
        await Assert.ThrowsAsync<WorkerProtocolException>(() =>
            client.SessionAsync(command, new JsonObject(), want is null ? null : [want]));
        Assert.True(client.IsStopped);
    }

    // ---- what the client sends ----

    [Fact]
    public async Task Requests_are_utf8_without_a_bom_one_line_each_with_increasing_ids()
    {
        var record = Path.Combine(Path.GetTempPath(), $"gordium_record_{Guid.NewGuid():N}.bin");
        try
        {
            using (var client = await WorkerClient.StartAsync(Env.Fake("record", record)))
            {
                await client.CheckSiteAsync(Json.Obj("""{"name": "Café – ½ lot"}"""), Facts);
                await client.SessionAsync("session.undo", new JsonObject());
            }
            var bytes = File.ReadAllBytes(record);
            Assert.False(bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF, "a byte-order mark was sent");
            // only ASCII: non-English text goes as JSON \u escapes, which no code page or encoding mix-up can change
            Assert.All(bytes, b => Assert.True(b < 0x80, $"a byte {b:X2} that isn't ASCII was sent"));
            var text = new UTF8Encoding(false, true).GetString(bytes);
            Assert.DoesNotContain('\r', text);
            var lines = text.Split('\n');
            Assert.Equal("", lines[^1]);                    // every request ends its line
            var requests = lines[..^1].Select(l => JsonNode.Parse(l)!.AsObject()).ToList();
            Assert.Equal([1L, 2L, 3L], requests.Select(r => r["id"]!.GetValue<long>()));
            Assert.Equal(["hello", "check_site", "session.undo"], requests.Select(r => r["cmd"]!.GetValue<string>()));
            Assert.All(requests, r => Assert.Equal("1.0", r["protocol"]!.GetValue<string>()));
            Assert.Equal("Café – ½ lot", requests[1]["site"]!["name"]!.GetValue<string>());
            Assert.False(requests[1].ContainsKey("report"));      // an optional field left null is not sent
        }
        finally
        {
            File.Delete(record);
        }
    }

    [Fact]
    public async Task A_value_JSON_cant_carry_is_refused_before_sending_and_the_worker_keeps_serving()
    {
        using var client = await Start("ok");
        var facts = new JsonObject { ["grade_elevation"] = double.NaN };
        await Assert.ThrowsAsync<ArgumentException>(() => client.CheckSiteAsync(Site, facts));
        Assert.False(client.IsStopped);
        Assert.NotEmpty((await client.CheckSiteAsync(Site, Facts)).Items);
    }

    [Theory]
    [InlineData("id")]
    [InlineData("cmd")]
    [InlineData("protocol")]
    [InlineData("progress")]
    [InlineData("want")]
    public async Task A_requests_own_field_is_never_sent_as_a_commands(string field)
    {
        using var client = await Start("ok");
        await Assert.ThrowsAsync<ArgumentException>(() => client.SendAsync("future.command", new JsonObject { [field] = 1 }));
        await Assert.ThrowsAsync<ArgumentException>(() => client.SessionAsync("session.undo", new JsonObject { [field] = 1 }));
        Assert.False(client.IsStopped);
    }

    [Theory]
    [InlineData("check")]
    [InlineData("start")]
    [InlineData("facts")]
    [InlineData("options")]
    [InlineData("sample_site")]
    public async Task The_older_commands_are_not_sent(string command)
    {
        using var client = await Start("ok");
        await Assert.ThrowsAsync<ArgumentException>(() => client.SendAsync(command));
    }

    public static TheoryData<string> TypedCommands()
    {
        var data = new TheoryData<string>();
        foreach (var c in Protocol.ModelCommands.Concat(Protocol.SessionCommands.Keys))
            data.Add(c);
        return data;
    }

    [Theory]
    [MemberData(nameof(TypedCommands))]
    public async Task A_command_with_a_typed_method_is_never_sent_unread(string command)
    {
        using var client = await Start("ok");
        await Assert.ThrowsAsync<ArgumentException>(() => client.SendAsync(command));
        Assert.False(client.IsStopped);
    }

    [Fact]
    public async Task A_command_a_later_worker_adds_is_sent_with_its_envelope_checked()
    {
        using var client = await Start("ok");
        var answer = await client.SendAsync("future.command", new JsonObject { ["x"] = 1 });
        Assert.Equal("gordium.site/1", answer.About.SiteSchema);
    }

    [Fact]
    public async Task A_worker_that_stops_reading_times_out_and_is_stopped_never_a_hang()
    {
        using var client = await Start("no_read", TimeSpan.FromSeconds(2));
        var big = new JsonObject { ["schema"] = new string('x', 20_000_000) };     // far more than a pipe holds
        var check = client.CheckSiteAsync(big, Facts);
        var first = await Task.WhenAny(check, Task.Delay(TimeSpan.FromSeconds(30)));
        Assert.Same(check, first);                                                   // it ended: no hang
        await Assert.ThrowsAsync<WorkerTimeoutException>(() => check);
        Assert.True(client.IsStopped);
    }

    [Fact]
    public async Task One_time_limit_covers_sending_a_request_and_its_answer()
    {
        // the stand-in takes 1.5 s to start reading the request, then 1.5 s to answer: 3 s in all, over the 2 s limit
        using var client = await Start("slow", TimeSpan.FromSeconds(2));
        var big = new JsonObject { ["schema"] = new string('x', 20_000_000) };     // more than a pipe holds
        await Assert.ThrowsAsync<WorkerTimeoutException>(() => client.CheckSiteAsync(big, Facts));
        Assert.True(client.IsStopped);
    }

    [Fact]
    public void A_verdict_never_set_is_never_a_pass()
    {
        Assert.Equal(Verdict.NeedsReview, default(Verdict));
        var none = new Dictionary<string, Verdict>();
        Assert.Equal(Verdict.NeedsReview, none.GetValueOrDefault("R-1b.height"));
    }

    [Fact]
    public async Task A_row_the_worker_didnt_send_is_never_read_as_a_pass()
    {
        using var client = await Start("ok");
        var rows = (await client.CheckSiteAsync(Site, Facts)).ById();
        Assert.NotEqual(Verdict.Complies, rows.GetValueOrDefault("R-1b.front_yard"));
    }

    [Fact]
    public async Task Session_commands_and_answers_outside_the_protocol_are_refused()
    {
        using var client = await Start("ok");
        await Assert.ThrowsAsync<ArgumentException>(() => client.SessionAsync("facts.everything", new JsonObject()));
        await Assert.ThrowsAsync<ArgumentException>(() => client.SessionAsync("box.view", new JsonObject(), ["colour"]));
        await Assert.ThrowsAsync<ArgumentException>(() => client.SessionAsync("box.view", new JsonObject(), []));
    }

    [Fact]
    public async Task The_callers_objects_are_not_changed()
    {
        using var client = await Start("ok");
        var site = Json.Obj("""{"schema": "gordium.site/1"}""");
        await client.CheckSiteAsync(site, Facts);
        await client.CheckSiteAsync(site, Facts);            // the same objects sent twice
        Assert.Equal("""{"schema":"gordium.site/1"}""", site.ToJsonString());
    }
}
