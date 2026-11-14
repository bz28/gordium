using System.Text.Json;
using Xunit;

namespace Gordium.Worker.Tests;

/// <summary>The strict reader refuses a key given twice in one object, on .NET 8 and .NET 10 alike (one code
/// path, no built-in .NET 10 switch), and accepts everything else a plain parse accepts.</summary>
public sealed class StrictJsonTests
{
    /// <summary>Each gives some key twice in one object.</summary>
    public static TheoryData<string> Duplicates => new()
    {
        """{"ok": false, "ok": true}""",
        """{"a": 1, "b": 2, "a": 1}""",                                   // same value: still refused
        """{"view": {"state": "needs_review", "state": "complies"}}""",    // nested
        """{"items": [{"status": "fails"}, {"status": "x", "status": "complies"}]}""",   // inside a list
        """[[{"k": 1, "k": 2}]]""",
        """{"a": 1, "\u0061": 2}""",                                       // the same key, one written as an escape
        """{"\u00e9": 1, "é": 2}""",
        """{"a\/b": 1, "a/b": 2}""",
        """{"\ud83d\ude00": 1, "😀": 2}""",                               // an emoji, once as its escape pair
        """{"": 1, "": 2}""",
        """{"x": {"y": {"z": {"w": 1, "w": 1}}}}""",
    };

    /// <summary>Each is good JSON with no key twice in one object.</summary>
    public static TheoryData<string> Distinct => new()
    {
        """{"a": 1, "A": 2}""",                                            // keys differ by case: two keys
        """{"a": {"a": {"a": 1}}}""",                                      // the same key at different depths
        """{"items": [{"status": "x"}, {"status": "y"}]}""",               // the same key in sibling objects
        """{"a": 1, "b": {"c": 2}, "c": 3}""",                             // a key closed in an inner object
        """[{"k": 1}, [{"k": 2}], {"k": 3}]""",
        """{"é": 1, "e\u0301": 2}""",                                      // looks alike, different text
        """{}""",
        """[]""",
        """5""",
        "\"text\"",
    };

    [Theory]
    [MemberData(nameof(Duplicates))]
    public void A_key_given_twice_is_refused(string json)
    {
        var e = Assert.ThrowsAny<JsonException>(() => StrictJson.Parse(json));
        Assert.Contains("is given twice in one object", e.Message);    // refused by the duplicate check itself
    }

    [Theory]
    [MemberData(nameof(Distinct))]
    public void Keys_that_differ_are_read(string json) => StrictJson.Parse(json);

    /// <summary>A key or text value whose escapes aren't text (half of a surrogate pair) is refused as JSON that
    /// can't be trusted, so no later read of it can fail. .NET 10's built-in check threw an
    /// InvalidOperationException on such a key (not a JsonException, so not read as "the answer isn't JSON"),
    /// and let such a value through to fail later, when read.</summary>
    [Theory]
    [InlineData("""{"\ud800": 1}""", "a key isn't valid text")]
    [InlineData("""{"\udc00": 1}""", "a key isn't valid text")]
    [InlineData("""{"a\ud800": 1, "b": 2}""", "a key isn't valid text")]
    [InlineData("""{"ok": true, "x": {"\ud800": 1}}""", "a key isn't valid text")]
    [InlineData("""{"error": "\ud800"}""", "a text value isn't valid text")]
    [InlineData("""{"items": [{"status": "compl\udc00ies"}]}""", "a text value isn't valid text")]
    [InlineData("""["\ud83d"]""", "a text value isn't valid text")]
    public void An_escape_that_isnt_text_is_refused(string json, string words)
    {
        var e = Assert.ThrowsAny<JsonException>(() => StrictJson.Parse(json));
        Assert.Contains(words, e.Message);
    }

    /// <summary>A line holding half a surrogate pair itself (not as an escape) is refused as JSON, never passed
    /// on with the half replaced. A Fact, not a Theory: xUnit would replace the half while passing the case in.</summary>
    [Fact]
    public void A_line_that_isnt_whole_text_is_refused()
    {
        foreach (var line in new[] { "{\"\uD800\": 1}", "{\"error\": \"\uDC00\"}", "[\"a\uD83D\"]" })
        {
            Assert.Contains(line, c => char.IsSurrogate(c));   // the case really holds the half
            var e = Assert.ThrowsAny<JsonException>(() => StrictJson.Parse(line));
            Assert.Contains("the answer isn't whole text", e.Message);
        }
    }

    [Fact]
    public void A_good_escape_pair_is_read() =>
        Assert.Equal("\U0001F600", StrictJson.Parse("""{"a": "\ud83d\ude00"}""").GetProperty("a").GetString());

    [Theory]
    [InlineData("""{"a": NaN}""")]
    [InlineData("""{"a": 1} // note""")]
    [InlineData("""{"a": 1,}""")]
    [InlineData("""{"a": 1} {"a": 2}""")]                                   // two answers on one line
    [InlineData("""{"a": 1""")]
    [InlineData("")]
    [InlineData("\uFEFF{\"a\": 1}")]                                       // a byte-order mark first
    public void Not_strict_json_is_refused(string json) => Assert.ThrowsAny<JsonException>(() => StrictJson.Parse(json));

    [Fact]
    public void Nesting_past_the_limit_is_refused()
    {
        var deep = new string('[', 257) + new string(']', 257);
        Assert.ThrowsAny<JsonException>(() => StrictJson.Parse(deep));
        StrictJson.Parse(new string('[', 256) + new string(']', 256));
    }

#if NET10_0_OR_GREATER
    /// <summary>On .NET 10 the built-in duplicate check (the one this replaces) says the same as ours for every
    /// case: never weaker, never stricter.</summary>
    [Theory]
    [MemberData(nameof(Duplicates))]
    [MemberData(nameof(Distinct))]
    public void Agrees_with_the_built_in_dotnet10_check(string json)
    {
        bool builtIn;
        try
        {
            using var _ = JsonDocument.Parse(json, new JsonDocumentOptions { AllowDuplicateProperties = false, MaxDepth = 256 });
            builtIn = true;
        }
        catch (JsonException)
        {
            builtIn = false;
        }
        bool ours;
        try
        {
            StrictJson.Parse(json);
            ours = true;
        }
        catch (JsonException)
        {
            ours = false;
        }
        Assert.Equal(builtIn, ours);
    }
#endif
}
