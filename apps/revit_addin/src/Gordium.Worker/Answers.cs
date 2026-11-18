using System.Text.Json;
using System.Text.RegularExpressions;

namespace Gordium.Worker;

/// <summary>What the worker says about itself (<c>hello</c>'s result, and <c>about</c> on every answer): the
/// protocol, the site description version, and the fingerprints that trace an answer to the code and rules that
/// gave it.</summary>
public sealed record WorkerAbout(
    string Protocol,
    string SiteSchema,
    string WorkerFingerprint,
    IReadOnlyDictionary<string, string> Rulebook)
{
    private static readonly Regex Version = new(@"^(\d+)\.(\d+)$", RegexOptions.CultureInvariant);

    /// <summary>Reads it strictly and refuses a worker that doesn't speak protocol 1.x and gordium.site/1.</summary>
    internal static WorkerAbout Parse(JsonElement e, string where)
    {
        var protocol = StrictJson.String(e, "protocol", where);
        var m = Version.Match(protocol);
        if (!m.Success)
            throw new WorkerProtocolException($"{where}.protocol is {JsonSerializer.Serialize(protocol)}, not a version like \"1.0\"");
        if (m.Groups[1].Value != Gordium.Worker.Protocol.Major.ToString(System.Globalization.CultureInfo.InvariantCulture))
            throw new WorkerVersionException(
                $"The Gordium checker speaks protocol {protocol}; this add-in speaks {Gordium.Worker.Protocol.Version} " +
                "(a different major version is refused: update the add-in or the checker so they match)");
        var schema = StrictJson.String(e, "site_schema", where);
        if (schema != Gordium.Worker.Protocol.SiteSchema)
            throw new WorkerVersionException(
                $"The Gordium checker reads site descriptions {schema}; this add-in sends {Gordium.Worker.Protocol.SiteSchema}");
        var fingerprint = StrictJson.String(e, "worker_fingerprint", where, nonEmpty: true);
        var books = StrictJson.Object(e, "rulebook", where);
        var rulebook = new Dictionary<string, string>();
        foreach (var p in books.EnumerateObject())
        {
            if (p.Value.ValueKind != JsonValueKind.String || p.Value.GetString()!.Length == 0)
                throw new WorkerProtocolException($"{where}.rulebook[\"{p.Name}\"] is {StrictJson.Kind(p.Value)}, not a fingerprint");
            rulebook[p.Name] = p.Value.GetString()!;
        }
        return new WorkerAbout(protocol, schema, fingerprint, rulebook);
    }
}

/// <summary>An <c>"ok": true</c> answer: its <c>result</c> and its <c>about</c>.</summary>
public sealed record WorkerAnswer(JsonElement Result, WorkerAbout About);

/// <summary>A row's status: the checker's five (design_checker/present.py: COMPLIES, FAILS, REVIEW, NOT_CHECKED, and
/// NOT_APPLICABLE: a rule the interior description sets aside by saying the house has none of a kind). The default
/// value (0) is <see cref="NeedsReview"/>, never <see cref="Complies"/>: a verdict never set, or looked up for a row
/// that isn't there with <c>GetValueOrDefault</c>, is never a pass. A status word this add-in doesn't know (one a
/// later 1.x worker adds) is read as <see cref="NeedsReview"/>, never as a kinder status, and its own word is kept
/// (<see cref="CheckItem.StatusWord"/>): shown, never hidden, as the Rhino panel's grouping does
/// (design_checker/grouping.py: "anything unknown is review").</summary>
public enum Verdict
{
    NeedsReview = 0,
    DoesNotComply = 1,
    Complies = 2,
    NotChecked = 3,
    /// <summary>The rule doesn't apply to this house, for the reason the row gives ("Not applicable: the
    /// description says the house has no ramps (A-2)"). Shown with that reason, folded with what complies, and
    /// counted as neither a pass nor a failure: a check that complies needs a row that does (present.state).</summary>
    NotApplicable = 4,
}

