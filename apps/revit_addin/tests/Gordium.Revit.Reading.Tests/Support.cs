using System.Diagnostics;
using Gordium.Worker;
using Xunit;

[assembly: CollectionBehavior(MaxParallelThreads = 2)]   // at most two workers starting at once

namespace Gordium.Revit.Reading.Tests;

/// <summary>Where the tests find Python and the repository (as Gordium.Worker.Tests' Env).</summary>
internal static class Env
{
    public static string Python => Environment.GetEnvironmentVariable("GORDIUM_PYTHON") is { Length: > 0 } p ? p : "python";

    public static string Repo { get; } = FindRepo();

    private static string FindRepo()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "pyproject.toml"))
                && Directory.Exists(Path.Combine(d.FullName, "test_data", "host_conformance")))
                return d.FullName;
        throw new InvalidOperationException("no Gordium repository above " + AppContext.BaseDirectory);
    }

    public static WorkerOptions Real() => new() { PythonPath = Python, WorkingDirectory = Repo };

    /// <summary>Runs one of the tests' own Python scripts and gives its standard output.</summary>
    public static string RunPython(string script, params string[] args) =>
        Run([Path.Combine(AppContext.BaseDirectory, script), .. args], script);

    /// <summary>Runs a module of Gordium's Python packages (<c>python -m</c>) and gives its standard output.</summary>
    public static string RunModule(string module, params string[] args) => Run(["-m", module, .. args], module);

    /// <summary>Runs a line of Python (<c>python -c</c>, its arguments after it) and gives its standard output.</summary>
    public static string RunCode(string code, params string[] args) => Run(["-c", code, .. args], "python -c");

    private static string Run(string[] argv, string script)
    {
        var info = new ProcessStartInfo(Python)
        {
            WorkingDirectory = Repo,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        foreach (var a in argv)
            info.ArgumentList.Add(a);
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

/// <summary>One real worker shared by a test class; a new one when a test's refusal stopped it.</summary>
public sealed class RealWorker : IAsyncLifetime
{
    public WorkerClient Client { get; private set; } = null!;

    public async Task<WorkerClient> RunningAsync()
    {
        if (Client.IsStopped)
        {
            Client.Dispose();
            Client = await WorkerClient.StartAsync(Env.Real());
        }
        return Client;
    }

    public async Task InitializeAsync() => Client = await WorkerClient.StartAsync(Env.Real());

    public Task DisposeAsync()
    {
        Client.Dispose();
        return Task.CompletedTask;
    }
}
