using System.Globalization;
using System.Text.Json.Nodes;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>The one check_site request "Check my project" sends: the site description (the outside), the lot facts
/// (the architect's marks on Project Information) and the interior description (the inside).</summary>
public sealed record ProjectRequest(JsonObject Site, JsonObject Facts, JsonObject Interior);

/// <summary>What "Check my project" read, ready to send, or why nothing is sent.</summary>
/// <param name="Request">The request, or null when a fact is missing (nothing is sent: principle 4).</param>
/// <param name="Missing">Exactly what the architect must fill in, in the architect's words (empty when sent).</param>
/// <param name="PhaseChecked">The phase checked (the last one), the same for the outside and the inside.</param>
/// <param name="OptionsChecked">Each design option set's option checked, the same for both.</param>
/// <param name="Inside">The interior read (its not-read lists for the dialog), or null when nothing was read.</param>
/// <param name="Street">The street line sent, in words ("the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)"), so
/// every result names the street it was checked against; null when nothing was sent.</param>
/// <param name="StreetRefused">Why the street edge kept wasn't sent, typed (<see cref="StreetEdges.NeedsNewPick"/>).</param>
public sealed record ProjectPrepared(ProjectRequest? Request, IReadOnlyList<string> Missing, string? PhaseChecked,
                                     IReadOnlyList<string> OptionsChecked, InteriorReadResult? Inside, string? Street = null,
                                     StreetRefusal StreetRefused = StreetRefusal.None);

/// <summary>
/// "Check my project" without Revit (reading design note, section 9): the architect's own open project read outside
/// (<see cref="SiteReader"/>) and inside (<see cref="InteriorReader"/>), with the lot facts from Gordium's marks on
/// Project Information (<see cref="ProjectFacts"/>), as one check_site request. A fact missing, or a street edge that
/// isn't an edge of the lot read, and no request is made: the dialog lists what to fill in, never a check on a guess.
/// </summary>
public static class ProjectCheck
{
    /// <summary>Reads both models (the same document, read once by each Revit layer) into one request.
    /// <paramref name="outside"/> is RevitRead's model (elements, lot lines), <paramref name="inside"/> RevitInterior's
    /// (marks, Project Information, the interior records). Refused (<see cref="ReadRefusedException"/>) when the two
    /// don't name the same phases and design options: the outside and the inside must be the same design.</summary>
    public static async Task<ProjectPrepared> PrepareAsync(RevitModel outside, RevitModel inside, ILeftOutAsker asker,
                                                           CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(outside);
        ArgumentNullException.ThrowIfNull(inside);
        ArgumentNullException.ThrowIfNull(asker);
        if (SameDesign(outside, inside) is { } differs)
            throw new ReadRefusedException("the outside and the inside weren't read in the same design (" + differs +
                                           "): nothing is sent; click Check project again");
        var read = ProjectFacts.Read(inside);
        if (read.Missing.Count > 0)
            return new ProjectPrepared(null, read.Missing, null, [], null);

        // everything read from the records before the first await, on the caller's thread (Revit's: a lot line's
        // points call back into the API; SiteReader reads the lot before it asks the worker anything)
        var interior = InteriorReader.Read(inside);
        var site = await SiteReader.DescribeAsync(outside, read.Facts, asker, cancel).ConfigureAwait(false);
        var match = StreetEdges.Match(read.StreetEdges!, site.Site["lot"] as JsonObject, outside.InternalToShared);
        if (match.StreetLine is not { } street)
            return new ProjectPrepared(null, [match.Why!], site.PhaseChecked, site.OptionsChecked, null, StreetRefused: match.Reason);
        var facts = read.Facts.DeepClone().AsObject();
        facts["street_line"] = street;
        var words = match.Words;
        return new ProjectPrepared(new ProjectRequest(site.Site, facts, interior.Interior), [], site.PhaseChecked,
                                   site.OptionsChecked, interior, words);
    }

    /// <summary>The one check_site: the site, the facts and the interior, together.</summary>
    public static Task<CheckResult> SendAsync(WorkerClient worker, ProjectRequest request, CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(worker);
        ArgumentNullException.ThrowIfNull(request);
        return worker.CheckSiteAsync(request.Site, request.Facts, interior: request.Interior, cancel: cancel);
    }

