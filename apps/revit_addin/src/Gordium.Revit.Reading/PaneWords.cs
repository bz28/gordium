using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>What the pane shows at first: the welcome (nothing checked in it yet), the Setup form, or results.</summary>
public enum PaneShows { Welcome, Setup, Results, Error }

/// <summary>The pane's small line icons (UI polish change 46): drawn by the add-in in the text's colour, never a status
/// colour (a status has its own glyph, StatusLook).</summary>
public enum PaneIcon { Page, Review, Pencil, Pin, Form, Map, Ruler, Scales, Question }

/// <summary>
/// The pane's one vocabulary and its plain-words states (docs/revit/ui_design_pass.md, the intuitive pane, changes 1,
/// 2, 3, 6, 7, 9, 10, 11; Ben, 2026-11-23), Revit-free so they are tested: "results" (never "rows"), "needs review"
/// (the worker's "to review" said the same way), "set" a fact, "fix"; the first-run welcome and when it shows; the
/// header's button; the Setup footer; the results' first sentence; the filters' counts; what changed as a short list;
/// the error and stale states. Every count is a count of the worker's rows; nothing here makes or changes a verdict.
/// </summary>
public static class PaneWords
{
    /// <summary>"1 result", "130 results".</summary>
    public static string Results(int n) => $"{n} result{(n == 1 ? "" : "s")}";

    /// <summary>The first letter in capitals (the worker's reasons start lower case: they are written to follow a name).</summary>
    public static string Capital(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        return s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s[1..];
    }

    /// <summary>What the questions card's Save says when Revit didn't take every answer (a write refused, or the
    /// transaction not committed): what was saved, if anything (one Ctrl+Z undoes it: review round 1, a partly saved
    /// set was said as "weren't saved" while Project Information had changed), what wasn't, and that nothing was
    /// checked.</summary>
    public static string AnswersNotSaved(IReadOnlyList<string> refused, int applied, string status)
    {
        ArgumentNullException.ThrowIfNull(refused);
        var saved = applied > 0 && status == "Committed";
        var why = refused.Count > 0 ? string.Join("; ", refused) : $"Revit didn't take the change ({status})";
        return saved
            ? $"Saved {applied} (Ctrl+Z undoes it), but not written: {why}. Nothing was checked: fix that on Project Information, or click Check again."
            : $"Your answers weren't saved, so nothing was checked: {why}. They are still chosen in the card: try Save again.";
    }

    /// <summary>"a", "a and b", "a, b and c".</summary>
    public static string And(IReadOnlyList<string> items)
    {
        ArgumentNullException.ThrowIfNull(items);
        return items.Count switch
        {
            0 => "",
            1 => items[0],
            _ => string.Join(", ", items.Take(items.Count - 1)) + " and " + items[^1],
        };
    }

    /// <summary>A count chip's words in the pane's vocabulary: the worker's "8 to review" is "8 need review" (the same
    /// count, the same status; one word for it everywhere).</summary>
    public static string Count(string words)
    {
        ArgumentNullException.ThrowIfNull(words);
        return words.Replace(" to review", " need review", StringComparison.Ordinal);
    }

    // ---- the first-run welcome (change 1) and the header (change 2) -------------------------------------------

    /// <summary>The welcome's title (UI polish: what the pane is for, in one line; the dock tab already says Gordium).</summary>
    public const string WelcomeTitle = "Check this design against the code";

    /// <summary>The welcome's one sentence on what Gordium does.</summary>
    public const string WelcomeIntro =
        "Gordium measures your model and checks it, rule by rule, against Ithaca zoning and the New York State egress code.";

    /// <summary>The welcome's three lines, each with its icon (<see cref="PaneIcon"/>): the code's own words, never a
    /// false pass, nothing written without a click.</summary>
    public static IReadOnlyList<(PaneIcon Icon, string Words)> WelcomeLines { get; } =
    [
        (PaneIcon.Page, "Every result shows the code's own words and page."),
        (PaneIcon.Review, "If Gordium can't measure something, it says Needs review. It never guesses a pass."),
        (PaneIcon.Pencil, "Nothing is written to your model without your click."),
    ];

    // ---- picking the street edge (UI polish change 9) ---------------------------------------------------------------

    /// <summary>The picking card's title, while Revit waits for the click.</summary>
    public const string PickTitle = "Click the lot edge along the street";

    public const string PickWords = "In any plan that shows the property line. Gordium asks you to confirm the edge before it keeps it.";

    public const string PickEsc = "Esc cancels.";