public static class Verdicts
{
    /// <summary>The status word the worker sends for each verdict.</summary>
    public static string Word(Verdict v) => v switch
    {
        Verdict.Complies => "complies",
        Verdict.DoesNotComply => "does_not_comply",
        Verdict.NeedsReview => "needs_review",
        Verdict.NotChecked => "not_checked",
        Verdict.NotApplicable => "not_applicable",
        _ => throw new ArgumentOutOfRangeException(nameof(v)),
    };

    /// <summary>Whether the word is one of the checker's five statuses.</summary>
    public static bool IsKnown(string word) => word is "complies" or "does_not_comply" or "needs_review"
        or "not_checked" or "not_applicable";

    /// <summary>The verdict for a status word: a word this add-in doesn't know is needs review, never a pass.</summary>
    public static Verdict Parse(string word) => word switch
    {
        "complies" => Verdict.Complies,
        "does_not_comply" => Verdict.DoesNotComply,
        "not_checked" => Verdict.NotChecked,
        "not_applicable" => Verdict.NotApplicable,
        _ => Verdict.NeedsReview,
    };

    /// <summary>A row's verdict: <see cref="Parse"/>, except that a row "not applicable" that doesn't say why (no
    /// reason, or an empty one) is needs review: a rule is never set aside without its reason shown.</summary>
    internal static Verdict OfRow(string word, string? reason) =>
        Parse(word) is var v && v == Verdict.NotApplicable && string.IsNullOrWhiteSpace(reason) ? Verdict.NeedsReview : v;

    /// <summary>The most cautious first: a failure, then needs review, not checked, complies, not applicable (the
    /// order of design_checker/grouping.py's CAUTION).</summary>
    internal static int Caution(Verdict v) => v switch
    {
        Verdict.DoesNotComply => 0,
        Verdict.NeedsReview => 1,
        Verdict.NotChecked => 2,
        Verdict.Complies => 3,
        Verdict.NotApplicable => 4,
        _ => 1,
    };
}

/// <summary>One row of a check as the panel shows it (<c>result.view.items[]</c>).</summary>
/// <param name="Id">The row's id, such as <c>R-1b.front_yard</c> or <c>R-1b.side_yards#east</c>.</param>
/// <param name="Name">The row's name as the panel shows it.</param>
/// <param name="Group">What the row is about: <c>building</c>, <c>site</c>, <c>not_checked</c>, <c>not_covered</c>
/// or <c>law</c> (the item's own <c>group</c>; the panel's headings are <see cref="CheckResult.Groups"/>, not this).</param>
/// <param name="Status">Its verdict (a status word this add-in doesn't know is <see cref="Verdict.NeedsReview"/>).</param>
/// <param name="Reason">Why it needs review, isn't checked or doesn't apply, when the checker says (else null).</param>
/// <param name="Raw">The whole item as the worker sent it (its detail, its quotes, the objects to show red).</param>
/// <param name="StatusWord">The status word exactly as the worker sent it.</param>
public sealed record CheckItem(string Id, string Name, string Group, Verdict Status, string? Reason, JsonElement Raw,
                               string StatusWord);

/// <summary>One line of a law's group (design_checker/grouping.py, PR #111): a part's rules, or one cause Gordium
/// can't read yet, shown as one line that opens to its rows.</summary>
/// <param name="Key">The line's key (the same across edits, so a line the architect opened stays open).</param>
/// <param name="Title">Its words ("Bedroom 3 › Window 5: 1 does not comply (...)", "Ramps: not applicable").</param>
/// <param name="Status">The most cautious of the worker's word for the line and its rows' verdicts.</param>
/// <param name="StatusWord">The line's status as the worker sent it.</param>
/// <param name="Folded">Whether it is shown folded (the worker's; a line of failures never is).</param>
/// <param name="Items">Its rows' ids, in order.</param>
public sealed record CheckLine(string Key, string Title, Verdict Status, string StatusWord, bool Folded,
                               IReadOnlyList<string> Items);

