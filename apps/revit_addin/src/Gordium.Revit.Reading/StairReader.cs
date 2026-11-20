using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>
/// The stairs, section 7 step 4 of docs/revit/revit_interior_reading_design.md: each run of a component stair is a
/// flight of the interior description (<c>stairs</c>), read from what is drawn and checked against what was typed.
/// The rules are the note's sections 2 and 4:
/// <list type="bullet">
/// <item><c>stairs</c> is sent only when the architect has ticked <c>Gordium: These are all the stairs</c> (Yes) and
/// nothing could be a stair the reader doesn't walk (a stair not made of components, a multistory stair, anything in
/// Stairs, Railings or Generic Models that isn't a Stairs or a Railing, a closed workset, an unloaded link, a link
/// holding stairs, a coordination model). Nothing found is never "none": with no stair found the list is left out.</item>
/// <item>A flight found is never dropped: a value that can't be read exactly is left out, with its reason.</item>
/// <item><c>bottom_elevation</c>: the top of the floor or landing in front of the first riser, as drawn (below the
/// first tread), even where it stands off the run's own base. <c>nosings</c>: each tread's front edge from the run's own
/// geometry, then the edge of the floor or landing at the head, as drawn (above the last tread, nothing of the run
/// above it): so a first or last riser taller or shorter than the run's is sent as it is drawn, and the checker
/// measures it. Sent only when the run's own risers (base to top) and treads agree with the stair's typed
/// <c>ActualRiserHeight</c> and <c>ActualTreadDepth</c>, and the counts with the run's own. A run that isn't straight
/// sends neither.</item>
/// <item><c>sides</c>: on each side, the band from the middle of the flight to 6 in past its tread ends, from 1 in
/// under the line of nosings to 80 in over it, searched for anything: the innermost wall face there running the whole
/// band is the side line; nothing at all is <c>open</c>; anything else (a column, the stair's own support rising into
/// it, a railing not read as below) leaves <c>sides</c> out. A vertical face is judged exactly up the run (a roof's
/// side rising more slowly than the stair is in the band only where it is).</item>
/// <item><c>handrails</c> (step 5): a railing on this stair beside a wall, read exactly (flat faces, straight edges),
/// every point between the wall face and the flight's middle and none more than 38 in over the nosings, is a handrail,
/// not a side: its handrails (and its top rail where its type is marked <c>Gordium: Top rail is handrail</c> Yes; unset
/// with a top rail: none sent) each give their edge nearest the middle, as far as they run. Sent only on the tick
/// <c>Gordium: These are all the guards and handrails</c> and with both sides read; none found is then an empty list.
/// Any other railing beside the flight (on an open side: a guard along a stair; not the stair's; round; higher) leaves
/// <c>sides</c> and <c>handrails</c> out, and the guards with them.</item>
/// <item><c>overhead</c>: the downward flat faces of everything over the flight, clipped to its plan (a floor's
/// stairwell opening taken out exactly), each above the line of nosings; anything there it can't read exactly, a
/// railing reaching over it that isn't the stair's own no higher than 38 in over the nosings, or something crossing
/// the flight leaves <c>overhead</c> out.</item>
/// <item>A loaded link reaching the flight's plan leaves its bottom, nosings, sides and overhead out.</item>
/// </list>
/// </summary>
public static class StairReader
{
    private const double Sixteenth = InteriorReader.Sixteenth;
    private const double Inch = 1.0 / 12;

    /// <summary>The strip in front of the first riser, and past the last, where the floor is looked for (ft).</summary>
    public const double Strip = 1.0 / 12;

    /// <summary>The deepest a riser board's top may be along the run (ft): 2 in, a fifth of the shallowest tread
    /// the code allows (10 in), and four times Revit's default riser (1/2 in).</summary>
    public const double RiserBoard = 2.0 / 12;

    /// <summary>How far past the tread ends a side is looked for (ft): beyond the 1 1/2 in a stringer may take.</summary>
    public const double SideReach = 0.5;

    /// <summary>How far over the line of nosings a side is looked for: the headroom the code asks (80 in).</summary>
    public const double SideHeight = 80.0 / 12;

    /// <summary>The lowest a handrail may be (34 in): a stair's own support under it can't narrow the width above it.</summary>
    public const double HandrailLow = 34.0 / 12;

    /// <summary>The highest a handrail may be (38 in, R318.7.8.1): a railing of the stair's beside a wall wholly at or
    /// under it is a handrail, inside the width at the handrail, never narrowing the width above it (step 5).</summary>
    public const double HandrailHigh = 38.0 / 12;

    /// <summary>What the flights made of the railings beside them (step 5): those read as a handrail beside a wall on
    /// every flight they stand by, and those refused (on an open side, not the stair's, not read exactly). The guards
    /// are read only when every railing on a stair is one of the first (<see cref="GuardReader"/>).</summary>
    public sealed class RailingUse
    {
        public HashSet<string> BesideWall { get; } = new(StringComparer.Ordinal);
        public HashSet<string> Refused { get; } = new(StringComparer.Ordinal);
    }

    /// <summary>A railing and its parts.</summary>
    public static readonly IReadOnlySet<string> Railings = new HashSet<string>(StringComparer.Ordinal)
    {
        "OST_StairsRailing", "OST_RailingTopRail", "OST_RailingHandRail", "OST_RailingSupport", "OST_RailingTermination",
        "OST_StairsRailingBaluster", "OST_StairsRailingRail",
    };

    // ---- what stops the stairs being read -----------------------------------------------------------------------

    /// <summary>Why no stair can be read, the architect's tick first, then each thing that could be a stair the reader
    /// doesn't walk (<see cref="Blockers"/>). Empty when the stairs can be read.</summary>
    public static List<string> NotRead(RevitModel model)
    {
        if (model.Interior is null)
            return ["the model's inside wasn't read"];
        var why = new List<string>();
        if (MarkReading.AllStairs(model) is not true)
            why.Add($"{Marks.AllStairs.Name} is {(MarkReading.AllStairs(model) is false ? "No" : "not set")} on Project " +
                    "Information: until it says Yes, a stair not drawn as one would go unchecked");
        why.AddRange(Blockers(model));
        return why;
    }

    /// <summary>Everything in the model that could be a stair the reader doesn't walk: listed first in the marking
    /// list (design note, section 2).</summary>
    public static List<string> Blockers(RevitModel model)
    {
        if (model.Interior is not { } records)
            return [];
        var why = new List<string>();
        if (records.Stairs is null)
            why.Add("the stairs couldn't be read");
        foreach (var s in records.Stairs ?? [])
        {
            if (!SiteReader.InDesignChecked(model, s.PhaseDemolished, s.DesignOption))
                continue;
            if (!s.IsByComponent)
                why.Add($"Stair \"{s.Name ?? s.UniqueId}\" isn't made of runs and landings (a stair sketched the old way): it isn't read");
            if (s.MultistoryStairsId is not null)
                why.Add($"Stair \"{s.Name ?? s.UniqueId}\" is one of a multistory stair, whose copies on other levels aren't read yet");
        }
        // one line per category and kind (a real model has hundreds alike: Pacific Continental's 272 grilles), each
        // element still listed by id in the Revit layer's log
        foreach (var g in records.StairCandidates.Where(c => SiteReader.InDesignChecked(model, c.PhaseDemolished, c.DesignOption)
                                                             && !InsideWindowOrDoor(c))
                     .GroupBy(c => (c.BuiltInCategory, c.Kind)))
        {
            var cat = g.Key.BuiltInCategory.Replace("OST_", "");
            var list = g.ToList();
            if (list.Count == 1)
                why.Add($"{cat} \"{list[0].Name ?? list[0].UniqueId}\" is {list[0].Kind}: a stair or its railing " +
                        "drawn this way isn't read, so Gordium can't tell every stair is read");
            else
            {
                var names = list.GroupBy(c => c.Name ?? "(no name)").OrderByDescending(n => n.Count()).ThenBy(n => n.Key, StringComparer.Ordinal)
                    .Select(n => $"{n.Key} x{n.Count()}").ToList();
                why.Add($"{list.Count} {cat} elements are each {g.Key.Kind} ({names.Count} " + (names.Count == 1 ? "type" : "types") + ": " +
                        string.Join(", ", names) + "; each listed by id in the log): a stair or its railing drawn this way isn't read, " +
                        "so Gordium can't tell every stair is read");
            }
        }
        foreach (var w in model.UserWorksets.Where(w => !w.IsOpen))
            why.Add($"Workset \"{w.Name}\" is closed: a stair could be in it (open it)");
        foreach (var link in records.Links)
        {
            if (!link.Loaded)
                why.Add($"Linked model \"{link.Name}\" isn't loaded: a stair could be in it");
            else if (link.HasLinks)
                why.Add($"Linked model \"{link.Name}\" holds links of its own, which aren't read: a stair could be in one");
            else if (link.Stairs > 0)
                why.Add($"Linked model \"{link.Name}\" holds {link.Stairs} stairs, railings or generic models: a linked model's stairs aren't read yet");
        }
        if (records.CoordinationModels > 0)
            why.Add($"{records.CoordinationModels} coordination model(s) linked: what is in one isn't read, and a stair could be in it");
        return why;
    }

