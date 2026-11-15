using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

[assembly: CollectionBehavior(MaxParallelThreads = 2)]   // at most two workers starting at once

namespace Gordium.Worker.Tests;

/// <summary>Where the tests find Python and the repository.</summary>
internal static class Env
{
    /// <summary>The Python with Gordium installed (<c>pip install -e ".[dev]"</c>): GORDIUM_PYTHON, else
    /// <c>python</c> on the PATH (as CI's setup-python gives).</summary>
    public static string Python => Environment.GetEnvironmentVariable("GORDIUM_PYTHON") is { Length: > 0 } p ? p : "python";

    /// <summary>The repository root: the first folder above the tests with pyproject.toml and test_data/.</summary>
    public static string Repo { get; } = FindRepo();

    public static string Conformance => Path.Combine(Repo, "test_data", "host_conformance");

    private static string FindRepo()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "pyproject.toml"))
                && Directory.Exists(Path.Combine(d.FullName, "test_data", "host_conformance")))
                return d.FullName;
        throw new InvalidOperationException("no Gordium repository above " + AppContext.BaseDirectory);
    }

    public static WorkerOptions Real() => new() { PythonPath = Python, WorkingDirectory = Repo };

    /// <summary>The stand-in worker (fake_worker.py) in one of its modes.</summary>
    public static WorkerOptions Fake(string mode, string? record = null, TimeSpan? timeout = null) => new()
    {
        PythonPath = Python,
        WorkingDirectory = Repo,
        Arguments = record is null
            ? [Path.Combine(AppContext.BaseDirectory, "fake_worker.py"), mode]
            : [Path.Combine(AppContext.BaseDirectory, "fake_worker.py"), mode, record],
        StartTimeout = TimeSpan.FromSeconds(30),
        RequestTimeout = timeout ?? TimeSpan.FromSeconds(30),
    };

    /// <summary>Runs a Python script of the tests' own and gives its standard output.</summary>
    public static string RunPython(string script)
    {
        var info = new ProcessStartInfo(Python)
        {
            WorkingDirectory = Repo,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        info.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, script));
        using var p = Process.Start(info)!;
        var stderr = p.StandardError.ReadToEndAsync();
        var stdout = p.StandardOutput.ReadToEnd();
        if (!p.WaitForExit(120_000))
        {
            p.Kill(true);
            throw new TimeoutException(script + " didn't finish in 120 s");
        }
        if (p.ExitCode != 0)
            throw new InvalidOperationException($"{script} failed ({p.ExitCode}): {stderr.Result}");
        return stdout;
    }
}

/// <summary>One step of one conformance scene: the description to send, the facts and the hand-worked verdicts.</summary>
public sealed record SceneCase(string Scene, string Step, JsonNode Site, JsonNode Facts, IReadOnlyDictionary<string, string> Verdicts)
{
    public override string ToString() => $"{Scene} ({Step})";

    /// <summary>Every scene step, from the scene files through the conformance suite's own functions
    /// (scene_cases.py), the description read from expected/ for a drawn scene.</summary>
    public static IReadOnlyList<SceneCase> All => _all.Value;

    private static readonly Lazy<IReadOnlyList<SceneCase>> _all = new(Load);

    private static IReadOnlyList<SceneCase> Load()
    {
        var cases = new List<SceneCase>();
        foreach (var line in Env.RunPython("scene_cases.py").Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var c = JsonNode.Parse(line)!.AsObject();
            var site = c["expected_file"] is JsonNode f
                ? JsonNode.Parse(File.ReadAllText(Path.Combine(Env.Conformance, f.GetValue<string>())))!
                : c["site"]!.DeepClone();
            var verdicts = c["verdicts"]!.AsObject().ToDictionary(p => p.Key, p => p.Value!.GetValue<string>());
            cases.Add(new SceneCase(c["scene"]!.GetValue<string>(), c["step"]!.GetValue<string>(), site,
                                    c["facts"]!.DeepClone(), verdicts));
        }
        return cases;
    }
}

/// <summary>One real worker shared by a test class (starting Python and loading the rules takes seconds). A test whose
/// answer the client refused has stopped it; the next test starts a new one (<see cref="EnsureRunningAsync"/>, called
/// once before each test), so one refusal is one failure, not a run of WorkerStoppedException in whichever tests
/// happen to come after it. Within a test the client never changes, so "the worker keeps serving" is a real check.</summary>
public sealed class RealWorker : IAsyncLifetime
{
    public WorkerClient Client { get; private set; } = null!;

    public async Task EnsureRunningAsync()
    {
        if (!Client.IsStopped)
            return;
        Client.Dispose();
        Client = await WorkerClient.StartAsync(Env.Real());
    }

    public async Task InitializeAsync() => Client = await WorkerClient.StartAsync(Env.Real());

    public Task DisposeAsync()
    {
        Client.Dispose();
        return Task.CompletedTask;
    }
}

internal static class Json
{
    public static JsonObject Obj(string json) => JsonNode.Parse(json)!.AsObject();

    public static string Text(JsonElement e) => e.GetRawText();
}
