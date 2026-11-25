using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Review round 1 of UI changes 13 to 15: which check the badge, the selection strip and the summary follow.
/// The Setup form never replaces it; its own project's changes make it stale and its closing takes it down, whichever
/// project the pane shows; a merged rooms card's rooms are its elements; and the summary says what qualifies the results.</summary>
public sealed class FollowedStateTests
{
    private static readonly DateTime At = new(2026, 11, 23, 14, 32, 0);

    /// <summary>A complying check of the document keyed "K-" + <paramref name="project"/> (DocKeys), titled <paramref name="title"/>.</summary>
    private static FollowedCheck Complying(string project, string? title = null) => new(title ?? project, At,
        UxAnswers.Model(UxAnswers.Answer("complies", UxAnswers.Item("a", "complies"), UxAnswers.Item("b", "complies"))), Key: "K-" + project);

    /// <summary>The Setup form's content (ResultsView.ShowSetup): no rows, nothing to set.</summary>
    private static FollowedCheck Setup(string project) => new(project, At.AddMinutes(1), null);

    /// <summary>The pin of P0: a complying check, then the Setup form (Mark facts), then a change to the model (Setup's
    /// Save): the badge is no longer a pass and the summary is refused.</summary>
    [Fact]
    public void A_change_after_the_setup_form_makes_the_complying_check_stale()
    {
        var state = new FollowedState();
        state.Shown(Complying("A"));
        Assert.Equal(BadgeKind.Complies, state.Badge.Kind);
        Assert.Null(state.SummaryRefusal);
        state.Shown(Setup("A"));
        Assert.True(state.Changed("K-A"));
        Assert.NotEqual(BadgeKind.Complies, state.Badge.Kind);
        Assert.Equal(BadgeKind.Stale, state.Badge.Kind);
        Assert.NotNull(state.SummaryRefusal);
        Assert.Throws<InvalidOperationException>(() => state.SummaryHtml(At));
    }

    /// <summary>Mark facts in project B (the pane shows B's Setup form), then an edit in A: A's check goes stale.</summary>
    [Fact]
    public void An_edit_in_the_checked_project_makes_it_stale_while_the_pane_shows_another()
    {
        var state = new FollowedState();
        state.Shown(Complying("A"));
        state.Shown(Setup("B"));
        Assert.False(state.Changed("K-B"));
        Assert.Equal(BadgeKind.Complies, state.Badge.Kind);           // B's edits don't touch A's check
        Assert.True(state.Changed("K-A"));
        Assert.Equal(BadgeKind.Stale, state.Badge.Kind);
        Assert.Equal("A", state.Check!.Project);
    }

    /// <summary>Closing A takes its check down (whatever the pane shows); closing another project doesn't.</summary>
    [Fact]
    public void Closing_the_checked_project_clears_it()
    {
        var state = new FollowedState();
        state.Shown(Complying("A"));
        state.Shown(Setup("B"));
        Assert.False(state.Closed("K-B"));
        Assert.Equal(BadgeKind.Complies, state.Badge.Kind);
        Assert.True(state.Closed("K-A"));
        Assert.Null(state.Check);
        Assert.Equal(BadgeKind.NotChecked, state.Badge.Kind);
        Assert.NotNull(state.SummaryRefusal);
    }

    /// <summary>The pin of review round 2: a check of document K1 titled "Project1", then its Setup form after a Save As
    /// titled it "House": a change to K1 still makes the check stale and the summary is refused; its closing clears it.
    /// The title is for display only.</summary>
    [Fact]
    public void A_check_follows_its_document_through_a_save_as_never_its_title()
    {
        var state = new FollowedState();
        state.Shown(new FollowedCheck("Project1", At, Complying("x").Model, Key: "K1"));
        state.Shown(Setup("House"));
        Assert.False(state.Changed("K2"));                         // another document, even one titled the same
        Assert.True(state.Changed("K1"));
        Assert.Equal(BadgeKind.Stale, state.Badge.Kind);
        Assert.NotNull(state.SummaryRefusal);
        Assert.True(state.Closed("K1"));
        Assert.Null(state.Check);
        Assert.Equal(BadgeKind.NotChecked, state.Badge.Kind);
    }

    /// <summary>A check whose document isn't known: any change makes it stale and any closing takes it down (fail closed).</summary>
    [Fact]
    public void A_check_of_no_known_document_fails_closed()
    {
        var state = new FollowedState();
        state.Shown(new FollowedCheck("P", At, Complying("x").Model));
        Assert.True(state.Changed("K-anything"));
        Assert.Equal(BadgeKind.Stale, state.Badge.Kind);
        state.Shown(new FollowedCheck("P", At, Complying("x").Model));
        Assert.True(state.Closed("K-other"));
        Assert.Null(state.Check);
    }