    /// <summary>Under the card when the Setup form is behind it.</summary>
    public const string PickFormStays = "The form stays as you left it.";

    /// <summary>Under the welcome's button.</summary>
    public const string WelcomeAlso = "Also on the ribbon: Gordium › Check project";

    /// <summary>The header's title before any project is known (the project's name once it is).</summary>
    public static string HeaderTitle(string? project) => string.IsNullOrWhiteSpace(project) ? RibbonPlan.PaneTitle : project.Trim();

    /// <summary>Ribbon's Results button when the pane can't be shown (the exception goes to the log only).</summary>
    public const string PaneWontOpen = "The Gordium pane couldn't open. Restart Revit; if it happens again, send the details to support.";

    /// <summary>Whether the welcome shows: only while no check's results have been shown in this pane (before the
    /// first, during the first check, after a first check failed or was cancelled), and never with results or the
    /// Setup form on screen.</summary>
    public static bool WelcomeShows(PaneShows shows, bool everShownResults) =>
        shows == PaneShows.Welcome && !everShownResults;

    /// <summary>Whether the header shows Check again: once a check's results were shown here (before that, the welcome's
    /// Check project and the Setup form's Save are the one action), and never while the Setup form is shown before the
    /// first check.</summary>
    public static bool HeaderCheckAgain(PaneShows shows, bool everShownResults) =>
        everShownResults && shows != PaneShows.Welcome;

    /// <summary>The header's line under the title when nothing is checked yet.</summary>
    public const string NotCheckedYet = "Not checked yet";

    // ---- the Setup footer (change 3) ---------------------------------------------------------------------------

    /// <summary>The Setup footer before anything is chosen: what a blank does.</summary>
    public const string BlankFact = "A fact left blank makes its rules Needs review, never a pass.";

    /// <summary>The Setup footer (UI polish change 7): before a choice, <see cref="BlankFact"/>; after, what Save writes
    /// ("Saves 4 facts to Project Information (one undo).") and what stays unset, by name, with what that leaves
    /// ("Escape openings and exit doors still need marking: their rules will need review."). <paramref name="chosen"/>
    /// is what Save writes (<see cref="Unsaved"/>), so the footer and the button never disagree.</summary>
    public static string SetupFooter(int chosen, IReadOnlyList<string> unsetFacts, IReadOnlyList<string> unmarked,
                                     IReadOnlyList<string>? blockers = null)
    {
        blockers ??= [];
        ArgumentNullException.ThrowIfNull(unsetFacts);
        ArgumentNullException.ThrowIfNull(unmarked);

        // before a choice: a fact without which nothing is checked says so first (review round 3), never only that
        // a blank makes its rules need review
        if (chosen == 0)
            return blockers.Count == 0 ? BlankFact
                : string.Join(" ", blockers) + (unsetFacts.Count + unmarked.Count > 0 ? " " + BlankFact : "");
        var words = new List<string> { $"Saves {chosen} {(chosen == 1 ? "fact" : "facts")} to Project Information (one undo)." };
        words.AddRange(blockers);
        if (unsetFacts.Count > 0)
            words.Add($"{Capital(And(unsetFacts))} {(unsetFacts.Count == 1 ? "isn't" : "aren't")} set yet: {(unsetFacts.Count == 1 ? "its" : "their")} rules will need review.");
        if (unmarked.Count > 0)
            words.Add($"{Capital(And(unmarked))} still need marking: {(unmarked.Count == 1 ? "its" : "their")} rules will need review.");
        return string.Join(" ", words);
    }

    /// <summary>The zoning district's step as the footer names it, and what the footer says while it isn't set.</summary>
    public const string ZoneStep = "zoning district";

    public const string NoZone = "Choose the zoning district: nothing can be checked without it.";

    /// <summary>What the footer says while the street edge kept is no longer an edge of the lot.</summary>
    public const string NoStreet = "Pick the street edge again: nothing can be checked until then.";

    /// <summary>The Setup form's one button: "Save and check" (greyed with nothing chosen) or "Save 4 and check".
    /// Save writes the facts chosen, then checks (anything still unset makes its rules need review, never a pass).</summary>
    public static string SaveAndCheck(int chosen) => chosen == 0 ? "Save and check" : $"Save {chosen} and check";

