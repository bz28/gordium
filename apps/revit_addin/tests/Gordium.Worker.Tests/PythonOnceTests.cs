using System.Diagnostics;
using Xunit;

namespace Gordium.Worker.Tests;

/// <summary>Running Python once (the Revit add-in uses it to get a conformance scene's facts and verdicts): its
/// output is given, a failure is an error, and a Python that hangs is stopped at the time limit.</summary>
public sealed class PythonOnceTests
{
    private static string Run(string code, TimeSpan timeout) =>
        PythonOnce.Run(Env.Python, Env.Repo, ["-c", code], timeout);

    [Fact]
    public void Its_output_is_given()
    {
        Assert.Equal("é 2\n", Run("print('\\u00e9', 1 + 1)", TimeSpan.FromSeconds(60)).Replace("\r\n", "\n"));
    }

    [Fact]
    public void The_environment_given_is_added_to_its_own()
    {
        // the add-in points Python at its clone's packages this way (Trial.PythonEnvironment)
        var got = PythonOnce.Run(Env.Python, Env.Repo, ["-c", "import os; print(os.environ['GORDIUM_TEST_VALUE'], 'PATH' in os.environ)"],
                                 TimeSpan.FromSeconds(60), new Dictionary<string, string> { ["GORDIUM_TEST_VALUE"] = "given" });
        Assert.Equal("given True\n", got.Replace("\r\n", "\n"));
    }

    [Fact]
    public void A_failure_is_an_error_with_its_words()
    {
        var e = Assert.Throws<InvalidOperationException>(() => Run("import sys; sys.exit('no scene')", TimeSpan.FromSeconds(60)));
        Assert.Contains("no scene", e.Message);
    }

    [Fact]
    public void A_python_that_hangs_is_stopped_at_the_limit()
    {
        var clock = Stopwatch.StartNew();
        var e = Assert.Throws<TimeoutException>(() => Run("import time; time.sleep(600)", TimeSpan.FromSeconds(3)));
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(30), $"took {clock.Elapsed}");
        Assert.Contains("3 s", e.Message);
    }

    [Fact]
    public void A_python_that_exits_leaving_its_output_open_is_an_error_at_the_limit()
    {
        // Python exits at once, but a process it started holds its output open for 20 s (then ends by itself)
        const string code = "import subprocess, sys; " +
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], stdout=sys.stdout, stderr=sys.stderr); " +
            "print('done')";
        var clock = Stopwatch.StartNew();
        var e = Assert.Throws<TimeoutException>(() => Run(code, TimeSpan.FromSeconds(3)));
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(15), $"took {clock.Elapsed}");
        Assert.Contains("output stayed open", e.Message);
    }

    [Fact]
    public void A_python_waiting_on_its_input_gets_end_of_file_and_never_waits()
    {
        Assert.Equal("''\n", Run("import sys; print(repr(sys.stdin.read()))", TimeSpan.FromSeconds(60)).Replace("\r\n", "\n"));
    }
}
