namespace Gordium.Worker;

/// <summary>How to start the worker (<c>python -m design_checker serve</c>).</summary>
public sealed class WorkerOptions
{
    /// <summary>The Python to run: the clone's venv Python (Windows: <c>&lt;clone&gt;\.venv\Scripts\python.exe</c>).</summary>
    public required string PythonPath { get; init; }

    /// <summary>The folder the worker runs in: the clone, whose rulebooks the worker reads.</summary>
    public required string WorkingDirectory { get; init; }

    /// <summary>What follows the Python path. Changed only by tests (a stand-in worker).</summary>
    public IReadOnlyList<string> Arguments { get; init; } = ["-m", "design_checker", "serve"];

    /// <summary>Environment variables to set for the worker (added to this process's own).</summary>
    public IReadOnlyDictionary<string, string> Environment { get; init; } = new Dictionary<string, string>();

    /// <summary>The longest to wait for the first <c>hello</c> (it includes starting Python and loading the code).</summary>
    public TimeSpan StartTimeout { get; init; } = TimeSpan.FromSeconds(60);

    /// <summary>The longest one request may take, sending it and its answer together (the Rhino plugin's own limit:
    /// worker_client.ASK_LIMIT_S).</summary>
    public TimeSpan RequestTimeout { get; init; } = TimeSpan.FromSeconds(60);

    /// <summary>The longest to wait for <c>start_site</c>, which can take longer on a deep lot (ASK_LIMITS_S["start"]).</summary>
    public TimeSpan StartSiteTimeout { get; init; } = TimeSpan.FromSeconds(120);

    /// <summary>How many of the worker's last log lines (stderr) to keep for error messages.</summary>
    public int LogLines { get; init; } = 40;
}
