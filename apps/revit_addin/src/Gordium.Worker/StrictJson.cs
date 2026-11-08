using System.Text.Json;

namespace Gordium.Worker;

/// <summary>Reading the worker's answers strictly: a field missing or of the wrong kind is an error, never a
/// default (a missing status must never read as a pass).</summary>
internal static class StrictJson
{
    /// <summary>Duplicate keys refused (a reader would otherwise keep one of the two unseen), NaN and comments
    /// refused (System.Text.Json's defaults).</summary>
    internal static readonly JsonDocumentOptions Options = new()
    {
        AllowDuplicateProperties = false,
        MaxDepth = 256,
    };

    internal static JsonElement Parse(string line)
    {
        using var doc = JsonDocument.Parse(line, Options);
        return doc.RootElement.Clone();
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
