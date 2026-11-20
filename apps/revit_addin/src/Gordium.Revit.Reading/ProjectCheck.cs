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
public sealed record ProjectPrepared(ProjectRequest? Request, IReadOnlyList<string> Missing, string? PhaseChecked,
                                     IReadOnlyList<string> OptionsChecked, InteriorReadResult? Inside, string? Street = null);

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
                                           "): nothing is sent; run Check my project again");
        var read = ProjectFacts.Read(inside);
        if (read.Missing.Count > 0)
            return new ProjectPrepared(null, read.Missing, null, [], null);

        // everything read from the records before the first await, on the caller's thread (Revit's: a lot line's
        // points call back into the API; SiteReader reads the lot before it asks the worker anything)
        var interior = InteriorReader.Read(inside);
        var site = await SiteReader.DescribeAsync(outside, read.Facts, asker, cancel).ConfigureAwait(false);
        var (street, why) = StreetEdges.Match(read.StreetEdges!, site.Site["lot"] as JsonObject, outside.InternalToShared);
        if (street is null)
            return new ProjectPrepared(null, [why!], site.PhaseChecked, site.OptionsChecked, null);
        var facts = read.Facts.DeepClone().AsObject();
        facts["street_line"] = street;
        var words = string.Join(" and ", street.Select(e => StreetEdges.Describe(
            (e![0]![0]!.GetValue<double>(), e[0]![1]!.GetValue<double>()), (e[1]![0]!.GetValue<double>(), e[1]![1]!.GetValue<double>()))));
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
/// set); street_line is added once the lot is read (<see cref="StreetEdges.Match"/>).</param>
/// <param name="StreetEdges">The street edges picked (Revit's internal coordinates), or null when not set.</param>
/// <param name="Missing">What to fill in; empty when every required fact is stated.</param>
public sealed record ProjectFactsRead(JsonObject Facts, IReadOnlyList<(Xyz A, Xyz B)>? StreetEdges, IReadOnlyList<string> Missing);

/// <summary>The lot facts from the marks. Gordium checks the City of Ithaca only (CLAUDE.md: first city), so the
/// jurisdiction is fixed. Every required fact (the checker's own list, host_core.facts.REQUIRED: zone, use,
/// street_line, lot_surveyed) unset, and it is listed as missing; an unset optional one (corner lot, the ground) is
/// not sent, so the rows it decides need review.</summary>
public static class ProjectFacts
{
    public const string Jurisdiction = "regulations/jurisdictions/new_york/ithaca_city";

    private const string Where = " on Project Information (Manage > Project Information)";

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
        IReadOnlyList<(Xyz, Xyz)>? edges = null;
        var street = Marks.Text(Get(Marks.StreetEdge));
        if (street is null)
            missing.Add($"{Marks.StreetEdge.Name}: click the lot edge along the street when Check my project asks " +
                        "(in a plan or site view; with no property line drawn, draw it first).");
        else if ((edges = StreetEdges.Parse(street)) is null)
            missing.Add($"{Marks.StreetEdge.Name} holds \"{street}\", which isn't an edge Gordium wrote: clear it, then " +
                        "click the lot edge along the street when Check my project asks.");
        return new ProjectFactsRead(facts, edges, missing);
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

/// <summary>The street edges: picked by the architect on the property line (<see cref="Nearest"/>), kept in the
/// <see cref="Marks.StreetEdge"/> mark as their ends in Revit's internal coordinates (they don't move when the shared
/// coordinates are set again), and sent as the lot's own edges (<see cref="Match"/>): an edge the lot no longer has
/// (the property line redrawn) is asked for again, never sent as a street line no lot edge is.</summary>
public static class StreetEdges
{
    /// <summary>How near a picked point must be to an edge (ft): Revit puts the pick on the line itself.</summary>
    public const double PickReach = 1.0;

    /// <summary>How near a kept edge's ends must be to a lot edge's (ft).</summary>
    public const double Tolerance = 0.01;

    /// <summary>The kept edges as the mark's text: "x1 y1 x2 y2" per edge (feet, internal), "; " between.</summary>
    public static string Format(IEnumerable<(Xyz A, Xyz B)> edges) =>
        string.Join("; ", edges.Select(e => string.Join(" ", new[] { e.A.X, e.A.Y, e.B.X, e.B.Y }
            .Select(v => v.ToString("R", CultureInfo.InvariantCulture)))));