    /// <summary>The footer's words for a form and its draft: what Save writes (<see cref="Unsaved"/>: the same count
    /// the button says), and each numbered step still not set once it has, by its title (a fact to set, a mark to set
    /// on elements).</summary>
    public static string SetupFooter(SetupScreen screen, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        ArgumentNullException.ThrowIfNull(draft);
        var open = SetupSteps.Of(screen, draft).Where(s => !s.Done).ToList();
        // a step whose absence stops the whole check (the zoning district, a street edge off the lot) says so, never
        // that only its rules will need review (review rounds 1 and 2)
        var blockers = SetupSteps.Blockers(open);
        open = open.Where(s => blockers.All(b => b.Step != s)).ToList();
        return SetupFooter(Unsaved(screen, draft),
                           open.Where(s => s.Field is not null).Select(s => s.Title.ToLowerInvariant()).ToList(),
                           open.Where(s => s.Line is not null).Select(s => s.Title.ToLowerInvariant()).ToList(),
                           blockers.Select(b => b.Words).ToList());
    }

    /// <summary>The fields the draft changes (a choice that differs from what the model holds): what Save writes and
    /// counts ("Save 3 facts"), and what the footer calls chosen, not saved yet.</summary>
    public static int Unsaved(SetupScreen screen, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        ArgumentNullException.ThrowIfNull(draft);
        return screen.Fields.Count(draft.Changes);
    }

    /// <summary>Check now anyway, as a link beside Save.</summary>
    public const string CheckWithout = "Check without them";

    /// <summary>The form's one line on why it is shown (the Save promise is in the footer).</summary>
    public const string SetupWhy = "Gordium reads the geometry. These are design decisions it can't see in the model.";

    // ---- the results' top (change 7) ---------------------------------------------------------------------------

    /// <summary>The first sentence under the state: where to start (what fails, then fix 1).</summary>
    public static string StartHere(int fails, int fixes) => fails > 0
        ? fixes > 0 ? "Start with what fails, just below; then fix 1." : "Start with what fails, just below."
        : fixes > 0 ? "Nothing fails. Start with fix 1 below." : "";

    /// <summary>How many results a filter shows (the rows placed in its sections: needs review counts the results to
    /// check by hand too, as the filter shows them).</summary>
    public static int FilterCount(IReadOnlyList<ListRow> placed, ListFilter filter)
    {
        ArgumentNullException.ThrowIfNull(placed);
        return filter switch
        {
            ListFilter.Fails => placed.Count(r => r.Section == ListSection.Fails),
            ListFilter.Review => placed.Count(r => r.Section is ListSection.Review or ListSection.ByHand),
            ListFilter.Complies => placed.Count(r => r.Section == ListSection.Complies),
            _ => placed.Count,
        };
    }

    /// <summary>The fold for the worker's count by law: "Counts by law (Zoning, Egress)".</summary>
    public static string CountsByLaw(IEnumerable<string?> laws, bool open) =>
        open ? "Hide the counts by law" : $"Counts by law ({string.Join(", ", laws.Where(l => l is not null))})";

    // ---- what changed (change 9) -------------------------------------------------------------------------------

    /// <summary>How many changed results are listed by name; the rest are counted.</summary>
    public const int ChangesListed = 4;

    /// <summary>Whether what changed is a list (some verdict changed), or the worker's one line ("Nothing changed
    /// since the check at 01:10.", "2 results say something new").</summary>
    public static bool ChangeIsList(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return change.Rows.Count > 0;
    }

    /// <summary>"Since 14:32 · 9 results changed" (UI polish change 40: results, the pane's one word; the time of the
    /// check before, when known).</summary>
    public static string ChangeHeading(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        // the results no longer in the check counted apart from those that changed (egress UI audit, finding 4: setting
        // the occupancy group took 148 rules for other groups out, and the heading said "196 results changed")
        var gone = change.Rows.Count(r => r.After is null);
        var n = change.Rows.Count - gone;
        var since = change.Since is { } at ? $"Since {at.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)} · " : "";
        var left = $"{gone} {(gone == 1 ? "result" : "results")} left the check";
        return gone == 0 ? $"{since}{n} result{(n == 1 ? "" : "s")} changed"
            : n == 0 ? since + left
            : $"{since}{n} result{(n == 1 ? "" : "s")} changed · {gone} left the check";
    }

    /// <summary>The changed results listed: the first <see cref="ChangesListed"/>, or every one once "Show all" is
    /// opened (<paramref name="all"/>), in the worker's order.</summary>
    public static IReadOnlyList<RowChange> ChangesShown(CheckChange change, bool all = false)
    {
        ArgumentNullException.ThrowIfNull(change);
        return all ? change.Rows : change.Rows.Take(ChangesListed).ToList();
    }