    /// <summary>Why the two reads aren't of the same design (phases, option sets, the option being edited), or null.</summary>
    internal static string? SameDesign(RevitModel a, RevitModel b)
    {
        if (!a.Phases.SequenceEqual(b.Phases))
            return "their phases differ";
        if (a.ActiveOption != b.ActiveOption)
            return "the design option being edited differs";
        static string Sets(RevitModel m) => string.Join("|", m.OptionSets.OrderBy(s => s.Id, StringComparer.Ordinal)
            .Select(s => s.Id + ":" + string.Join(",", s.Options.OrderBy(o => o.Id, StringComparer.Ordinal)
                .Select(o => o.Id + (o.IsPrimary ? "*" : "")))));
        return Sets(a) == Sets(b) ? null : "their design option sets differ";
    }
}

/// <summary>The lot facts as Gordium's marks on Project Information give them.</summary>
/// <param name="Facts">The facts to send (jurisdiction, zone, use, lot_surveyed, and corner_lot and grade_from when
/// set); street_line is added once the lot is read (<c>StreetEdges.Match</c>).</param>
/// <param name="StreetEdges">The street edges picked (Revit's internal coordinates), or null when not set.</param>
/// <param name="Missing">What to fill in; empty when every required fact is stated.</param>
public sealed record ProjectFactsRead(JsonObject Facts, IReadOnlyList<KeptEdge>? StreetEdges, IReadOnlyList<string> Missing);

/// <summary>The lot facts from the marks. Gordium checks the City of Ithaca only (CLAUDE.md: first city), so the
/// jurisdiction is fixed. Every required fact (the checker's own list, host_core.facts.REQUIRED: zone, use,
/// street_line, lot_surveyed) unset, and it is listed as missing; an unset optional one (corner lot, the ground) is
/// not sent, so the rows it decides need review.</summary>
public static class ProjectFacts
{
    public const string Jurisdiction = "regulations/jurisdictions/new_york/ithaca_city";

    private const string Where = " on Project Information (Manage > Project Information)";

    /// <summary>The street edge not set, as the panel lists it.</summary>
    public static readonly string StreetNotSet = $"{Marks.StreetEdge.Name}: click the lot edge along the street when Check " +
                                                 "project asks (in a plan or site view; with no property line drawn, draw it first).";

    public static ProjectFactsRead Read(RevitModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        var missing = new List<string>();
        var facts = new JsonObject { ["jurisdiction"] = Jurisdiction };
        MarkValue? Get(MarkDefinition m) => model.ProjectMarks.TryGetValue(m.Guid, out var v) ? v : null;

        if (Marks.Text(Get(Marks.Zone)) is { } zone)
            facts["zone"] = zone;
        else
            missing.Add($"{Marks.Zone.Name}: type the lot's zoning district as the City's zoning map writes it (R-1b, R-2a...){Where}.");
        if (Marks.Text(Get(Marks.Use)) is { } use)
            facts["use"] = use;
        else
            missing.Add($"{Marks.Use.Name}: type what the building is used for, in Gordium's word (one_family_detached...){Where}.");
        if (Marks.YesNo(Get(Marks.LotSurveyed)) is { } surveyed)
            facts["lot_surveyed"] = surveyed;
        else
            missing.Add($"{Marks.LotSurveyed.Name}: tick Yes if the property line is drawn from a survey, No if from the tax map{Where}.");
        if (Marks.YesNo(Get(Marks.CornerLot)) is { } corner)
            facts["corner_lot"] = corner;
        var ground = Marks.Text(Get(Marks.GroundFrom));
        if (ground is not null)
        {
            var word = Marks.GroundWords.FirstOrDefault(w => string.Equals(w.Word, ground, StringComparison.OrdinalIgnoreCase));
            if (word.Word is null)
                missing.Add($"{Marks.GroundFrom.Name} is \"{ground}\": type one of " +
                            string.Join(" or ", Marks.GroundWords.Select(w => w.Word)) + $", or leave it blank{Where}.");
            else
                facts["grade_from"] = word.GradeFrom;
        }
        IReadOnlyList<KeptEdge>? edges = null;
        var street = Marks.Text(Get(Marks.StreetEdge));
        if (street is null)
            missing.Add(StreetNotSet);
        else if ((edges = StreetEdges.Parse(street)) is null)
            missing.Add($"{Marks.StreetEdge.Name} holds \"{street}\", which isn't an edge Gordium wrote: clear it, then " +
                        "click the lot edge along the street when Check project asks.");
        return new ProjectFactsRead(facts, edges, missing);
    }

