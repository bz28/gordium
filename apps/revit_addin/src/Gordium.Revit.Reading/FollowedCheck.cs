namespace Gordium.Revit.Reading;

/// <summary>A check the ribbon badge, the selection strip and the summary follow (UI changes 13 to 15): what the pane
/// was given for it, in Revit-free terms.</summary>
/// <param name="Project">The project checked, by its title: for display only (a Save As changes it).</param>
/// <param name="When">When it was checked.</param>
/// <param name="Model">Its rows, or null when nothing was sent (a fact to set first: <paramref name="Missing"/>).</param>
/// <param name="Missing">How many facts are to be set before anything is checked.</param>
/// <param name="NotStated">A check sent anyway: each fact left out, in the pane's words.</param>
/// <param name="ClearWords">What happened to the makers' clear openings this run (drafts filled), "" when nothing.</param>
/// <param name="MarksAdded">How many of Gordium's marks this run added.</param>
/// <param name="Key">The document the check was run on, by identity (the add-in's DocKeys: never its title or path,
/// which a Save As changes), or null when not known: then any project's change makes it stale and any closing takes it
/// down (fail closed).</param>
public sealed record FollowedCheck(string Project, DateTime When, ResultModel? Model, int Missing = 0,
                                   IReadOnlyList<string>? NotStated = null, string ClearWords = "", int MarksAdded = 0,
                                   string? Key = null);

/// <summary>
/// Which check the badge, the selection strip and the summary follow, and whether it still stands (review round 1 of
/// changes 13 to 15), Revit-free so it is tested. It follows the last check the pane showed, keyed by its own
/// document's identity (<see cref="FollowedCheck.Key"/>, never a name: review round 2), not by what the pane shows now: the Setup form (a pane with no rows) never replaces it, and a change to that
/// project, or its closing, makes it stale or takes it down whichever project the pane shows. So the badge never keeps
/// a pass tick, and Summary never saves a check, after the model it was of changed.
/// </summary>
public sealed class FollowedState
{
    /// <summary>The check followed, or null when none (nothing checked, a check that failed, its project closed).</summary>
    public FollowedCheck? Check { get; private set; }

    /// <summary>Whether the last thing shown was a check that didn't finish (or its project closed).</summary>
    public bool Failed { get; private set; }

    /// <summary>The pane was given <paramref name="content"/>: null when it took its rows down (a failure, the project
    /// closed), else a check (rows, or facts to set first). A content with no rows and no fact to set is the Setup form
    /// (ResultsView.ShowSetup), not a check: the check followed is kept as it is, still made stale by its project's
    /// changes and taken down by its closing.</summary>
    public void Shown(FollowedCheck? content)
    {
        if (content is { Model: null, Missing: 0 })
            return;
        Check = content;
        Failed = content is null;
    }

    /// <summary>A change to the document keyed <paramref name="key"/> that changes the check (ResultRows.ChangesTheCheck):
    /// the check followed, if it is of that document (or of one not known), goes stale (its words kept, every colour the
    /// clock). Gives whether it did.</summary>
    public bool Changed(string key)
    {
        if (Check is not { Model: { Stale: null } model } check || !Mine(check, key))
            return false;
        Check = check with { Model = ResultRows.Stale(model, check.When) };
        return true;
    }

    /// <summary>The document keyed <paramref name="key"/> closing: the check followed, if it is of that document (or of
    /// one not known), taken down.</summary>
    public bool Closed(string key)
    {
        if (Check is null || !Mine(Check, key))
            return false;
        Check = null;
        Failed = true;
        return true;
    }

    private static bool Mine(FollowedCheck check, string key) => check.Key is null || string.Equals(check.Key, key, StringComparison.Ordinal);

    /// <summary>The badge for the check followed.</summary>
    public BadgeState Badge => Check is { } c ? RibbonBadge.Of(c.Model, c.When, c.Missing) : RibbonBadge.Of(null, default, failed: Failed);

    /// <summary>Why Summary can't save the check followed now, or null when it can.</summary>
    public string? SummaryRefusal => ComplianceSummary.Refusal(Check?.Model, Check?.When ?? default);

    /// <summary>The summary of the check followed (throws when <see cref="SummaryRefusal"/> refuses).</summary>
    public string SummaryHtml(DateTime madeAt)
    {
        if (SummaryRefusal is { } why || Check?.Model is not { } model)
            throw new InvalidOperationException(SummaryRefusal ?? "nothing checked");
        return ComplianceSummary.Html(model, Check.Project, Check.When, madeAt, Check.NotStated,
                                      ClearPrefills.PanelStatus(Check.MarksAdded, Check.ClearWords, stale: false));
    }
}