    /// <summary>A Generic Model family nested in a window or door (a grille's muntins: 272 of them in Autodesk's
    /// Pacific Continental sample, 2026-11-20), at any depth of nesting, whose box lies within that window's or door's
    /// box (1/16 in to spare): it is part of the window or door, not a stair or a guard, so it doesn't stop the stairs
    /// being read. Anything else stays a blocker: not nested, nested in anything else, sticking out of the window's
    /// box, or with a box Revit doesn't give.</summary>
    public static bool InsideWindowOrDoor(StairCandidate c)
    {
        if (c.BuiltInCategory != "OST_GenericModel" || c.Box is not { } box || c.NestedIn is not { Count: > 0 } hosts)
            return false;
        var own = World(box);
        return hosts.Any(h => h.BuiltInCategory is "OST_Windows" or "OST_Doors" && h.Box is { } hb && Within(own, World(hb)));
    }

    private static Box3 World(RevitBox b) => Box3.Turned(b.Min, b.Max, b.Transform ?? Transform3.Identity);

    private static bool Within(Box3 inner, Box3 outer)
    {
        const double t = InteriorReader.Sixteenth;
        return inner.Min.X >= outer.Min.X - t && inner.Min.Y >= outer.Min.Y - t && inner.Min.Z >= outer.Min.Z - t
            && inner.Max.X <= outer.Max.X + t && inner.Max.Y <= outer.Max.Y + t && inner.Max.Z <= outer.Max.Z + t;
    }

    /// <summary>Every flight of every stair in the design checked (the list is the caller's to send or not).</summary>
    public static JsonArray Flights(RevitModel model, List<InteriorNote> notes, JsonObject evidence, RailingUse? use = null)
    {
        var flights = new JsonArray();
        use ??= new RailingUse();
        foreach (var stair in model.Interior?.Stairs ?? [])
        {
            if (!SiteReader.InDesignChecked(model, stair.PhaseDemolished, stair.DesignOption))
                continue;
            for (var k = 0; k < stair.Runs.Count; k++)
            {
                var name = stair.Runs.Count == 1 ? stair.Name ?? "Stair" : $"{stair.Name ?? "Stair"} (run {k + 1} of {stair.Runs.Count})";
                flights.Add(new Flight(model, stair, stair.Runs[k], name, notes, evidence, use).Read());
            }
        }
        use.BesideWall.ExceptWith(use.Refused);                     // beside a wall on one flight, refused on another
        return flights;
    }

    /// <summary>The railing a part belongs to (the railing's own id, or its top rail's or a handrail's), by id.</summary>
    internal static Dictionary<string, RailingRecord> RailingsByPart(RevitModel model)
    {
        var by = new Dictionary<string, RailingRecord>(StringComparer.Ordinal);
        foreach (var r in model.Interior?.Railings ?? [])
        {
            by.TryAdd(r.UniqueId, r);
            foreach (var p in r.Parts)
                by.TryAdd(p.UniqueId, r);
        }
        return by;
    }

    /// <summary>Whether a railing stands on this stair (it lists it, or hosts it).</summary>
    internal static bool OnStair(StairRecord stair, RailingRecord r) => stair.Railings.Contains(r.UniqueId) || r.Host == stair.UniqueId;

    /// <summary>Every point of every part of the railing, internal; null when a part can't be read exactly (its
    /// geometry refused or a mesh, a curved face, a curved edge: a round handrail's extremes aren't its corners).</summary>
    internal static List<Xyz>? ExactPoints(RailingRecord r)
    {
        var pts = new List<Xyz>();
        foreach (var p in r.Parts)
        {
            if (p.GeometryFailed || p.Solids is null)
                return null;
            foreach (var f in p.Solids.SelectMany(s => s))
            {
                if (!f.Planar || f.Loops.Any(l => l.Any(c => !c.IsLine)))
                    return null;
                pts.AddRange(f.Points);
            }
        }
        return pts;
    }

    // ---- one flight --------------------------------------------------------------------------------------------