/// <summary>One heading of the panel's list (<c>result.view.groups[]</c>, design_checker/present.grouped): zoning's
/// groups by status, and each law's tiers (does not comply, needs review, check by hand, complies), a law's as lines.
/// A not-applicable row is in its law's "Complies" group, which is folded.</summary>
/// <param name="Key">The group's key: <c>fails</c>, <c>review</c>, <c>complies</c>..., or <c>&lt;law&gt;:&lt;tier&gt;</c>.</param>
/// <param name="Title">Its heading ("IRC egress · Complies").</param>
/// <param name="Count">The number its heading shows (the worker's: what an architect counts).</param>
/// <param name="Folded">Whether it is shown folded.</param>
/// <param name="Items">Every row in it, by id.</param>
/// <param name="Lines">Its lines (a law's group); empty for a group listed row by row.</param>
public sealed record CheckGroup(string Key, string Title, int Count, bool Folded, IReadOnlyList<string> Items,
                                IReadOnlyList<CheckLine> Lines);

/// <summary>The answer to <c>check_site</c>: the panel's rows, its groups, its one summary line and the overall state.</summary>
public sealed class CheckResult
{
    /// <summary>Every row, in the worker's order.</summary>
    public IReadOnlyList<CheckItem> Items { get; }

    /// <summary>The panel's list as the Rhino panel shows it (panel_words.list_tree): every row in exactly one group,
    /// and in a group with lines, in exactly one line (checked when the answer is read: grouping folds, never hides).</summary>
    public IReadOnlyList<CheckGroup> Groups { get; }

    /// <summary>The panel's summary line (<c>view.summary</c>), such as "2 need review · 7 comply".</summary>
    public string Summary { get; }

    /// <summary>The panel's overall state (<c>view.state</c>): complies, does not comply, needs review or not
    /// checked; any other word (not applicable is a row's, never a design's) is needs review.</summary>
    public Verdict State { get; }

    /// <summary>Why the report couldn't be written, when one was asked for (<c>report_error</c>), else null.</summary>
    public string? ReportError { get; }

    /// <summary>The whole result as the worker sent it.</summary>
    public JsonElement Raw { get; }

    /// <summary>The <c>about</c> of the answer: which code and rules gave it.</summary>
    public WorkerAbout About { get; }

    private CheckResult(IReadOnlyList<CheckItem> items, IReadOnlyList<CheckGroup> groups, string summary,
                        Verdict state, string? reportError, JsonElement raw, WorkerAbout about)
    {
        Items = items;
        Groups = groups;
        Summary = summary;
        State = state;
        ReportError = reportError;
        Raw = raw;
        About = about;
    }

    /// <summary>{row id: verdict}, every row (ids are unique: checked when the answer is read). A row id that isn't
    /// there is not in the dictionary; <c>GetValueOrDefault</c> gives <see cref="Verdict.NeedsReview"/> for it.</summary>
    public IReadOnlyDictionary<string, Verdict> ById() => Items.ToDictionary(i => i.Id, i => i.Status);