    /// <summary>The sweep of review round 2: no document is matched by its title or path in the add-in (the followed
    /// check, the selection, the Setup form's "checked anyway", what changed and the ticks): each by DocKeys.</summary>
    [Fact]
    public void The_add_in_matches_documents_by_identity_never_by_name()
    {
        string Read(string f) => File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", f));
        var setup = Read("SetupFlow.cs");
        Assert.Contains("private static string Key(Document doc) => DocKeys.Of(doc);", setup, StringComparison.Ordinal);
        Assert.DoesNotContain("PathName", setup, StringComparison.Ordinal);
        var extras = Read("PaneExtras.cs");
        Assert.DoesNotContain(".Title", extras, StringComparison.Ordinal);
        Assert.Contains("Followed.Changed(DocKeys.Of(e.GetDocument()))", extras, StringComparison.Ordinal);
        Assert.Contains("Followed.Closed(DocKeys.Of(e.Document))", extras, StringComparison.Ordinal);
        var view = Read("ResultsView.cs");
        Assert.Contains("var key = content.Key;", view, StringComparison.Ordinal);
        Assert.DoesNotContain("var key = content.Project;", view, StringComparison.Ordinal);
        Assert.Contains("Key: DocKeys.Of(doc)", Read("CheckProject.cs"), StringComparison.Ordinal);
    }

    /// <summary>The pin of review round 2's P3: the which_code line's cites (section, document, page and quote), as the
    /// pane's tooltip shows them, are in the summary.</summary>
    [Fact]
    public void The_summary_prints_the_which_code_cites()
    {
        var code = new WhichCode("rcnys_2025", "2025 Residential Code of New York State", "a one-family house", null,
                                 [new CodeCite("R101.2", "34", "The provisions of this code shall apply to detached one- and two-family dwellings", "RCNYS 2025")]);
        var model = UxAnswers.Model(UxAnswers.Answer("needs_review", UxAnswers.Item("a", "needs_review"))) with { Code = code };
        var html = ComplianceSummary.Html(model, "P", At, At);
        Assert.Contains("R101.2", html, StringComparison.Ordinal);
        Assert.Contains("p.34", html, StringComparison.Ordinal);
        Assert.Contains("RCNYS 2025", html, StringComparison.Ordinal);
        Assert.Contains("“The provisions of this code shall apply to detached one- and two-family dwellings”", html, StringComparison.Ordinal);
        Assert.Contains("<div id=\"which-code-cites\" class=\"law verbatim\">" + System.Net.WebUtility.HtmlEncode(code.Tooltip!) + "</div>", html, StringComparison.Ordinal);
    }

    [Fact]
    public void A_new_check_a_check_that_sent_nothing_or_rows_taken_down_replace_what_is_followed()
    {
        var state = new FollowedState();
        state.Shown(Complying("A"));
        state.Shown(new FollowedCheck("A", At, null, Missing: 2));
        Assert.Equal(BadgeKind.NotChecked, state.Badge.Kind);
        Assert.Contains("2 things to set first", state.Badge.ToolTip, StringComparison.Ordinal);
        state.Shown(Complying("A"));
        state.Shown(null);
        Assert.Null(state.Check);
        Assert.True(state.Failed);
    }

    /// <summary>The pin of the setter: every write of ResultsView's content goes through the one setter that raises
    /// Shown (ShowSetup's included), so PaneExtras never keeps a check the pane replaced.</summary>
    [Fact]
    public void Every_write_of_the_panes_content_raises_shown()
    {
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        Assert.Single(Regex.Matches(view, @"_contentValue = "));
        Assert.Matches(new Regex(@"_contentValue = value;\s*Shown\?\.Invoke\(this, value\);"), view);
        Assert.Matches(new Regex(@"private PanelContent\? _content\s*\{"), view);              // a property, not a field
        Assert.Contains("_content = new PanelContent(project, DateTime.Now, null, [], 0,", view, StringComparison.Ordinal);  // ShowSetup's
    }