    /// <summary>"Show all 9" when more changed than are listed, "Show fewer" once open; null when every one is listed.</summary>
    public static string? ChangesMore(CheckChange change, bool all = false)
    {
        ArgumentNullException.ThrowIfNull(change);
        if (change.Rows.Count <= ChangesListed)
            return null;
        return all ? "Show fewer" : $"Show all {change.Rows.Count}";
    }

    /// <summary>What changed's one line when the architect changed a fact and no result changed at all (review round 2:
    /// "Nothing changed" beside "You changed: …" contradicted itself): "No result changed since 14:32."; else the
    /// checker's own line.</summary>
    public static string ChangeWords(CheckChange change, bool factsChanged)
    {
        ArgumentNullException.ThrowIfNull(change);
        return factsChanged && change.Rows.Count == 0 && change.Said == 0 && change.Compared
            ? "No result changed" + (change.Since is { } at ? $" since {at.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)}." : ".")
            : change.Words;
    }

    /// <summary>"2 more say something new (the same verdict)", or null.</summary>
    public static string? ChangesSaid(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return change.Said == 0 ? null
            : $"{change.Said} more result{(change.Said == 1 ? " says" : "s say")} something new with the same verdict.";
    }

    private static bool Same(SetupField a, SetupField b) =>
        a.Current == b.Current
        || a.Kind == b.Kind && a.Problem is null && b.Problem is null
           && (a.Kind == FieldKind.Feet ? a.HeldFeet is { } x && b.HeldFeet is { } y && x == y
               : a.CurrentChoice is { } c && b.CurrentChoice is { } d && c.Value == d.Value);

    /// <summary>What the architect changed between the two checks (change 40: "You changed: …"), from both checks'
    /// project facts as the Setup form reads them (null: not known for one of them); null when nothing changed.</summary>
    public static string? FactsChanged(IReadOnlyList<SetupField>? before, IReadOnlyList<SetupField>? after)
    {
        if (before is null || after is null)
            return null;
        var old = before.GroupBy(f => f.Mark.Guid).ToDictionary(g => g.Key, g => g.First());
        var said = new List<string>();
        foreach (var f in after)
        {
            // what it holds and whether Gordium can read it (a value that isn't one of its words is its own state: never
            // said as cleared, and a change into it is said; review after #190/#191)
            // a problem counts only when both reads could tell (the zone's and use's lists come with the place's options,
            // which one read may not have had: the same value is then no change)
            // the same value held is no change, whatever the project's units now show it in (a length or an area: its
            // exact feet or square feet) or however a word is typed (a choice the check reads the same; review after
            // main 7bdad7c5: m² for sq ft said "You changed" of an area nobody touched)
            if (!old.TryGetValue(f.Mark.Guid, out var o) || Same(o, f) && (o.Problem == f.Problem || o.Kind != f.Kind))
                continue;
            var label = SetupSteps.Title(f.Mark, f.Label);
            said.Add(f.Problem is not null && o.Kind == f.Kind ? $"{label}: a value Gordium can't read"
                     : f.Current is null ? $"{label} cleared"
                     : f.Kind == FieldKind.StreetPick ? $"{label} picked again"            // never the edge's coordinates
                     : $"{label}: {f.CurrentLabel}");
        }
        return said.Count == 0 ? null : "You changed: " + string.Join("; ", said) + ".";
    }

    /// <summary>What a screen reader says for What changed: every changed result, each on its line in the worker's
    /// order (the ones listed and the ones "Show all" opens: never a count of its own), then the results that say
    /// something new, in the card's own words (<see cref="ChangesSaid"/>; the count is the heading's, said before it:
    /// review round 5). A change that is no list: the worker's one line.</summary>
    public static string ChangesAll(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        if (!ChangeIsList(change))
            return change.Words;
        var lines = change.Rows.Select(r => "• " + r.Words).ToList();
        if (ChangesSaid(change) is { } said)
            lines.Add(said);
        return string.Join("\n", lines);
    }

    /// <summary>A changed result's glyph status: its new verdict's (<see cref="ChangeTone"/>) while the results
    /// stand, the clock once they are stale (never a green complies for a model that may have changed).</summary>
    public static PanelStatus ChangeStatus(RowChange change, bool stale) => StatusLook.Of(ChangeTone(change), stale);