    /// <summary>A check said to comply must be one the rows back (the worker's rule, present.state, from Ben's
    /// decision of 2026-11-09; a worker from before it is refused, never read as a pass): no row it counts (any
    /// but the rules not in Gordium yet, <c>not_covered</c>, and a rule that doesn't apply, with its reason) does not
    /// comply, needs review, is not checked (waiting on a fact, or not checked in this release: Ben, 2026-11-09) or
    /// has a status this add-in doesn't know; no use detail waits for an answer (<c>use_detail</c>); and at least one
    /// counted row complies. Anything else is refused, never shown as a pass.</summary>
    private static void CheckComplies(IReadOnlyList<CheckItem> items)
    {
        var complies = false;
        for (var n = 0; n < items.Count; n++)
        {
            var where = $"result.view.items[{n}]";
            var row = items[n];
            var detail = row.Raw.TryGetProperty("use_detail", out var d) ? d : default;
            if (detail.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.True or JsonValueKind.False or JsonValueKind.Null))
                throw new WorkerProtocolException($"{where}.use_detail is {StrictJson.Kind(detail)}, not true or false");
            if (detail.ValueKind == JsonValueKind.True)
                throw new WorkerProtocolException($"the check says it complies, but {where} is a use detail still to answer");
            if (row.Group == "not_covered" || row.Status == Verdict.NotApplicable)
                continue;      // counted toward nothing: never the row that makes a check comply
            if (row.Status != Verdict.Complies)
                throw new WorkerProtocolException($"the check says it complies, but {where} is {row.StatusWord}" +
                    (!Verdicts.IsKnown(row.StatusWord) ? ", a status this add-in doesn't know"
                     : row.StatusWord == "not_applicable" ? " without saying why" : ""));
            complies = true;   // reaching here, the row complies: every other status was refused above
        }
        if (!complies)
            throw new WorkerProtocolException("the check says it complies, but none of its rows complies");
    }

    /// <summary>Zoning's groups shown folded when the answer doesn't say (panel_words.FOLDED_GROUPS).</summary>
    private static readonly HashSet<string> FoldedGroups = new(StringComparer.Ordinal) { "complies", "not_covered", "use_details" };

    /// <summary>The panel's groups (present.grouped), read strictly: every row in exactly one group, and a group with
    /// lines has each of its rows in exactly one line (the Rhino panel lists such a group by its lines alone,
    /// panel_words.list_tree, so a row in no line would be hidden). A group's folded and count, when not given, are
    /// list_tree's: zoning's complies, not covered and use details folded; the count is its rows.</summary>
    private static List<CheckGroup> ReadGroups(JsonElement view, IReadOnlyList<CheckItem> items)
    {
        var list = StrictJson.Field(view, "groups", "result.view");
        if (list.ValueKind != JsonValueKind.Array)
            throw new WorkerProtocolException($"result.view.groups is {StrictJson.Kind(list)}, not a list");
        var rows = items.ToDictionary(i => i.Id, StringComparer.Ordinal);
        var placed = new HashSet<string>(StringComparer.Ordinal);
        var keys = new HashSet<string>(StringComparer.Ordinal);
        var groups = new List<CheckGroup>();
        var n = 0;
        foreach (var g in list.EnumerateArray())
        {
            var where = $"result.view.groups[{n++}]";
            var key = StrictJson.String(g, "key", where, nonEmpty: true);
            if (!keys.Add(key))
                throw new WorkerProtocolException($"{where}: the group {key} is given twice");
            var ids = Ids(g, where, rows);
            foreach (var id in ids)
                if (!placed.Add(id))
                    throw new WorkerProtocolException($"{where}: the row {id} is in two groups");
            var lines = new List<CheckLine>();
            var ls = g.TryGetProperty("lines", out var l) ? l : default;
            if (ls.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null))
            {
                if (ls.ValueKind != JsonValueKind.Array)
                    throw new WorkerProtocolException($"{where}.lines is {StrictJson.Kind(ls)}, not a list");
                var inLine = new HashSet<string>(StringComparer.Ordinal);
                var m = 0;
                foreach (var ln in ls.EnumerateArray())
                {
                    var at = $"{where}.lines[{m++}]";
                    var mine = Ids(ln, at, rows);
                    if (mine.Count == 0)
                        throw new WorkerProtocolException($"{at} has no rows");
                    foreach (var id in mine)
                    {
                        if (!ids.Contains(id))
                            throw new WorkerProtocolException($"{at}: the row {id} is not one of its group's");
                        if (!inLine.Add(id))
                            throw new WorkerProtocolException($"{at}: the row {id} is in two lines");
                    }
                    var word = StrictJson.String(ln, "status", at);
                    // never kinder than its rows: the most cautious of the worker's word and each row's verdict
                    var status = mine.Select(id => rows[id].Status).Append(Verdicts.Parse(word)).MinBy(Verdicts.Caution);
                    lines.Add(new CheckLine(StrictJson.String(ln, "key", at, nonEmpty: true),
                                            StrictJson.String(ln, "title", at), status, word,
                                            Bool(ln, "folded", at, true), mine));
                }
                if (inLine.Count != ids.Count)
                    throw new WorkerProtocolException(
                        $"{where}: the row {ids.First(id => !inLine.Contains(id))} is in none of its lines (it would be hidden)");
            }
            var count = ids.Count;
            if (g.TryGetProperty("count", out var c) && c.ValueKind != JsonValueKind.Null
                && (c.ValueKind != JsonValueKind.Number || !c.TryGetInt32(out count) || count < 0))
                throw new WorkerProtocolException($"{where}.count is {StrictJson.Kind(c)}, not a whole number");
            groups.Add(new CheckGroup(key, StrictJson.String(g, "title", where), count,
                                      Bool(g, "folded", where, FoldedGroups.Contains(key)), ids, lines));
        }
        var lost = items.FirstOrDefault(i => !placed.Contains(i.Id));
        if (lost is not null)
            throw new WorkerProtocolException($"result.view.groups: the row {lost.Id} is in no group (it would be hidden)");
        return groups;
    }

    /// <summary>A group's or line's <c>items</c>: a list of the check's row ids, each once.</summary>
    private static List<string> Ids(JsonElement e, string where, IReadOnlyDictionary<string, CheckItem> rows)
    {
        var list = StrictJson.Field(e, "items", where);
        if (list.ValueKind != JsonValueKind.Array)
            throw new WorkerProtocolException($"{where}.items is {StrictJson.Kind(list)}, not a list");
        var ids = new List<string>();
        foreach (var x in list.EnumerateArray())
        {
            if (x.ValueKind != JsonValueKind.String)
                throw new WorkerProtocolException($"{where}.items holds {StrictJson.Kind(x)}, not a row id");
            var id = x.GetString()!;
            if (!rows.ContainsKey(id))
                throw new WorkerProtocolException($"{where}.items holds {JsonSerializer.Serialize(id)}, not one of the check's rows");
            if (ids.Contains(id))
                throw new WorkerProtocolException($"{where}.items holds the row {id} twice");
            ids.Add(id);
        }
        return ids;
    }

    private static bool Bool(JsonElement e, string name, string where, bool otherwise)
    {
        if (!e.TryGetProperty(name, out var v) || v.ValueKind == JsonValueKind.Null)
            return otherwise;
        return v.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => throw new WorkerProtocolException($"{where}.{name} is {StrictJson.Kind(v)}, not true or false"),
        };
    }

    internal static CheckResult Parse(WorkerAnswer answer)
    {
        var result = answer.Result;
        var view = StrictJson.Object(result, "view", "result");
        var list = StrictJson.Field(view, "items", "result.view");
        if (list.ValueKind != JsonValueKind.Array)
            throw new WorkerProtocolException($"result.view.items is {StrictJson.Kind(list)}, not a list");
        var items = new List<CheckItem>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var n = 0;
        foreach (var e in list.EnumerateArray())
        {
            var where = $"result.view.items[{n++}]";
            var id = StrictJson.String(e, "id", where, nonEmpty: true);
            if (!seen.Add(id))
                throw new WorkerProtocolException($"{where}: the row {id} is given twice");
            var name = StrictJson.String(e, "name", where);
            var group = StrictJson.String(e, "group", where);
            var word = StrictJson.String(e, "status", where);
            var reason = StrictJson.StringOrNull(e, "reason", where);
            items.Add(new CheckItem(id, name, group, Verdicts.OfRow(word, reason), reason, e, word));
        }
        // a check with no rows checked nothing: never shown as a result (the worker's own state would say "complies")
        if (items.Count == 0)
            throw new WorkerProtocolException("result.view.items is empty: a check with no rows can't be shown as a result");
        var stateWord = StrictJson.String(view, "state", "result.view");
        var state = Verdicts.Parse(stateWord) is var s && s == Verdict.NotApplicable ? Verdict.NeedsReview : s;
        if (state == Verdict.Complies)
            CheckComplies(items);
        return new CheckResult(items, ReadGroups(view, items), StrictJson.String(view, "summary", "result.view"), state,
                               StrictJson.StringOrNull(result, "report_error", "result"), result, answer.About);
    }
}

