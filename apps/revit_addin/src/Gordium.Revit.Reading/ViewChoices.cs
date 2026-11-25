using System.Text;
using System.Text.Json;

namespace Gordium.Revit.Reading;

/// <summary>The results view each project was last shown in (UI polish change 17: "What to fix" or "By code",
/// remembered per project, Ben 2026-11-23), kept in one small file on this computer
/// (%LOCALAPPDATA%\Gordium\results_views.json) by the document's identity, so it holds across Revit sessions. A file
/// that can't be read or written is ignored (the default view is shown): a remembered view is a convenience, never a
/// result.</summary>
public sealed class ViewChoices
{
    private readonly string? _file;
    private readonly Dictionary<string, ResultsViewKind> _views = new(StringComparer.Ordinal);

    /// <summary>The choices kept in <paramref name="file"/> (null: this session only).</summary>
    public ViewChoices(string? file)
    {
        _file = file;
        if (file is null || !File.Exists(file))
            return;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
                return;
            foreach (var p in doc.RootElement.EnumerateObject())
                if (p.Value.ValueKind == JsonValueKind.String && Enum.TryParse<ResultsViewKind>(p.Value.GetString(), out var v)
                    && Enum.IsDefined(v))
                    _views[p.Name] = v;
        }
        catch (Exception x) when (x is IOException or UnauthorizedAccessException or JsonException)
        {
            _views.Clear();                                       // unreadable: every project starts on What to fix
        }
    }

    /// <summary>The view a project was last shown in, or What to fix (the default).</summary>
    public ResultsViewKind Of(string project) => _views.TryGetValue(project, out var v) ? v : ResultsViewKind.WhatToFix;

    /// <summary>Remembers a project's view, and writes the file (a failed write is ignored).</summary>
    public void Set(string project, ResultsViewKind view)
    {
        _views[project] = view;
        if (_file is null)
            return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_file)!);
            var json = JsonSerializer.Serialize(_views.OrderBy(p => p.Key, StringComparer.Ordinal)
                                                      .ToDictionary(p => p.Key, p => p.Value.ToString()));
            File.WriteAllText(_file, json, new UTF8Encoding(false));
        }
        catch (Exception x) when (x is IOException or UnauthorizedAccessException)
        {
            // kept for this session; the file is only a convenience
        }
    }

    /// <summary>Where the add-in keeps them.</summary>
    public static string DefaultFile =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gordium", "results_views.json");
}