    /// <summary>Every write of a Gordium mark (the street pick's and a request file's) goes through here:
    /// <paramref name="set"/> is Revit's Parameter.Set, which says false when it didn't set the value; then it throws
    /// naming the mark, so nothing is checked or logged as set on a mark the project doesn't hold.</summary>
    public static void Write(MarkDefinition mark, string value, Func<bool> set)
    {
        ArgumentNullException.ThrowIfNull(mark);
        ArgumentNullException.ThrowIfNull(set);
        if (!set())
            throw new InvalidOperationException($"Revit didn't set {mark.Name} to {value}: nothing was checked");
    }

    /// <summary>A mark's value in a request file (check_project_request.json's "marks"), as Revit's Parameter.Set
    /// takes it: a Yes/No mark needs true or false (1 or 0), a text mark text. Anything else is refused naming the
    /// mark, never set as something near it: a check made on a mark the request didn't mean.</summary>
    public static (int? YesNo, string? Text) RequestValue(MarkDefinition mark, JsonNode? value)
    {
        ArgumentNullException.ThrowIfNull(mark);
        var v = value as JsonValue;
        switch (mark.Kind)
        {
            case MarkValueKind.YesNo when v is not null && v.TryGetValue<bool>(out var yes):
                return (yes ? 1 : 0, null);
            case MarkValueKind.Text when v is not null && v.TryGetValue<string>(out var text):
                return (null, text);
            default:
                throw new InvalidOperationException(
                    $"{mark.Name} is a {(mark.Kind == MarkValueKind.YesNo ? "Yes/No mark: give true or false" : mark.Kind == MarkValueKind.Text ? "text mark: give text" : "length mark, which a request can't set")}, " +
                    $"not {value?.ToJsonString() ?? "null"}: nothing was checked");
        }
    }
}

/// <summary>A lot edge picked as the street: its ends (internal coordinates), whether it is straight, and its length
/// (along the curve for a curved one); Mid, a point on it, halfway along (internal coordinates): with IsLine, what tells an arc
/// from its chord, or two arcs on the same ends, apart (review round 4).</summary>
public sealed record PickedEdge(Xyz A, Xyz B, bool IsLine, double Length, Xyz? Mid = null);

/// <summary>A street edge as the mark keeps it: its ends and, when Gordium wrote them (from round 4), whether it is
/// straight and its point halfway along. An older mark has the ends alone (<see cref="IsLine"/> null).</summary>
public sealed record KeptEdge(Xyz A, Xyz B, bool? IsLine = null, Xyz? Mid = null);

/// <summary>Whether "Check my project" asks for the street edge by a click now (<see cref="StreetEdges.Ask"/>).</summary>
public enum StreetAsk
{
    /// <summary>Kept and usable: nothing to ask.</summary>
    NotNeeded,
    /// <summary>Asked for now: every other fact is set and the view shows a property line.</summary>
    Pick,
    /// <summary>Not asked: other facts are missing (the panel lists them first).</summary>
    OtherFactsFirst,
    /// <summary>Not asked: the active view can't show the property line (the panel says to open a site plan).</summary>
    OpenAPlan,
}

/// <summary>Why a kept street edge wasn't sent as a lot edge.</summary>
public enum StreetRefusal
{
    None,
    /// <summary>No lot edge has its ends (and kind and middle): the property line was changed.</summary>
    NoLongerAnEdge,
    /// <summary>More than one lot edge matches what was kept (an older mark with its ends alone, on a lot with an arc
    /// and its chord): which was meant can't be told.</summary>
    Ambiguous,
}

/// <summary>What <see cref="StreetEdges.Match(IReadOnlyList{KeptEdge}, JsonObject?, Transform3)"/> gives: the street
/// line to send, or why not (in words, and typed).</summary>
public sealed record StreetMatch(JsonArray? StreetLine, string? Why, StreetRefusal Reason)
{
    /// <summary>The street line sent, in words: each the lot edge matched, by its own points (a curved one by its
    /// length along them); a kept edge sent with no lot read, without a length.</summary>
    public string? Words { get; init; }