    private sealed class Flight(RevitModel model, StairRecord stair, RunRecord run, string name, List<InteriorNote> notes,
                                JsonObject evidence, RailingUse use)
    {
        private readonly Transform3 _t = model.InternalToShared;
        private readonly JsonObject _flight = new() { ["id"] = run.UniqueId, ["name"] = name };
        private readonly JsonObject _ev = new();
        private readonly Dictionary<string, RailingRecord> _railingOf = RailingsByPart(model);

        // the railings of this stair read as a handrail beside a wall on one side of this flight (railing id → side),
        // and those that aren't (each beside it, refused)
        private readonly Dictionary<string, string> _accepted = new(StringComparer.Ordinal);
        private readonly HashSet<string> _refused = new(StringComparer.Ordinal);

        // the flight's frame, in shared coordinates: s up the run, a across it to the left looking up
        private P2 _o;
        private P2 _u;
        private P2 _v;

        // the treads read: each front edge's s, its ends (right a, left a) and its height; the top tread's back edge
        private readonly List<(double S, double Right, double Left, double Z)> _treads = [];
        private double _back;
        private double _headZ;

        private void Out(string field, string why) => notes.Add(new(run.UniqueId, field, why));

        private void OutAll(string why, params string[] fields)
        {
            foreach (var f in fields)
                Out(f, why);
        }

        private P2 Plan(Xyz internalPoint)
        {
            var p = _t.Apply(internalPoint);
            return new P2(p.X, p.Y);
        }

        private double S(P2 p) => (p.X - _o.X) * _u.X + (p.Y - _o.Y) * _u.Y;

        private double A(P2 p) => (p.X - _o.X) * _v.X + (p.Y - _o.Y) * _v.Y;

        private P2 Local(P2 p) => new(S(p), A(p));                  // the frame's own plan: (s, a)

        private JsonArray XY(double s, double a) =>
            new(_o.X + s * _u.X + a * _v.X, _o.Y + s * _u.Y + a * _v.Y);

        private Xyz TurnedNormal(Xyz n) => n.X * _t.BasisX + n.Y * _t.BasisY + n.Z * _t.BasisZ;

        private bool InDesign(NearbyElement e) => SiteReader.InDesignChecked(model, e.PhaseDemolished, e.DesignOption);

        private bool Own(NearbyElement e) => e.UniqueId == run.UniqueId;

        /// <summary>The stair element itself: its geometry may be all its runs and supports together. With one run and
        /// nothing else it is this run; else it can't be told apart run by run.</summary>
        private bool OwnStair(NearbyElement e) => e.UniqueId == stair.UniqueId;

        private bool StairIsThisRun => stair.Runs.Count == 1 && stair.Landings.Count == 0 && stair.Supports.Count == 0;

        /// <summary>The height of the line of nosings at s (level with its ends beyond them).</summary>
        private double Line(double s)
        {
            var pts = _treads.Select(x => (S: x.S, Z: x.Z)).Append((S: _back, Z: _headZ)).ToList();
            if (s <= pts[0].S)
                return pts[0].Z;
            for (var i = 1; i < pts.Count; i++)
                if (s <= pts[i].S)
                    return pts[i - 1].Z + (s - pts[i - 1].S) / (pts[i].S - pts[i - 1].S) * (pts[i].Z - pts[i - 1].Z);
            return pts[^1].Z;
        }

        private static string Named(NearbyElement e) =>
            string.IsNullOrWhiteSpace(e.Name) ? e.BuiltInCategory.Replace("OST_", "") : $"{e.BuiltInCategory.Replace("OST_", "")} \"{e.Name}\"";

        private static string In(double ft) => ClearStamp.Inches(ft);

        public JsonObject Read()
        {
            evidence[run.UniqueId] = _ev;
            _ev["revit_layer"] = new JsonArray(run.Diagnostics.Select(d => (JsonNode?)d).ToArray());
            string[] all = ["bottom_elevation", "nosings", "sides", "handrails", "overhead"];
            if (run.Faces is null || run.GeometryFailed)
            {
                OutAll("the run's geometry couldn't be read exactly (a mesh, or Revit refused)", all);
                return _flight;
            }
            if (run.Path.Count < 2 || stair.BaseElevation is null || run.BaseElevation is null || run.TopElevation is null)
            {
                OutAll("the run's path or its base and top elevations couldn't be read", all);
                return _flight;
            }
            var path = run.Path.Select(Plan).ToList();
            var d = path[^1] - path[0];
            var len = Math.Sqrt(d.X * d.X + d.Y * d.Y);
            if (len < 1e-9)
            {
                OutAll("the run's path has no length", all);
                return _flight;
            }
            _o = path[0];
            _u = new P2(d.X / len, d.Y / len);
            _v = new P2(-_u.Y, _u.X);
            if (run.Style != "Straight" || path.Any(p => Math.Abs(A(p)) > Sixteenth))
            {
                OutAll($"a {(run.Style == "Straight" ? "bent" : run.Style.ToLowerInvariant())} run (its treads turn) isn't measured: only straight flights are", all);
                return _flight;
            }
            var at = run.Path[0];
            var baseZ = _t.Apply(new Xyz(at.X, at.Y, stair.BaseElevation.Value + run.BaseElevation.Value)).Z;
            var topZ = _t.Apply(new Xyz(at.X, at.Y, stair.BaseElevation.Value + run.TopElevation.Value)).Z;
            if (Treads(topZ) is { } bad)
            {
                OutAll(bad, all);
                return _flight;
            }
            _headZ = topZ;                                   // until the floor at the head is read: the line's top
            _ev["run_base"] = baseZ;
            _ev["run_top"] = topZ;
            _ev["typed_riser"] = stair.ActualRiserHeight;
            _ev["typed_tread"] = stair.ActualTreadDepth;
            _ev["treads"] = new JsonArray(_treads.Select(x => (JsonNode)new JsonArray(x.S, x.Right, x.Left, x.Z)).ToArray());
            _ev["back"] = _back;

            // a loaded link reaching the flight: what is in it (a floor, a beam) isn't read yet
            if (model.Interior!.Links.Where(l => l.Loaded && l.Box is not null && Reaches(l.Box!)).Select(l => l.Name).ToList()
                is { Count: > 0 } links)
            {
                OutAll("linked model " + string.Join(", ", links.Select(n => $"\"{n}\"")) +
                       " reaches over this flight, and what is in a link isn't read yet", all);
                return _flight;
            }
            if (run.Near is null)
            {
                OutAll("what is around the run couldn't be looked for", all);
                return _flight;
            }

            var first = _treads[0];
            var last = _treads[^1];
            var foot = Rect(first.S - Strip, first.S, first.Right, first.Left);
            var head = Rect(_back, _back + Strip, last.Right, last.Left);
            // the first riser and the last are measured as drawn, to the floor in front and the floor at the head (R318.7.5.1:
            // "measured vertically between leading edges of the adjacent treads"), not to the run's own base and top: a
            // floor standing off the run (level heights that don't divide evenly, a finish) makes that riser taller or
            // shorter than the run's, and the checker sees it (Ben, 2026-11-20, Q1). Each is read only where it is exact:
            // a floor found whole there, below the first tread or above the last, and at the head nothing of the run's
            // own standing above it (a riser board proud of the floor would be the real top nosing, unread)
            double? bottom = null, headZ = null;
            if (TopAt(foot, baseZ, out var footWhy) is { } fz)
            {
                _ev["foot"] = fz;
                if (fz >= first.Z - Sixteenth)
                    Out("bottom_elevation", footWhy = $"the floor in front of its first riser is {In(fz - first.Z)} from its first tread: no riser there to measure");
                else
                    bottom = fz;
            }
            else
                Out("bottom_elevation", footWhy!);
            if (bottom is { } b)
                _flight["bottom_elevation"] = b;

            if (TopAt(head, topZ, out var headWhy) is { } hz)
            {
                _ev["head"] = hz;
                if (hz <= last.Z + Sixteenth)
                    headWhy = $"the floor at its head is {In(hz - last.Z)} from its top tread: no riser there to measure";
                else if (RunAbove(hz) is { } above)
                    headWhy = above;
                else if (ReachesBack(hz) is { } reachesBack)
                    headWhy = reachesBack;
                else
                    headZ = hz;
            }
            if (headZ is { } h)
                _headZ = h;
            if (NosingsProblem(bottom, headZ, headWhy, footWhy, baseZ, topZ) is { } nosingsWhy)
                Out("nosings", nosingsWhy);
            else
            {
                var nosings = new JsonArray();
                foreach (var x in _treads)
                    nosings.Add(new JsonArray(Point3(x.S, x.Right, x.Z), Point3(x.S, x.Left, x.Z)));
                nosings.Add(new JsonArray(Point3(_back, last.Right, _headZ), Point3(_back, last.Left, _headZ)));
                _flight["nosings"] = nosings;
            }

            var sides = Sides(out var sidesWhy);
            if (sides is not null)
            {
                _flight["sides"] = sides;
                use.BesideWall.UnionWith(_accepted.Keys);
            }
            else
                Out("sides", sidesWhy!);
            use.Refused.UnionWith(_refused);
            if (sides is null)
                use.Refused.UnionWith(_accepted.Keys);              // not read beside a wall after all: never a handrail only
            if (Handrails(sides is not null, out var railsWhy) is { } rails)
                _flight["handrails"] = rails;
            else
                Out("handrails", railsWhy!);
            if (Overhead(out var overWhy) is { } over)
                _flight["overhead"] = over;
            else
                Out("overhead", overWhy!);
            _ev["handrails_beside_walls"] = new JsonArray(_accepted.Select(p => (JsonNode)$"{p.Key} ({p.Value})").ToArray());
            _ev["railings_refused"] = new JsonArray(_refused.Select(x => (JsonNode)x).ToArray());
            return _flight;
        }

        // ---- the railings beside it (step 5) ------------------------------------------------------------------

        /// <summary>Whether a railing element in a side's band is this stair's handrail beside the wall there: a railing
        /// on this stair, every part read exactly, every point between the wall face (1/16 in to spare) and the flight's
        /// middle, and none higher over the line of nosings than a handrail may be (38 in). Then it is inside the width
        /// at the handrail and never narrows the width above it. Remembered per railing; a railing not so is refused.</summary>
        private bool HandrailBeside(NearbyElement e, string side, int sign, double wallA, double mid)
        {
            if (!_railingOf.TryGetValue(e.UniqueId, out var r))
                return false;
            if (_accepted.TryGetValue(r.UniqueId, out var was))
                return was == side;
            if (_refused.Contains(r.UniqueId))
                return false;
            var ok = OnStair(stair, r) && ExactPoints(r) is { } pts && pts.Count > 0 && pts.Select(_t.Apply).All(p =>
            {
                var q = Local(new P2(p.X, p.Y));
                return sign * (q.Y - wallA) <= Sixteenth && sign * (q.Y - mid) >= 0
                       && p.Z <= Line(Math.Clamp(q.X, _treads[0].S, _back)) + HandrailHigh + Sixteenth;
            });
            // and nothing of it that isn't sent as a handrail (a top rail marked No or unset, a newel post, a baluster)
            // stands farther toward the middle than the innermost handrail edge sent: the width at the handrail is
            // read from those edges alone (review round 1: a top rail marked No read the width at the handrail 36 in,
            // drawn 32.5). With nothing sent as a handrail, the railing narrows a width nothing says: refused
            if (ok)
            {
                var top = Marks.YesNo(r.TypeMarks.TryGetValue(Marks.TopRailIsHandrail.Guid, out var v) ? v : null);
                bool Sent(RailingPart p) => p.Kind == RailingPartKind.Handrail || (p.Kind == RailingPartKind.TopRail && top is true);
                List<double> As(IEnumerable<RailingPart> parts) => parts.SelectMany(p => p.Solids!.SelectMany(s => s)).SelectMany(f => f.Points)
                    .Select(_t.Apply).Select(p => Local(new P2(p.X, p.Y)).Y).ToList();
                var sent = As(r.Parts.Where(Sent));
                var rest = As(r.Parts.Where(p => !Sent(p)));
                if (sent.Count == 0)
                    ok = false;
                else
                {
                    var inner = sign > 0 ? sent.Min() : sent.Max();
                    ok = rest.All(a => sign * (a - inner) >= -1e-9);
                }
            }
            if (ok)
                _accepted[r.UniqueId] = side;
            else
                _refused.Add(r.UniqueId);
            return ok;
        }

        /// <summary>A railing on this stair read exactly whose every point is at or under handrail height (38 in) over the
        /// line of nosings: whatever side it stands on, it is no part of the headroom.</summary>
        private bool LowRailing(RailingRecord r) =>
            OnStair(stair, r) && ExactPoints(r) is { Count: > 0 } pts && pts.Select(_t.Apply).All(p =>
                p.Z <= Line(Math.Clamp(Local(new P2(p.X, p.Y)).X, _treads[0].S, _back)) + HandrailHigh + Sixteenth);

        private void RefuseRailing(NearbyElement e)
        {
            if (_railingOf.TryGetValue(e.UniqueId, out var r))
                _refused.Add(r.UniqueId);
        }

        /// <summary>The flight's handrails: the handrails (and, where the railing's type is marked so, the top rail) of
        /// each railing read as a handrail beside a wall, each as the plan line of its edge nearest the flight's middle,
        /// from its first point along the run to its last. Sent only on the architect's tick that every guard and
        /// handrail is drawn as a railing, and with the flight's sides read; with none, an empty list. Null with why.</summary>
        private JsonArray? Handrails(bool sidesRead, out string? why)
        {
            why = null;
            if (MarkReading.AllGuards(model) is not true)
            {
                why = $"{Marks.AllGuards.Name} is {(MarkReading.AllGuards(model) is false ? "No" : "not set")} on Project " +
                      "Information: until it says Yes, a handrail drawn as something else (a wall sweep) would be missed";
                return null;
            }
            if (model.Interior!.Railings is null)
            {
                why = "the railings couldn't be read";
                return null;
            }
            if (!sidesRead)
            {
                why = "its sides weren't read, so the railings beside it aren't read as its handrails";
                return null;
            }
            var rails = new JsonArray();
            foreach (var (uid, side) in _accepted.OrderBy(p => p.Key, StringComparer.Ordinal))
            {
                var r = _railingOf[uid];
                var top = Marks.YesNo(r.TypeMarks.TryGetValue(Marks.TopRailIsHandrail.Guid, out var v) ? v : null);
                if (top is null && r.Parts.Any(p => p.Kind == RailingPartKind.TopRail && p.Solids is { Count: > 0 }))
                {
                    why = $"{Marks.TopRailIsHandrail.Name} isn't set on the type of railing \"{r.Name ?? r.UniqueId}\": whether its top rail is a handrail isn't stated";
                    return null;
                }
                foreach (var p in r.Parts.Where(p => p.Kind == RailingPartKind.Handrail || (p.Kind == RailingPartKind.TopRail && top is true)))
                {
                    var pts = p.Solids!.SelectMany(s => s).SelectMany(f => f.Points).Select(_t.Apply).Select(q => Local(new P2(q.X, q.Y))).ToList();
                    if (pts.Count == 0)
                        continue;
                    var inner = side == "left" ? pts.Min(q => q.Y) : pts.Max(q => q.Y);
                    rails.Add(new JsonObject
                    {
                        ["side"] = side,
                        ["inner_edge"] = new JsonArray(XY(pts.Min(q => q.X), inner), XY(pts.Max(q => q.X), inner)),
                    });
                }
            }
            return rails;
        }

        private JsonArray Point3(double s, double a, double z)
        {
            var xy = XY(s, a);
            return new JsonArray(xy[0]!.GetValue<double>(), xy[1]!.GetValue<double>(), z);
        }

        private List<P2> Rect(double s0, double s1, double a0, double a1) => [new(s0, a0), new(s1, a0), new(s1, a1), new(s0, a1)];

        private bool Reaches(RevitBox box)
        {
            var (s0, s1, a0, a1, _, _) = Hull(box);
            return s0 < _back + Strip && s1 > _treads[0].S - Strip && a0 < _treads.Max(x => x.Left) && a1 > _treads.Min(x => x.Right);
        }

        /// <summary>A box's extent in the flight's frame (s, a) and in height, from its 8 corners: only ever bigger
        /// than what it holds.</summary>
        private (double S0, double S1, double A0, double A1, double Z0, double Z1) Hull(RevitBox box)
        {
            var t = box.Transform is { } own ? _t.After(own) : _t;
            var pts = new List<Xyz>();
            foreach (var x in new[] { box.Min.X, box.Max.X })
                foreach (var y in new[] { box.Min.Y, box.Max.Y })
                    foreach (var z in new[] { box.Min.Z, box.Max.Z })
                        pts.Add(t.Apply(new Xyz(x, y, z)));
            var local = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
            return (local.Min(p => p.X), local.Max(p => p.X), local.Min(p => p.Y), local.Max(p => p.Y), pts.Min(p => p.Z), pts.Max(p => p.Z));
        }

        // ---- the treads, from the run's own faces -------------------------------------------------------------

        /// <summary>Each tread's top, from the run's own upward flat faces (a face sitting under another of the run's
        /// own, a riser's top under its tread, is inside the run and set aside), grouped by height: its front edge is
        /// its nosing. Null when they read as straight rectangular treads, one per tread the run has; else why.</summary>
        private string? Treads(double topZ)
        {
            var faces = run.Faces!;
            if (faces.Any(f => !f.Planar))
                return "the run has a curved face (a rounded nosing, a curved tread), which isn't read exactly";
            var up = new List<(double Z, List<P2> Loop, List<Xyz> Pts)>();
            var down = new List<(double Z, List<P2> Loop)>();
            foreach (var f in faces)
            {
                var n = TurnedNormal(f.Normal);
                if (Math.Abs(n.Z) < 1 - 1e-6 || f.Loops.Count == 0)
                    continue;                                       // a riser, a side, a sloped soffit
                var pts = f.Points.Select(_t.Apply).ToList();
                if (pts.Count == 0)
                    continue;
                if (pts.Max(p => p.Z) - pts.Min(p => p.Z) > Sixteenth)
                    return "a tread's top slopes";
                var loop = f.Loops[0].Select(c => Local(Plan(c.Start))).ToList();
                if (n.Z > 0)
                    up.Add((pts.Average(p => p.Z), loop, pts));
                else
                    down.Add((pts.Average(p => p.Z), loop));
            }
            var tops = up.Where(u => !down.Any(dn => Math.Abs(dn.Z - u.Z) <= Sixteenth
                                                     && PlanGeometry.OverlapArea(u.Loop, dn.Loop) is { } o
                                                     && o >= PlanGeometry.Area(u.Loop) * (1 - 1e-9)))
                .OrderBy(u => u.Z).ToList();
            var groups = new List<List<(double Z, List<P2> Loop, List<Xyz> Pts)>>();
            foreach (var top in tops)
            {
                if (groups.Count > 0 && top.Z - groups[^1][0].Z <= Sixteenth)
                    groups[^1].Add(top);
                else
                    groups.Add([top]);
            }
            _ev["tread_faces"] = tops.Count;
            _ev["tread_groups"] = new JsonArray(groups.Select(g =>
            {
                var p = g.SelectMany(x => x.Loop).ToList();
                return (JsonNode)new JsonObject
                {
                    ["z"] = g[0].Z, ["s"] = new JsonArray(p.Min(q => q.X), p.Max(q => q.X)), ["a"] = new JsonArray(p.Min(q => q.Y), p.Max(q => q.Y)),
                    ["faces"] = g.Count,
                };
            }).ToArray());
            if (groups.Count == 0)
                return "no tread top was found in the run's geometry";
            // a run that ends with a riser has that riser board's own top face too (Revit 2027.4, trial step 4 runs 1
            // and 2: 16 tops for 15 treads, house 3 13 for 12; house 2's a sliver 1/2 in deep along the path at 12.5 to
            // 12.5417 ft, just past the last tread, 9.75 ft up: the run's top less the 3 in tread). It is the head's
            // edge, never a tread: its front edge is the last riser's line, the top nosing's place along the run.
            // Only when exactly one top too many, the top one, past the last tread, no deeper than a riser board
            // (RiserBoard), above the last tread and not above the run's top.
            double? headEdge = null;
            if (run.EndsWithRiser && run.TreadsNumber is { } treadCount && groups.Count == treadCount + 1 && groups.Count >= 2
                && groups[^1].SelectMany(x => x.Loop).ToList() is var riserTop
                && riserTop.Max(p => p.X) - riserTop.Min(p => p.X) <= RiserBoard
                && riserTop.Min(p => p.X) >= groups[^2].SelectMany(x => x.Loop).Max(p => p.X) - Sixteenth
                && groups[^1][0].Z > groups[^2][0].Z && groups[^1][0].Z <= topZ + Sixteenth)
            {
                headEdge = groups[^1].SelectMany(x => x.Loop).Min(p => p.X);
                _ev["head_riser_top"] = new JsonObject { ["z"] = groups[^1][0].Z, ["front"] = headEdge };
                groups.RemoveAt(groups.Count - 1);
            }
            if (run.TreadsNumber is not { } count || groups.Count != count)
                return $"its geometry has {groups.Count} tread tops, but the run says it has {run.TreadsNumber?.ToString(CultureInfo.InvariantCulture) ?? "no number of"} treads";
            foreach (var g in groups)
            {
                var pts = g.SelectMany(x => x.Loop).ToList();
                var front = pts.Min(p => p.X);
                var edge = pts.Where(p => p.X <= front + Sixteenth).ToList();
                double right = edge.Min(p => p.Y), left = edge.Max(p => p.Y);
                if (pts.Min(p => p.Y) < right - Sixteenth || pts.Max(p => p.Y) > left + Sixteenth)
                    return $"the tread at {In(g[0].Z - groups[0][0].Z)} over the first isn't a rectangle square to the run (a winder, a flared step)";
                _treads.Add((front, right, left, g.Average(x => x.Z)));
                _back = pts.Max(p => p.X);
            }
            if (headEdge is { } riserLine)
                _back = riserLine;                                  // the last riser's line, from the riser's own top
            for (var i = 1; i < _treads.Count; i++)
                if (_treads[i].S <= _treads[i - 1].S)
                    return "its treads don't move up the run as they rise";
            if (_back <= _treads[^1].S)
                return "its head isn't past its top tread";
            if (_treads.Any(x => x.Right >= x.Left))
                return "a tread has no width across the run";
            return null;
        }

        /// <summary>Why the nosings can't be sent (null when they can): the floor at the foot and at the head must be read,
        /// the run must begin and end with a riser, its counts must be its own, and the run's own risers (its base to its
        /// top through its treads) and every tread must agree with the stair's typed riser height and tread depth within
        /// 1/16 in: the cross-check that its geometry is read right. The risers sent are as drawn, the first from the
        /// floor in front of it and the last to the floor at the head, whatever the run's own base and top.</summary>
        private string? NosingsProblem(double? bottom, double? head, string? headWhy, string? footWhy, double baseZ, double topZ)
        {
            if (bottom is not { } b)
                return "the first riser can't be measured: " + (footWhy ?? "the floor in front of it wasn't read");
            if (head is not { } h)
                return headWhy is null ? "the floor at its head wasn't found"
                    : headWhy.StartsWith("the floor at its head", StringComparison.Ordinal) ? headWhy : "the floor at its head: " + headWhy;
            if (!run.BeginsWithRiser || !run.EndsWithRiser)
                return "a run that doesn't begin and end with a riser isn't read yet";
            if (run.RisersNumber != _treads.Count + 1)
                return $"its geometry has {_treads.Count + 1} risers, but the run says {run.RisersNumber?.ToString(CultureInfo.InvariantCulture) ?? "nothing"}";
            if (stair.ActualRiserHeight is not { } riser || stair.ActualTreadDepth is not { } tread)
                return "the stair's typed riser height or tread depth couldn't be read, so its drawn ones can't be checked";
            List<double> Rises(double lo, double hi)
            {
                var zs = new List<double> { lo };
                zs.AddRange(_treads.Select(x => x.Z));
                zs.Add(hi);
                return zs.Zip(zs.Skip(1), (a, c) => c - a).ToList();
            }
            var own = Rises(baseZ, topZ);                   // the run's own: equal by construction, typed
            var risers = Rises(b, h);                       // as drawn: what is sent
            var ss = _treads.Select(x => x.S).Append(_back).ToList();
            var treads = ss.Zip(ss.Skip(1), (lo, hi) => hi - lo).ToList();
            _ev["run_risers_in"] = new JsonArray(own.Select(r => (JsonNode)(r * 12)).ToArray());
            _ev["drawn_risers_in"] = new JsonArray(risers.Select(r => (JsonNode)(r * 12)).ToArray());
            _ev["drawn_treads_in"] = new JsonArray(treads.Select(r => (JsonNode)(r * 12)).ToArray());
            for (var i = 0; i < own.Count; i++)
                if (Math.Abs(own[i] - riser) > Sixteenth)
                    return $"the run's riser {i + 1} is drawn {In(own[i])}, but the stair's Actual Riser Height is {In(riser)}: they must agree within 1/16 in";
            for (var i = 0; i < treads.Count; i++)
                if (Math.Abs(treads[i] - tread) > Sixteenth)
                    return $"tread {i + 1} is drawn {In(treads[i])} deep (nosing to nosing), but the stair's Actual Tread Depth is {In(tread)}: they must agree within 1/16 in";
            return null;
        }

        // ---- the floor at the foot and at the head ----------------------------------------------------------------

        /// <summary>The top of the one floor or landing covering the whole strip (in the frame's own plan), within a
        /// foot of <paramref name="claimed"/>; null with why when none, several at different heights, a sloped or curved
        /// one, or one covering only part of it.</summary>
        private double? TopAt(List<P2> strip, double claimed, out string? why)
        {
            why = null;
            var area = PlanGeometry.Area(strip);
            var tops = new List<(double Z, List<List<P2>> Loops, string By)>();
            foreach (var e in run.Near!)
            {
                if (!InDesign(e) || Own(e) || InteriorReader.NotBuilding.Contains(e.BuiltInCategory) || (OwnStair(e) && StairIsThisRun))
                    continue;
                if (e.GeometryFailed || e.Faces is null)
                {
                    if (e.Box is { } box && Hull(box) is var hb && hb.Z1 >= claimed - InteriorReader.SlabBand && hb.Z0 <= claimed + InteriorReader.SlabBand
                        && PlanGeometry.OverlapArea(strip, Rect(hb.S0, hb.S1, hb.A0, hb.A1)) is not (null or <= 0))
                    {
                        why = $"the geometry of {Named(e)} there couldn't be read";
                        return null;
                    }
                    if (e.Box is null && e.GeometryFailed)        // the cautious side (review round 3), as ReachesBack
                    {
                        why = $"the geometry of {Named(e)} near it couldn't be read, and where it stands isn't known";
                        return null;
                    }
                    continue;
                }
                foreach (var f in e.Faces)
                {
                    var pts = f.Points.Select(_t.Apply).ToList();
                    if (pts.Count == 0 || pts.Max(p => p.Z) < claimed - InteriorReader.SlabBand || pts.Min(p => p.Z) > claimed + InteriorReader.SlabBand)
                        continue;
                    var loops = f.Loops.Select(l => l.Select(c => Local(Plan(c.Start))).ToList()).OrderByDescending(PlanGeometry.Area).ToList();
                    if (!f.Planar)
                    {
                        var plan = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                        if (plan.Count > 0 && PlanGeometry.OverlapArea(strip, Rect(plan.Min(p => p.X), plan.Max(p => p.X), plan.Min(p => p.Y), plan.Max(p => p.Y))) is not (null or <= 0))
                        {
                            why = $"a curved face of {Named(e)} is there";
                            return null;
                        }
                        continue;
                    }
                    if (TurnedNormal(f.Normal).Z <= 1e-9 || loops.Count == 0)
                        continue;
                    var overlap = PlanGeometry.OverlapArea(strip, loops[0]);
                    if (overlap is null)
                    {
                        why = $"a top face of {Named(e)} there isn't a simple outline";
                        return null;
                    }
                    if (overlap <= area * 1e-9)
                        continue;
                    if (pts.Max(p => p.Z) - pts.Min(p => p.Z) > Sixteenth)
                    {
                        why = $"the top of {Named(e)} there slopes";
                        return null;
                    }
                    if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                    {
                        why = $"the top of {Named(e)} there has a curved edge, which isn't read exactly";
                        return null;
                    }
                    tops.Add((pts.Average(p => p.Z), loops, Named(e)));
                }
            }
            if (tops.Count == 0)
            {
                why = "no floor or landing top was found there within a foot of the run";
                return null;
            }
            if (tops.Max(x => x.Z) - tops.Min(x => x.Z) > Sixteenth)
            {
                why = "the floor tops there are at different heights (" +
                      string.Join(", ", tops.Select(x => In(x.Z - claimed) + " from the run, " + x.By).Distinct()) + ")";
                return null;
            }
            var covered = tops.Any(x => PlanGeometry.OverlapArea(strip, x.Loops[0]) is { } a && a >= area * (1 - 1e-9)
                                        && x.Loops.Skip(1).All(hole => PlanGeometry.OverlapArea(strip, hole) is { } ha && ha <= area * 1e-9));
            if (!covered)
            {
                why = "no one floor top covers the stair's whole width there";
                return null;
            }
            return tops[0].Z;
        }

        /// <summary>The last riser rises to the floor at the head only if nothing of the run's own stands above that floor
        /// (1/16 in to spare): a floor lower than the run's last riser board leaves the board's top proud of it, a lip
        /// that would be the real top nosing, which isn't read. Null when the floor is at or above all of the run; else
        /// why.</summary>
        private string? RunAbove(double headZ)
        {
            var top = run.Faces!.SelectMany(f => f.Points).Select(p => _t.Apply(p).Z).DefaultIfEmpty(double.NegativeInfinity).Max();
            _ev["run_highest"] = top;
            return top > headZ + Sixteenth
                ? $"the run itself reaches {In(top - headZ)} above the floor at its head (its last riser board standing proud of the floor): its last riser isn't read exactly"
                : null;
        }

        /// <summary>The top nosing is the floor's edge at the head only if that floor stops at the last riser's line:
        /// a top at the head's height reaching back over the last tread (a landing nosing, a slab edge drawn past the
        /// riser line) makes the last tread shallower than the riser line says (review round 1: 8.5 in read as 10).
        /// Null when nothing at the head's height lies over the last tread's plan more than 1/16 in short of the line;
        /// else why.</summary>
        private string? ReachesBack(double headZ)
        {
            var last = _treads[^1];
            if (_back - Sixteenth <= last.S)
                return null;
            var tread = Rect(last.S, _back - Sixteenth, last.Right, last.Left);
            var area = PlanGeometry.Area(tread);
            bool Over(List<P2> plan) =>
                plan.Count > 0 && PlanGeometry.OverlapArea(tread, Rect(plan.Min(p => p.X), plan.Max(p => p.X), plan.Min(p => p.Y), plan.Max(p => p.Y))) is not (null or <= 0);
            foreach (var e in run.Near!)
            {
                if (!InDesign(e) || Own(e) || NotPhysical(e) || (OwnStair(e) && StairIsThisRun))
                    continue;
                // what can't be read (a mesh, a geometry Revit refused) at the head's height over the last tread refuses
                // the nosings, as TopAt does: by its box, or, with none, whatever its extent (review round 2)
                if (e.GeometryFailed || e.Faces is null)
                {
                    if (e.Box is { } box)
                    {
                        var h = Hull(box);
                        if (h.Z1 >= headZ - Sixteenth && h.Z0 <= headZ + Sixteenth && Over([new(h.S0, h.A0), new(h.S1, h.A1)]))
                            return $"the geometry of {Named(e)} at its head, over the last tread, couldn't be read";
                    }
                    else if (e.GeometryFailed)
                        return $"the geometry of {Named(e)} near its head couldn't be read, and where it stands isn't known";
                    if (e.Faces is null)
                        continue;
                }
                foreach (var f in e.Faces)
                {
                    var pts = f.Points.Select(_t.Apply).ToList();
                    if (pts.Count == 0 || pts.Max(p => p.Z) < headZ - Sixteenth || pts.Min(p => p.Z) > headZ + Sixteenth)
                        continue;
                    var plan = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                    if (f.Planar && Math.Abs(TurnedNormal(f.Normal).Z) <= 1e-9)
                        continue;                                   // a side: nothing over the tread seen from above
                    if (!f.Planar || f.Loops.Count == 0)            // judged by its points: never skipped (review round 2)
                    {
                        if (Over(plan.Concat(f.Loops.SelectMany(l => l).Select(c => Local(Plan(c.Start)))).ToList()))
                            return $"a face of {Named(e)} at its head's height that isn't read exactly reaches over the last tread";
                        continue;
                    }
                    // the outer loop less its holes (an upper floor's stairwell opening, its edge at the riser line)
                    var loops = f.Loops.Select(l => l.Select(c => Local(Plan(c.Start))).ToList()).OrderByDescending(PlanGeometry.Area).ToList();
                    var over = PlanGeometry.Overlap(tread, loops[0]);
                    foreach (var hole in loops.Skip(1))
                        over = over is null ? null : PlanGeometry.Subtract(over, hole);
                    // a sloped face (a handrail rising up the stair) is at the head's height over the tread only where
                    // its plane is: judged at the corners of its part over the tread, where its height is least and most
                    if (over is not null && over.Sum(PlanGeometry.Area) > area * 1e-9)
                    {
                        var n = TurnedNormal(f.Normal);
                        var p0 = pts[0];
                        var n2 = Local(new P2(_o.X + n.X, _o.Y + n.Y));
                        var q0 = Local(new P2(p0.X, p0.Y));
                        var zs = over.SelectMany(piece => piece).Select(q => p0.Z - (n2.X * (q.X - q0.X) + n2.Y * (q.Y - q0.Y)) / n.Z).ToList();
                        if (zs.All(z => z > headZ + Sixteenth) || zs.All(z => z < headZ - Sixteenth))
                            continue;
                    }
                    if (over is null || over.Sum(PlanGeometry.Area) > area * 1e-9)
                        return $"the floor at its head ({Named(e)}) reaches back over the last tread, short of the last riser's line, " +
                               "so the last tread is shallower than drawn by the riser: its nosing there isn't read yet";
                }
            }
            return null;
        }

        /// <summary>Not a thing at all (a Room, a room separation line): everything else, furniture and fixtures too, is
        /// in a stair's way (R311.7.2's headroom is "in all parts of the stairway"; its width is clear of all).</summary>
        private static bool NotPhysical(NearbyElement e) => e.BuiltInCategory is "OST_Rooms" or "OST_RoomSeparationLines";

        // ---- the sides ----------------------------------------------------------------------------------------

        private JsonObject? Sides(out string? why)
        {
            why = null;
            var sides = new JsonObject();
            double lo = _treads.Min(x => x.Right), hi = _treads.Max(x => x.Left);
            double innerRight = _treads.Max(x => x.Right), innerLeft = _treads.Min(x => x.Left);
            var mid = (innerRight + innerLeft) / 2;
            double s0 = _treads[0].S + Sixteenth, s1 = _back - Sixteenth;
            foreach (var (side, end) in new[] { ("left", hi), ("right", lo) })
            {
                var sign = side == "left" ? 1 : -1;
                double aIn = mid, aOut = end + sign * SideReach;
                double bandA0 = Math.Min(aIn, aOut), bandA1 = Math.Max(aIn, aOut);
                var inBand = new List<(NearbyElement E, (double S0, double S1, double A0, double A1, double Z0, double Z1) H)>();
                foreach (var e in run.Near!)
                {
                    if (!InDesign(e) || Own(e) || NotPhysical(e))   // furniture and fixtures too: in the way (review round 1)
                        continue;
                    if (Extent(e) is not { } hull)
                        continue;                                   // nothing drawn
                    var cs0 = Math.Max(hull.S0, s0);
                    var cs1 = Math.Min(hull.S1, s1);
                    if (cs0 >= cs1 || hull.A0 >= bandA1 || hull.A1 <= bandA0)
                        continue;
                    if (hull.Z0 > Line(cs1) + SideHeight || hull.Z1 < Line(cs0) - Inch)
                        continue;
                    if (OwnStair(e))
                    {
                        if (StairIsThisRun)
                            continue;
                        why = "the stair's own geometry (its runs, landings and supports together) can't be told apart run by run beside this flight";
                        return null;
                    }
                    if (stair.Supports.Contains(e.UniqueId))
                    {
                        if (SupportBelowHandrail(e, side, end))
                            continue;
                        why = $"the stair's support {Named(e)} stands over its treads or rises 34 in over them on the {side}";
                        return null;
                    }
                    inBand.Add((e, hull));
                }
                // the innermost wall face facing the flight, parallel to the run
                (NearbyElement E, SurfaceRecord F, double A, double S0, double S1)? best = null;
                foreach (var (e, _) in inBand.Where(x => x.E.BuiltInCategory == "OST_Walls"))
                {
                    foreach (var f in e.Faces ?? [])
                    {
                        if (!f.Planar || f.Points.Count == 0)
                            continue;
                        var n = TurnedNormal(f.Normal);
                        if (sign * (n.X * _v.X + n.Y * _v.Y) > -(1 - 1e-6))
                            continue;                               // not facing the flight across the run
                        var local = f.Points.Select(_t.Apply).Select(p => Local(new P2(p.X, p.Y))).ToList();
                        var a = local.Average(p => p.Y);
                        if (a < bandA0 || a > bandA1)
                            continue;
                        if (best is null || sign * (a - best.Value.A) < 0)
                            best = (e, f, a, local.Min(p => p.X), local.Max(p => p.X));
                    }
                }
                if (best is { } w)
                {
                    if (WallCoversBand(w.F) is { } gap)
                    {
                        why = $"the {side} wall face beside it ({Named(w.E)}) {gap}";
                        return null;
                    }
                    // this stair's railing beside the wall, at or under handrail height: its handrail, not its side
                    var others = inBand.Where(x => x.E.UniqueId != w.E.UniqueId
                                                   && !(side == "left" ? x.H.A0 >= w.A - Sixteenth : x.H.A1 <= w.A + Sixteenth)
                                                   && !(Railings.Contains(x.E.BuiltInCategory) && HandrailBeside(x.E, side, sign, w.A, mid))
                                                   && InTheWay(x.E, sign, mid, w.A, s0, s1)).ToList();
                    if (others.Count > 0)
                    {
                        why = BesideWords(others[0].E, side);
                        return null;
                    }
                    sides[side] = new JsonArray(XY(w.S0, w.A), XY(w.S1, w.A));
                }
                else if (inBand.FirstOrDefault(x => InTheWay(x.E, sign, mid, aOut, s0, s1)) is { E: not null } first)
                {
                    foreach (var x in inBand.Where(x => Railings.Contains(x.E.BuiltInCategory)))
                        RefuseRailing(x.E);                         // on a side with no wall: a guard along a stair
                    why = Railings.Contains(first.E.BuiltInCategory)
                        ? $"a railing ({Named(first.E)}) stands on its {side} side, where there is no wall: a guard along a stair isn't read yet"
                        : BesideWords(first.E, side);
                    return null;
                }
                else
                    sides[side] = "open";
            }
            return sides;
        }

        /// <summary>Whether any part of the element stands in a side's band between the flight's middle and
        /// <paramref name="limit"/> (the wall face, 1/16 in kept off it; or the band's outer edge), from 1 in under the
        /// line of nosings to 80 in over it. Read face by face where every face is flat with straight edges (an upper
        /// floor around a stairwell opening is in the way only where it really is: its box spans the opening); else by
        /// its box, only ever bigger than what it holds.</summary>
        private bool InTheWay(NearbyElement e, int sign, double mid, double limit, double s0, double s1)
        {
            double a0 = sign > 0 ? mid : limit + Sixteenth, a1 = sign > 0 ? limit - Sixteenth : mid;
            if (a1 <= a0 || s1 <= s0)
                return false;
            bool ZIn(double zLo, double zHi, double sa, double sb) =>
                zHi >= Line(Math.Min(sa, sb)) - Inch && zLo <= Line(Math.Max(sa, sb)) + SideHeight;
            var exact = !e.GeometryFailed && e.Faces is { Count: > 0 } fs && fs.All(f => f.Planar && f.Loops.All(l => l.All(c => c.IsLine)));
            if (!exact)
            {
                if (Extent(e) is not { } h)
                    return false;
                double cs0 = Math.Max(h.S0, s0), cs1 = Math.Min(h.S1, s1);
                return cs0 < cs1 && h.A0 < a1 && h.A1 > a0 && ZIn(h.Z0, h.Z1, cs0, cs1);
            }
            var rect = Rect(s0, s1, a0, a1);
            var breaks = _treads.Select(x => x.S).Append(_back).ToList();
            foreach (var f in e.Faces!)
            {
                var pts = f.Points.Select(_t.Apply).ToList();
                if (pts.Count == 0)
                    continue;
                var n = TurnedNormal(f.Normal);
                if (Math.Abs(n.Z) <= 1e-9)
                {
                    // a side face: its plan is a straight piece; clipped to the band's plan, its heights against the band's
                    var plan = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                    var p0 = plan.MinBy(p => p.X * 1e6 + p.Y)!;
                    var far = plan.MaxBy(p => (p.X - p0.X) * (p.X - p0.X) + (p.Y - p0.Y) * (p.Y - p0.Y))!;
                    if (Clip(p0, far, s0, s1, a0, a1) is not { } seg)
                        continue;
                    if (SideFaceInBand(f, seg.Sa, seg.Sb, breaks))
                        return true;
                    continue;
                }
                var loops = f.Loops.Select(l => l.Select(c => Local(Plan(c.Start))).ToList()).OrderByDescending(PlanGeometry.Area).ToList();
                if (loops.Count == 0)
                    continue;
                var over = PlanGeometry.Overlap(rect, loops[0]);
                foreach (var hole in loops.Skip(1))
                    over = over is null ? null : PlanGeometry.Subtract(over, hole);
                if (over is null)
                    return true;                                    // not a simple outline: the cautious side
                var q0 = Local(new P2(pts[0].X, pts[0].Y));
                var n2 = Local(new P2(_o.X + n.X, _o.Y + n.Y));
                double Z(P2 q) => pts[0].Z - (n2.X * (q.X - q0.X) + n2.Y * (q.Y - q0.Y)) / n.Z;
                foreach (var piece in over)
                {
                    var check = new List<P2>(piece);
                    for (var i = 0; i < piece.Count; i++)
                    {
                        P2 a = piece[i], b = piece[(i + 1) % piece.Count];
                        foreach (var s in breaks.Where(s => (s - a.X) * (s - b.X) < 0))
                            check.Add(new P2(s, a.Y + (s - a.X) / (b.X - a.X) * (b.Y - a.Y)));
                    }
                    var gaps = check.Select(q => Z(q) - Line(q.X)).ToList();
                    if (!gaps.All(g => g < -Inch) && !gaps.All(g => g > SideHeight))
                        return true;
                }
            }
            return false;
        }

        /// <summary>Whether a vertical flat face, over the part of it in a side's band between <paramref name="sa"/> and
        /// <paramref name="sb"/> along the run, reaches between 1 in under the line of nosings and 80 in over it: exact,
        /// the face drawn up the run (s, z) against the band drawn the same way (a sloped roof's side rising more slowly
        /// than the stair is over the band at its foot only where it really is). A face square across the run is
        /// judged at its one place along it.</summary>
        private bool SideFaceInBand(SurfaceRecord f, double sa, double sb, List<double> breaks)
        {
            List<P2> Up(IEnumerable<Xyz> pts) => pts.Select(_t.Apply).Select(p => new P2(S(new P2(p.X, p.Y)), p.Z)).ToList();
            var sz = f.Loops.Count == 0 ? Up(f.Points)
                : f.Loops.Select(l => Up(l.Select(c => c.Start))).OrderByDescending(PlanGeometry.Area).First();
            if (sz.Count == 0)
                return false;
            if (sz.Max(p => p.X) - sz.Min(p => p.X) < 1e-9)
            {
                var s = sz[0].X;
                return sz.Max(p => p.Y) >= Line(s) - Inch && sz.Min(p => p.Y) <= Line(s) + SideHeight;
            }
            if (sb - sa < 1e-9)
                return false;
            var cuts = breaks.Where(s => s > sa && s < sb).Prepend(sa).Append(sb).ToList();
            var band = cuts.Select(s => new P2(s, Line(s) - Inch)).Concat(Enumerable.Reverse(cuts).Select(s => new P2(s, Line(s) + SideHeight))).ToList();
            // the face's outline up the run, or (not a simple outline) its box there: only ever bigger
            var face = PlanGeometry.Clean(sz) is { } clean && PlanGeometry.IsSimple(clean) ? clean
                : [new(sz.Min(p => p.X), sz.Min(p => p.Y)), new(sz.Max(p => p.X), sz.Min(p => p.Y)), new(sz.Max(p => p.X), sz.Max(p => p.Y)), new(sz.Min(p => p.X), sz.Max(p => p.Y))];
            return PlanGeometry.OverlapArea(band, face) is not { } a || a > 1e-12;
        }

        /// <summary>A plan segment clipped to the box s0..s1, a0..a1 (Liang–Barsky): the s range of what is inside, or
        /// null when nothing is.</summary>
        private static (double Sa, double Sb)? Clip(P2 p, P2 q, double s0, double s1, double a0, double a1)
        {
            double t0 = 0, t1 = 1, dx = q.X - p.X, dy = q.Y - p.Y;
            foreach (var (den, num) in new[] { (-dx, p.X - s0), (dx, s1 - p.X), (-dy, p.Y - a0), (dy, a1 - p.Y) })
            {
                if (Math.Abs(den) < 1e-12)
                {
                    if (num < 0)
                        return null;
                    continue;
                }
                var t = num / den;
                if (den < 0)
                    t0 = Math.Max(t0, t);
                else
                    t1 = Math.Min(t1, t);
                if (t0 > t1)
                    return null;
            }
            return (p.X + t0 * dx, p.X + t1 * dx);
        }

        private string BesideWords(NearbyElement e, string side)
        {
            if (!Railings.Contains(e.BuiltInCategory))
                return $"{Named(e)} stands on its {side} side, within the clear width or above it, and isn't read as a side";
            RefuseRailing(e);
            return $"a railing ({Named(e)}) stands on its {side} side and isn't read as its handrail beside the wall (it isn't on " +
                   "this stair, rises more than 38 in over the nosings, reaches past the middle or the wall face, can't be read exactly, " +
                   $"or has a part not sent as a handrail, such as a top rail not marked {Marks.TopRailIsHandrail.Name} Yes, a post " +
                   "or a baluster, standing farther in than its handrail)";
        }

        /// <summary>An element's extent in the frame: from its flat faces' corners when every face is flat (exact: a
        /// box axis-aligned in Revit's own coordinates swells when the flight is turned from them), else from its box
        /// (only ever bigger than what it holds); null when nothing is drawn.</summary>
        private (double S0, double S1, double A0, double A1, double Z0, double Z1)? Extent(NearbyElement e)
        {
            // only lines and points (a railing's path extension lines, a model line), its geometry read: nothing physical,
            // never a side, an obstruction or overhead, whatever its box (Revit 2027.4, trial step 5 run 2). Geometry that
            // failed is still read by its box: the cautious side
            if (e is { GeometryFailed: false, Faces.Count: 0 })
                return null;
            var exact = !e.GeometryFailed && e.Faces is { Count: > 0 } fs && fs.All(f => f.Planar && f.Loops.All(l => l.All(c => c.IsLine)));
            if (!exact && e.Box is { } box)
                return Hull(box);
            var pts = (e.Faces ?? []).SelectMany(f => f.Points).Select(_t.Apply).ToList();
            if (pts.Count == 0)
                return e.GeometryFailed ? (double.MinValue, double.MaxValue, double.MinValue, double.MaxValue, double.MinValue, double.MaxValue) : null;
            var local = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
            return (local.Min(p => p.X), local.Max(p => p.X), local.Min(p => p.Y), local.Max(p => p.Y), pts.Min(p => p.Z), pts.Max(p => p.Z));
        }

        /// <summary>Whether the wall face runs the whole band: from the first nosing to the top one, from 1 in under the
        /// line of nosings to 80 in over it (null), else what it misses.</summary>
        private string? WallCoversBand(SurfaceRecord f)
        {
            if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                return "has a curved edge";
            var sz = f.Loops.Select(l => l.Select(c => _t.Apply(c.Start)).Select(p => new P2(S(new P2(p.X, p.Y)), p.Z)).ToList())
                .OrderByDescending(PlanGeometry.Area).ToList();
            double s0 = _treads[0].S, s1 = _back;
            var cuts = _treads.Select(x => x.S).Append(_back).Where(s => s > s0 && s < s1).Prepend(s0).Append(s1).ToList();
            var band = cuts.Select(s => new P2(s, Line(s) - Inch)).Concat(Enumerable.Reverse(cuts).Select(s => new P2(s, Line(s) + SideHeight))).ToList();
            var area = PlanGeometry.Area(band);
            if (PlanGeometry.OverlapArea(band, sz[0]) is not { } covered || covered < area * (1 - 1e-9))
                return "doesn't run the whole flight from its treads to 80 in over them";
            if (sz.Skip(1).Any(hole => PlanGeometry.OverlapArea(band, hole) is not { } h || h > area * 1e-9))
                return "has an opening beside the flight";
            return null;
        }

        /// <summary>A stair's own support beside its treads that can't narrow the width: every face flat, every point
        /// outside the tread ends (1/16 in to spare) and under the lowest handrail height over the line of nosings.</summary>
        private bool SupportBelowHandrail(NearbyElement e, string side, double end)
        {
            if (e.GeometryFailed || e.Faces is null || e.Faces.Any(f => !f.Planar))
                return false;
            foreach (var p in e.Faces.SelectMany(f => f.Points).Select(_t.Apply))
            {
                var q = Local(new P2(p.X, p.Y));
                var outside = side == "left" ? q.Y >= end - Sixteenth : q.Y <= end + Sixteenth;
                if (!outside || p.Z > Line(q.X) + HandrailLow)
                    return false;
            }
            return true;
        }

        // ---- what is overhead --------------------------------------------------------------------------------

        private JsonArray? Overhead(out string? why)
        {
            why = null;
            double lo = _treads.Min(x => x.Right), hi = _treads.Max(x => x.Left);
            var plan = Rect(_treads[0].S, _back, lo, hi);
            var planArea = PlanGeometry.Area(plan);
            var nosingS = _treads.Select(x => x.S).Append(_back).ToList();
            var pieces = new JsonArray();
            foreach (var e in run.Near!)
            {
                if (!InDesign(e) || Own(e) || NotPhysical(e))   // a pendant light, a cabinet: in the headroom too
                    continue;
                if (OwnStair(e))
                {
                    if (StairIsThisRun || e is { GeometryFailed: false, Faces.Count: 0 })
                        continue;
                    why = "the stair's own geometry (its runs, landings and supports together) can't be told apart run by run over this flight";
                    return null;
                }
                var known = InteriorReader.Building.Contains(e.BuiltInCategory) || InteriorReader.NotBuilding.Contains(e.BuiltInCategory);
                if (!known && e is { GeometryFailed: false, Faces.Count: 0 })
                    continue;
                if (Extent(e) is not { } hull || hull.S1 <= _treads[0].S + Sixteenth || hull.S0 >= _back - Sixteenth
                    || hull.A1 <= lo + Sixteenth || hull.A0 >= hi - Sixteenth || hull.Z1 <= Line(Math.Max(hull.S0, _treads[0].S)) + Sixteenth)
                    continue;                                       // nowhere over the flight's plan, or wholly under it
                if (Railings.Contains(e.BuiltInCategory))
                {
                    // this stair's railing read as its handrail beside a wall (no higher than 38 in over the nosings):
                    // inside the stairway's width at the handrail, never its headroom
                    if (_railingOf.TryGetValue(e.UniqueId, out var r) && (_accepted.ContainsKey(r.UniqueId) || LowRailing(r)))
                        continue;
                    why = $"a railing ({Named(e)}) reaches over it and isn't read as its handrail beside a wall";
                    return null;
                }
                if (!known)
                {
                    why = $"{Named(e)} is over it, in a category Gordium doesn't read as overhead or as furniture";
                    return null;
                }
                if (e.GeometryFailed || e.Faces is null)
                {
                    why = $"the geometry of {Named(e)} over it couldn't be read";
                    return null;
                }
                bool above = false, under = false;
                var mine = new List<JsonArray>();
                foreach (var f in e.Faces)
                {
                    var pts = f.Points.Select(_t.Apply).ToList();
                    if (pts.Count == 0)
                        continue;
                    if (!f.Planar)
                    {
                        var local = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                        if (PlanGeometry.OverlapArea(plan, Rect(local.Min(p => p.X), local.Max(p => p.X), local.Min(p => p.Y), local.Max(p => p.Y))) is not (null or <= 0)
                            && pts.Max(p => p.Z) > Line(local.Min(p => p.X)) - Inch)
                        {
                            why = $"a curved face of {Named(e)} is over it, which isn't read exactly";
                            return null;
                        }
                        continue;
                    }
                    var n = TurnedNormal(f.Normal);
                    if (Math.Abs(n.Z) <= 1e-9 || f.Loops.Count == 0)
                        continue;                                   // a side: no area seen from above
                    var loops = f.Loops.Select(l => l.Select(c => Local(Plan(c.Start))).ToList()).OrderByDescending(PlanGeometry.Area).ToList();
                    var over = PlanGeometry.Overlap(plan, loops[0]);
                    foreach (var hole in loops.Skip(1))
                        over = over is null ? null : PlanGeometry.Subtract(over, hole);
                    if (over is null)
                    {
                        why = $"an underside of {Named(e)} over it isn't a simple outline";
                        return null;
                    }
                    if (over.Sum(PlanGeometry.Area) <= planArea * 1e-9)
                        continue;
                    if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                    {
                        why = $"an underside of {Named(e)} over it has a curved edge, which isn't read exactly";
                        return null;
                    }
                    // the face's plane, in the frame: z at (s, a)
                    var p0 = pts[0];
                    var n2 = Local(new P2(_o.X + n.X, _o.Y + n.Y));          // its normal turned into the frame
                    var q0 = Local(new P2(p0.X, p0.Y));
                    double Z(P2 q) => p0.Z - (n2.X * (q.X - q0.X) + n2.Y * (q.Y - q0.Y)) / n.Z;
                    foreach (var piece in over)
                    {
                        // above the line of nosings all over (its least over the piece is at a corner, or where the line
                        // bends on the piece's edge), or under it all over (under the stair); never across it
                        var check = new List<P2>(piece);
                        for (var i = 0; i < piece.Count; i++)
                        {
                            P2 a = piece[i], b = piece[(i + 1) % piece.Count];
                            foreach (var s in nosingS.Where(s => (s - a.X) * (s - b.X) < 0))
                                check.Add(new P2(s, a.Y + (s - a.X) / (b.X - a.X) * (b.Y - a.Y)));
                        }
                        var gaps = check.Select(q => Z(q) - Line(q.X)).ToList();
                        if (gaps.All(g => g <= Sixteenth))
                            under = true;                           // under the treads, or at them
                        else if (gaps.Any(g => g <= Sixteenth))
                            under = above = true;                   // across the line itself
                        else
                        {
                            above = true;
                            if (n.Z < 0)                            // an underside over the flight
                                mine.Add(new JsonArray(piece.Select(q => (JsonNode)Point3(q.X, q.Y, Z(q))).ToArray()));
                        }
                    }
                }
                if (above && under)
                {
                    why = $"{Named(e)} crosses the flight (part of it is under the line of its nosings, part over it)";
                    return null;
                }
                foreach (var piece in mine)
                    pieces.Add(piece);
            }
            if (pieces.Count == 0)
            {
                why = "nothing was found over it";
                return null;
            }
            return pieces;
        }
    }
}
