using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using System.Text.Json;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>What the trial's buttons share: where the clone and its Python are, and the results log.</summary>
internal static class Trial
{
    /// <summary>The repo clone, which the worker reads its rulebooks from: the one named in <c>gordium_clone.txt</c>
    /// beside the add-in (written by the install script), else the first folder above the add-in's own file that
    /// holds <c>pyproject.toml</c>.</summary>
    internal static string Clone()
    {
        // installed by install_trial_addin.ps1: a copy of the build, with the clone's path written beside it
        var here = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location)!;
        var note = Path.Combine(here, "gordium_clone.txt");
        if (File.Exists(note))
        {
            var clone = File.ReadAllText(note).Trim();
            if (!File.Exists(Path.Combine(clone, "pyproject.toml")))
                throw new InvalidOperationException($"{note} names {clone}, which is not Gordium's clone (no pyproject.toml)");
            return clone;
        }
        var dir = here;
        while (dir is not null && !File.Exists(Path.Combine(dir, "pyproject.toml")))
            dir = Path.GetDirectoryName(dir);
        return dir ?? throw new InvalidOperationException(
            "Gordium's clone wasn't found above the add-in's folder (no pyproject.toml): load the add-in from the clone");
    }

    /// <summary>The clone's venv Python, as the runbook sets it up (<c>py -3.12 -m venv .venv</c>); or, for a clone
    /// with no venv of its own (a git worktree beside the main clone), the Python named in <c>gordium_python.txt</c>
    /// beside the add-in (written by the install script's <c>-Python</c>).</summary>
    internal static string Python(string clone)
    {
        var note = Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location)!, "gordium_python.txt");
        var python = File.Exists(note) ? File.ReadAllText(note).Trim() : Path.Combine(clone, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            throw new InvalidOperationException($"No venv Python at {python}: run the setup list (runbook section 2)");
        return python;
    }

    /// <summary>Python pointed at the clone's own packages (<c>PYTHONPATH</c>, every <c>packages/&lt;package&gt;</c>
    /// folder): the code run is always the clone's, even through another clone's venv.</summary>
    internal static Dictionary<string, string> PythonEnvironment(string clone)
    {
        var packages = Path.Combine(clone, "packages");
        return Directory.Exists(packages)
            ? new() { ["PYTHONPATH"] = string.Join(Path.PathSeparator, Directory.GetDirectories(packages).Order(StringComparer.Ordinal)) }
            : [];
    }

    internal static WorkerOptions Options(string clone) =>
        new() { PythonPath = Python(clone), WorkingDirectory = clone, Environment = PythonEnvironment(clone) };

    /// <summary>The worker this Revit session uses, started (off Revit's thread) if it isn't running, and waited for.</summary>
    internal static WorkerClient Worker() => WorkerAsync().GetAwaiter().GetResult();

    private static readonly object WorkerLock = new();
    private static Task<WorkerClient>? _starting;
    private static bool _closing;

    /// <summary>The worker this Revit session uses, without waiting: the running one, the one being started, or one
    /// started now on a pool thread (Check project starts it before its read, so Python starts while Revit reads; PR
    /// 8). A start that failed is tried again by the next call. One at a time (the lock): a check's start and a
    /// trial tool's never make two.</summary>
    /// <summary>Takes the session's worker away (Revit closing), under the same lock: the caller disposes it.</summary>
    internal static WorkerClient? StopWorker()
    {
        lock (WorkerLock)
        {
            var worker = App.Worker;
            App.Worker = null;
            _closing = true;                                  // a start still running stops its worker when it ends
            return worker;
        }
    }

    internal static Task<WorkerClient> WorkerAsync()
    {
        lock (WorkerLock)
        {
            if (App.Worker is { IsStopped: false } running)
                return Task.FromResult(running);
            if (_starting is { IsCompleted: false } starting)
                return starting;
            App.Worker?.Dispose();
            App.Worker = null;
            var clone = Clone();                              // on the caller's thread: a missing clone throws here
            _starting = Task.Run(async () =>
            {
                var started = await WorkerClient.StartAsync(Options(clone)).ConfigureAwait(false);
                lock (WorkerLock)
                {
                    if (_closing)
                    {
                        started.Dispose();                    // Revit closed while it started: never left running
                        throw new InvalidOperationException("Revit is closing: the worker was stopped");
                    }
                    App.Worker = started;
                }
                return started;
            });
            return _starting;
        }
    }

    /// <summary>The target framework this build was made for (<c>.NETCoreApp,Version=v10.0</c>).</summary>
    internal static string Build() =>
        Assembly.GetExecutingAssembly().GetCustomAttribute<TargetFrameworkAttribute>()?.FrameworkName ?? "unknown";

    /// <summary>The .NET runtime Revit is running this add-in on.</summary>
    internal static string Runtime() => $"{RuntimeInformation.FrameworkDescription} ({Environment.Version})";

    /// <summary>The results log: one JSON line per event, in the user's local app data, so whoever runs the trial
    /// (a person or a script) can read each button's numbers without reading them off the screen.</summary>
    internal static string LogPath()
    {
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gordium", "trial");
        Directory.CreateDirectory(dir);
        return Path.Combine(dir, "results.jsonl");
    }

    internal static void Log(string what, IDictionary<string, object?> fields)
    {
        var line = new Dictionary<string, object?> { ["at"] = DateTimeOffset.Now.ToString("o"), ["what"] = what };
        foreach (var (k, v) in fields)
            line[k] = v;
        File.AppendAllText(LogPath(), JsonSerializer.Serialize(line) + "\n", new UTF8Encoding(false));
    }

    /// <summary>Runs the clone's Python once and gives its output (for the conformance scene's facts and verdicts,
    /// which only Python works out). A failure, or a run past 2 minutes (stopped), is an error, never an empty answer.</summary>
    internal static string RunPython(string clone, string code) =>
        PythonOnce.Run(Python(clone), clone, ["-c", code], TimeSpan.FromMinutes(2), PythonEnvironment(clone));
}