    public void Deconstruct(out JsonArray? streetLine, out string? why) => (streetLine, why) = (StreetLine, Why);
}

/// <summary>The street edges: picked by the architect on the property line (<see cref="Nearest"/>), kept in the
/// <see cref="Marks.StreetEdge"/> mark as their ends in Revit's internal coordinates (they don't move when the shared
/// coordinates are set again), and sent as the lot's own edges (<c>Match</c>): an edge the lot no longer has
/// (the property line redrawn) is asked for again, never sent as a street line no lot edge is.</summary>
public static class StreetEdges
{
    /// <summary>How near a picked point must be to an edge (ft): Revit puts the pick on the line itself.</summary>
    public const double PickReach = 1.0;

    /// <summary>How near a kept edge's ends must be to a lot edge's (ft).</summary>
    public const double Tolerance = 0.01;

    /// <summary>How near a kept edge's middle must be to a lot edge's (ft): a curved lot edge is sent as points
    /// <see cref="LotReader.ArcStep"/> apart, so its middle is found to within that.</summary>
    public const double MidTolerance = LotReader.ArcStep;

    private static string R(double v) => v.ToString("R", CultureInfo.InvariantCulture);

    /// <summary>The kept edges as the mark's text, "; " between (feet, internal): "x1 y1 x2 y2 line mx my" or
    /// "x1 y1 x2 y2 arc mx my" (its kind and its point halfway along); an edge with no middle known, the ends alone.</summary>
    public static string Format(IEnumerable<KeptEdge> edges) =>
        string.Join("; ", edges.Select(e => string.Join(" ", new[] { e.A.X, e.A.Y, e.B.X, e.B.Y }.Select(R))
            + (e.IsLine is { } line && e.Mid is { } m ? $" {(line ? "line" : "arc")} {R(m.X)} {R(m.Y)}" : "")));

    /// <summary>Ends alone (a lot line's own ends, as the log lists them; an older mark).</summary>
    public static string Format(IEnumerable<(Xyz A, Xyz B)> edges) => Format(edges.Select(e => new KeptEdge(e.A, e.B)));

    /// <summary>The mark's text as edges (an older mark's ends alone still read), or null when it isn't text
    /// <see cref="Format(IEnumerable{KeptEdge})"/> wrote.</summary>
    public static IReadOnlyList<KeptEdge>? Parse(string text)
    {
        var edges = new List<KeptEdge>();
        foreach (var part in text.Split(';'))
        {
            var v = part.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (v.Length != 4 && !(v.Length == 7 && v[4] is "line" or "arc"))
                return null;
            var idx = v.Length == 4 ? new[] { 0, 1, 2, 3 } : new[] { 0, 1, 2, 3, 5, 6 };
            var n = new double[7];
            foreach (var i in idx)
                if (!double.TryParse(v[i], NumberStyles.Float, CultureInfo.InvariantCulture, out n[i]) || !double.IsFinite(n[i]))
                    return null;
            if (n[0] == n[2] && n[1] == n[3])
                return null;
            edges.Add(v.Length == 4
                ? new KeptEdge(new Xyz(n[0], n[1], 0), new Xyz(n[2], n[3], 0))
                : new KeptEdge(new Xyz(n[0], n[1], 0), new Xyz(n[2], n[3], 0), v[4] == "line", new Xyz(n[5], n[6], 0)));
        }
        return edges.Count > 0 ? edges : null;
    }

    /// <summary>What PickObject's status bar says while the street edge is asked for.</summary>
    public const string PickPrompt = "Click the lot edge along the street (Esc to skip)";

    /// <summary>The words listed in the panel when the street edge is needed but the active view can't show it.</summary>
    public static readonly string OpenAPlan = $"{Marks.StreetEdge.Name}: open a site plan (or a floor plan) that shows the " +
                                              "property line, then click Check again: it asks you to click the lot edge along the street.";