/// <summary>The answer to a session command: each part's answer under its own name, and the parts that refused
/// their input (worker_protocol_v1.md, How a command is answered).</summary>
public sealed class SessionAnswer
{
    /// <summary>The command answered.</summary>
    public string Command { get; }

    /// <summary>The whole result as the worker sent it.</summary>
    public JsonElement Result { get; }

    /// <summary>The parts that refused, by their first answer name, with the worker's words.</summary>
    public IReadOnlyDictionary<string, string> Refused { get; }

    /// <summary>The <c>about</c> of the answer.</summary>
    public WorkerAbout About { get; }

    private readonly IReadOnlyList<IReadOnlyList<string>> _parts;

    private SessionAnswer(string command, JsonElement result, IReadOnlyDictionary<string, string> refused,
                          WorkerAbout about, IReadOnlyList<IReadOnlyList<string>> parts)
    {
        Command = command;
        Result = result;
        Refused = refused;
        About = about;
        _parts = parts;
    }

    /// <summary>One answer by name. Throws <see cref="PartRefusedException"/> when its part refused its input, and
    /// <see cref="AnswerMissingException"/> when it wasn't given: never a default in its place.</summary>
    public JsonElement Get(string name)
    {
        var part = _parts.FirstOrDefault(p => p.Contains(name))
            ?? throw new ArgumentException($"{Command} has no answer {name} (it answers: {string.Join(", ", _parts.SelectMany(p => p))})", nameof(name));
        if (Refused.TryGetValue(part[0], out var words))
            throw new PartRefusedException(Command, name, words);
        if (!Result.TryGetProperty(name, out var value))
            throw new AnswerMissingException(
                $"{Command} didn't answer {name}: send the fields it needs, or name it in want");
        return value;
    }

