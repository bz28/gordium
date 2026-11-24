namespace Gordium.Revit.Reading;

/// <summary>One button on the Gordium tab (docs/revit/ui_design_pass.md section 2.2).</summary>
/// <param name="Id">Revit's name for the button, kept stable. Revit names an add-in's Quick Access Toolbar copy and
/// keyboard shortcut by tab, panel and name, so moving a button to another panel loses them once: Mark facts, About,
/// Read inside and Record houses moved panels in the ribbon pass (PR 2): a copy or shortcut made before must be added
/// again by the architect, once (nothing restores it).</param>
/// <param name="Text">The words under the icon; a line break where Revit should wrap a large button's words.</param>
/// <param name="ToolTip">One line, shown on hover.</param>
/// <param name="LongDescription">Up to three short lines, shown on a longer hover (Revit's LongDescription).</param>
/// <param name="Icon">The icon's name in <see cref="RibbonIcons"/>.</param>
/// <param name="AnyTime">Usable with no project open (Panel, About); the others keep Revit's default for an add-in
/// command (usable once a project is open), as before.</param>
public sealed record RibbonButton(string Id, string Text, string ToolTip, IReadOnlyList<string> LongDescription, string Icon,
                                  bool AnyTime = false)
{
    /// <summary>The button's words on one line ("Check project").</summary>
    public string Name => Text.Replace('\n', ' ');

    /// <summary>The long description as Revit takes it: its lines joined by line breaks.</summary>
    public string LongDescriptionText => string.Join("\n", LongDescription);
}

/// <summary>A pull-down on a panel (one button that drops its own list): the trial's test tools in one "Trial"
/// pull-down, out of the architect's way (UI polish, change 48).</summary>
/// <param name="Id">Revit's name for the pull-down.</param>
/// <param name="Text">Its words under the icon.</param>
/// <param name="ToolTip">One line, shown on hover.</param>
/// <param name="Icon">The icon's name in <see cref="RibbonIcons"/>.</param>
/// <param name="Buttons">Its buttons, in order.</param>
public sealed record RibbonPulldown(string Id, string Text, string ToolTip, string Icon, IReadOnlyList<RibbonButton> Buttons);

/// <summary>One panel of the Gordium tab: its buttons, in order, then its pull-down (if any).</summary>
public sealed record RibbonPanel(string Name, IReadOnlyList<RibbonButton> Buttons, RibbonPulldown? Pulldown = null)
{
    /// <summary>Every button the panel holds: its own, then its pull-down's.</summary>
    public IEnumerable<RibbonButton> All => Pulldown is null ? Buttons : Buttons.Concat(Pulldown.Buttons);
}

/// <summary>
/// The Gordium tab as data (docs/revit/ui_design_pass.md section 2.2; UI polish change 48, Ben 2026-11-23): which panels
/// and buttons exist, their words and icons. An architect sees <b>Check</b> (Check project, Set up), <b>Results</b>
/// (Results, Summary) and <b>Help</b> (About); the trial's test tools are one <b>Trial</b> pull-down on the Help panel,
/// made only in a trial build or with <c>GORDIUM_TRIAL=1</c>. The add-in builds the ribbon from this list
/// (App.OnStartup), so what it shows is what is tested here. No Settings button yet: there is nothing to set.
/// </summary>
public static class RibbonPlan
{
    public const string Tab = "Gordium";

    /// <summary>The results pane's title, and its header's (design pass section 2.3: one pane, "Gordium"; the pane id
    /// stays the same, so Revit keeps where it is docked).</summary>
    public const string PaneTitle = "Gordium";

    /// <summary>The environment variable that adds the Trial panel to any build: exactly "1" (spaces around it allowed).</summary>
    public const string TrialVariable = "GORDIUM_TRIAL";

    public const string CheckProject = "gordium_check_project";
    public const string MarkFacts = "gordium_mark_for_egress";
    public const string Panel = "gordium_results_panel";
    public const string About = "gordium_about";
    public const string Summary = "gordium_summary";
    public const string CheckBoxHouse = "gordium_check_box_house";
    public const string RecordScenes = "gordium_record_scenes";
    public const string ReadInside = "gordium_read_interior";
    public const string RecordHouses = "gordium_record_houses";
    public const string TrialMenu = "gordium_trial";