    /// <summary>The mark's text as edges, or null when it isn't text <see cref="Format"/> wrote.</summary>
    public static IReadOnlyList<(Xyz A, Xyz B)>? Parse(string text)
    {
        var edges = new List<(Xyz, Xyz)>();
        foreach (var part in text.Split(';'))
        {
            var v = part.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (v.Length != 4)
                return null;
            var n = new double[4];
            for (var i = 0; i < 4; i++)
                if (!double.TryParse(v[i], NumberStyles.Float, CultureInfo.InvariantCulture, out n[i]) || !double.IsFinite(n[i]))
                    return null;
            if (n[0] == n[2] && n[1] == n[3])
                return null;
            edges.Add((new Xyz(n[0], n[1], 0), new Xyz(n[2], n[3], 0)));
        }
        return edges.Count > 0 ? edges : null;
    }

    /// <summary>How near a corner a click is refused (ft): a click this near an end the edge shares with another can
    /// land on either edge (Revit highlights the whole property line, not the edge hit). A quarter of a shorter edge's
    /// length, so every edge keeps a middle that can be clicked.</summary>
    public const double CornerReach = 2.0;

    /// <summary>The edge of the property line nearest the point picked on it (plan distance, internal coordinates):
    /// its two ends, or why none: the pick off every edge; or at a corner (the two nearest edges within half
    /// <see cref="PickReach"/> of each other, or the click within <see cref="CornerReach"/> of an end the edge shares
    /// with another), where a click meant for one edge can keep the other.</summary>
    public static ((Xyz A, Xyz B)? Edge, string? Why) Nearest(LotLineElement line, Xyz picked)
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
        var reach = Math.Min(CornerReach, Plan(c0.Start, c0.End) / 4);
        foreach (var end in new[] { c0.Start, c0.End })
            if (Plan(end, picked) < reach && line.Curves.Any(c => !ReferenceEquals(c, c0)
                    && (Plan(c.Start, end) <= Tolerance || Plan(c.End, end) <= Tolerance)))
                return (null, corner);
        return ((new Xyz(c0.Start.X, c0.Start.Y, 0), new Xyz(c0.End.X, c0.End.Y, 0)), null);
    }

    private static double Plan(Xyz a, Xyz b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    /// <summary>An edge as the architect confirms it: "the 60.0 ft lot edge from (0.0, 0.0) to (60.0, 0.0)" (the
    /// straight distance between its ends; the coordinates as given: shared for what is sent and shown).</summary>
    public static string Describe((double X, double Y) a, (double X, double Y) b) =>
        string.Create(CultureInfo.InvariantCulture,
            $"the {Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y)):0.0} ft lot edge from ({a.X:0.0}, {a.Y:0.0}) to ({b.X:0.0}, {b.Y:0.0})");

    /// <summary>A kept edge (internal coordinates) described in the shared coordinates the check uses.</summary>
    public static string Describe((Xyz A, Xyz B) edge, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(toShared);
        Xyz a = toShared.Apply(edge.A), b = toShared.Apply(edge.B);
        return Describe((a.X, a.Y), (b.X, b.Y));
    }

    /// <summary>The kept edges as the facts' <c>street_line</c>: each the lot's own edge whose ends they are (turned
    /// into the shared coordinates), sent with the lot edge's exact first and last points; or why not (an edge the
    /// lot doesn't have). With no lot read, the kept edges are sent turned as they are: the check then says there is
    /// no lot, so nothing complies.</summary>
    public static (JsonArray? StreetLine, string? Why) Match(IReadOnlyList<(Xyz A, Xyz B)> edges, JsonObject? lot, Transform3 toShared)
    {
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentNullException.ThrowIfNull(toShared);
        static JsonArray Pt(double x, double y) => new(x, y);
        var line = new JsonArray();
        foreach (var (a, b) in edges)
        {
            Xyz sa = toShared.Apply(a), sb = toShared.Apply(b);
            if (lot is null)
            {
                line.Add(new JsonArray(Pt(sa.X, sa.Y), Pt(sb.X, sb.Y)));
                continue;
            }
            JsonArray? found = null;
            foreach (var e in lot["edges"]!.AsArray())
            {
                var pts = e!["points"]!.AsArray();
                var (f, l) = (pts[0]!.AsArray(), pts[^1]!.AsArray());
                double fx = f[0]!.GetValue<double>(), fy = f[1]!.GetValue<double>();
                double lx = l[0]!.GetValue<double>(), ly = l[1]!.GetValue<double>();
                bool Near(Xyz p, double x, double y) => Math.Abs(p.X - x) <= Tolerance && Math.Abs(p.Y - y) <= Tolerance;
                if (Near(sa, fx, fy) && Near(sb, lx, ly) || Near(sa, lx, ly) && Near(sb, fx, fy))
                {
                    found = new JsonArray(Pt(fx, fy), Pt(lx, ly));
                    break;
                }
            }
            if (found is null)
                return (null, $"{Marks.StreetEdge.Name}: the street edge picked is no longer an edge of the lot (the " +
                              "property line was changed): click the lot edge along the street again when Check my project asks.");
            line.Add(found);
        }
        return (line, null);
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
