using System.Windows;
using Gordium.Revit.Reading;
using Gordium.Revit.PanePrototype;

// PROTOTYPE: drives the add-in's own view (linked unchanged) for "proposed"'s renders.
namespace Gordium.Revit.PanePrototype.Proposed;

internal sealed class ProposedPane : IPane
{
    private readonly ResultsView _view;

    public ProposedPane(PanelTheme theme, List<string> asked)
    {
        _view = new ResultsView(r => asked.Add("zoom " + r.Id), r => asked.Add("select " + r.Id), () => asked.Add("check again"),
                                () => asked.Add("project information"), c => asked.Add($"card {c.Action} {c.Elements.Count}"),
                                () => asked.Add("set up"), theme);
    }

    public FrameworkElement View => _view;

    public string Name => "proposed";

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

    public IReadOnlyList<string> FirstCardRows => _view.Groups.Count == 0 ? [] : _view.Groups[0].Rows;

    public void OpenFirstCard() => _view.SetOpen(_view.Groups[0], true);

    public void OpenRow(string id) => _view.OpenRow(id);

    public (int Shown, int Total, int Actions) Cards => (Math.Min(CardGroups.Top, _view.Groups.Count), _view.Groups.Count, _view.AllCards.Count);

    public void Stale() => _view.MarkStale();

    public void Failed(string words) => _view.Failed(words);
}
