namespace Gordium.Revit.Reading;

/// <summary>One button on the Gordium tab (docs/revit/ui_design_pass.md section 2.2).</summary>
/// <param name="Id">Revit's name for the button, never changed (Revit keeps a Quick Access Toolbar copy under it).</param>
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

/// <summary>One panel of the Gordium tab and its buttons, in order.</summary>
public sealed record RibbonPanel(string Name, IReadOnlyList<RibbonButton> Buttons);

/// <summary>
/// The Gordium tab as data (docs/revit/ui_design_pass.md section 2.2): which panels and buttons exist, their words and
/// icons. An architect sees <b>Check</b> (Check project, Mark facts), <b>Results</b> (Panel) and <b>Help</b> (About);
/// the trial's test tools are in a <b>Trial</b> panel made only in a trial build or with <c>GORDIUM_TRIAL=1</c>. The
/// add-in builds the ribbon from this list (App.OnStartup), so what it shows is what is tested here. No Settings
/// button yet: there is nothing to set.
/// </summary>
public static class RibbonPlan
{
    public const string Tab = "Gordium";

    /// <summary>The environment variable that adds the Trial panel to any build: exactly "1" (spaces around it allowed).</summary>
    public const string TrialVariable = "GORDIUM_TRIAL";

    public const string CheckProject = "gordium_check_project";
    public const string MarkFacts = "gordium_mark_for_egress";
    public const string Panel = "gordium_results_panel";
    public const string About = "gordium_about";
    public const string CheckBoxHouse = "gordium_check_box_house";
    public const string RecordScenes = "gordium_record_scenes";
    public const string ReadInside = "gordium_read_interior";
    public const string RecordHouses = "gordium_record_houses";

    /// <summary>Whether the Trial panel is made: a trial build (install_trial_addin.ps1 builds one), or
    /// <c>GORDIUM_TRIAL</c> set to "1" in the environment Revit started with.</summary>
    public static bool TrialOn(bool trialBuild, string? variable) => trialBuild || variable?.Trim() == "1";

    private static readonly RibbonPanel Check = new("Check",
    [
        new(CheckProject, "Check\nproject", "Check this project against its zoning and egress rules",
            ["Reads the lot facts on Project Information, the site outside and the rooms, windows and doors inside.",
             "The results open in the Gordium panel, beside Properties.",
             "If a fact is missing, nothing is sent: the panel lists what to fill in."],
            RibbonIcons.CheckProject),
        new(MarkFacts, "Mark\nfacts", "List the facts Gordium needs from you, anything not set first",
            ["Adds Gordium's marks to this project if they aren't there, then lists every room, window and door.",
             "The list opens in a window, anything not set first; each mark is set in Properties.",
             "Nothing is checked or sent: set what is listed, then Check project."],
            RibbonIcons.MarkFacts),
    ]);

    private static readonly RibbonPanel Results = new("Results",
    [
        new(Panel, "Panel", "Show or hide the Gordium results panel",
            ["The panel keeps the last check's results; a result goes grey when the model changes after it.",
             "It docks beside Properties; Revit remembers where you put it."],
            RibbonIcons.Panel, AnyTime: true),
    ]);

    private static readonly RibbonPanel Help = new("Help",
    [
        new(About, "About", "Which Gordium build Revit loaded, and where its log is",
            ["Shows Revit's version, the add-in's build and the .NET runtime it runs on.",
             "Nothing is sent anywhere."],
            RibbonIcons.About, AnyTime: true),
    ]);

    private static readonly RibbonPanel Trial = new("Trial",
    [
        new(CheckBoxHouse, "Check box\nhouse", "Trial: check the box house scene against its hand-worked verdicts",
            ["Starts Gordium's checker and checks conformance scene 01 (the box house).",
             "Compares every row with the scene's hand-worked verdicts; the result is logged."],
            RibbonIcons.TrialTool),
        new(RecordScenes, "Record\nscenes", "Trial: draw and record every conformance scene",
            ["Draws each scene in a new Revit model and reads it as a check would.",
             "Records it to test_data/host_conformance/recorded/revit/ and checks it by the suite's rules."],
            RibbonIcons.TrialTool),
        new(ReadInside, "Read\ninside", "Trial: read this project's inside as a check would, and log it",
            ["Reads the rooms, escape windows, doors and stairs, and says what is left out and why.",
             "Nothing is sent to the checker."],
            RibbonIcons.TrialTool),
        new(RecordHouses, "Record\nhouses", "Trial: draw and record each hand-worked interior house",
            ["Draws each house in a new Revit project and reads it.",
             "Records it to test_data/interior_houses/recorded/revit/ and checks it against the hand-worked measures."],
            RibbonIcons.TrialTool),
    ]);

    /// <summary>The tab's panels in order: Check, Results, Help, then Trial when <paramref name="trial"/>.</summary>
    public static IReadOnlyList<RibbonPanel> Panels(bool trial) => trial ? [Check, Results, Help, Trial] : [Check, Results, Help];

    /// <summary>Every button on the tab, panel by panel.</summary>
    public static IEnumerable<RibbonButton> Buttons(bool trial) => Panels(trial).SelectMany(p => p.Buttons);
}
