using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Selection;
using Gordium.Revit.Reading;
using Gordium.Worker;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;
using RevitApplication = Autodesk.Revit.ApplicationServices.Application;

namespace Gordium.Revit.Addin;

/// <summary>
/// "Check my project" (docs/revit/revit_reading_design.md, section 9): the open project read outside
/// (<see cref="RevitRead"/>, then SiteReader) and inside (<see cref="RevitInterior"/>, then InteriorReader), with the
/// lot facts from Gordium's marks on Project Information, sent as one check_site, and shown in the results panel
/// (<see cref="ResultsPane"/>, rows from ResultRows): the worker's state and counts, the phase and design options
/// checked, the groups in the worker's order with every row; every row also in check_project_result.txt (ResultText).
/// Its first run adds the marks (as Mark for egress does); a street edge not set is asked for by a pick; any other
/// fact missing and nothing is sent: the panel lists what to fill in. The request and the answer go to the log.
/// </summary>
[Transaction(TransactionMode.Manual)]
public sealed class CheckProjectCommand : IExternalCommand
{
    private const string Title = "Gordium: check my project";

    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var (result, why) = Check(commandData.Application);
        if (why is not null)
            message = why;
        return result;
    }

    /// <summary>The button's check of the active project, shown in the results panel: the button's and the panel's
    /// Check again (on Revit's thread: a command, or a panel action raised through its ExternalEvent).</summary>
    internal static (Result Result, string? Why) Check(UIApplication ui)
    {
        var doc = ui.ActiveUIDocument?.Document;
        if (doc is null || doc.IsFamilyDocument)
        {
            TaskDialog.Show(Title, "Open a project (not a family) to check it.");
            return (Result.Cancelled, null);
        }
        var log = new Dictionary<string, object?> { ["document"] = doc.Title };
        try
        {
            var added = RevitMarks.AddMarks(doc, ui.Application, MarkSetup.Plan(RevitMarks.Bindings(doc)));
            log["marks_added"] = added.Select(s => $"{s.Action}: {s.Mark.Name}").ToList();
            // each window type a maker's formula covers, its three Clear marks empty: filled as a draft the architect
            // confirms (never the stamp, so this check sends no clear opening for it)
            // (a failure is shown and the check goes on: the types stay empty, so their clear opening needs review)
            var (filled, failed) = RevitMarks.TryPrefill(doc, RevitMarks.Model(doc), log);
            var clear = ClearPrefills.Head(filled.Count, failed);
            // the street edge asked for only when it is the one fact left and the view shows a property line to click
            var read = ProjectFacts.Read(RevitMarks.Model(doc));
            var view = ShowsPropertyLine(ui.ActiveUIDocument!);
            var ask = StreetEdges.Ask(read, read.StreetEdges is null, view);
            log["street_ask"] = ask.ToString();
            if (ask == StreetAsk.Pick)
                PickStreet(ui.ActiveUIDocument!, log);
            var run = Run(doc, ui.Application, log);
            // the edge kept can't be sent (no longer a lot edge, or matching two): asked for again at once, as its
            // message says, and checked once more (the typed reason, never its words); in a view that can show it
            if (StreetEdges.NeedsNewPick(run.Prepared))
            {
                ask = StreetEdges.Ask(ProjectFacts.Read(RevitMarks.Model(doc)), needed: true, view);
                log["street_ask_again"] = ask.ToString();
                if (ask == StreetAsk.Pick && PickStreet(ui.ActiveUIDocument!, log))
                    run = Run(doc, ui.Application, log);
            }
            Show(ui, doc, run, added.Count, ask, clear);
            return (Result.Succeeded, null);
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            log["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList();
            Trial.Log("check_project", log);
            // the last check's rows taken down: never left showing as if they were this one's
            ResultsPane.Failed($"Nothing was checked: {e.GetType().Name}: {e.Message} (logged to {Trial.LogPath()})");
            TaskDialog.Show(Title, $"Nothing was checked: {e.GetType().Name}\n{e.Message}\n\nLogged to {Trial.LogPath()}");
            return (Result.Failed, e.Message);
        }
    }

    internal sealed record Ran(ProjectPrepared Prepared, CheckResult? Result, ResultWords? Words, string? FullText,
                               ResultModel? Model = null);

    /// <summary>Reads, sends and logs one check of the document (everything in the log, whatever happens).</summary>
    internal static Ran Run(Document doc, RevitApplication app, Dictionary<string, object?> log)
    {
        var sw = Stopwatch.StartNew();
        // both reads on Revit's thread, one after the other, of the same document: the same phases and options
        var outside = RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance);
        var inside = RevitInterior.Model(doc);
        var worker = Trial.Worker();
        // the lot's lines are read on this thread before anything is awaited (a lot line's points call into Revit)
        var prepared = ProjectCheck.PrepareAsync(outside, inside, new WorkerLeftOut(worker)).GetAwaiter().GetResult();
        log["read_s"] = sw.Elapsed.TotalSeconds;
        log["missing"] = prepared.Missing;
        // in Revit's internal coordinates, as the Street edge mark keeps them (the request's site is in shared ones)
        log["lot_edges_internal"] = outside.LotLines.Where(l => l.IsPropertyLine).Select(l => new Dictionary<string, object?>
        {
            ["property_line"] = l.UniqueId,
            ["edges"] = l.Curves.Select(c => StreetEdges.Format([(c.Start, c.End)])).ToList(),
        }).ToList();
        if (prepared.Request is not { } request)
        {
            Trial.Log("check_project", log);
            return new Ran(prepared, null, null, null);
        }
        log["request"] = new JsonObject
        {
            ["site"] = request.Site.DeepClone(), ["facts"] = request.Facts.DeepClone(), ["interior"] = request.Interior.DeepClone(),
        }.ToJsonString();
        sw.Restart();
        // the worker client is async: off Revit's thread, waited for (as the box house's check)
        var result = Task.Run(() => ProjectCheck.SendAsync(worker, request)).GetAwaiter().GetResult();
        log["check_s"] = sw.Elapsed.TotalSeconds;
        log["answer"] = result.Raw.GetRawText();
        var words = ResultText.Format(result, PhaseName(doc, prepared.PhaseChecked), prepared.OptionsChecked, prepared.Inside,
                                      uid => Label(doc, uid), street: prepared.Street);
        var full = ResultText.Format(result, PhaseName(doc, prepared.PhaseChecked), prepared.OptionsChecked, prepared.Inside,
                                     uid => Label(doc, uid), maxOtherRows: int.MaxValue, street: prepared.Street).ToString();
        var model = ResultRows.Build(result, PhaseName(doc, prepared.PhaseChecked), prepared.OptionsChecked, prepared.Inside, prepared.Street);
        log["street"] = prepared.Street;
        log["state"] = result.State.ToString();
        log["summary"] = result.Summary;
        log["shown"] = words.ToString();
        log["notes"] = prepared.Inside?.Notes.Select(n => $"{n.Part} {n.Field}: {n.Why}").ToList();
        Trial.Log("check_project", log);
        return new Ran(prepared, result, words, full, model);
    }

    /// <summary>The run in the results panel (what to fill in first when nothing was sent), every row in the text
    /// file; each element's label read here, on Revit's thread, for the panel. <paramref name="clear"/> is
    /// <see cref="ClearPrefills.Head"/>'s words (the makers' clear openings filled, or why they couldn't be): shown in
    /// the panel's status line beside the marks added, and first in the text file.</summary>
    private static void Show(UIApplication ui, Document doc, Ran run, int marksAdded, StreetAsk ask, string clear)
    {
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        string files;
        if (run.Model is { } model)
        {
            var file = Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "check_project_result.txt");
            File.WriteAllText(file, clear + run.FullText + "\n", new UTF8Encoding(false));
            foreach (var uid in model.Groups.SelectMany(g => g.AllRows).SelectMany(r => r.Elements).Distinct(StringComparer.Ordinal))
                if (Label(doc, uid) is { } label)
                    labels[uid] = label;
            files = $"Every row: {file}. The request and the answer: {Trial.LogPath()}";
        }
        else
            files = $"Logged to {Trial.LogPath()}";
        ResultsPane.Show(ui, doc, new PanelContent(doc.Title, DateTime.Now, run.Model,
                                                   StreetEdges.MissingAsShown(run.Prepared.Missing, ask), marksAdded, labels, files,
                                                   ClearWords: clear));
    }

    /// <summary>Whether the active view is a plan (a site plan or floor plan) with a property line visible in it:
    /// the only view a street-edge click can land in.</summary>
    private static bool ShowsPropertyLine(UIDocument ui) =>
        ui.ActiveView is ViewPlan { IsTemplate: false } plan
        && new FilteredElementCollector(ui.Document, plan.Id).OfClass(typeof(PropertyLine)).Any();

    /// <summary>Asks the architect to click the lot edges along the street, and keeps them in the Street edge mark.
    /// True when an edge was kept.</summary>
    internal static bool PickStreet(UIDocument ui, Dictionary<string, object?> log)
    {
        var doc = ui.Document;
        var lines = RevitRead.LotLines(doc).Where(l => l.IsPropertyLine).ToDictionary(l => l.UniqueId);
        if (lines.Count == 0)
            return false;                                            // no property line: the dialog says what is missing
        var toShared = RevitRead.InternalToShared(doc);
        var kept = new List<PickedEdge>();
        var said = new List<string>();
        while (true)
        {
            Reference picked;
            try
            {
                picked = ui.Selection.PickObject(ObjectType.Element, new PropertyLines(),
                    kept.Count == 0 ? "Gordium: " + StreetEdges.PickPrompt
                                    : "Gordium: click another lot edge along the street, or press Esc when done");
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                break;
            }
            var e = doc.GetElement(picked);
            if (e is null || !lines.TryGetValue(e.UniqueId, out var line))
                continue;
            var (edge, why) = StreetEdges.Nearest(line, RevitInterior.P(picked.GlobalPoint));
            if (edge is { } got)
            {
                // said back before it is kept: Revit highlights the whole property line, never the edge it took
                var words = StreetEdges.Describe(got, toShared);
                var ask = new TaskDialog(Title)
                {
                    MainInstruction = $"Use {words} as the street line?",
                    MainContent = "Shared coordinates, feet. No: the click is forgotten; click the edge again.",
                    CommonButtons = TaskDialogCommonButtons.Yes | TaskDialogCommonButtons.No,
                    DefaultButton = TaskDialogResult.No,
                };
                if (ask.Show() == TaskDialogResult.Yes)
                {
                    if (!kept.Contains(got))
                        kept.Add(got);
                    said.Add("kept " + words);
                }
                else
                    said.Add("not kept " + words);
            }
            else
            {
                said.Add(why!);
                TaskDialog.Show(Title, why);
            }
        }
        log["street_picks"] = said;
        if (kept.Count == 0)
            return false;
        using var t = new Transaction(doc, ResultRows.StreetTransaction);
        t.Start();
        var p = doc.ProjectInformation.get_Parameter(Marks.StreetEdge.Guid)
                ?? throw new InvalidOperationException($"{Marks.StreetEdge.Name} isn't on Project Information");
        // Set's false throws naming the mark (the transaction then rolls back) and nothing is logged as kept
        StreetEdges.Keep(kept, p.Set, log);
        t.Commit();
        return true;
    }

    private sealed class PropertyLines : ISelectionFilter
    {
        public bool AllowElement(Element elem) => elem is PropertyLine;

        public bool AllowReference(Reference reference, XYZ position) => true;
    }

    private static string? PhaseName(Document doc, string? id) =>
        id is null ? null : long.TryParse(id, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n)
            ? doc.GetElement(new ElementId(n))?.Name ?? id : id;

    /// <summary>A UniqueId as the architect finds the element: its category and Revit's element id (Select by ID).</summary>
    private static string? Label(Document doc, string uid) =>
        doc.GetElement(uid) is { } e ? $"{e.Category?.Name ?? "element"} id {e.Id.Value.ToString(CultureInfo.InvariantCulture)}" : null;

    /// <summary>A check asked for by file while Revit is idle, no clicks (check_project_request.json:
    /// <c>{"model": "&lt;path&gt;.rvt", "marks": {"Gordium: Zone": "R-1b", "Gordium: Lot surveyed": true, ...}}</c>,
    /// "marks" optional): the model opened, the marks given set (Gordium's marks added first), checked as the button
    /// checks it but with no street pick, logged (the result's words too) and closed unsaved.</summary>
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "check_project_request.json");

    internal static void RunRequest(RevitApplication app, string requestFile)
    {
        var request = JsonNode.Parse(File.ReadAllText(requestFile, Encoding.UTF8))!;
        var path = request["model"]!.GetValue<string>();
        var log = new Dictionary<string, object?> { ["file"] = path };
        var doc = app.OpenDocumentFile(path);
        try
        {
            log["document"] = doc.Title;
            if (request["marks"] is JsonObject marks)
            {
                RevitMarks.AddMarks(doc, app, MarkSetup.Plan(RevitMarks.Bindings(doc)));
                using var t = new Transaction(doc, "Gordium: the request's marks");
                t.Start();
                foreach (var (name, value) in marks)
                {
                    var m = Marks.All.FirstOrDefault(x => x.Name == name)
                            ?? throw new InvalidOperationException($"{name} is not one of Gordium's marks");
                    var p = doc.ProjectInformation.get_Parameter(m.Guid)
                            ?? throw new InvalidOperationException($"{name} isn't on Project Information");
                    // by the mark's own kind: a value of another kind, or a Set Revit refuses, and nothing is checked
                    var (yesNo, words) = ProjectFacts.RequestValue(m, value);
                    ProjectFacts.Write(m, value?.ToJsonString() ?? "null", () => yesNo is { } i ? p.Set(i) : p.Set(words!));
                }
                t.Commit();
            }
            var run = Run(doc, app, log);
            if (run.FullText is { } text)
                File.WriteAllText(Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "check_project_result.txt"), text + "\n",
                                  new UTF8Encoding(false));
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            log["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList();
            Trial.Log("check_project", log);
        }
        finally
        {
            doc.Close(false);
        }
    }
}