    /// <summary>The pin of P2: two rows whose own causes say rooms:A,B and rooms:B,C, merged by the worker into one card
    /// rooms:A,B,C (its Rooms empty: no row has its key). Selecting A or C lists both rows.</summary>
    [Fact]
    public void A_merged_rooms_card_is_found_by_each_of_its_rooms()
    {
        var r1 = UxAnswers.Item("r1", "needs_review", "Common path");
        r1["causes"] = new JsonArray(new JsonObject { ["key"] = "rooms:A,B", ["rooms"] = new JsonArray(new JsonObject { ["id"] = "A" }, new JsonObject { ["id"] = "B" }) });
        var r2 = UxAnswers.Item("r2", "needs_review", "Travel distance");
        r2["causes"] = new JsonArray(new JsonObject { ["key"] = "rooms:B,C", ["rooms"] = new JsonArray(new JsonObject { ["id"] = "B" }, new JsonObject { ["id"] = "C" }) });
        var model = UxAnswers.Model(UxAnswers.Parse(new JsonObject
        {
            ["view"] = new JsonObject
            {
                ["items"] = new JsonArray(r1, r2), ["summary"] = "s", ["state"] = "needs_review",
                ["groups"] = new JsonArray(UxAnswers.Group("review", ["r1", "r2"], new JsonObject
                {
                    ["key"] = "rooms:A,B,C", ["kind"] = "fix_model", ["words"] = "3 rooms have no route", ["items"] = new JsonArray("r1", "r2"),
                    ["elements"] = new JsonArray("A", "B", "C"),
                })),
            },
            ["report_error"] = null,
        }));
        Assert.Empty(model.Causes.Single().Rooms);
        var map = SelectionMap.Of(model, At);
        foreach (var room in new[] { "A", "B", "C" })
            Assert.Equal(["r1", "r2"], map.For([room]).Select(r => r.Row.Id));
    }

    /// <summary>The pin of P2: what the pane shows that qualifies the results is in the summary, verbatim: what wasn't
    /// read from the model, which code, the facts a check sent anyway left out, the drafts this run filled.</summary>
    [Fact]
    public void The_summary_says_what_was_not_read_which_code_what_was_left_out_and_the_drafts()
    {
        var inside = "Not read from the model yet: handrails (10 rules).\nLeft out: 2 doors with no level.";
        var model = UxAnswers.Model(UxAnswers.Answer("needs_review", UxAnswers.Item("a", "complies"), UxAnswers.Item("b", "needs_review")))
                    with { Inside = inside, Code = new WhichCode("rcnys_2025", "2025 Residential Code of New York State", "a one-family house", null, []) };
        var check = new FollowedCheck("106 Ithaca Rd", At, model, NotStated: ["Use not set: every rule that turns on the use needs review."],
                                      ClearWords: "Window W1: Gordium filled the clear opening as a draft.", MarksAdded: 3);
        var state = new FollowedState();
        state.Shown(check);
        var html = state.SummaryHtml(At);
        Assert.Contains("<p id=\"not-read\" class=\"verbatim\">" + System.Net.WebUtility.HtmlEncode(inside) + "</p>", html, StringComparison.Ordinal);
        Assert.Contains(".verbatim { white-space: pre-line; }", html, StringComparison.Ordinal);
        Assert.Contains("<h2>Not read from the model</h2>", html, StringComparison.Ordinal);
        Assert.Contains("<p id=\"which-code\">" + System.Net.WebUtility.HtmlEncode(model.Code!.Words) + "</p>", html, StringComparison.Ordinal);
        Assert.Contains("<b>Checked without 1 fact: the rules they decide need review</b>", html, StringComparison.Ordinal);
        Assert.Contains("<li>Use not set: every rule that turns on the use needs review.</li>", html, StringComparison.Ordinal);
        Assert.Contains(System.Net.WebUtility.HtmlEncode(ClearPrefills.PanelStatus(3, check.ClearWords, stale: false)), html, StringComparison.Ordinal);
        // none of it before the head that says it is not a permit
        Assert.True(html.IndexOf("not-a-permit", StringComparison.Ordinal) < html.IndexOf("not-read", StringComparison.Ordinal));
        // and with nothing to qualify, none of these sections
        var plain = ComplianceSummary.Html(UxAnswers.Model(UxAnswers.Answer("needs_review", UxAnswers.Item("a", "needs_review"))), "P", At, At);
        Assert.DoesNotContain("id=\"not-read\"", plain, StringComparison.Ordinal);
        Assert.DoesNotContain("id=\"not-stated\"", plain, StringComparison.Ordinal);
    }

    /// <summary>The pane's own heading for a check sent anyway is the summary's (the same words).</summary>
    [Fact]
    public void The_not_stated_heading_is_the_panes()
    {
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        Assert.Contains("$\"Checked without {notStated.Count} {(notStated.Count == 1 ? \"fact\" : \"facts\")}: the rules they decide need review\"",
                        view, StringComparison.Ordinal);
        Assert.Equal("Checked without 2 facts: the rules they decide need review", ComplianceSummary.NotStatedTitle(2));
    }
}
