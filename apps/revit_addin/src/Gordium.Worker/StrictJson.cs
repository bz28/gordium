using System.Text;
using System.Text.Json;

namespace Gordium.Worker;

/// <summary>Reading the worker's answers strictly: a field missing or of the wrong kind is an error, never a
/// default (a missing status must never read as a pass).</summary>
internal static class StrictJson
{
    /// <summary>NaN, comments and trailing commas refused (System.Text.Json's defaults). Duplicate keys and
    /// escapes that aren't text are refused by <see cref="RefuseDuplicateKeys"/> before the parse: it runs the same
    /// on .NET 8 and .NET 10 (the .NET 10-only <c>AllowDuplicateProperties = false</c> would leave .NET 8 without the
    /// check). Private, so no caller parses with these options alone and skips that check.</summary>
    private static readonly JsonDocumentOptions Options = new() { MaxDepth = 256 };

    private static readonly JsonReaderOptions ReaderOptions = new()
    {
        MaxDepth = Options.MaxDepth,
        CommentHandling = JsonCommentHandling.Disallow,
        AllowTrailingCommas = false,
    };

    /// <summary>Text that isn't whole (half of a surrogate pair) is an error here, never replaced.</summary>
    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    /// <summary>Reads one answer line. Anything refused is a JsonException: not JSON, a key given twice in one
    /// object, an escape that isn't text, or the line itself not being whole text.</summary>
    internal static JsonElement Parse(string line)
    {
        byte[] utf8;
        try
        {
            utf8 = Utf8.GetBytes(line);
        }
        catch (ArgumentException e)   // EncoderFallbackException: a lone half of a surrogate pair
        {
            throw new JsonException("the answer isn't whole text", e);
        }
        RefuseDuplicateKeys(utf8);
        // the same bytes the check read, so the two can't see different text
        using var doc = JsonDocument.Parse(utf8, Options);
        return doc.RootElement.Clone();
    }

    /// <summary>Refuses an object that gives the same key twice, at any depth: a reader would otherwise keep one
    /// of the two unseen (a "status" of needs_review followed by "complies" would read as complies). Keys are
    /// compared after their escapes are read (<c>"a"</c> and <c>"\u0061"</c> are the same key), exactly, case
    /// and all. A key or text value whose escapes aren't text (<c>"\ud800"</c>) is refused too, so no later read
    /// of it can fail. Not JSON at all is a JsonException, as from the parse.</summary>
    private static void RefuseDuplicateKeys(byte[] utf8)
    {
        var reader = new Utf8JsonReader(utf8, ReaderOptions);
        var open = new Stack<HashSet<string>?>();   // one set of keys per open object; null for an open list
        while (reader.Read())
        {
            switch (reader.TokenType)
            {
                case JsonTokenType.StartObject:
                    open.Push(new HashSet<string>(StringComparer.Ordinal));
                    break;
                case JsonTokenType.StartArray:
                    open.Push(null);
                    break;
                case JsonTokenType.EndObject:
                case JsonTokenType.EndArray:
                    open.Pop();
                    break;
                case JsonTokenType.PropertyName:
                    var name = Text(ref reader, "a key");
                    if (!open.Peek()!.Add(name))
                        throw new JsonException($"the key \"{name}\" is given twice in one object");
                    break;
                case JsonTokenType.String:
                    Text(ref reader, "a text value");
                    break;
            }
        }
    }

    private static string Text(ref Utf8JsonReader reader, string what)
    {
        try
        {
            return reader.GetString()!;
        }
        catch (InvalidOperationException e)
        {
            throw new JsonException($"{what} isn't valid text", e);
        }
    }

    internal static JsonElement Field(JsonElement obj, string name, string where)
    {
        if (obj.ValueKind != JsonValueKind.Object)
            throw new WorkerProtocolException($"{where} is {Kind(obj)}, not an object");
        if (!obj.TryGetProperty(name, out var value))
            throw new WorkerProtocolException($"{where} has no \"{name}\"");
        return value;
    }

    internal static JsonElement Object(JsonElement obj, string name, string where)
    {
        var value = Field(obj, name, where);
        if (value.ValueKind != JsonValueKind.Object)
            throw new WorkerProtocolException($"{where}.{name} is {Kind(value)}, not an object");
        return value;
    }

    internal static string String(JsonElement obj, string name, string where, bool nonEmpty = false)
    {
        var value = Field(obj, name, where);
        if (value.ValueKind != JsonValueKind.String)
            throw new WorkerProtocolException($"{where}.{name} is {Kind(value)}, not text");
        var text = value.GetString()!;
        if (nonEmpty && text.Length == 0)
            throw new WorkerProtocolException($"{where}.{name} is empty");
        return text;
    }

    /// <summary>A field that must be there, as text or null.</summary>
    internal static string? StringOrNull(JsonElement obj, string name, string where)
    {
        var value = Field(obj, name, where);
        return value.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.String => value.GetString(),
            _ => throw new WorkerProtocolException($"{where}.{name} is {Kind(value)}, not text or null"),
        };
    }

    internal static string Kind(JsonElement e) => e.ValueKind switch
    {
        JsonValueKind.Object => "an object",
        JsonValueKind.Array => "a list",
        JsonValueKind.String => "text",
        JsonValueKind.Number => "a number",
        JsonValueKind.True or JsonValueKind.False => "true or false",
        JsonValueKind.Null => "null",
        _ => "nothing",
    };
}
