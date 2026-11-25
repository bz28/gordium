using System.Text;
using System.Text.RegularExpressions;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The ribbon's renames (UI polish change 48: "Mark facts" became "Set up", "Panel" became "Results", and the
/// results window is "the Gordium pane") reach every word the add-in shows, not only the ribbon (review round 5: four
/// messages still sent the architect to a "Mark facts" button that no longer exists). Every string literal in the
/// add-in's code is read, comments left out and pieces joined with + read as one, so a name split across two lines is
/// caught too.</summary>
public sealed class RibbonNamesTests
{
    /// <summary>The names the ribbon no longer has: a sentence naming one points at nothing.</summary>
    private static readonly Regex Retired = new(@"\bmark\s+facts\b|\bpanel\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    [Fact]
    public void No_message_names_a_button_the_ribbon_no_longer_has()
    {
        var buttons = RibbonPlan.Buttons(trial: true).Select(b => b.Name).ToList();
        Assert.Contains("Set up", buttons);
        Assert.DoesNotContain(buttons, b => Retired.IsMatch(b));
        var src = Path.Combine(Env.Repo, "apps", "revit_addin", "src");
        var found = new List<string>();
        foreach (var file in Directory.EnumerateFiles(src, "*.cs", SearchOption.AllDirectories)
                     .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}", StringComparison.Ordinal)
                                 && !f.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}", StringComparison.Ordinal)))
            foreach (var words in Literals(File.ReadAllText(file, Encoding.UTF8)))
                // a literal with a space is words someone reads; one without is an id or a log key ("results_panel")
                if (words.Contains(' ', StringComparison.Ordinal) && Retired.IsMatch(words))
                    found.Add($"{Path.GetFileName(file)}: {words}");
        Assert.True(found.Count == 0, "messages naming a retired ribbon name:\n" + string.Join("\n", found));
    }

    /// <summary>The scanner finds a name split across pieces, ignores comments and ids, and reads every literal
    /// form the add-in uses (the pin's own pin: a scanner that read nothing would pass anything).</summary>
    [Fact]
    public void The_scanner_reads_every_literal_form_and_skips_comments()
    {
        const string code = "// click Mark facts\n/* the panel */ var a = \"click Cancel in the Gordium \" +\n  \"panel, then\";\n" +
                            "var b = $\"{(x ? \"one\" : \"two\")} Mark facts {{y}}\"; var c = '\"'; var d = @\"a \"\"q\"\" b\";\n" +
                            "var e = \"\"\"\n raw \"quoted\" text\n \"\"\"; var f = \"results_panel\";";
        Assert.Equal(["click Cancel in the Gordium panel, then", "one", "two", "{} Mark facts {{y}}", "a \"q\" b",
                      "\n raw \"quoted\" text\n ", "results_panel"], Literals(code));
    }

    /// <summary>Every string literal's text, in order; literals joined only by + read as one. An interpolated
    /// string's holes are left as "{}" and the literals inside them come first.</summary>
    internal static List<string> Literals(string code)
    {
        var all = new List<string>();
        var current = new StringBuilder();
        var open = false;   // a literal was read and only whitespace or + has followed since
        var i = 0;
        void Add(string s)
        {
            if (open) current.Append(s);
            else { current.Clear().Append(s); open = true; }
        }
        void Close()
        {
            if (open) all.Add(current.ToString());
            open = false;
        }
        while (i < code.Length)
        {
            var c = code[i];
            if (c == '/' && i + 1 < code.Length && code[i + 1] == '/')
            {
                while (i < code.Length && code[i] != '\n') i++;
            }
            else if (c == '/' && i + 1 < code.Length && code[i + 1] == '*')
            {
                var end = code.IndexOf("*/", i + 2, StringComparison.Ordinal);
                i = end < 0 ? code.Length : end + 2;
            }
            else if (c == '\'')
            {
                Close();
                i++;
                if (i < code.Length && code[i] == '\\') i++;
                i += 2;   // the character and the closing quote
            }
            else if (c == '"' || (c is '$' or '@' && Starts(code, i)))
            {
                var interpolated = false;
                var verbatim = false;
                while (code[i] is '$' or '@')
                {
                    interpolated |= code[i] == '$';
                    verbatim |= code[i] == '@';
                    i++;
                }
                var (text, next, inner) = Read(code, i, interpolated, verbatim);
                if (inner.Count > 0)
                {
                    Close();
                    all.AddRange(inner);
                }
                Add(text);
                i = next;
            }
            else
            {
                if (!char.IsWhiteSpace(c) && c != '+') Close();
                i++;
            }
        }
        Close();
        return all;
    }

    private static bool Starts(string code, int i)
    {
        while (i < code.Length && code[i] is '$' or '@') i++;
        return i < code.Length && code[i] == '"';
    }

    /// <summary>One literal starting at its first quote: its text, the index after it, and the literals inside its
    /// holes.</summary>
    private static (string Text, int Next, List<string> Inner) Read(string code, int i, bool interpolated, bool verbatim)
    {
        var inner = new List<string>();
        var text = new StringBuilder();
        if (code.AsSpan(i).StartsWith("\"\"\""))
        {
            var end = code.IndexOf("\"\"\"", i + 3, StringComparison.Ordinal);
            return (code[(i + 3)..end], end + 3, inner);
        }
        i++;
        while (i < code.Length)
        {
            var c = code[i];
            if (c == '"')
            {
                if (verbatim && i + 1 < code.Length && code[i + 1] == '"') { text.Append('"'); i += 2; continue; }
                return (text.ToString(), i + 1, inner);
            }
            if (c == '\\' && !verbatim) { text.Append(code[i + 1] == 'n' ? '\n' : code[i + 1]); i += 2; continue; }
            if (interpolated && c == '{')
            {
                if (i + 1 < code.Length && code[i + 1] == '{') { text.Append("{{"); i += 2; continue; }
                // a hole: code up to its closing brace, with literals of its own
                var depth = 1;
                var start = ++i;
                while (depth > 0)
                {
                    if (code[i] == '"' || code[i] is '$' or '@' && Starts(code, i))
                    {
                        var interp = false;
                        var verb = false;
                        while (code[i] is '$' or '@') { interp |= code[i] == '$'; verb |= code[i] == '@'; i++; }
                        var (t, n, more) = Read(code, i, interp, verb);
                        inner.AddRange(more);
                        inner.Add(t);
                        i = n;
                        continue;
                    }
                    if (code[i] == '{') depth++;
                    else if (code[i] == '}') depth--;
                    i++;
                }
                text.Append("{}");
                continue;
            }
            if (interpolated && c == '}' && i + 1 < code.Length && code[i + 1] == '}') { text.Append("}}"); i += 2; continue; }
            text.Append(c);
            i++;
        }
        return (text.ToString(), i, inner);
    }
}