    /// <summary>A changed result's glyph: its new verdict's (the worker's; complies only from a known complies).</summary>
    public static Tone ChangeTone(RowChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return change.After switch
        {
            Verdict.DoesNotComply => Tone.Fails,
            Verdict.Complies => Tone.Complies,
            Verdict.NotApplicable => Tone.Neutral,
            _ => Tone.Review,
        };
    }

    // ---- the error (change 10) and stale (change 11) states -----------------------------------------------------

    /// <summary>The error's title.</summary>
    public const string ErrorTitle = "Gordium couldn't finish this check";

    /// <summary>The error's one sentence: nothing passes, nothing changed.</summary>
    public const string ErrorWords = "Nothing was checked, so nothing here passes or fails. Your model wasn't changed.";

    /// <summary>The error's buttons.</summary>
    public const string TryAgain = "Try again";

    public const string CopyDetails = "Copy details for support";

    /// <summary>When stale results are from, by why: "before the model changed", "before the check you cancelled".
    /// Every stale wording of the pane (the banner, the state line, a copied row, a result's detail) says it from here.</summary>
    public static string StaleBefore(StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => "before the check you cancelled",
        _ => "before the model changed",
    };

    /// <summary>The state line's words once stale: "Does not comply (before the model changed)".</summary>
    public static string StaleState(string state, DateTime checkedAt) =>
        $"{state} (at {checkedAt.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)})";

    /// <summary>The header's second line once stale (UI polish change 39): "Checked 14:32 · model changed since".</summary>
    public static string StaleSub(StaleReason reason, DateTime checkedAt) => reason switch
    {
        StaleReason.Cancelled => $"Checked {checkedAt.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)} · a later check was cancelled",
        _ => $"Checked {checkedAt.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)} · model changed since",
    };

    /// <summary>A copied row once stale: "... (checked 14:32, before the check you cancelled)".</summary>
    public static string StaleCopy(string line, DateTime checkedAt, StaleReason reason) =>
        $"{line} (checked {checkedAt:HH:mm}, {StaleBefore(reason)})";

    /// <summary>A result's detail once stale: what it says first, and its Check again step's words.</summary>
    public static string StaleDetail(DateTime checkedAt, StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => $"These results are from {checkedAt:HH:mm}, {StaleBefore(reason)}: this verdict may no longer hold. Check again before acting on it.",
        _ => $"The model changed after this check ({checkedAt:HH:mm}): this verdict may no longer hold. Check again before acting on it.",
    };

    public static string StaleStep(StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => $"Check again: these results are from {StaleBefore(reason)}.",
        _ => "Check again: the model changed after this check.",
    };

    /// <summary>The ribbon badge's tooltip once stale (PR #168), by why.</summary>
    public static string StaleBadgeTip(StaleReason reason, string at) => reason switch
    {
        StaleReason.Cancelled => $"These results are from the {at} check, {StaleBefore(reason)}. Click to check again.",
        _ => $"The model changed after the {at} check. Click to check again.",
    };

    /// <summary>The selection strip's line once stale (PR #168), by why: "2 results mentioned it at 14:32. The model
    /// changed since." (UI polish strings, selection strip).</summary>
    public static string StaleSelection(string mentioned, string at, StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => $"{mentioned} at the check at {at}, {StaleBefore(reason)}, so check again.",
        _ => $"{mentioned} at {at}. The model changed since.",
    };

    /// <summary>Why no compliance summary is made of stale results (PR #168), by why.</summary>
    public static string StaleSummaryRefusal(string at, StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => $"These results are from the check at {at}, {StaleBefore(reason)}, so they may not hold: click Check project, then save the summary.",
        _ => $"The model changed after the check at {at}, so its results may not hold: click Check project, then save the summary.",
    };

    /// <summary>The stale banner's title, from why: "The model changed after this check (14:32)", or for a cancelled
    /// check "These results are from 14:32, before the check you cancelled".</summary>
    public static string StaleTitle(StaleReason reason, DateTime when) => reason switch
    {
        StaleReason.Cancelled => "Check cancelled",
        _ => "The model changed after this check",
    };

    /// <summary>What stale means for the results below, from why.</summary>
    public static string StaleWords(StaleReason reason, DateTime when) => reason switch
    {
        StaleReason.Cancelled => $"These results are from {when.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)}, before the check you cancelled, and may be out of date. They stay greyed until you check again.",
        _ => $"These results are from {when.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)} and may be out of date. They stay greyed until you check again.",
    };

    /// <summary>The check's progress card's title.</summary>
    public static string Checking(string? project) => $"Checking {project ?? "this project"}…";
}
