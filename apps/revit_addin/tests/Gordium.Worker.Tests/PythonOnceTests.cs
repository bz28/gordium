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
    public void A_python_waiting_on_its_input_gets_end_of_file_and_never_waits()
    {
        Assert.Equal("''\n", Run("import sys; print(repr(sys.stdin.read()))", TimeSpan.FromSeconds(60)).Replace("\r\n", "\n"));
    }
}
