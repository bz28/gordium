using System.Diagnostics;
using System.Text;

namespace Gordium.Worker;

/// <summary>Runs Python once (not the worker: a short script, such as the conformance suite working out a scene's
/// facts) and gives its standard output. A failure or a run past the time limit is an error, never an empty
/// answer; a run past the limit is stopped, its child processes too.</summary>
public static class PythonOnce
{
    /// <summary>Runs <paramref name="python"/> with <paramref name="arguments"/> in
    /// <paramref name="workingDirectory"/>, and gives its standard output (UTF-8).</summary>
    /// <exception cref="TimeoutException">It ran longer than <paramref name="timeout"/> (it is stopped).</exception>
    /// <exception cref="InvalidOperationException">It didn't start, or it exited with an error (its stderr is in
    /// the message).</exception>
    public static string Run(string python, string workingDirectory, IReadOnlyList<string> arguments, TimeSpan timeout)
    {
        var start = new ProcessStartInfo(python)
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardInput = true,     // closed at once: a script that reads its input gets end of file, never waits
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false),
        };
        foreach (var a in arguments)
            start.ArgumentList.Add(a);
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        using var p = Process.Start(start) ?? throw new InvalidOperationException($"Python didn't start ({python})");
        p.StandardInput.Close();
        // both streams are read while waiting, so neither a full pipe nor a hung Python can block past the limit
        var stdout = p.StandardOutput.ReadToEndAsync();
        var stderr = p.StandardError.ReadToEndAsync();
        if (!p.WaitForExit(timeout))
        {
            try
            {
                p.Kill(entireProcessTree: true);
            }
            catch (InvalidOperationException)
            {
                // it exited just now
            }
            throw new TimeoutException($"Python ran longer than {timeout.TotalSeconds:0.#} s and was stopped");
        }
        p.WaitForExit();   // the streams are complete only after the parameterless wait
        if (p.ExitCode != 0)
            throw new InvalidOperationException($"Python failed (exit code {p.ExitCode}): {stderr.GetAwaiter().GetResult()}");
        return stdout.GetAwaiter().GetResult();
    }
}
