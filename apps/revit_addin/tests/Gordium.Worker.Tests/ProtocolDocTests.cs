using System.Text.RegularExpressions;
using Xunit;

namespace Gordium.Worker.Tests;

/// <summary>The client's copy of the protocol is the document's (docs/protocol/worker_protocol_v1.md), which a
/// Python test keeps equal to the worker's own table.</summary>
public sealed class ProtocolDocTests
{
    private static string Doc => File.ReadAllText(Path.Combine(Env.Repo, "docs", "protocol", "worker_protocol_v1.md"));

    /// <summary>{command: each part's answer names}, from the document's command reference.</summary>
    private static Dictionary<string, List<List<string>>> Reference()
    {
        var doc = Doc;
        var start = doc.IndexOf("<!-- the command reference", StringComparison.Ordinal);
        var end = doc.IndexOf("<!-- end of the command reference -->", StringComparison.Ordinal);
        Assert.True(start >= 0 && end > start, "the command reference markers are missing");
        var out_ = new Dictionary<string, List<List<string>>>();
        List<List<string>>? parts = null;
        foreach (var line in doc[start..end].Split('\n'))
        {
            var heading = Regex.Match(line, @"^### `([^`]+)`\s*$");
            if (heading.Success)
            {
                parts = [];
                out_.Add(heading.Groups[1].Value, parts);
                continue;
            }
            var row = Regex.Match(line, @"^\| (`[^|]+`) \| `");
            if (row.Success && parts is not null)
                parts.Add(Regex.Matches(row.Groups[1].Value, "`([^`]+)`").Select(m => m.Groups[1].Value).ToList());
        }
        return out_;
    }

    [Fact]
    public void The_session_commands_and_their_parts_are_the_documents()
    {
        var doc = Reference();
        Assert.Equal(20, doc.Count);
        Assert.Equal(doc.Keys.Order(), Protocol.SessionCommands.Keys.Order());
        foreach (var (command, parts) in doc)
            Assert.Equal(parts.Select(p => string.Join(",", p)),
                         Protocol.SessionCommands[command].Select(p => string.Join(",", p)));
    }

    [Fact]
    public void The_version_is_the_documents()
    {
        Assert.Contains($"# The worker protocol, version {Protocol.Major} (`{Protocol.Version}`)", Doc);
        Assert.Contains($"`{Protocol.SiteSchema}`", File.ReadAllText(Path.Combine(Env.Repo, "docs", "protocol", "site_description_v1.md")));
    }

    [Fact]
    public void The_model_commands_are_the_documents()
    {
        // the doc's own list: "- `hello`: ..." and "- `read_model`, `check_site`, `start_site`: ..."
        var section = Regex.Match(Doc, @"^## `hello` and the model commands\n(.*?)^## ", RegexOptions.Multiline | RegexOptions.Singleline);
        Assert.True(section.Success, "the doc's model commands section is missing");
        var listed = Regex.Matches(section.Groups[1].Value, @"^- (`[a-z_]+`(?:, `[a-z_]+`)*):", RegexOptions.Multiline)
            .SelectMany(m => Regex.Matches(m.Groups[1].Value, "`([a-z_]+)`").Select(x => x.Groups[1].Value)).ToList();
        Assert.Equal(["hello", "read_model", "check_site", "start_site"], listed);
        Assert.Equal(listed, Protocol.ModelCommands);
    }
}