    /// <summary>Whether to ask for the street edge now (Revit trial, 2026-11-20: asked from a sheet view, the pick
    /// waited with no prompt where no property line could be clicked). Only when the street edge is the one fact
    /// still to give (<paramref name="needed"/>: not set, or kept but no longer a lot edge) and every other fact is
    /// set, and only in a view that shows a property line (<paramref name="viewShowsPropertyLine"/>: a plan view
    /// with one visible). <see cref="StreetAsk.OpenAPlan"/>: the panel lists <see cref="OpenAPlan"/> instead.</summary>
    public static StreetAsk Ask(ProjectFactsRead read, bool needed, bool viewShowsPropertyLine)
    {
        ArgumentNullException.ThrowIfNull(read);
        if (!needed)
            return StreetAsk.NotNeeded;
        if (read.Missing.Any(m => !m.StartsWith(Marks.StreetEdge.Name, StringComparison.Ordinal)))
            return StreetAsk.OtherFactsFirst;
        return viewShowsPropertyLine ? StreetAsk.Pick : StreetAsk.OpenAPlan;
    }

    /// <summary>What to fill in, as the panel lists it: when the view couldn't show the property line, the street
    /// edge's "click when Check project asks" replaced by <see cref="OpenAPlan"/> (a kept edge's own reason kept,
    /// <see cref="OpenAPlan"/> after it).</summary>
    public static IReadOnlyList<string> MissingAsShown(IReadOnlyList<string> missing, StreetAsk ask)
    {
        ArgumentNullException.ThrowIfNull(missing);
        if (ask != StreetAsk.OpenAPlan)
            return missing;
        var shown = missing.Where(m => m != ProjectFacts.StreetNotSet).ToList();
        if (!shown.Contains(OpenAPlan))
            shown.Add(OpenAPlan);
        return shown;
    }

    /// <summary>Whether the refusal's fix is a new pick (the button then asks for the edge again).</summary>
    public static bool NeedsNewPick(ProjectPrepared prepared)
    {
        ArgumentNullException.ThrowIfNull(prepared);
        return prepared.Request is null && prepared.StreetRefused is StreetRefusal.NoLongerAnEdge or StreetRefusal.Ambiguous;
    }

    /// <summary>How near a corner a click is refused (ft): a click this near an end the edge shares with another can
    /// land on either edge (Revit highlights the whole property line, not the edge hit). A quarter of a shorter edge's
    /// length, so every edge keeps a middle that can be clicked.</summary>
    public const double CornerReach = 2.0;

    /// <summary>The edge of the property line nearest the point picked on it (plan distance, internal coordinates):
    /// its two ends, or why none: the pick off every edge; or at a corner (the two nearest edges within half
    /// <see cref="PickReach"/> of each other, or the click within <see cref="CornerReach"/> of an end the edge shares
    /// with another), where a click meant for one edge can keep the other.</summary>
    public static (PickedEdge? Edge, string? Why) Nearest(LotLineElement line, Xyz picked)
    {
        ArgumentNullException.ThrowIfNull(line);
        var near = line.Curves.Select(c => (Curve: c, D: PlanDistance(LotReader.Points(c), picked)))
                              .OrderBy(x => x.D).ToList();
        if (near.Count == 0 || near[0].D > PickReach)
            return (null, "the click wasn't on an edge of the property line: click on the edge along the street");
        const string corner = "the click was too near a corner, where it could be on either edge: click nearer the middle of the edge along the street";
        if (near.Count > 1 && near[1].D - near[0].D < PickReach / 2)
            return (null, corner);
        var c0 = near[0].Curve;
        var reach = Math.Min(CornerReach, (c0.IsLine ? Plan(c0.Start, c0.End) : c0.Length) / 4);
        foreach (var end in new[] { c0.Start, c0.End })
            if (Plan(end, picked) < reach && line.Curves.Any(c => !ReferenceEquals(c, c0)
                    && (Plan(c.Start, end) <= Tolerance || Plan(c.End, end) <= Tolerance)))
                return (null, corner);
        // its point halfway along: a line's midpoint; a curve's at half its normalised parameter (Curve.Evaluate)
        var mid = c0.IsLine || c0.PointAt is null ? 0.5 * (c0.Start + c0.End) : c0.PointAt(0.5);
        return (new PickedEdge(new Xyz(c0.Start.X, c0.Start.Y, 0), new Xyz(c0.End.X, c0.End.Y, 0), c0.IsLine,
                               c0.IsLine ? Plan(c0.Start, c0.End) : c0.Length, new Xyz(mid.X, mid.Y, 0)), null);
    }

