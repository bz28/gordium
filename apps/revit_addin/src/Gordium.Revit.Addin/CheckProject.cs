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
/// <para>A check that doesn't freeze Revit (design pass PR 8; <see cref="CheckFlow"/> decides each step, tested
/// without Revit): the panel says "Reading the model..." first, then the read runs on Revit's thread (Revit's API is
/// called only there, so Revit waits for it); the request is sent and waited for on a pool thread (Revit is free:
/// "Checking..." with Cancel); the answer comes back to Revit's thread through the panel's ExternalEvent and is
/// shown fresh only if no edit was committed since the read, else stale. Where Revit's thread went is the log's
/// <c>ui_thread</c>.</para>
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

    /// <summary>The button's check of the active project, and the panel's Check again (on Revit's thread: a command,
    /// or a panel action raised through its ExternalEvent): begins the check (<see cref="CheckRun.Start"/>), whose read
    /// runs once the panel has drawn "Reading the model...". Refused, and said, while another check runs.</summary>
    internal static (Result Result, string? Why) Check(UIApplication ui)
    {
        var doc = ui.ActiveUIDocument?.Document;
        if (doc is null || doc.IsFamilyDocument)
        {
            TaskDialog.Show(Title, "Gordium checks projects. Open a project (not a family) to check it.");
            return (Result.Cancelled, null);
        }
        if (CheckRun.Start(ui, doc) is { } refused)
        {
            TaskDialog.Show(Title, refused);
            return (Result.Cancelled, null);
        }
        return (Result.Succeeded, null);
    }

    /// <summary>The check's read, on Revit's thread (the read action <see cref="CheckRun.Start"/> queues): Gordium's
    /// marks added, the makers' clear openings filled as drafts, the street edge asked for, the model read; then the
    /// request sent off Revit's thread (<see cref="CheckRun.Send"/>), or, with nothing to send, the panel says what to
    /// fill in. A failure is the panel's error state (no row of this check): one card in the pane, brought into view,
    /// with what was already written under its words (UI polish PR 5).</summary>
    internal static void ReadAndSend(UIApplication ui, Document doc, CheckRun check)
    {
        var log = check.Log;
        var started = Stopwatch.GetTimestamp();
        var picked = check.Clock.ArchitectSeconds;
        // the read's blocked time: all of it but the architect's picks (Revit answers while it waits for a click)
        void Blocked() => check.Clock.Blocked("read", Stopwatch.GetElapsedTime(started).TotalSeconds - (check.Clock.ArchitectSeconds - picked));
        // the makers' clear openings' words, kept outside the try: a check that fails after the drafts were written
        // still says they were (review round 7)
        var clear = "";
        var marksAdded = 0;
        if (!CheckRun.Flow.IsCurrent(check.Ticket) || !doc.IsValidObject)
        {
            check.End("cancelled");                       // cancelled (or the project closed) before the read began
            return;
        }
        try
        {
            var added = RevitMarks.AddMarks(doc, ui.Application, MarkSetup.Plan(RevitMarks.Bindings(doc)));
            marksAdded = added.Count;
            check.Wrote = added.Count > 0;
            log["marks_added"] = added.Select(s => $"{s.Action}: {s.Mark.Name}").ToList();
            // each window type a maker's formula covers, its three Clear marks empty: filled as a draft the architect
            // confirms (never the stamp, so this check sends no clear opening for it)
            // (a failure is shown and the check goes on: the types stay empty, so their clear opening needs review)
            var (filled, failed) = RevitMarks.TryPrefill(doc, RevitMarks.Model(doc), log);
            clear = ClearPrefills.Head(filled.Count, failed);
            check.Wrote |= filled.Count > 0;
            // the street edge asked for only when it is the one fact left and the view shows a property line to click,
            // and only in the project being checked while it is the active one (the read is queued after the click: the
            // architect may have switched projects since; a pick, and the mark it writes, would land in another one)
            bool Active() => ui.ActiveUIDocument?.Document.Equals(doc) == true;
            // the Setup form (docs/decisions/2026-11-22_setup_form.md): a fact the check needs missing, and the form
            // shows instead of a check (unless the architect chose Check now anyway for exactly these): nothing sent
            // the place's districts and uses known before the gate decides (a stated zone or use is checked against
            // them whatever the form was opened before): the worker being started is waited for here, as the read does
            if (!check.Anyway)
            {
                var asked = Stopwatch.GetTimestamp();
                SetupRun.Options(check.Worker, log);
                log["setup_options_s"] = Stopwatch.GetElapsedTime(asked).TotalSeconds;
            }
            var (setup, step) = check.Anyway ? (null, SetupStep.SendAnyway) : SetupRun.Needs(doc);
            // sent anyway: the architect's Check now anyway, or a check whose missing facts were already checked anyway
            var anyway = step == SetupStep.SendAnyway;
            log["setup_step"] = step.ToString();
            if (step == SetupStep.Show && setup is not null)
            {
                log["setup"] = setup.Needed;
                var shown = CheckRun.Flow.NothingSent(check.Ticket);
                if (shown)
                {
                    if (clear.Length > 0)
                        ResultsPane.Say(clear.Trim());
                    SetupRun.Show(ui, doc, setup);
                }
                Blocked();
                check.End(shown ? "setup" : "cancelled");
                return;
            }
            var read = ProjectFacts.Read(RevitMarks.Model(doc));
            var view = Active() && ShowsPropertyLine(ui.ActiveUIDocument!);
            // checked anyway: never a pick first (the form's Pick on plan is the way to give it)
            var ask = anyway ? StreetAsk.NotNeeded : StreetEdges.Ask(read, read.StreetEdges is null, view, Active());
            log["street_ask"] = ask.ToString();
            if (ask == StreetAsk.Pick && Active() && check.Clock.Architect("street_pick", () => PickStreet(ui.ActiveUIDocument!, log)))
                check.Wrote = true;                       // the edge picked is written to its mark
            if (!CheckRun.Flow.IsCurrent(check.Ticket))
            {
                Blocked();
                check.End("cancelled");                   // cancelled during the pick (Revit answers then): not read
                return;
            }
            var prepared = ReadModel(doc, ui.Application, log, check.Worker, anyway);
            // the edge kept can't be sent (no longer a lot edge, or matching two): asked for again at once, as its
            // message says, and checked once more (the typed reason, never its words); in a view that can show it
            if (StreetEdges.NeedsNewPick(prepared))
            {
                ask = StreetEdges.Ask(ProjectFacts.Read(RevitMarks.Model(doc)), needed: true, view && Active(), Active());
                log["street_ask_again"] = ask.ToString();
                // (not read again once cancelled during that pick: Send then sends nothing)
                if (ask == StreetAsk.Pick && Active() && check.Clock.Architect("street_pick", () => PickStreet(ui.ActiveUIDocument!, log)))
                {
                    check.Wrote = true;                   // the edge picked is written to its mark
                    if (CheckRun.Flow.IsCurrent(check.Ticket))
                        prepared = ReadModel(doc, ui.Application, log, check.Worker, anyway);
                }
            }
            check.Read(prepared, added.Count, ask, clear);
            if (prepared.Request is not { } request)
            {
                // nothing sent: what to fill in, shown now (Done), unless the check was cancelled during a pick
                var shown = CheckRun.Flow.NothingSent(check.Ticket);
                // the Setup form, saying why nothing was sent (the zone missing on Check now anyway, a street edge
                // no longer on the lot): every way to give the fact is there
                if (shown)
                {
                    // in plain words from what is missing (the old typing instructions stay in the log's "missing")
                    var marks = RevitMarks.Model(doc);
                    var notSet = SetupFacts.NotSent(marks, ProjectFacts.Read(marks));
                    SetupRun.Show(ui, doc, notice: clear + SetupWords.NothingSent(prepared.StreetRefused, notSet,
                        SetupWords.Noun(Marks.Text(marks.ProjectMarks.GetValueOrDefault(Marks.Use.Guid))), LengthUnits.Of(marks.DisplayUnits).Symbol,
                        AreaUnits.Of(marks.AreaDisplayUnits).Symbol));
                }
                Blocked();
                check.End(shown ? "nothing_sent" : "cancelled");
                return;
            }
            Blocked();
            // the read's end (its edit count kept now: an edit made after it makes the answer stale), then the send,
            // queued behind the input Revit queued during the read (WPF runs Background work after pending input): a
            // Cancel clicked during the read is handled first, and then nothing is sent and the worker keeps running
            if (check.ReadEnded())
                ResultsPane.AfterInput(() => check.Send(request));
        }
        catch (Exception e)
        {
            Blocked();
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            log["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList();
            if (!CheckRun.Flow.Fail(check.Ticket))
            {
                check.End("cancelled");                   // cancelled meanwhile (a pick, the project closed): not shown
                return;
            }
            check.End("failed");
            // the last check's rows taken down: never left showing as if they were this one's; in the pane, never a
            // dialog that blocks Revit (UI polish change 16), the technical words only behind Copy details
            ResultsPane.Reveal(ui);                       // the old dialog always showed: a hidden pane is brought up
            ResultsPane.Failed(CheckFailures.OfRead(e, clear + $"Nothing was checked: {e.GetType().Name}: {e.Message} (logged to {Trial.LogPath()})")
                                            .After(ClearPrefills.StatusLine(marksAdded, clear), check.Wrote));
        }
    }

    /// <summary>The worker's answer, back on Revit's thread (the panel's ExternalEvent): shown fresh, shown stale (an
    /// edit was committed after the read), or ignored (cancelled, or not the check the panel waits for), as
    /// <see cref="CheckFlow"/> decides now, on this thread, where every edit is counted. A failed wait (the worker
    /// crashed, timed out, or answered something unreadable) is the error state: no row of it is ever shown.</summary>
    internal static void Answered(UIApplication ui, Document doc, CheckRun check, Task<CheckResult> sent)
    {
        var log = check.Log;
        var started = Stopwatch.GetTimestamp();
        // the time this took on Revit's thread, added before the log line is written
        void End(string how)
        {
            check.Clock.Blocked("show", Stopwatch.GetElapsedTime(started).TotalSeconds);
            check.End(how);
        }
        try
        {
            var use = CheckRun.Flow.Arrived(check.Ticket, sent);
            log["answer_use"] = use.ToString();
            if (sent.Status != TaskStatus.RanToCompletion)
            {
                var e = sent.Exception?.GetBaseException() ?? new OperationCanceledException("the check was cancelled");
                log["error"] = $"{e.GetType().Name}: {e.Message}";
            }
            if (use == AnswerUse.Ignore)
            {
                End("cancelled");                         // cancelled (its stopped worker's error too): nothing shown
                return;
            }
            if (use == AnswerUse.ShowError)
            {
                End("failed");
                // one message per failure (UI polish change 13), from what the wait ended with
                var why = sent.Exception is { } failed ? CheckFailures.Unwrap(failed) : new OperationCanceledException("the check was cancelled");
                ResultsPane.Reveal(ui);
                ResultsPane.Failed(CheckFailures.Of(why, CheckWords.CheckerStopped((string)log["error"]!) + $" (logged to {Trial.LogPath()})")
                                                .After(ClearPrefills.StatusLine(check.MarksAdded, check.Clear), check.Wrote));
                return;
            }
            var run = Answer(doc, check.Prepared!, sent.Result, log);
            Show(ui, doc, run, check.MarksAdded, check.Ask, check.Clear, check.ReadAt, stale: use == AnswerUse.ShowStale);
            End(use == AnswerUse.ShowStale ? "shown_stale" : "shown");
        }
        catch (Exception e)
        {
            // an answer that can't be shown (its words or rows can't be made): the error state, never part of it
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            log["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList();
            End("failed");
            ResultsPane.Reveal(ui);
            ResultsPane.Failed(CheckFailures.Of(e, check.Clear + $"Nothing was checked: {e.GetType().Name}: {e.Message} (logged to {Trial.LogPath()})")
                                            .After(ClearPrefills.StatusLine(check.MarksAdded, check.Clear), check.Wrote));
        }
    }

    internal sealed record Ran(ProjectPrepared Prepared, CheckResult? Result, ResultWords? Words, string? FullText,
                               ResultModel? Model = null);

    /// <summary>Reads, sends and logs one check of the document, all on this thread (the check asked for by file:
    /// no panel, nothing to keep free); everything in the log, whatever happens.</summary>
    internal static Ran Run(Document doc, RevitApplication app, Dictionary<string, object?> log)
    {
        var prepared = ReadModel(doc, app, log, Trial.WorkerAsync());
        if (prepared.Request is not { } request)
        {
            Trial.Log("check_project", log);
            return new Ran(prepared, null, null, null);
        }
        var sw = Stopwatch.StartNew();
        var result = Task.Run(async () => await ProjectCheck.SendAsync(await Trial.WorkerAsync().ConfigureAwait(false), request).ConfigureAwait(false))
                         .GetAwaiter().GetResult();
        log["check_s"] = sw.Elapsed.TotalSeconds;
        var run = Answer(doc, prepared, result, log);
        Trial.Log("check_project", log);
        return run;
    }

    /// <summary>Reads the document into the request, on Revit's thread (where the read's time went: the log's
    /// read_steps, README "The results log"; kept on this thread for this read only, never in a record or the request;
    /// logged with whatever was read, a failure's too). <paramref name="worker"/> is the worker being started: waited
    /// for here only when the read asks it which objects are left out.</summary>
    internal static ProjectPrepared ReadModel(Document doc, RevitApplication app, Dictionary<string, object?> log, Task<WorkerClient> worker,
                                              bool anyway = false)
    {
        var steps = new ReadSteps();
        using var keep = ReadSteps.Begin(steps);
        try
        {
            return ReadModel(doc, app, log, worker, steps, anyway);
        }
        catch
        {
            log["read_steps"] = steps.ToLog();
            throw;
        }
    }

    private static ProjectPrepared ReadModel(Document doc, RevitApplication app, Dictionary<string, object?> log, Task<WorkerClient> worker,
                                             ReadSteps steps, bool anyway)
    {
        var sw = Stopwatch.StartNew();
        // both reads on Revit's thread, one after the other, of the same document: the same phases and options
        var outside = ReadSteps.Time("outside", () => RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance));
        var inside = ReadSteps.Time("inside", () => RevitInterior.Model(doc));
        // the lot's lines are read on this thread before anything is awaited (a lot line's points call into Revit)
        var prepared = ReadSteps.Time("prepare", () => ProjectCheck.PrepareAsync(outside, inside, new StartedLeftOut(worker), anyway: anyway).GetAwaiter().GetResult());
        log["read_s"] = sw.Elapsed.TotalSeconds;
        log["missing"] = prepared.Missing;
        log["not_stated"] = prepared.NotStated.Select(m => m.Name).ToList();
        // in Revit's internal coordinates, as the Street edge mark keeps them (the request's site is in shared ones)
        log["lot_edges_internal"] = outside.LotLines.Where(l => l.IsPropertyLine).Select(l => new Dictionary<string, object?>
        {
            ["property_line"] = l.UniqueId,
            ["edges"] = l.Curves.Select(c => StreetEdges.Format([(c.Start, c.End)])).ToList(),
        }).ToList();
        if (prepared.Request is not { } request)
        {
            log["read_steps"] = steps.ToLog();
            return prepared;
        }
        using (ReadSteps.Step("log_request"))
            log["request"] = new JsonObject
            {
                ["site"] = request.Site.DeepClone(), ["facts"] = request.Facts.DeepClone(), ["interior"] = request.Interior.DeepClone(),
            }.ToJsonString();
        log["read_steps"] = steps.ToLog();
        return prepared;
    }

    /// <summary>The worker's left-out question (<see cref="WorkerLeftOut"/>), the worker being started waited for only
    /// when it is asked (on Revit's thread, as the read's step worker_wait): its start overlaps the read.</summary>
    private sealed class StartedLeftOut(Task<WorkerClient> worker) : ILeftOutAsker
    {
        public Task<IReadOnlyList<LeftOutDecision>> AskAsync(JsonObject? lot, JsonArray objects, JsonArray buildings,
                                                             JsonObject definitions, CancellationToken cancel)
        {
            WorkerClient client;
            try
            {
                client = ReadSteps.Time("worker_wait", () => worker.GetAwaiter().GetResult());
            }
            catch (Exception e) when (e is not WorkerException and not OperationCanceledException)
            {
                // the worker couldn't be started (no Gordium folder, Revit closing): the checker's failure, said as such
                // in the pane, never as Revit's read (UI polish PR 5 review round 6)
                throw new WorkerUnavailableException($"The Gordium checker couldn't be started: {e.Message}", e);
            }
            return new WorkerLeftOut(client).AskAsync(lot, objects, buildings, definitions, cancel);
        }
    }

    /// <summary>The answer in words and rows (each element's label and the phase read here, on Revit's thread), and
    /// logged.</summary>
    private static Ran Answer(Document doc, ProjectPrepared prepared, CheckResult result, Dictionary<string, object?> log)
    {
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
        log["route_notes"] = prepared.Inside?.RouteNotes.Select(n => $"{n.Part} {n.Field}: {n.Why}").ToList();   // the escape routes, apart
        return new Ran(prepared, result, words, full, model);
    }

    /// <summary>The run in the results panel (what to fill in first when nothing was sent), every row in the text
    /// file; each element's label read here, on Revit's thread, for the panel. <paramref name="clear"/> is
    /// <see cref="ClearPrefills.Head"/>'s words (the makers' clear openings filled, or why they couldn't be): shown in
    /// the panel's status line beside the marks added, and first in the text file. <paramref name="when"/> is when the
    /// model was read; <paramref name="stale"/>: an answer whose model was edited after its read (shown greyed, saying
    /// so, never green).</summary>
    private static void Show(UIApplication ui, Document doc, Ran run, int marksAdded, StreetAsk ask, string clear, DateTime when, bool stale)
    {
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        var ids = new Dictionary<string, long>(StringComparer.Ordinal);
        string files;
        var model = run.Model;
        if (model is not null)
        {
            var file = Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "check_project_result.txt");
            File.WriteAllText(file, clear + run.FullText + "\n", new UTF8Encoding(false));
            foreach (var uid in model.Groups.SelectMany(g => g.AllRows).SelectMany(r => r.Elements).Distinct(StringComparer.Ordinal))
                if (Label(doc, uid) is { } label)
                {
                    labels[uid] = label;
                    ids[uid] = doc.GetElement(uid).Id.Value;
                }
            files = $"Every row: {file}. The request and the answer: {Trial.LogPath()}";
            if (stale)
                model = ResultRows.Stale(model, when, CheckWords.ChangedWhileChecking(when));
        }
        else
            files = $"Logged to {Trial.LogPath()}";
        // the project's facts as the Setup form's fields: what the questions card asks with, and what What changed says
        // the architect changed since the check before (UI polish change 40)
        var questions = model?.Views is not null ? SetupRun.Questions(doc) : null;
        ResultsPane.Show(ui, doc, new PanelContent(doc.Title, when, model,
                                                   StreetEdges.MissingAsShown(run.Prepared.Missing, ask), marksAdded, labels, files,
                                                   ClearWords: clear, Ids: ids, Key: DocKeys.Of(doc), Questions: questions,
                                                   NotStated: run.Prepared.NotStated.Select(m => SetupWords.SentWithout(m, SetupWords.Noun(
                                                       run.Prepared.Request?.Facts["use"]?.GetValue<string>()), LengthUnits.Of(doc.GetUnits()
                                                       .GetFormatOptions(SpecTypeId.Length).GetUnitTypeId().TypeId).Symbol,
                                                       AreaUnits.Of(doc.GetUnits().GetFormatOptions(SpecTypeId.Area).GetUnitTypeId().TypeId).Symbol)).ToList()));
    }

    /// <summary>Whether the active view is a plan (a site plan or floor plan) with a property line visible in it:
    /// the only view a street-edge click can land in.</summary>
    internal static bool ShowsPropertyLine(UIDocument ui) =>
        ui.ActiveView is ViewPlan { IsTemplate: false } plan
        && new FilteredElementCollector(ui.Document, plan.Id).OfClass(typeof(PropertyLine)).Any();

    /// <summary>Asks the architect to click the lot edges along the street, and keeps them in the Street edge mark.
    /// True when an edge was kept. (The check's own pick; the Setup form picks with <see cref="PickEdges"/> and writes
    /// the edge only on Save.)</summary>
    internal static bool PickStreet(UIDocument ui, Dictionary<string, object?> log)
    {
        var doc = ui.Document;
        var kept = PickEdges(ui, log);
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

    /// <summary>Revit's pick of the lot edges along the street, each said back in the architect's words ("the south
    /// edge of the lot, 100'-0\" long") and confirmed (UI polish changes 10 and 11): "Use this edge" ends the pick,
    /// "Use it, and pick another street edge" asks for one more, "Pick a different edge" forgets the click; never a
    /// silent wait for Esc after a confirmation (Ben hit it in the trial). The edges kept, nothing written (empty when
    /// none was, or no property line is drawn). The coordinates go only to the log.</summary>
    internal static List<PickedEdge> PickEdges(UIDocument ui, Dictionary<string, object?> log)
    {
        var doc = ui.Document;
        var all = RevitRead.LotLines(doc);
        var lines = all.Where(l => l.IsPropertyLine).ToDictionary(l => l.UniqueId);
        if (lines.Count == 0)
            return [];                                               // no property line: the dialog says what is missing
        var toShared = RevitRead.InternalToShared(doc);
        var tol = doc.Application.VertexTolerance;
        var session = new PickSession();
        var said = new List<string>();
        ResultsPane.Picking(true);                                   // the pane says what Revit is waiting for
        try
        {
        while (session.Asking)
        {
            Reference picked;
            try
            {
                picked = ui.Selection.PickObject(ObjectType.Element, new PropertyLines(), session.Prompt);
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                session.Escape();
                break;
            }
            var e = doc.GetElement(picked);
            if (e is null || !lines.TryGetValue(e.UniqueId, out var line))
                continue;
            var (edge, why) = StreetEdges.Nearest(line, RevitInterior.P(picked.GlobalPoint));
            if (edge is { } got)
            {
                // said back before it is kept: Revit highlights the whole property line, never the edge it took
                var words = EdgeWords.Of(got.A, got.B, all, toShared, tol) ?? new EdgeDescription(null, EdgeWords.FeetInches(got.Length));
                var (instruction, content, use, another, different) = PickSession.Confirm(words);
                var ask = new TaskDialog(StreetEdges.PickTitle)
                {
                    MainInstruction = instruction, MainContent = content, CommonButtons = TaskDialogCommonButtons.Cancel,
                    AllowCancellation = true,
                };
                ask.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, use);
                ask.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, another);
                ask.AddCommandLink(TaskDialogCommandLinkId.CommandLink3, different);
                var answer = ask.Show() switch
                {
                    TaskDialogResult.CommandLink1 => PickAnswer.Use,
                    TaskDialogResult.CommandLink2 => PickAnswer.UseAndAnother,
                    TaskDialogResult.CommandLink3 => PickAnswer.Different,
                    _ => PickAnswer.Close,
                };
                session.Answer(got, answer);
                said.Add($"{answer}: {StreetEdges.Describe(got, toShared)} ({words.Words})");
            }
            else
            {
                said.Add(why!);
                TaskDialog.Show(StreetEdges.PickTitle, why);
            }
        }
        }
        finally
        {
            ResultsPane.Picking(false);
        }
        log["street_picks"] = said;
        return [.. session.Kept];
    }

    /// <summary>The edges picked, in words ("the south edge, 100'-0\" and the east edge, 60'-0\""), or null when any
    /// can't be said.</summary>
    internal static string? EdgesInWords(Document doc, IReadOnlyList<PickedEdge> kept)
    {
        var all = RevitRead.LotLines(doc);
        var toShared = RevitRead.InternalToShared(doc);
        var said = kept.Select(e => EdgeWords.Of(e.A, e.B, all, toShared, doc.Application.VertexTolerance)?.Words).ToList();
        return said.Count == 0 || said.Any(w => w is null) ? null : PaneWords.And(said!);
    }

    private sealed class PropertyLines : ISelectionFilter
    {
        public bool AllowElement(Element elem) => elem is PropertyLine;

        public bool AllowReference(Reference reference, XYZ position) => true;
    }

    private static string? PhaseName(Document doc, string? id) =>
        id is null ? null : long.TryParse(id, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n)
            ? doc.GetElement(new ElementId(n))?.Name ?? id : id;

    /// <summary>A UniqueId as the architect names the element (ElementNames: "CLOSET (40)", "Door D06", "Level: 1st
    /// floor"), by Revit's id only when nothing else names it; null for one not in the model.</summary>
    internal static string? Label(Document doc, string uid)
    {
        if (doc.GetElement(uid) is not { } e)
            return null;
        var room = e as SpatialElement;
        var name = room is not null ? e.get_Parameter(BuiltInParameter.ROOM_NAME)?.AsString() : e.Name;
        var mark = room is null ? e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString() : null;
        return ElementNames.Of(e.Category?.Name, name, room?.Number, mark, e.Id.Value);
    }

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
