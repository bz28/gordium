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
    private static IReadOnlyList<string>? _noticeFor;     // the facts needed when the notice was made (SetupNotice)
    private static SetupScreen? _shown;
    private static bool _reading;
    private static readonly SetupDraft Draft = new();
    private static readonly HashSet<string> Open = new(StringComparer.Ordinal);

    /// <summary>What the architect chose "Check now anyway" for, per project, this session: the form isn't shown
    /// again for the same facts missing (a fact newly missing shows it again).</summary>
    private static readonly Dictionary<string, HashSet<string>> Anyway = new(StringComparer.Ordinal);

    private static string Key(Document doc) => DocKeys.Of(doc);       // identity, never a title or path (a Save As changes them)

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
        _sides = RevitMarks.Sides(doc);                      // read again each time: a window added since has its rooms
        _lastCode = ResultsPane.LastCode(doc);
        var kept = Marks.Text(SetupFacts.Value(_model, Marks.StreetEdge));
        _streetWords = EdgeWords.OfMark(kept, RevitRead.LotLines(doc), RevitRead.InternalToShared(doc), doc.Application.VertexTolerance);
        // a kept edge (text Gordium wrote) no property line has any more: the form waits for a new pick, as the check would
        _streetOnLot = kept is not null && StreetEdges.Parse(kept) is not null ? _streetWords is not null : null;
        return Screen();
    }

    private static string? _lastCode;
    private static string? _streetWords;
    private static bool? _streetOnLot;

    private static SetupScreen Screen() => SetupScreen.Build(_model!, _sides, _options, Draft, _lastCode, _streetWords, _streetOnLot);

    /// <summary>Check project's gate (Revit's thread, during the check's read): the form's screen, and what to do
    /// (SetupGate.Decide: show the form, send anyway for what was already checked anyway, or send).</summary>
    internal static (SetupScreen Screen, SetupStep Step) Needs(Document doc)
    {
        var screen = Read(doc);
        return (screen, SetupGate.Decide(screen.Needed, Anyway.TryGetValue(Key(doc), out var a) ? a : null));
    }

    /// <summary>Shows the form (Revit's thread): the screen given (Check project's) or read now (Mark facts, the
    /// results' Set up button); <paramref name="notice"/> says why it shows (a check that couldn't be sent).</summary>
    internal static void Show(UIApplication ui, Document doc, SetupScreen? screen = null, string? notice = null)
    {
        screen ??= Read(doc);
        _noticeFor = screen.Needed;                         // a new notice (or none): made for the facts missing now
        ShowKept(ui, doc, screen, notice);
    }

    /// <summary>Shows the form with the notice it had, while the facts it names are still the ones needed
    /// (SetupNotice.Keep: after a Save or an edit that set one, it goes).</summary>
    private static void ShowKept(UIApplication ui, Document doc, SetupScreen screen, string? notice)
    {
        _notice = SetupNotice.Keep(notice, _noticeFor, screen);
        notice = _notice;
        _shown = screen;
        AskOptions();
        ResultsPane.ShowSetup(ui, doc, screen, Draft, Handlers, notice, Open);
    }

    /// <summary>The form drawn again from what is kept (the panel's thread, no Revit call): after a choice, or when the
    /// options arrive.</summary>
    private static void Redraw()
    {
        if (_model is null || _doc is null || !_doc.IsValidObject)
            return;
        _shown = Screen();
        _notice = SetupNotice.Keep(_notice, _noticeFor, _shown);   // only while the facts it names are still needed
        ResultsPane.RedrawSetup(_shown, Draft, Handlers, _notice, Open);
    }

    /// <summary>The project shown in the form changed (Revit's DocumentChanged: a value set in Properties after Select
    /// them, an undo): its marks read again through the panel's ExternalEvent, once however many changes came, and the
    /// check run by itself when that set the last fact needed.</summary>
    internal static void Changed(Document doc)
    {
        if (_doc is null || !_doc.Equals(doc) || _shown is null || !ResultsPane.ShowsSetup() || _reading)
            return;
        _reading = true;
        ResultsPane.Post("Read the facts again", ui =>
        {
            _reading = false;
            if (_doc is { IsValidObject: true } d && ResultsPane.ShowsSetup())
                Refreshed(ui, d, "");
        }, refused: () => _reading = false);
    }

    /// <summary>The place's districts and uses before Check project's gate decides (Revit's thread: the worker being
    /// started is waited for, at most <see cref="OptionsWait"/>), so the gate checks a stated zone or use against them
    /// whether or not the form was opened before. A worker that can't answer is logged; the check then goes on and its
    /// own answer says what is wrong (an unknown zone is refused by the checker, an unknown use needs review).</summary>
    internal static void Options(Task<WorkerClient> worker, Dictionary<string, object?> log)
    {
        if (_options is not null)
            return;
        try
        {
            var asked = Task.Run(async () => await (await worker.ConfigureAwait(false)).OptionsAsync(ProjectFacts.Jurisdiction).ConfigureAwait(false));
            if (asked.Wait(OptionsWait))
                _options = asked.Result;
            else
                log["setup_options"] = $"not known after {OptionsWait.TotalSeconds:0} s: the zone and use are checked by the checker";
        }
        catch (AggregateException e)
        {
            log["setup_options"] = $"{e.GetBaseException().GetType().Name}: {e.GetBaseException().Message}";
        }
    }

    /// <summary>How long Check project waits for the place's options (the worker's start included).</summary>
    private static readonly TimeSpan OptionsWait = TimeSpan.FromSeconds(30);

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
        // a box typed in: the draft only (no redraw while typing); emptied, nothing chosen
        Type: (mark, value) =>
        {
            if (value.Trim().Length == 0)
                Draft.Forget(mark);
            else
                Draft.Choose(mark, value);
        },
        // Save and check: the facts chosen written (one undo), then the check, whatever is still unset (each makes its
        // rules need review, never a pass: UI polish change 7)
        Save: () => Write("Save the project facts", SetupWrites.FactsTransaction, () =>
        {
            var (writes, problems) = Draft.Writes(Screen().Fields);
            foreach (var w in writes)
                Draft.Forget(w.Mark);
            if (writes.Any(w => w.Mark == Marks.StreetEdge))
                Draft.PickedWords = null;
            return (writes, problems);
        }, checkAfter: true),
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
        ProjectInformation: ResultsPane.OpenProjectInformation,
        Redraw: Redraw);

    /// <summary>One write (Revit's thread): the writes made from what is chosen now, in one transaction; then the
    /// form read again, and the check run by itself when nothing needed is left.</summary>
    private static void Write(string what, string transaction, Func<(IReadOnlyList<MarkWrite> Writes, IReadOnlyList<string> Problems)> make,
                              bool checkAfter = false) =>
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
            var said = string.Join(" ", problems.Concat(refused.Select(r => "Not written: " + r))
                .Prepend(status == "Committed" ? $"Saved {applied.Count} (Ctrl+Z undoes it)." : applied.Count == 0 && writes.Count > 0 ? "Nothing was written." : "")
                .Where(s => s.Length > 0));
            // Save and check: checks once every write went in (a write refused or a choice not taken: the form stays,
            // saying why, and nothing is checked on facts the architect didn't get)
            if (checkAfter && problems.Count == 0 && refused.Count == 0 && status is "Committed" or "Nothing")
            {
                var screen = Read(doc);
                _shown = null;
                ResultsPane.Say(said);
                if (!screen.Ready)
                    Anyway[Key(doc)] = [.. screen.Needed];
                if (CheckRun.Start(ui, doc, anyway: !screen.Ready) is { } refusedCheck)
                    ResultsPane.Say(refusedCheck);
                return;
            }
            Refreshed(ui, doc, said);
        });

    /// <summary>After a write or a pick: the form read again; the check runs by itself when nothing needed is left.</summary>
    private static void Refreshed(UIApplication ui, Document doc, string said)
    {
        var before = _shown;
        var screen = Read(doc);
        if (before is not null && SetupGate.RunsByItself(before, screen))
        {
            _shown = null;
            ResultsPane.Say(said);
            // the form's own project, never whichever is active now
            if (CheckRun.Start(ui, doc) is { } refused)
                ResultsPane.Say(refused);
            return;
        }
        ShowKept(ui, doc, screen, _notice);                 // the notice only while it still holds
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

    /// <summary>The street edge picked on the plan: Revit's pick (its words and confirmation, on Revit's thread), in a
    /// view that shows the property line, kept in the form as "not saved yet": nothing is written until Save, which
    /// writes it with the other facts in the one "Gordium: project facts" transaction.</summary>
    private static void PickStreet() => ResultsPane.Post("Pick the street edge", ui =>
    {
        if (_doc is not { IsValidObject: true } doc || ui.ActiveUIDocument is not { } uidoc || !uidoc.Document.Equals(doc))
        {
            ResultsPane.Say(StreetEdges.SwitchToItFromSetup);   // pressed in the form: the next step is that button
            return;
        }
        if (!RevitRead.LotLines(doc).Any(l => l.IsPropertyLine))
        {
            ResultsPane.Say(StreetEdges.NoPropertyLineFromSetup);
            return;
        }
        if (!CheckProjectCommand.ShowsPropertyLine(uidoc))
        {
            ResultsPane.Say(StreetEdges.OpenAPlanFromSetup);     // pressed in the form: the next step is that button
            return;
        }
        var log = new Dictionary<string, object?> { ["document"] = doc.Title };
        var kept = CheckProjectCommand.PickEdges(uidoc, log);
        var text = Draft.Pick(kept);
        if (text is not null)
            Draft.PickedWords = CheckProjectCommand.EdgesInWords(doc, kept);
        log["street_edge_chosen"] = text;
        Trial.Log("setup", log);
        Redraw();
        ResultsPane.Say(text is null ? StreetEdges.NonePickedFromSetup
            : $"Street edge picked: {Draft.PickedWords ?? "kept"}. Save writes it with the other facts.");
    });
}
