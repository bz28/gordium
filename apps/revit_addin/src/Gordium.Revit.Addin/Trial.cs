using System.IO;
using System.Diagnostics;
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

    /// <summary>The clone's venv Python, as the runbook sets it up (<c>py -3.12 -m venv .venv</c>).</summary>
    internal static string Python(string clone)
    {
        var python = Path.Combine(clone, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            throw new InvalidOperationException($"No venv Python at {python}: run the setup list (runbook section 2)");
        return python;
    }

    internal static WorkerOptions Options(string clone) => new() { PythonPath = Python(clone), WorkingDirectory = clone };

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
    /// which only Python works out). A failure is an error, never an empty answer.</summary>
    internal static string RunPython(string clone, string code)
    {
        var start = new ProcessStartInfo(Python(clone))
        {
            WorkingDirectory = clone,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardOutputEncoding = new UTF8Encoding(false),
        };
        start.ArgumentList.Add("-c");
        start.ArgumentList.Add(code);
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        using var p = Process.Start(start) ?? throw new InvalidOperationException("Python didn't start");
        var stderr = p.StandardError.ReadToEndAsync();
        var stdout = p.StandardOutput.ReadToEnd();
        if (!p.WaitForExit(120_000))
        {
            p.Kill(entireProcessTree: true);
            throw new TimeoutException("Python took longer than 2 minutes");
        }
        if (p.ExitCode != 0)
            throw new InvalidOperationException($"Python failed ({p.ExitCode}): {stderr.Result}");
        return stdout;
    }
}
