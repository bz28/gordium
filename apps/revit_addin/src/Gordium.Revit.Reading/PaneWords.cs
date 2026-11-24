using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>What the pane shows at first: the welcome (nothing checked in it yet), the Setup form, or results.</summary>
public enum PaneShows { Welcome, Setup, Results, Error }

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

    /// <summary>The welcome's title.</summary>
    public const string WelcomeTitle = "Welcome to Gordium";

    /// <summary>The welcome's three lines: what Gordium does, that it never says pass without the facts, how to start.</summary>
    public static IReadOnlyList<(string Lead, string Words)> WelcomeLines { get; } =
    [
        ("What it does. ", "Checks this project, rule by rule, against its city's zoning and the state's egress code, with the law's exact words."),
        ("Never a false pass. ", "What Gordium can't measure or wasn't told is marked needs review, never complies."),
        ("To start: ", "click Check project. If a fact it needs is missing, it asks for it here first."),
    ];

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

    /// <summary>"4 facts needed; 3 chosen, not saved yet." (and the street edge's way, when it is still to pick).</summary>
    public static string SetupFooter(int needed, int chosen, bool streetToPick)
    {
        if (needed == 0)                                         // the form opened with everything set (Mark facts)
            return chosen == 0 ? "Every fact the check needs is set." : $"Every fact the check needs is set; {chosen} chosen, not saved yet.";
        // "chosen" is what Save writes (Unsaved), never only the needed ones: the footer and the button agree
        var words = $"{needed} {(needed == 1 ? "fact" : "facts")} needed; " + (chosen == 0 ? "none chosen yet" : $"{chosen} chosen, not saved yet");
        return words + (streetToPick ? ". The street edge is picked on the plan (Pick on plan, above)." : ".");
    }

    /// <summary>The Setup form's one button: "Save" (greyed with nothing chosen), "Save 3 facts", or "Save 3 facts and
    /// check" when saving them leaves nothing needed (the check then runs by itself: SetupGate.RunsByItself).</summary>
    public static string SaveAndCheck(int chosen, bool checksAfter) =>
        (chosen == 0 ? "Save" : $"Save {chosen} {(chosen == 1 ? "fact" : "facts")}") + (checksAfter && chosen > 0 ? " and check" : "");

    /// <summary>Whether Save runs the check: SetupGate's own rule (<see cref="SetupGate.RunsByItself"/>) on the form
    /// now and the form as it will be once the draft is written (each needed fact the architect chose, no longer
    /// needed). A form with nothing needed never checks on Save (Mark facts opened on a project already set).</summary>
    public static bool ChecksAfterSave(SetupScreen screen, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        ArgumentNullException.ThrowIfNull(draft);
        return SetupGate.RunsByItself(screen, screen with { Needed = StillNeeded(screen, draft) });
    }

    /// <summary>The needed facts the draft doesn't choose: what stays needed after Save.</summary>
    public static IReadOnlyList<string> StillNeeded(SetupScreen screen, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        ArgumentNullException.ThrowIfNull(draft);
        return screen.Needed.Where(n => !screen.Fields.Any(f => f.Mark.Name == n && draft.Chosen(f.Mark) is not null)).ToList();
    }

    /// <summary>The footer's words for a form and its draft: how many facts are needed (the form's Needed list), how
    /// many are chosen and not saved yet (<see cref="Unsaved"/>: the same count Save writes, so the footer and the
    /// button never disagree), and the street edge's way when it is still needed and not picked.</summary>
    public static string SetupFooter(SetupScreen screen, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        ArgumentNullException.ThrowIfNull(draft);
        return SetupFooter(screen.Needed.Count, Unsaved(screen, draft), StillNeeded(screen, draft).Contains(Marks.StreetEdge.Name));
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

    /// <summary>The form's one line on why it is shown.</summary>
    public const string SetupWhy = "Gordium can't read these from the model and never guesses them. Nothing is written until you click Save.";

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

    /// <summary>"WHAT CHANGED SINCE THE LAST CHECK · 9 verdicts".</summary>
    public static string ChangeHeading(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return $"WHAT CHANGED SINCE THE LAST CHECK · {change.Rows.Count} verdict{(change.Rows.Count == 1 ? "" : "s")}";
    }

    /// <summary>The changed results listed (the first <see cref="ChangesListed"/>, in the worker's order).</summary>
    public static IReadOnlyList<RowChange> ChangesShown(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return change.Rows.Take(ChangesListed).ToList();
    }

    /// <summary>"And 5 more changed verdicts; 2 more say something new (hover for all).", or null.</summary>
    public static string? ChangesMore(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        var rest = change.Rows.Count - Math.Min(ChangesListed, change.Rows.Count);
        var more = new List<string>();
        if (rest > 0)
            more.Add($"{rest} more changed verdict{(rest == 1 ? "" : "s")}");
        if (change.Said > 0)
            more.Add($"{change.Said} more say something new");
        return more.Count == 0 ? null : "And " + string.Join("; ", more) + " (hover for all).";
    }

    /// <summary>What "hover for all" shows: every changed verdict, each on its line in the worker's order (the ones
    /// listed and the ones <see cref="ChangesMore"/> counts: never a count of its own), then the results that say
    /// something new, counted as <see cref="ChangesMore"/> counts them. A change that is no list: the worker's one line.</summary>
    public static string ChangesAll(CheckChange change)
    {
        ArgumentNullException.ThrowIfNull(change);
        if (!ChangeIsList(change))
            return change.Words;
        var lines = new List<string> { $"{change.Rows.Count} changed verdict{(change.Rows.Count == 1 ? "" : "s")}:" };
        lines.AddRange(change.Rows.Select(r => "• " + r.Words));
        if (change.Said > 0)
            lines.Add($"{change.Said} more say something new");
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
    public static string StaleState(string state, StaleReason reason) => $"{state} ({StaleBefore(reason)})";

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
        StaleReason.Cancelled => $"These results are from the check at {at}, {StaleBefore(reason)}: they may not hold. Click to check again.",
        _ => $"The model changed after the check at {at}: its results may not hold. Click to check again.",
    };

    /// <summary>The selection strip's line once stale (PR #168), by why: "2 results mentioned it at the check at
    /// 14:32; the model changed since, so check again."</summary>
    public static string StaleSelection(string mentioned, string at, StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => $"{mentioned} at the check at {at}, {StaleBefore(reason)}, so check again.",
        _ => $"{mentioned} at the check at {at}; the model changed since, so check again.",
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
        StaleReason.Cancelled => $"These results are from {when:HH:mm}, {StaleBefore(reason)}",
        _ => $"The model changed after this check ({when:HH:mm})",
    };

    /// <summary>What stale means for the results below, from why.</summary>
    public static string StaleWords(StaleReason reason) => reason switch
    {
        StaleReason.Cancelled => "The model may have changed since: they are greyed until you check again.",
        _ => "Any result below may have changed: they are greyed until you check again.",
    };

    /// <summary>The check's progress card's title.</summary>
    public static string Checking(string? project) => $"Checking {project ?? "this project"}…";
}
