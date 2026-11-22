using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Setup form's flow (docs/decisions/2026-11-22_setup_form.md): shown by Check project when a fact the check needs
/// is missing (and by Mark facts), it keeps the project's marks as last read, the architect's choices not saved
/// (<see cref="SetupDraft"/>), the openings' sides and the place's options. Every decision is Gordium.Revit.Reading's
/// (<see cref="SetupScreen"/>, <see cref="SetupGate"/>); every Revit call here runs on Revit's thread through the
/// panel's one ExternalEvent (<see cref="ResultsPane.Post"/>), and every write is one transaction named for Gordium
/// (<see cref="SetupWrites"/>), so one Ctrl+Z takes a Save or an accept back and results shown go stale after it.
/// </summary>
internal static class SetupRun
{
    private static Document? _doc;
    private static RevitModel? _model;
    private static List<OpeningSides>? _sides;
    private static PlaceOptions? _options;
    private static Task? _asking;
    private static string? _notice;
    private static readonly SetupDraft Draft = new();
    private static readonly HashSet<string> Open = new(StringComparer.Ordinal);

    /// <summary>What the architect chose "Check now anyway" for, per project, this session: the form isn't shown
    /// again for the same facts missing (a fact newly missing shows it again).</summary>
    private static readonly Dictionary<string, HashSet<string>> Anyway = new(StringComparer.Ordinal);

    private static string Key(Document doc) => doc.PathName is { Length: > 0 } p ? p : doc.Title;

    /// <summary>The form's screen for <paramref name="doc"/>, read now (Revit's thread): its marks, and the openings'
    /// sides once per project shown.</summary>
    private static SetupScreen Read(Document doc)
    {
        if (_doc is null || !_doc.Equals(doc))
        {
            _doc = doc;
            _sides = null;
            Draft.Clear();
            Open.Clear();
        }
        _model = RevitMarks.Model(doc);
        _sides ??= RevitMarks.Sides(doc);
        return Screen();
    }

    private static SetupScreen Screen() => SetupScreen.Build(_model!, _sides, _options, Draft);

    /// <summary>Check project's gate (Revit's thread, during the check's read): the screen when the form must show
    /// (something needed missing, not already checked anyway for), else null and the check goes on.</summary>
    internal static SetupScreen? Needs(Document doc)
    {
        var screen = Read(doc);
        return SetupGate.ShowSetup(screen.Needed, Anyway.TryGetValue(Key(doc), out var a) ? a : null) ? screen : null;
    }

    /// <summary>Shows the form (Revit's thread): the screen given (Check project's) or read now (Mark facts, the
    /// results' Set up button); <paramref name="notice"/> says why it shows (a check that couldn't be sent).</summary>
    internal static void Show(UIApplication ui, Document doc, SetupScreen? screen = null, string? notice = null)
    {
        screen ??= Read(doc);
        _notice = notice;
        AskOptions();
        ResultsPane.ShowSetup(ui, doc, screen, Draft, Handlers, notice, Open);
    }

    /// <summary>The form drawn again from what is kept (the panel's thread, no Revit call): after a choice, or when the
    /// options arrive.</summary>
    private static void Redraw()
    {
        if (_model is null || _doc is null || !_doc.IsValidObject)
            return;
        ResultsPane.RedrawSetup(Screen(), Draft, Handlers, _notice, Open);
    }

    /// <summary>The place's districts and uses, asked of the worker once (off Revit's thread); until they come the
    /// zone and use are typed fields. A worker that can't answer leaves them typed, and says so in the log.</summary>
    private static void AskOptions()
    {
        if (_options is not null || _asking is { IsCompleted: false })
            return;
        _asking = Task.Run(async () =>
        {
            try
            {
                var worker = await Trial.WorkerAsync().ConfigureAwait(false);
                var options = await worker.OptionsAsync(ProjectFacts.Jurisdiction).ConfigureAwait(false);
                ResultsPane.Ui(() =>
                {
                    _options = options;
                    Redraw();
                });
            }
            catch (Exception e)
            {
                Trial.Log("setup", new Dictionary<string, object?> { ["options"] = $"{e.GetType().Name}: {e.Message}" });
            }
        });
    }