    /// <summary>Whether the Trial panel is made: a trial build (install_trial_addin.ps1 builds one), or
    /// <c>GORDIUM_TRIAL</c> set to "1" in the environment Revit started with.</summary>
    public static bool TrialOn(bool trialBuild, string? variable) => trialBuild || variable?.Trim() == "1";

    private static readonly RibbonPanel Check = new("Check",
    [
        new(CheckProject, "Check\nproject", "Check this design against Ithaca zoning and NY egress",
            ["Results open in the Gordium pane.",
             "Adds Gordium's fields if missing (and a maker's clear opening as a draft), then reads the model.",
             "If a fact is missing (zone, use…), the pane asks for it first."],
            RibbonIcons.CheckProject),
        new(MarkFacts, "Set\nup", "The facts Gordium can't read from the model: lot, use, escape openings, exits",
            ["Opens Setup in the Gordium pane: choose each fact there; nothing is written until you click Save.",
             "Adds Gordium's fields if missing (and a maker's clear opening as a draft)."],
            RibbonIcons.MarkFacts),
    ]);

    private static readonly RibbonPanel Results = new("Results",
    [
        new(Panel, "Results", "Show or hide the Gordium pane",
            ["Results go grey when the model changes after a check.",
             "It docks beside Properties; Revit remembers where you put it."],
            RibbonIcons.Panel, AnyTime: true),
        new(Summary, "Summary", "A printable summary of the last check (not a permit or approval)",
            ["Every result: proposed, required, its verdict and the code's exact words, as the checker said them.",
             "Opens in your browser to print or save as PDF; every needs review is for you to resolve.",
             "Only for results that still stand: after a change to the model, check again first."],
            RibbonIcons.Summary),
    ]);

    private static readonly RibbonButton AboutButton = new(About, "About", "Which Gordium build Revit loaded, and where its log is",
        ["Shows Revit's version, the add-in's build and the .NET runtime it runs on.",
         "Nothing is sent anywhere."],
        RibbonIcons.About, AnyTime: true);

    private static readonly RibbonPanel Help = new("Help", [AboutButton]);

    /// <summary>The trial's test tools, one pull-down (shown only in a trial build or with GORDIUM_TRIAL=1).</summary>
    private static readonly RibbonPulldown TrialTools = new(TrialMenu, "Trial", "Trial tools: test scenes and recordings (not for design work)",
        RibbonIcons.TrialTool,
    [
        new(CheckBoxHouse, "Check box house", "Trial: check the box house scene against its hand-worked verdicts",
            ["Starts Gordium's checker and checks conformance scene 01 (the box house).",
             "Compares every row with the scene's hand-worked verdicts; the result is logged."],
            RibbonIcons.TrialTool),
        new(RecordScenes, "Record scenes", "Trial: draw and record every conformance scene",
            ["Draws each scene in a new Revit model and reads it as a check would.",
             "Records it to test_data/host_conformance/recorded/revit/ and checks it by the suite's rules."],
            RibbonIcons.TrialTool),
        new(ReadInside, "Read inside", "Trial: read this project's inside as a check would, and log it",
            ["Reads the rooms, escape windows, doors and stairs, and says what is left out and why.",
             "Nothing is sent to the checker."],
            RibbonIcons.TrialTool),
        new(RecordHouses, "Record houses", "Trial: draw and record each hand-worked interior house",
            ["Draws each house in a new Revit project and reads it.",
             "Records it to test_data/interior_houses/recorded/revit/ and checks it against the hand-worked measures."],
            RibbonIcons.TrialTool),
    ]);

    /// <summary>The tab's panels in order: Check, Results, Help (with the Trial pull-down when <paramref name="trial"/>).</summary>
    public static IReadOnlyList<RibbonPanel> Panels(bool trial) =>
        [Check, Results, trial ? Help with { Pulldown = TrialTools } : Help];

    /// <summary>Every button on the tab, panel by panel (a pull-down's buttons after its panel's own).</summary>
    public static IEnumerable<RibbonButton> Buttons(bool trial) => Panels(trial).SelectMany(p => p.All);
}
