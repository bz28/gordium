using Autodesk.Revit.DB;

namespace Gordium.Revit.Addin;

/// <summary>
/// A key for each open document by its identity, never its name (review round 2 of UI changes 13 to 15): a title or
/// path changes on Save As (a new "Project1"'s first save too), so a check, a Setup draft or the ticks kept by name
/// would stop matching their own document. Each Document gets "doc:N" the first time it is asked for, found again by
/// Document.Equals (as ResultsPane matches the project checked); a document closed and opened again is a new one and
/// gets a new key, so whatever was kept for the old one is never taken as current (fail closed). Revit's thread only.
/// </summary>
internal static class DocKeys
{
    private static readonly List<(Document Doc, string Key)> Known = [];
    private static int _next;

    /// <summary>The key of <paramref name="doc"/> for this session.</summary>
    internal static string Of(Document doc)
    {
        ArgumentNullException.ThrowIfNull(doc);
        Known.RemoveAll(k => !k.Doc.IsValidObject);              // closed documents: their keys are never given again
        foreach (var (d, key) in Known)
            if (d.Equals(doc))
                return key;
        var made = $"doc:{++_next}";
        Known.Add((doc, made));
        return made;
    }
}
