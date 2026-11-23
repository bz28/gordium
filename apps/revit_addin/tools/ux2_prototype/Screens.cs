using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static Gordium.Revit.Ux2Prototype.T;

namespace Gordium.Revit.Ux2Prototype;

/// <summary>The proposed screens, each a function of screens.json (the checker's rows, counted by make_screens.py) and
/// the proposal's words. Every screen keeps the rules: never a false pass (no green over anything that needs review or
/// isn't checked), needs review is never green, the pane works out no verdict, nothing is written without a click.</summary>
internal static class Screens
{
    public static JsonElement Data;

    static JsonElement Apt => Data.GetProperty("apartment");
    static JsonElement House => Data.GetProperty("house");
    static int N(JsonElement e, string k) => e.GetProperty(k).GetInt32();

    /// <summary>How many of the checker's rows wait on a project fact (make_screens.py's count).</summary>
    static int Fact(string label) => Apt.GetProperty("actions")[0].GetProperty("entries").EnumerateArray()
        .Where(e => e.GetProperty("label").GetString() == label).Select(e => e.GetProperty("count").GetInt32()).FirstOrDefault();
    static string S(JsonElement e, string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";

    // ---- the pane's frame: Revit's dock title, then the header ------------------------------------------------

    public static FrameworkElement Frame(UIElement header, UIElement body, UIElement? footer = null)
    {
        var dock = new DockPanel { Background = Pane, LastChildFill = true };
        var title = new Border
        {
            Background = Chrome, Padding = new Thickness(6, 3, 6, 4),
            Child = Row(Tx("Gordium", Body, fg: ChromeText, wrap: false), Tx("✕", Small, fg: ChromeText, wrap: false)),
        };
        DockPanel.SetDock(title, Dock.Top);
        dock.Children.Add(title);
        var head = new Border { Padding = new Thickness(12, 10, 12, 8), Child = header, BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) };
        DockPanel.SetDock(head, Dock.Top);
        dock.Children.Add(head);
        if (footer is not null)
        {
            var foot = new Border { Padding = new Thickness(12, 10, 12, 12), Child = footer, Background = Surface, BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0) };
            DockPanel.SetDock(foot, Dock.Bottom);
            dock.Children.Add(foot);
        }
        dock.Children.Add(new Border { Padding = new Thickness(12, 4, 12, 16), Child = body });
        return dock;
    }

    static UIElement Header(string title, string sub, UIElement? action = null, FrameworkElement? subIcon = null)
    {
        var words = V(Tx(title, Title, semi: true, wrap: false),
                      subIcon is null ? Tx(sub, Small, fg: Muted, top: 1) : WithIcon(subIcon, Tx(sub, Small, fg: Muted), 5, 1));
        if (action is FrameworkElement a)
            a.VerticalAlignment = VerticalAlignment.Top;
        return Row(words, action);
    }

    // ---- 01 welcome -------------------------------------------------------------------------------------------

    public static FrameworkElement Welcome() => Frame(
        Header("Four-unit apartment", "Not checked yet"),
        V(
            Card(V(
                Tx("Check this design against the code", Heading, semi: true),
                Tx("Gordium measures your model and checks it, rule by rule, against Ithaca zoning and the New York State egress code.", Body, fg: Muted, top: 4),
                WithIcon(Icon("doc"), Tx("Every result shows the code's own words and page.", Body), top: 12),
                WithIcon(Icon("review"), Tx("If Gordium can't measure something, it says Needs review. It never guesses a pass.", Body), top: 8),
                WithIcon(Icon("drawing"), Tx("Nothing is written to your model unless you click Save.", Body), top: 8),
                Btn("Check project", primary: true, top: 14),
                Tx("Also on the ribbon: Gordium › Check project", Small, fg: Muted, top: 6)), top: 8)));

    // ---- 02/03 Setup: only what the check needs; the rest folded -------------------------------------------------

    static UIElement Fact(int n, string label, UIElement control, string help, string? state = null, Brush? stateFg = null)
    {
        var title = Row(Tx($"{label}", Body, semi: true, wrap: false),
                        state is null ? null : Tx(state, Small, fg: stateFg ?? Muted, wrap: false));
        return WithIcon(new Border
        {
            Width = 18, Height = 18, CornerRadius = new CornerRadius(9), VerticalAlignment = VerticalAlignment.Top, Background = state == "Set" ? PassFill : Sunken,
            Child = new TextBlock { Text = state == "Set" ? "✓" : n.ToString(), FontSize = 10.5, FontWeight = FontWeights.SemiBold, Foreground = state == "Set" ? Pass : Muted, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center },
        }, V(title, control, Tx(help, Small, fg: Muted, top: 3)), 8, 12);
    }

    public static FrameworkElement Setup(bool filled)
    {
        var set = filled ? 4 : 0;
        var lot = V(
            Overline("The lot", top: 14),
            Fact(1, "Zoning district", Dropdown(filled ? "R-3a" : null, "Choose the district"), "As the City's zoning map shows it.", filled ? "Set" : null),
            Fact(2, "Use", Dropdown(filled ? "Multiple family dwelling" : null, "Choose the use"), "As the zoning chart names it.", filled ? "Set" : null),
            Fact(3, "Property line drawn from", Top(Segmented(["Survey", "Tax map"], filled ? 1 : -1, stretch: true), 4),
                 filled ? "Tax map lines are ±2 ft, so lot area and coverage will need review." : "A survey, or traced from the tax map?", filled ? "Set" : null),
            Fact(4, "Street edge", Top(H(8, Btn(filled ? "Pick again" : "Pick on plan"), Tx(filled ? "South edge, 100'-0\"" : "Not picked", Body, fg: Muted, top: 4)), 4),
                 "Click the lot edge along the street in a plan.", filled ? "Set" : null));
        var model = V(
            Overline("In the model", top: 18),
            Fact(5, "Escape openings", Top(H(8, Btn("Select 10"), Link("Why?")), 4), "0 of 10 doors and windows marked Yes or No."),
            Fact(6, "Exit doors", Top(H(8, Btn("Select 10"), Btn("Accept 2 suggestions")), 4), "0 of 10 doors marked. Gordium suggests the doors to the outside."));
        var recommended = V(
            Overline("Recommended for this building", top: 18),
            Card(V(
                Tx("The NY Building Code governs this building. Two facts decide most of its egress limits:", Small, fg: Muted),
                Row(Tx("Occupancy group", Body, semi: true), Tx($"{Fact("Occupancy group")} results", Small, fg: Muted), top: 8),
                Dropdown(null, "Choose the groups"),
                Row(Tx("Sprinkler system", Body, semi: true), Tx($"{Fact("Sprinkler system")} results", Small, fg: Muted), top: 8),
                Dropdown(null, "Choose the system")), top: 0));
        var more = Card(Row(WithIcon(Chevron(false), V(Tx("More facts (optional)", Body, semi: true), Tx("Corner lot, ADU, dwelling units and 14 more. Gordium asks for one when a result needs it.", Small, fg: Muted, top: 2)), 8)), top: 10);
        var body = V(
            Callout(V(Tx("Set 6 things to check this project", Heading, semi: true),
                      Tx("Gordium reads the geometry. These are design decisions it can't see in the model.", Small, fg: Muted, top: 2),
                      Row(Tx($"{set} of 6 set", Small, semi: true, fg: Muted), null, 6),
                      CountBar(0, 0, 6 - set, set, 4)), Surface, Line, top: 8),
            lot, model, recommended, more);
        var foot = V(
            H(10, Btn(filled ? "Save 4 and check" : "Save and check", primary: true, disabled: !filled), Link("Check without them")),
            Tx(filled ? "Saves 4 facts to Project Information (one undo). Escape openings and exit doors still need marking: their rules will need review." :
                        "A fact left blank makes its rules Needs review, never a pass.", Small, fg: Muted, top: 6));
        return Frame(Header("Four-unit apartment", "Not checked yet"), body, foot);
    }

    public static FrameworkElement SetupMoreOpen()
    {
        static UIElement YN(string q, string? help = null, int sel = -1) => V(Row(Tx(q, Body), Segmented(["Yes", "No"], sel)), help is null ? null : Tx(help, Small, fg: Muted, top: 2));
        var body = V(
            Card(Row(WithIcon(Chevron(true), Tx("More facts (optional)", Body, semi: true), 8)), top: 8),
            Overline("The lot"),
            YN("Corner lot (on two streets)?"), Top(new Border(), 8),
            YN("Next to R-1 land?", "Touching, or across a street or creek from R-1a or R-1b."),
            Top(new Border(), 8), YN("Stream or inlet within 20 ft?"),
            Overline("Dwellings"),
            Row(Tx("Dwelling units", Body), Dropdown("4", "", 0)), Top(new Border(), 8),
            YN("Accessory dwelling unit on the lot?"), Top(new Border(), 8),
            YN("Home business planned?"),
            Overline("Building code"),
            Row(Tx("Stories above grade plane", Body), Dropdown(null, "From the model", 0)),
            Top(new Border(), 8), YN("Designed to the Building Code anyway?", "Only if you chose to; Gordium otherwise picks the code from the use."),
            Overline("What is drawn"),
            WithIcon(Tick(false), Tx("These are all the stairs", Body), 0, 2),
            WithIcon(Tick(false), Tx("These are all the guards and handrails", Body), 0, 6),
            Tx("Each answer is saved to Project Information when you click Save. Blank is fine: Gordium says what it couldn't decide.", Small, fg: Muted, top: 12));
        return Frame(Header("Four-unit apartment", "Not checked yet"), body,
                     V(H(10, Btn("Save 4 and check", primary: true), Link("Check without them"))));
    }

    // ---- 04 the street pick: the pane says what Revit waits for, and the dialog ends it ------------------------

    public static FrameworkElement Picking() => Frame(
        Header("Four-unit apartment", "Not checked yet", Btn("Cancel")),
        V(Callout(WithIcon(Icon("pin"), V(
                Tx("Click the lot edge along the street", Heading, semi: true),
                Tx("In any plan that shows the property line. Gordium asks you to confirm the edge before it keeps it.", Small, fg: Muted, top: 2),
                Tx("Esc cancels.", Small, fg: Muted, top: 6))), AccentFill, Accent, top: 8),
          Tx("The form stays as you left it.", Small, fg: Muted, top: 10)));

    public static FrameworkElement PickConfirm()
    {
        // a Revit TaskDialog with command links: one click ends the pick (no silent wait for Esc after Yes)
        var body = V(
            Tx("Use this edge as the street line?", Heading, semi: true, fg: Brushes.Black),
            Tx("The south edge of the lot, 100'-0\" long, is highlighted in the plan.", Body, fg: Brushes.Black, top: 6),
            CmdLink("Use this edge", "Gordium keeps it and goes back to Setup."),
            CmdLink("Use it, and pick another street edge", "For a corner lot or a lot on two streets."),
            CmdLink("Pick a different edge", "This click is forgotten."));
        var dlg = new Border
        {
            Background = Brushes.White, BorderBrush = new SolidColorBrush(Color.FromRgb(0x9A, 0x9A, 0x9A)), BorderThickness = new Thickness(1),
            Width = 420, Child = new DockPanel
            {
                Children =
                {
                    Docked(new Border { Background = Brushes.White, Padding = new Thickness(10, 6, 10, 6), Child = Tx("Gordium: street edge", Small, fg: Brushes.Black) }, System.Windows.Controls.Dock.Top),
                    Docked(new Border { Background = new SolidColorBrush(Color.FromRgb(0xF0, 0xF0, 0xF0)), Padding = new Thickness(10, 8, 10, 8), Child = Row(new Border(), new Border { Child = Tx("Cancel", Body, fg: Brushes.Black), BorderBrush = Brushes.Gray, BorderThickness = new Thickness(1), Padding = new Thickness(14, 2, 14, 3) }) }, System.Windows.Controls.Dock.Bottom),
                    new Border { Padding = new Thickness(16, 12, 16, 14), Child = body },
                },
            },
        };
        return new Border { Background = CanvasBg, Padding = new Thickness(20), Child = dlg };

        static UIElement CmdLink(string a, string b) => new Border
        {
            Margin = new Thickness(0, 10, 0, 0), Padding = new Thickness(8, 4, 8, 6),
            Child = WithIcon(Tx("➜", Heading, fg: new SolidColorBrush(Color.FromRgb(0x15, 0x6F, 0x2E))), V(Tx(a, Heading, fg: new SolidColorBrush(Color.FromRgb(0x15, 0x3E, 0x9E))), Tx(b, Small, fg: Brushes.DimGray)), 8),
        };
    }

    static UIElement Docked(UIElement e, System.Windows.Controls.Dock d)
    {
        DockPanel.SetDock(e, d);
        return e;
    }

    // ---- 05 checking -------------------------------------------------------------------------------------------

    public static FrameworkElement Checking(int seconds) => Frame(
        Header("Four-unit apartment", "Not checked yet", Btn("Cancel")),
        V(Card(V(
            Tx("Checking Four-unit apartment", Heading, semi: true),
            WithIcon(Icon("check"), Row(Tx("Read the model", Body), Tx("2 s", Small, fg: Muted)), top: 10),
            WithIcon(Icon("spinner"), Row(Tx("Checking zoning and egress rules", Body, semi: true), Tx($"{seconds} s", Small, fg: Muted)), top: 6),
            WithIcon(new Border { Width = 14 }, Tx("Showing results", Body, fg: Faint), top: 6),
            Divider(10),
            Tx("You can keep working in Revit. If you edit the model now, these results will be marked out of date.", Small, fg: Muted, top: 8),
            seconds > 40 ? Tx("Large models can take a minute or two.", Small, fg: Muted, top: 4) : null), top: 8)));

    // ---- 06 results: two views, one click apart ------------------------------------------------------------------

    static Border Switch(int sel) => Segmented(["What to fix", "By code"], sel, top: 0, stretch: true);

    static UIElement Summary(JsonElement t, string headline, string sub)
    {
        var fail = N(t, "fail"); var review = N(t, "review"); var notyet = N(t, "notyet"); var pass = N(t, "pass");
        var kind = fail > 0 ? "fail" : review + notyet > 0 ? "review" : "pass";
        var parts = new List<string>();
        if (fail > 0) parts.Add($"{fail} fail{(fail == 1 ? "s" : "")}");
        if (review > 0) parts.Add($"{review} need review");
        if (notyet > 0) parts.Add($"{notyet} not checked yet");
        if (pass > 0) parts.Add($"{pass} compl{(pass == 1 ? "ies" : "y")}");
        return V(
            WithIcon(Icon(kind, 16), V(Tx(headline, Heading + 1, semi: true, fg: StateBrush(kind)), Tx(sub, Small, fg: Muted, top: 1)), 8, 12),
            CountBar(fail, review, notyet, pass, 8),
            Tx(string.Join(" · ", parts), Small, fg: Muted, top: 4));
    }

    static UIElement ActionCard(int n, JsonElement a, bool open = false)
    {
        var kind = S(a, "kind");
        var count = N(a, "count");
        var body = V(
            Row(Tx(S(a, "title"), Body, semi: true), Tx(kind == "notyet" ? $"{count}" : $"{count} results", Small, fg: Muted)),
            Tx(S(a, "sub"), Small, fg: Muted, top: 2));
        if (kind == "facts" && !open)
        {
            var chips = new WrapPanel { Margin = new Thickness(0, 6, 0, 0) };
            var i = 0;
            foreach (var e in a.GetProperty("entries").EnumerateArray())
            {
                if (i++ == 3) { chips.Children.Add(Tx($"+{a.GetProperty("entries").GetArrayLength() - 3} more", Small, fg: Muted, top: 2)); break; }
                var chip = Pill(S(e, "label"), Text, Sunken); chip.Margin = new Thickness(0, 0, 4, 4); chips.Children.Add(chip);
            }
            body.Children.Add(chips);
        }
        if (kind == "facts" && open)
        {
            foreach (var e in a.GetProperty("entries").EnumerateArray().Take(5))
            {
                var label = S(e, "label");
                UIElement control = label is "Occupancy group" or "Sprinkler system" or "Dwelling units"
                    ? Dropdown(null, label == "Dwelling units" ? "How many?" : "Choose…", 2)
                    : Top(Segmented(["Yes", "No"], -1), 2);
                body.Children.Add(Top(new Border(), 10));
                body.Children.Add(Row(Tx(S(e, "ask"), Body), Tx($"{N(e, "count")} results", Small, fg: Muted)));
                body.Children.Add(control);
                if (label == "Occupancy group")
                    body.Children.Add(Tx(S(e, "why").Split(" Today")[0], Small, fg: Muted, top: 2));
            }
            body.Children.Add(Link($"+ {a.GetProperty("entries").GetArrayLength() - 5} more questions", Small, 8));
            body.Children.Add(Callout(WithIcon(Icon("info"), Tx("Gordium's Building Code egress rules are drafted for day care (Group I-4) so far. For an R-2 building, most egress results will stay Needs review: check egress by hand.", Small)), AccentFill, Line, 10));
            body.Children.Add(H(10, Top(Btn("Save and check again", primary: true), 10), Top(Link("Open Project Information"), 14)));
        }
        else if (S(a, "button") is { Length: > 0 } b)
            body.Children.Add(H(10, Top(Btn(b, primary: n == 1), 8), Top(Link($"See {count} results", Small), 12)));
        else if (kind != "notyet")
            body.Children.Add(Top(Link($"See {count} results", Small), 6));
        var icon = Icon(kind);
        return Card(WithIcon(icon, body, 10), edge: kind == "notyet" ? null : n == 1 ? Review : null, fill: kind == "notyet" ? Pane : null, top: 8);
    }

    public static FrameworkElement ResultsFix(bool open = false)
    {
        var a = Apt;
        var body = V(Top(Switch(0), 8),
            Summary(a.GetProperty("totals"), "Needs review", "Nothing fails yet. 98 results can't be decided until the questions below are answered."));
        body.Children.Add(Overline("Start here · by what you can do", 16));
        var n = 1;
        foreach (var x in a.GetProperty("actions").EnumerateArray())
        {
            if (open && n > 2) break;
            body.Children.Add(ActionCard(n, x, open && n == 1));
            n++;
        }
        if (!open)
            body.Children.Add(Top(Row(WithIcon(Chevron(false), Tx("Complies or doesn't apply (2)", Body, fg: Muted), 8)), 14));
        return Frame(Header("Four-unit apartment", "Checked 14:32 · R-3a · Multiple family", Btn("Check again", primary: true)), body);
    }

    public static FrameworkElement ResultsHouse()
    {
        var h = House;
        var f = h.GetProperty("fails")[0];
        var body = V(Top(Switch(0), 8),
            Summary(h.GetProperty("totals"), "Does not comply", "1 rule fails. Fix it first; 132 results also need review."),
            Overline("Fails · 1", 16),
            Card(WithIcon(Icon("fail"), V(
                Row(Tx("Lot coverage", Body, semi: true), Tx("§325-8", Small, fg: Muted)),
                Tx($"{S(f, "measured")} measured · {S(f, "limit")} allowed", Body, top: 2),
                Tx("3.24% over: about 213 sf of footprint", Small, fg: Fail, top: 1),
                H(10, Top(Btn("Show in model"), 8), Top(Link("Details", Small), 12))), 10), edge: Fail),
            Overline("Then · by what you can do", 18),
            Card(WithIcon(Icon("facts"), V(Row(Tx("Answer 12 questions about the project", Body, semi: true), Tx("18 results", Small, fg: Muted)),
                Tx("ADU on the lot, all the stairs drawn, all the guards drawn, garage cars and 8 more.", Small, fg: Muted, top: 2),
                H(10, Top(Btn("Answer here", primary: false), 8), Top(Link("See 18 results", Small), 12))), 10)),
            Card(WithIcon(Icon("drawing"), V(Row(Tx("Mark the stairs and escape windows", Body, semi: true), Tx("61 results", Small, fg: Muted)),
                Tx("The stairs and escape windows weren't sent from the model, so their rules can't be measured.", Small, fg: Muted, top: 2),
                H(10, Top(Btn("Select them"), 8), Top(Link("See 61 results", Small), 12))), 10)),
            Card(WithIcon(Icon("byhand"), V(Row(Tx("Measure 8 kinds of part by hand", Body, semi: true), Tx("54 results", Small, fg: Muted)),
                Tx("Handrails, ramps, ladders, lofts: Gordium doesn't read these from Revit yet.", Small, fg: Muted, top: 2)), 10)),
            Top(Row(WithIcon(Chevron(false), Tx("2 more · Complies (10) · Not checked yet (9)", Body, fg: Muted), 8)), 14));
        return Frame(Header("106 Ithaca Rd", "Checked 14:32 · R-1b · One-family, detached", Btn("Check again", primary: true)), body);
    }

    // ---- 07 a result's detail: a headline, the why on demand --------------------------------------------------

    public static FrameworkElement Detail(bool why)
    {
        var d = Apt.GetProperty("detail");
        var body = V(
            Top(Row(H(6, Tx("‹  Back", Body, fg: Accent)), H(8, Tx(S(d, "position"), Small, fg: Muted, top: 1), Tx("‹", Body, fg: Accent), Tx("›", Body, fg: Accent))), 8),
            WithIcon(Icon("review"), Tx("NEEDS REVIEW", 10.5, semi: true, fg: Review), 6, 14),
            Tx(S(d, "title"), Title, semi: true, top: 4),
            Tx(S(d, "where"), Small, fg: Muted, top: 2),
            Callout(V(
                Tx(S(d, "headline"), Body, semi: true),
                H(10, Top(Btn("Answer 2 questions", primary: true), 8), Top(Link(why ? "Hide why" : "Why?", Small), 12)),
                why ? V(Overline("In the checker's words", 12), Tx(S(d, "why").Split(": ", 2)[^1], Small, fg: Muted)) : null), ReviewFill, Line, 10),
            Overline("What to do", 18),
            Tx("1.  " + d.GetProperty("steps")[0].GetString(), Body),
            Tx("2.  " + d.GetProperty("steps")[1].GetString(), Body, top: 4),
            Tx("3.  Check again. Only a check changes a verdict.", Body, top: 4),
            Overline("What the code says", 18),
            new Border
            {
                BorderBrush = Line, BorderThickness = new Thickness(2, 0, 0, 0), Padding = new Thickness(10, 0, 0, 0),
                Child = V(Tx("“" + S(d, "quote").Replace("1006.2.1 Egress based on occupant load and common path of egress travel distance. ", "") + "…”", Body, italic: false),
                          Tx(S(d, "quote_where"), Small, fg: Muted, top: 4)),
            },
            H(10, Top(Btn("Open the code at p.315"), 10), Top(Link("Copy", Small), 14)),
            Top(Row(WithIcon(Chevron(false), Tx("Table 1006.2.1 and 2 more quotes", Body, fg: Muted), 8)), 12),
            Divider(14),
            Top(Row(WithIcon(Tick(false), Tx("Mark as looked at", Small, fg: Muted), 0), Tx("Ctrl+C copies", Small, fg: Faint)), 10));
        return Frame(Header("Four-unit apartment", "Checked 14:32 · R-3a · Multiple family", Btn("Check again", primary: true)), body);
    }

    // ---- 08 By code: the documents' own tree -------------------------------------------------------------------

    static UIElement Node(string num, string title, string line, string state, bool open, bool greyed = false, double indent = 0, bool bold = true)
    {
        var fg = greyed ? Faint : Text;
        var head = WithIcon(Icon(greyed ? "notyet" : state, 13), V(
            Row(Tx($"{num}  {title}", Body, semi: bold, fg: fg)),
            Tx(line, Small, fg: greyed ? Faint : Muted, top: 1)), 7);
        var g = new Grid { Margin = new Thickness(indent, 7, 0, 0) };
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(14) });
        g.ColumnDefinitions.Add(new ColumnDefinition());
        var chev = greyed ? new Border() : (UIElement)Chevron(open, 9);
        if (chev is FrameworkElement fe) { fe.VerticalAlignment = VerticalAlignment.Top; fe.Margin = new Thickness(0, 4, 0, 0); }
        g.Children.Add(chev);
        Grid.SetColumn(head, 1);
        g.Children.Add(head);
        return g;
    }

    static UIElement DocCard(JsonElement d, Func<JsonElement, bool> openChapter, Func<JsonElement, bool> openSection, string? scope = null)
    {
        var body = V(
            WithIcon(Icon("doc"), V(Tx(S(d, "title"), Heading, semi: true), Tx(S(d, "sub"), Small, fg: Muted, top: 1)), 8));
        if (scope is not null)
            body.Children.Add(Callout(WithIcon(Icon("info"), Tx(scope, Small)), AccentFill, Line, 8));
        foreach (var c in d.GetProperty("chapters").EnumerateArray())
        {
            var grey = c.GetProperty("greyed").GetBoolean();
            var oc = !grey && openChapter(c);
            body.Children.Add(Node(S(c, "num"), S(c, "title"), S(c, "line"), S(c, "state"), oc, grey));
            if (!oc)
                continue;
            foreach (var s in c.GetProperty("sections").EnumerateArray())
            {
                var os = openSection(s);
                body.Children.Add(Node(S(s, "num"), S(s, "title"), S(s, "line"), S(s, "state"), os, false, 14, bold: false));
                if (!os)
                    continue;
                foreach (var r in s.GetProperty("rules").EnumerateArray())
                {
                    var parts = r.GetProperty("parts").GetInt32();
                    var meta = (parts > 1 ? $"{parts} {(S(r, "section").StartsWith("1020") ? "corridors" : S(r, "section").StartsWith("1017") || S(r, "section").StartsWith("508") ? "levels" : "spaces")} · " : "") + S(r, "line");
                    var row = WithIcon(Icon(S(r, "state"), 12), V(Tx((S(r, "section").Length > 0 ? S(r, "section") + "  " : "") + S(r, "name"), Small, fg: Text), Tx(meta, Small, fg: Muted)), 6);
                    row.Margin = new Thickness(46, 6, 0, 0);
                    body.Children.Add(row);
                }
            }
            if (oc && S(c, "notyet") is { Length: > 0 } ny)
                body.Children.Add(Node("", ny, "Check these by hand", "notyet", false, true, 14, bold: false));
        }
        foreach (var x in d.GetProperty("extra").EnumerateArray())
            body.Children.Add(Node("", S(x, "title"), S(x, "line"), "notyet", false, true));
        body.Children.Add(Node("", S(d, "other"), "", "notyet", false, true));
        return Card(body, top: 10);
    }

    public static FrameworkElement ByCode(bool open)
    {
        var docs = Apt.GetProperty("bycode").EnumerateArray().ToList();
        var body = V(Top(Switch(1), 8),
            Summary(Apt.GetProperty("totals"), "Needs review", "In the order of the code documents, like a G-001 code analysis."));
        if (!open)
        {
            body.Children.Add(DocCard(docs[0], _ => false, _ => false));
            body.Children.Add(DocCard(docs[1], _ => false, _ => false, "Gordium's Building Code rules are drafted for day care (Group I-4) so far. Most results here need a hand check for an R-2 building."));
        }
        else
        {
            body.Children.Add(DocCard(docs[1], c => S(c, "num") == "Ch 10", s => S(s, "num") is "1006" or "1017"));
        }
        return Frame(Header("Four-unit apartment", "Checked 14:32 · R-3a · Multiple family", Btn("Check again", primary: true)), body);
    }

    // ---- 09 what changed --------------------------------------------------------------------------------------

    public static FrameworkElement WhatChanged()
    {
        var h = House;
        var ch = h.GetProperty("changes").EnumerateArray().ToList();
        var list = V();
        foreach (var c in ch.Take(4))
            list.Children.Add(WithIcon(Icon(S(c, "after") == "pass" ? "pass" : S(c, "after") == "na" ? "na" : "review", 12),
                V(Tx(S(c, "name"), Small, fg: Text), Tx(S(c, "words"), Small, fg: Muted)), 7, 6));
        var body = V(Top(Switch(0), 8),
            Callout(V(
                Row(Tx($"Since 14:32 · {ch.Count} results changed", Body, semi: true), Link("Hide", Small)),
                Tx("You answered: no ADU on the lot, no stream nearby, garage for 2 cars.", Small, fg: Muted, top: 2),
                list,
                Link($"Show all {ch.Count}", Small, 8)), AccentFill, Line, 10),
            Summary(h.GetProperty("after_totals"), "Does not comply", "Lot coverage still fails. 3 results now comply; 6 no longer apply."));
        return Frame(Header("106 Ithaca Rd", "Checked 14:41 · R-1b · One-family, detached", Btn("Check again", primary: true)), body);
    }

    // ---- 10 errors: what happened, what's safe, what to do -----------------------------------------------------

    static UIElement ErrorCard(string title, string what, string next, string primary, string? secondary = "Copy details for support", double top = 8) =>
        Callout(WithIcon(Icon("review"), V(
            Tx(title, Heading, semi: true),
            Tx(what, Body, top: 4),
            Tx(next, Small, fg: Muted, top: 6),
            H(10, Top(Btn(primary, primary: true), 10), secondary is null ? null : Top(Link(secondary, Small), 14)))), ReviewFill, Line, top);

    public static FrameworkElement ErrorTimeout() => Frame(
        Header("Four-unit apartment", "Not checked", Btn("Check again")),
        V(ErrorCard("The check took too long",
                    "Gordium stopped waiting after 60 seconds. Nothing was checked, and your model wasn't changed.",
                    "Large models can take longer. Try again; if it keeps stopping, send the details to support.",
                    "Try again with more time"),
          Tx("Your last results (14:32) are kept below, marked out of date.", Small, fg: Muted, top: 10)));

    public static FrameworkElement ErrorSheet() => Frame(
        Header("Every error, in plain words", "One card per failure path; the technical text goes only to Copy details"),
        V(
            ErrorCard("Gordium's checker stopped", "It closed before answering. Nothing was checked, and your model wasn't changed.", "Try again. If it happens again, send the details to support.", "Try again"),
            ErrorCard("Gordium couldn't read the checker's answer", "Nothing from this check is shown, so nothing passes or fails.", "This is a Gordium bug. Send the details to support.", "Try again"),
            ErrorCard("Gordium couldn't read the model", "Revit stopped the read of a wall (type “LS New 6\"”). Nothing was sent.", "Show the element, fix or hide it, then check again.", "Show in model"),
            ErrorCard("The project was closed", "Nothing was checked.", "Open it and click Check project.", "Check project", null),
            ErrorCard("A check is already running", "Wait for it, or cancel it first.", "", "Cancel the running check", null),
            ErrorCard("Gordium's checker isn't installed", "Revit couldn't start it (no Python found at the expected place).", "Run the installer again, or ask your BIM manager.", "Open setup guide")));

    // ---- 11 stale -----------------------------------------------------------------------------------------------

    public static FrameworkElement Stale()
    {
        var body = V(
            Callout(WithIcon(Icon("stale"), V(Tx("The model changed after this check", Body, semi: true),
                Tx("These results are from 14:32 and may be out of date. They stay greyed until you check again.", Small, fg: Muted, top: 2))), Sunken, Line, 8),
            Top(Switch(0), 10));
        var grey = new StackPanel { Opacity = 0.55 };
        grey.Children.Add(WithIcon(Icon("stale", 16), V(Tx("Does not comply (at 14:32)", Heading + 1, semi: true, fg: Muted), Tx("1 failed · 132 needed review · 9 not checked yet · 10 complied", Small, fg: Muted)), 8, 12));
        grey.Children.Add(Card(WithIcon(Icon("stale"), V(Row(Tx("Lot coverage", Body, semi: true, fg: Muted), Tx("§325-8", Small, fg: Muted)),
            Tx("28.3% measured · ≤ 25% allowed (at 14:32)", Body, fg: Muted, top: 2)), 10), top: 12));
        grey.Children.Add(Card(WithIcon(Icon("stale"), V(Tx("Answer 12 questions about the project", Body, semi: true, fg: Muted), Tx("18 results", Small, fg: Muted)), 10)));
        body.Children.Add(grey);
        return Frame(Header("106 Ithaca Rd", "Checked 14:32 · model changed since", Btn("Check again", primary: true), Icon("stale", 11)), body);
    }

    // ---- 12 selection strip ---------------------------------------------------------------------------------

    public static FrameworkElement Selection()
    {
        var strip = Callout(V(
            Row(Tx("Selected: Wall “LS New 6\"”", Body, semi: true), Link("Clear", Small)),
            Tx("8 results mention it · 8 need review", Small, fg: Muted, top: 1),
            WithIcon(Icon("review", 12), Tx("Lot coverage: the wall isn't a closed solid", Small), 6, 6),
            WithIcon(Icon("review", 12), Tx("Building height: the wall isn't a closed solid", Small), 6, 4),
            WithIcon(Icon("review", 12), Tx("Stories: the wall isn't a closed solid", Small), 6, 4),
            Link("Show all 8", Small, 6)), AccentFill, Line, 8);
        var none = Callout(V(
            Tx("Selected: Door D04", Body, semi: true),
            Tx("No result mentions this door. That isn't a pass: Gordium may not check doors of this kind yet.", Small, fg: Muted, top: 2)), Surface, Line, 10);
        return Frame(Header("Four-unit apartment", "Checked 14:32 · R-3a · Multiple family", Btn("Check again", primary: true)),
                     V(strip, none, Top(Switch(0), 10), Tx("(results below)", Small, fg: Faint, top: 8)));
    }

    // ---- 13 the ribbon badge ----------------------------------------------------------------------------------

    public static FrameworkElement Badges()
    {
        UIElement One(string icon, string? count, Brush? fill, string label, string tip)
        {
            var g = new Grid { Width = 40, Height = 40 };
            g.Children.Add(new Border { Width = 32, Height = 32, CornerRadius = new CornerRadius(4), Background = AccentFill, HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top, Child = new TextBlock { Text = "G", FontSize = 18, FontWeight = FontWeights.Bold, Foreground = Accent, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } });
            if (count is not null)
                g.Children.Add(new Border { MinWidth = 16, Height = 16, CornerRadius = new CornerRadius(8), Background = fill, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom, Padding = new Thickness(3, 0, 3, 0), Child = new TextBlock { Text = count, FontSize = 10, FontWeight = FontWeights.Bold, Foreground = fill == Review ? ReviewInk : Brushes.White, HorizontalAlignment = HorizontalAlignment.Center } });
            else if (icon.Length > 0)
            {
                var i = Icon(icon, 14); i.HorizontalAlignment = HorizontalAlignment.Right; i.VerticalAlignment = VerticalAlignment.Bottom; g.Children.Add(i);
            }
            return WithIcon(g, V(Tx(label, Body, semi: true), Tx(tip, Small, fg: Muted, top: 2)), 10, 12);
        }
        return Frame(Header("Ribbon: Check project button", "Its badge, and the tooltip it shows"),
            V(One("", null, null, "Not checked yet", "Check this project against Ithaca zoning and NY egress."),
              One("", "1", Fail, "1 fails", "Checked 14:32: 1 fails, 132 need review. Click to open the results."),
              One("", "98", Review, "98 need review", "Checked 14:32: nothing fails; 98 need review. Click to open the results."),
              One("stale", null, null, "Out of date", "The model changed after the 14:32 check. Click to check again."),
              One("notyet", null, null, "Not finished", "The last check didn't finish. Click to check again."),
              Tx("Never a green badge: even with nothing failing, “all comply” is shown only in the pane, with what Gordium didn't check.", Small, fg: Muted, top: 14)));
    }

    // ---- 14 the printable summary, in the By code order ------------------------------------------------------

    public static FrameworkElement Summary()
    {
        var page = V(
            Tx("Code check summary", 20, semi: true, fg: Brushes.Black),
            Tx("Four-unit apartment · checked 2026-11-23 14:32 · R-3a · Multiple family dwelling", Body, fg: Brushes.DimGray, top: 2),
            Tx("Not a permit or an approval. Gordium's rulebook is a draft not yet reviewed by a licensed professional. Every “needs review” is for the design team to resolve.", Small, fg: Brushes.DimGray, top: 6),
            Tx("0 fail · 98 need review · 8 not checked yet · 1 complies", Body, semi: true, fg: Brushes.Black, top: 10));
        foreach (var d in Apt.GetProperty("bycode").EnumerateArray())
        {
            page.Children.Add(Tx(S(d, "title"), 15, semi: true, fg: Brushes.Black, top: 18));
            page.Children.Add(Tx(S(d, "sub"), Small, fg: Brushes.DimGray));
            foreach (var c in d.GetProperty("chapters").EnumerateArray())
            {
                page.Children.Add(Tx($"{S(c, "num")} {S(c, "title")} — {S(c, "line")}", Body, semi: true, fg: c.GetProperty("greyed").GetBoolean() ? Brushes.Gray : Brushes.Black, top: 10));
                foreach (var s in c.GetProperty("sections").EnumerateArray().Take(2))
                {
                    page.Children.Add(Tx($"{S(s, "num")} {S(s, "title")}", Small, semi: true, fg: Brushes.Black, top: 4));
                    var grid = new Grid { Margin = new Thickness(0, 2, 0, 0) };
                    foreach (var w in new[] { 1.6, 3.4, 1.4, 1.4 })
                        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(w, GridUnitType.Star) });
                    var row = 0;
                    void Cell(string t, int col, bool head = false)
                    {
                        if (grid.RowDefinitions.Count <= row) grid.RowDefinitions.Add(new RowDefinition());
                        var x = new Border { BorderBrush = Brushes.LightGray, BorderThickness = new Thickness(0, 0, 0, 1), Padding = new Thickness(0, 2, 6, 2), Child = Tx(t, 10.5, semi: head, fg: Brushes.Black) };
                        Grid.SetRow(x, row); Grid.SetColumn(x, col); grid.Children.Add(x);
                    }
                    Cell("Result", 0, true); Cell("Rule", 1, true); Cell("Proposed", 2, true); Cell("Limit", 3, true);
                    foreach (var r in s.GetProperty("rules").EnumerateArray().Take(4))
                    {
                        row++;
                        Cell(S(r, "state") switch { "pass" => "Complies", "fail" => "DOES NOT COMPLY", "notyet" => "Not checked yet", _ => "Needs review" }, 0);
                        Cell(S(r, "name"), 1); Cell(S(r, "measured") is { Length: > 0 } m && m != "—" ? m : "—", 2); Cell(S(r, "limit"), 3);
                    }
                    page.Children.Add(grid);
                }
            }
        }
        page.Children.Add(Tx("Each row's full quote, page and link follow in the appendix, in the same order.", Small, fg: Brushes.DimGray, top: 14));
        return new Border { Background = Brushes.White, Padding = new Thickness(36, 30, 36, 30), Width = 720, Child = page };
    }
}
