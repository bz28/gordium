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

    public void Setup(string title, SetupScreen screen, SetupDraft draft)
    {
        var h = new SetupHandlers((_, _) => { }, (_, _) => { }, () => { }, () => { }, _ => { }, _ => { }, () => { }, () => { }, () => { });
        _view.ShowSetup(title, screen, draft, h, null, []);
    }

    public void Progress(CheckStage stage, DateTime since) => _view.Progress(stage, since);

    public void Show(string project, DateTime when, ResultModel model, IReadOnlyDictionary<string, string> labels)
    {
        _view.EndProgress();
        _view.Show(new PanelContent(project, when, model, [], 0, labels, "", ""));
    }

    public IReadOnlyList<string> FirstFixRows => _view.Groups.Count == 0 ? [] : _view.Groups[0].Rows;

    public void OpenFirstFix() => _view.SetOpen(_view.Groups[0], true);

    public void OpenRow(string id) => _view.OpenRow(id);

    /// <summary>Fixes shown at first, fixes in all, and the worker's cause cards.</summary>
    public (int Shown, int Total, int Cards) Cards => (Fixes.Shown(_view.Groups, _view.AllShown).Count, _view.Groups.Count, _view.AllCards.Count);

    public void Stale() => _view.MarkStale();

    public void Failed(string words) => _view.Failed(words);
}
