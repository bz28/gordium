using System.Windows;
using Gordium.Revit.Reading;
using Gordium.Revit.PanePrototype;

// PROTOTYPE: drives the add-in's own view (linked unchanged) for "today"'s renders.
namespace Gordium.Revit.Addin;

internal sealed class TodayPane : IPane
{
    private readonly ResultsView _view;

    public TodayPane(PanelTheme theme, List<string> asked)
    {
        _view = new ResultsView(r => asked.Add("zoom " + r.Id), r => asked.Add("select " + r.Id), () => asked.Add("check again"),
                                () => asked.Add("project information"), c => asked.Add($"card {c.Action} {c.Elements.Count}"),
                                () => asked.Add("set up"), theme);
    }

    public FrameworkElement View => _view;

    public string Name => "today";

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

    public IReadOnlyList<string> FirstCardRows => _view.AllCards.Count == 0 ? [] : _view.AllCards[0].Items;

    public void OpenFirstCard() => _view.SetOpen(_view.AllCards[0], true);

    public void OpenRow(string id) => _view.OpenRow(id);

    public (int Shown, int Total, int Actions) Cards => (CauseCards.Shown(_view.AllCards, _view.AllShown).Count, _view.AllCards.Count, _view.AllCards.Count);

    public void Stale() => _view.MarkStale();

    public void Failed(string words) => _view.Failed(words);
}
