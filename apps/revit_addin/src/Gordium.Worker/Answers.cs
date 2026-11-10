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

/// <summary>A row's status, exactly the checker's four (design_checker/present.py: COMPLIES, FAILS, REVIEW,
/// NOT_CHECKED). Any other word in an answer is an error, never read as one of these. The default value (0) is
/// <see cref="NeedsReview"/>, never <see cref="Complies"/>: a verdict never set, or looked up for a row that isn't
/// there with <c>GetValueOrDefault</c>, is never a pass.</summary>
public enum Verdict
{
    NeedsReview = 0,
    DoesNotComply = 1,
    Complies = 2,
    NotChecked = 3,
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
        _ => throw new ArgumentOutOfRangeException(nameof(v)),
    };

    internal static Verdict Parse(string word, string where) => word switch
    {
        "complies" => Verdict.Complies,
        "does_not_comply" => Verdict.DoesNotComply,
        "needs_review" => Verdict.NeedsReview,
        "not_checked" => Verdict.NotChecked,
        _ => throw new WorkerProtocolException($"{where} is {JsonSerializer.Serialize(word)}, not a status Gordium gives"),
    };
}

/// <summary>One row of a check as the panel shows it (<c>result.view.items[]</c>).</summary>
/// <param name="Id">The row's id, such as <c>R-1b.front_yard</c> or <c>R-1b.side_yards#east</c>.</param>
/// <param name="Name">The row's name as the panel shows it.</param>
/// <param name="Group">What the row is about: <c>building</c>, <c>site</c>, <c>not_checked</c> or <c>not_covered</c>
/// (the item's own <c>group</c>; the panel's headings are worked out from the statuses, not from this).</param>
/// <param name="Status">Its verdict.</param>
/// <param name="Reason">Why it needs review or isn't checked, when the checker says (else null).</param>
/// <param name="Raw">The whole item as the worker sent it (its detail, its quotes, the objects to show red).</param>
public sealed record CheckItem(string Id, string Name, string Group, Verdict Status, string? Reason, JsonElement Raw);

/// <summary>The answer to <c>check_site</c>: the panel's rows, its one summary line and the overall state.</summary>
public sealed class CheckResult
{
    /// <summary>Every row, in the worker's order.</summary>
    public IReadOnlyList<CheckItem> Items { get; }

    /// <summary>The panel's summary line (<c>view.summary</c>), such as "2 need review · 7 comply".</summary>
    public string Summary { get; }

    /// <summary>The panel's overall state (<c>view.state</c>).</summary>
    public Verdict State { get; }

    /// <summary>Why the report couldn't be written, when one was asked for (<c>report_error</c>), else null.</summary>
    public string? ReportError { get; }

    /// <summary>The whole result as the worker sent it.</summary>
    public JsonElement Raw { get; }

    /// <summary>The <c>about</c> of the answer: which code and rules gave it.</summary>
    public WorkerAbout About { get; }

    private CheckResult(IReadOnlyList<CheckItem> items, string summary, Verdict state, string? reportError,
                        JsonElement raw, WorkerAbout about)
    {
        Items = items;
        Summary = summary;
        State = state;
        ReportError = reportError;
        Raw = raw;
        About = about;
    }

    /// <summary>{row id: verdict}, every row (ids are unique: checked when the answer is read). A row id that isn't
    /// there is not in the dictionary; <c>GetValueOrDefault</c> gives <see cref="Verdict.NeedsReview"/> for it.</summary>
    public IReadOnlyDictionary<string, Verdict> ById() => Items.ToDictionary(i => i.Id, i => i.Status);

    /// <summary>A check said to comply must be one the rows back (the worker's own rule, present.state): no row it
    /// counts (any but the rules not in Gordium yet, <c>not_covered</c>) does not comply, needs review or is not checked
    /// (waiting on a fact, or not checked in this release: Ben, 2026-11-09), no use detail waits for an answer (<c>use_detail</c>), and at least one counted row complies. Anything else is refused,
    /// never shown as a pass.</summary>
    private static void CheckComplies(JsonElement items)
    {
        var complies = false;
        var n = 0;
        foreach (var e in items.EnumerateArray())
        {
            var where = $"result.view.items[{n++}]";
            var detail = e.TryGetProperty("use_detail", out var d) ? d : default;
            if (detail.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.True or JsonValueKind.False or JsonValueKind.Null))
                throw new WorkerProtocolException($"{where}.use_detail is {StrictJson.Kind(detail)}, not true or false");
            if (detail.ValueKind == JsonValueKind.True)
                throw new WorkerProtocolException($"the check says it complies, but {where} is a use detail still to answer");
            if (StrictJson.String(e, "group", where) == "not_covered")
                continue;
            var status = Verdicts.Parse(StrictJson.String(e, "status", where), $"{where}.status");
            if (status is Verdict.DoesNotComply or Verdict.NeedsReview or Verdict.NotChecked)
                throw new WorkerProtocolException($"the check says it complies, but {where} is {Verdicts.Word(status)}");
            complies = true;   // reaching here, the row complies: every other status was refused above
        }
        if (!complies)
            throw new WorkerProtocolException("the check says it complies, but none of its rows complies");
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
            items.Add(new CheckItem(
                id,
                StrictJson.String(e, "name", where),
                StrictJson.String(e, "group", where),
                Verdicts.Parse(StrictJson.String(e, "status", where), $"{where}.status"),
                StrictJson.StringOrNull(e, "reason", where),
                e));
        }
        // a check with no rows checked nothing: never shown as a result (the worker's own state would say "complies")
        if (items.Count == 0)
            throw new WorkerProtocolException("result.view.items is empty: a check with no rows can't be shown as a result");
        var state = Verdicts.Parse(StrictJson.String(view, "state", "result.view"), "result.view.state");
        if (state == Verdict.Complies)
            CheckComplies(list);
        return new CheckResult(items, StrictJson.String(view, "summary", "result.view"), state,
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