    internal static SessionAnswer Parse(string command, WorkerAnswer answer, IReadOnlyList<string>? want)
    {
        var parts = Protocol.SessionCommands[command];
        var result = answer.Result;
        var refused = new Dictionary<string, string>(StringComparer.Ordinal);
        if (result.TryGetProperty("refused", out var r))
        {
            if (r.ValueKind != JsonValueKind.Object)
                throw new WorkerProtocolException($"result.refused is {StrictJson.Kind(r)}, not an object");
            foreach (var p in r.EnumerateObject())
            {
                if (!parts.Any(part => part[0] == p.Name))
                    throw new WorkerProtocolException($"result.refused names {p.Name}, not one of {command}'s parts");
                if (p.Value.ValueKind != JsonValueKind.String)
                    throw new WorkerProtocolException($"result.refused.{p.Name} is {StrictJson.Kind(p.Value)}, not words");
                refused[p.Name] = p.Value.GetString()!;
            }
        }
        foreach (var part in parts)
        {
            var given = part.Where(o => result.TryGetProperty(o, out _)).ToList();
            var isRefused = refused.ContainsKey(part[0]);
            if (isRefused && given.Count > 0)
                throw new WorkerProtocolException($"{command}: {part[0]} is both refused and answered");
            if (given.Count > 0 && given.Count < part.Count)
                throw new WorkerProtocolException(
                    $"{command}: the part answering {string.Join(", ", part)} gave only {string.Join(", ", given)}");
            if (want is not null && part.Any(want.Contains) && !isRefused && given.Count == 0)
                throw new WorkerProtocolException($"{command}: {string.Join(", ", part)} asked for, but neither answered nor refused");
        }
        return new SessionAnswer(command, result, refused, answer.About, parts);
    }
}