    private static readonly SetupHandlers Handlers = new(
        Choose: (mark, value) =>
        {
            Draft.Choose(mark, value);
            Redraw();
        },
        Save: () => Write("Save the project facts", SetupWrites.FactsTransaction, () =>
        {
            var (writes, problems) = Draft.Writes(Screen().Fields);
            foreach (var w in writes)
                Draft.Forget(w.Mark);
            return (writes, problems);
        }),
        Discard: () =>
        {
            Draft.Clear();
            Redraw();
        },
        Accept: accepted => Write("Accept suggestions", SetupWrites.SuggestionsTransaction,
                                  () => (SetupWrites.Accept(accepted), [])),
        Select: Select,
        PickStreet: PickStreet,
        Anyway: () => ResultsPane.Post("Check now anyway", ui =>
        {
            if (_doc is not { IsValidObject: true } doc)
                return;
            Anyway[Key(doc)] = [.. Screen().Needed];
            if (CheckRun.Start(ui, doc, anyway: true) is { } refused)
                ResultsPane.Say(refused);
        }),
        ProjectInformation: ResultsPane.OpenProjectInformation);

    /// <summary>One write (Revit's thread): the writes made from what is chosen now, in one transaction; then the
    /// form read again, and the check run by itself when nothing needed is left.</summary>
    private static void Write(string what, string transaction, Func<(IReadOnlyList<MarkWrite> Writes, IReadOnlyList<string> Problems)> make) =>
        ResultsPane.Post(what, ui =>
        {
            if (_doc is not { IsValidObject: true } doc)
            {
                ResultsPane.Say("The project is closed: open it and click Check project.");
                return;
            }
            var (writes, problems) = make();
            var (applied, refused, status) = RevitMarks.Write(doc, transaction, writes);
            Trial.Log("setup", new Dictionary<string, object?>
            {
                ["document"] = doc.Title, ["transaction"] = transaction, ["status"] = status,
                ["applied"] = applied, ["refused"] = refused, ["problems"] = problems,
            });
            Refreshed(ui, doc, string.Join(" ", problems.Concat(refused.Select(r => "Not written: " + r))
                .Prepend(status == "Committed" ? $"Saved {applied.Count} (Ctrl+Z undoes it)." : applied.Count == 0 && writes.Count > 0 ? "Nothing was written." : "")
                .Where(s => s.Length > 0)));
        });

    /// <summary>After a write or a pick: the form read again; the check runs by itself when nothing needed is left.</summary>
    private static void Refreshed(UIApplication ui, Document doc, string said)
    {
        var screen = Read(doc);
        if (SetupGate.RunsByItself(screen))
        {
            ResultsPane.Say(said);
            CheckProjectCommand.Check(ui);
            return;
        }
        Show(ui, doc, screen, _notice);
        ResultsPane.Say(said);
    }

    /// <summary>Selects the elements in Revit (no zoom) and brings Properties up, so the architect sets them together.</summary>
    private static void Select(IReadOnlyList<string> uids) => ResultsPane.Post("Select them", ui =>
    {
        if (_doc is not { IsValidObject: true } doc || ui.ActiveUIDocument is not { } uidoc || !uidoc.Document.Equals(doc))
        {
            ResultsPane.Say("Switch to the project being set up to select its elements.");
            return;
        }
        var ids = uids.Select(u => doc.GetElement(u)?.Id).OfType<ElementId>().ToList();
        uidoc.Selection.SetElementIds(ids);
        try
        {
            ui.GetDockablePane(DockablePanes.BuiltInDockablePanes.PropertiesPalette).Show();
        }
        catch (Autodesk.Revit.Exceptions.ApplicationException) { }       // Properties can't be shown: the selection stands
        ResultsPane.Say($"Selected {ids.Count}: set them together in Properties (a type's mark: Edit Type).");
    });

    /// <summary>The street edge picked on the plan: the check's own pick (its words and confirmation), in a view that
    /// shows the property line; then the form read again.</summary>
    private static void PickStreet() => ResultsPane.Post("Pick the street edge", ui =>
    {
        if (_doc is not { IsValidObject: true } doc || ui.ActiveUIDocument is not { } uidoc || !uidoc.Document.Equals(doc))
        {
            ResultsPane.Say(StreetEdges.SwitchToIt);
            return;
        }
        if (!CheckProjectCommand.ShowsPropertyLine(uidoc))
        {
            ResultsPane.Say(StreetEdges.OpenAPlan);
            return;
        }
        var log = new Dictionary<string, object?> { ["document"] = doc.Title };
        var kept = CheckProjectCommand.PickStreet(uidoc, log);
        Trial.Log("setup", log);
        Refreshed(ui, doc, kept ? "Street edge kept." : "No street edge was kept.");
    });
}