    private static double Plan(Xyz a, Xyz b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    /// <summary>An edge as the architect confirms it: "the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)"; a curved
    /// one by its length along the curve, never its chord: "the curved 47.1 ft lot edge from ...". The coordinates
    /// as given (shared, for what is sent and shown); <paramref name="curvedLength"/> null for a straight edge.</summary>
    public static string Describe((double X, double Y) a, (double X, double Y) b, double? curvedLength = null) =>
        string.Create(CultureInfo.InvariantCulture,
            $"the {(curvedLength is null ? "" : "curved ")}{curvedLength ?? Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y)):0.0} ft lot edge from ({N(a.X)}, {N(a.Y)}) to ({N(b.X)}, {N(b.Y)})");

    /// <summary>A coordinate to a tenth, never "-0.0" (a point a hair below 0).</summary>
    private static string N(double v) => (Math.Round(v, 1) + 0.0).ToString("0.0", CultureInfo.InvariantCulture);

    /// <summary>A picked edge (internal coordinates) described in the shared coordinates the check uses.</summary>
    public static string Describe(PickedEdge edge, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(edge);
        ArgumentNullException.ThrowIfNull(toShared);
        Xyz a = toShared.Apply(edge.A), b = toShared.Apply(edge.B);
        return Describe((a.X, a.Y), (b.X, b.Y), edge.IsLine ? null : edge.Length);
    }

    /// <summary>The lot edge matched, in words: by its own points (a curved edge by its length along them).</summary>
    private static string Words(List<(double X, double Y)> pts, bool curved) =>
        curved ? Describe(pts[0], pts[^1], pts.Zip(pts.Skip(1), (p, q) => Math.Sqrt((p.X - q.X) * (p.X - q.X) + (p.Y - q.Y) * (p.Y - q.Y))).Sum())
               : Describe(pts[0], pts[^1]);

    /// <summary>A street edge sent as kept, matched to no lot edge: no length said (never the chord of an arc).</summary>
    private static string Unmatched((double X, double Y) a, (double X, double Y) b) => string.Create(CultureInfo.InvariantCulture,
        $"the street edge from ({N(a.X)}, {N(a.Y)}) to ({N(b.X)}, {N(b.Y)}), not matched to a lot (none was read)");

    /// <summary>Keeps the picked edges in the <see cref="Marks.StreetEdge"/> mark through <paramref name="set"/> (Revit's
    /// Parameter.Set, which says false when it didn't), and logs them only once set: never a street edge logged that
    /// the project doesn't hold.</summary>
    public static void Keep(IEnumerable<PickedEdge> edges, Func<string, bool> set, IDictionary<string, object?> log)
    {
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentNullException.ThrowIfNull(log);
        var text = Format(edges.Select(e => new KeptEdge(e.A, e.B, e.Mid is null ? null : e.IsLine, e.Mid)));
        ProjectFacts.Write(Marks.StreetEdge, text, () => set(text));
        log["street_edge"] = text;
    }

    /// <summary>The kept edges as the facts' <c>street_line</c>: each the lot's own edge whose ends they are (turned
    /// into the shared coordinates), sent with the lot edge's exact first and last points; or why not (an edge the
    /// lot doesn't have). With no lot read, the kept edges are sent turned as they are: the check then says there is
    /// no lot, so nothing complies. A kept edge with its kind and middle (from round 4) matches only the lot edge
    /// whose ends, kind and middle all agree, so an arc and its chord never match each other; an older mark's ends
    /// alone matching more than one lot edge is refused (<see cref="StreetRefusal.Ambiguous"/>).</summary>
    public static StreetMatch Match(IReadOnlyList<(Xyz A, Xyz B)> edges, JsonObject? lot, Transform3 toShared) =>
        Match(edges.Select(e => new KeptEdge(e.A, e.B)).ToList(), lot, toShared);

    public static StreetMatch Match(IReadOnlyList<KeptEdge> edges, JsonObject? lot, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentNullException.ThrowIfNull(toShared);
        static JsonArray Pt(double x, double y) => new(x, y);
        static (double X, double Y) P(JsonNode? p) => (p![0]!.GetValue<double>(), p[1]!.GetValue<double>());
        var line = new JsonArray();
        var words = new List<string>();
        foreach (var kept in edges)
        {
            Xyz sa = toShared.Apply(kept.A), sb = toShared.Apply(kept.B);
            Xyz? sm = kept.Mid is { } m ? toShared.Apply(m) : null;
            if (lot is null)
            {
                line.Add(new JsonArray(Pt(sa.X, sa.Y), Pt(sb.X, sb.Y)));
                words.Add(Unmatched((sa.X, sa.Y), (sb.X, sb.Y)));
                continue;
            }
            JsonArray? found = null;
            List<(double X, double Y)>? foundPts = null;
            var foundCurved = false;
            var matches = 0;
            foreach (var e in lot["edges"]!.AsArray())
            {
                var pts = e!["points"]!.AsArray();
                var (f, l) = (pts[0]!.AsArray(), pts[^1]!.AsArray());
                double fx = f[0]!.GetValue<double>(), fy = f[1]!.GetValue<double>();
                double lx = l[0]!.GetValue<double>(), ly = l[1]!.GetValue<double>();
                bool Near(Xyz p, double x, double y) => Math.Abs(p.X - x) <= Tolerance && Math.Abs(p.Y - y) <= Tolerance;
                if (!(Near(sa, fx, fy) && Near(sb, lx, ly) || Near(sa, lx, ly) && Near(sb, fx, fy)))
                    continue;
                if (kept.IsLine is { } isLine && sm is { } want)
                {
                    if (isLine != (e["curved"]?.GetValue<bool>() != true))
                        continue;                                    // an arc kept never matches a straight edge, nor a line an arc
                    var (mx, my) = Middle(pts.Select(P).ToList());
                    if (Math.Abs(want.X - mx) > MidTolerance || Math.Abs(want.Y - my) > MidTolerance)
                        continue;                                    // another curve on the same ends
                }
                if (found is null)
                {
                    found = new JsonArray(Pt(fx, fy), Pt(lx, ly));
                    foundPts = pts.Select(P).ToList();
                    foundCurved = e["curved"]?.GetValue<bool>() == true;
                }
                matches++;
            }
            // what will happen is said: the button asks for the edge again at once; a request file has no pick
            const string again = " Check project asks you to click the lot edge along the street again (from a request " +
                                 "file: give the Gordium: Street edge mark again); nothing is checked until then.";
            if (matches > 1)
                return new(null, $"{Marks.StreetEdge.Name}: the street edge kept matches more than one lot edge (two share its " +
                                 "ends, an arc and its chord: it was kept before Gordium noted which)." + again, StreetRefusal.Ambiguous);
            if (found is null)
                return new(null, $"{Marks.StreetEdge.Name}: the street edge picked is no longer an edge of the lot (the " +
                                 "property line was changed)." + again, StreetRefusal.NoLongerAnEdge);
            line.Add(found);
            words.Add(Words(foundPts!, foundCurved));
        }
        return new(line, null, StreetRefusal.None) { Words = string.Join(" and ", words) };
    }

    /// <summary>The point halfway along a run of points (by length).</summary>
    private static (double X, double Y) Middle(List<(double X, double Y)> pts)
    {
        var lengths = pts.Zip(pts.Skip(1), (p, q) => Math.Sqrt((p.X - q.X) * (p.X - q.X) + (p.Y - q.Y) * (p.Y - q.Y))).ToList();
        var half = lengths.Sum() / 2;
        for (var i = 0; i < lengths.Count; i++)
        {
            if (half <= lengths[i] && lengths[i] > 0)
            {
                var t = half / lengths[i];
                return (pts[i].X + t * (pts[i + 1].X - pts[i].X), pts[i].Y + t * (pts[i + 1].Y - pts[i].Y));
            }
            half -= lengths[i];
        }
        return pts[^1];
    }

    private static double PlanDistance(List<Xyz> pts, Xyz p)
    {
        var best = double.PositiveInfinity;
        for (var i = 0; i + 1 < pts.Count; i++)
        {
            double ax = pts[i].X, ay = pts[i].Y, dx = pts[i + 1].X - ax, dy = pts[i + 1].Y - ay;
            var len2 = dx * dx + dy * dy;
            var t = len2 == 0 ? 0 : Math.Clamp(((p.X - ax) * dx + (p.Y - ay) * dy) / len2, 0, 1);
            best = Math.Min(best, Math.Sqrt(Math.Pow(p.X - ax - t * dx, 2) + Math.Pow(p.Y - ay - t * dy, 2)));
        }
        return best;
    }
}
