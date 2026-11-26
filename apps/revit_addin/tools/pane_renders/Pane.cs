using System.Windows;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>The add-in's own results view, driven step by step as the pane is (the callbacks only note what was asked).</summary>
internal sealed class Pane
{
    private readonly ResultsView _view;

    public Pane(PanelTheme theme, List<string> asked)
    {
        _view = new ResultsView(r => asked.Add("zoom " + r.Id), r => asked.Add("select " + r.Id), () => asked.Add("check again"),
                                () => asked.Add("project information"), c => asked.Add($"card {c.Action} {c.Elements.Count}"),
                                () => asked.Add("set up"), theme);
    }

    public FrameworkElement View => _view;

    public void Setup(string title, SetupScreen screen, SetupDraft draft, HashSet<string>? open = null)
    {
        var h = new SetupHandlers((_, _) => { }, (_, _) => { }, () => { }, () => { }, _ => { }, _ => { }, () => { }, () => { }, () => { }, () => { });
        _view.ShowSetup(title, screen, draft, h, null, open ?? []);
    }

    /// <summary>The street pick waiting for its click (the card over the form).</summary>
    public void Picking(bool on) => _view.Picking(on, () => { });

    public void Progress(CheckStage stage, DateTime since) => _view.Progress(stage, since);

    public void Show(string project, DateTime when, ResultModel model, IReadOnlyDictionary<string, string> labels,
                     IReadOnlyList<SetupField>? questions = null, string? key = null)
    {
        _view.EndProgress();
        _view.Show(new PanelContent(project, when, model, [], 0, labels, "", "", Questions: questions, Key: key));
    }

    /// <summary>The selection strip in its slot (as PaneExtras puts it there when something is selected in Revit).</summary>
    public void Strip(SelectionAnswer answer) =>
        _view.SelectionSlot.Child = SelectionStrip.Build(answer, _ => { }, () => _view.SelectionSlot.Child = null, all: false, showAll: () => { });

    /// <summary>The detail's "Answer N questions": back to the questions card.</summary>
    public void Answer() => _view.Answer();

    public IReadOnlyList<string> FirstFixRows => _view.Groups.Count == 0 ? [] : _view.Groups[0].Rows;

    public void OpenFirstFix() => _view.SetOpen(_view.Groups[0], true);

    public void OpenRow(string id) => _view.OpenRow(id);

    /// <summary>A result opened wherever it is (the way to it opened first), as the selection strip opens one.</summary>
    public void OpenResult(string id) => _view.OpenResult(id);

    /// <summary>Fixes shown at first, fixes in all, and the worker's cause cards.</summary>
    public (int Shown, int Total, int Cards) Cards => (Fixes.Shown(_view.Groups, _view.AllShown).Count, _view.Groups.Count, _view.AllCards.Count);

    public void Stale() => _view.MarkStale();

    /// <summary>The switch (UI polish PR 3): What to fix or By code.</summary>
    public void UseView(ResultsViewKind view) => _view.UseView(view);

    /// <summary>A group, card or node opened (or folded) by its key.</summary>
    public void Toggle(string key) => _view.ToggleOpen(key);

    public void Failed(CheckFailure failure) => _view.Failed(failure);

    /// <summary>The checker's progress line (its stage).</summary>
    public void Step(string words) => _view.Step(words);
}
