using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>
/// The guards, section 7 step 5 of docs/revit/revit_interior_reading_design.md: each <c>Railing</c> that isn't on a stair
/// is a guard at a level walking surface (<c>guards</c>, its <c>walking_surface</c>, <c>top</c>, <c>extent</c> and
/// <c>members</c>), read from what is drawn. The rules are the note's sections 2 and 4:
/// <list type="bullet">
/// <item><c>guards</c> is sent only when the architect has ticked <c>Gordium: These are all the guards and handrails</c>
/// (Yes), nothing could be a stair or railing the reader doesn't walk (the stairs' blockers), and every railing on a stair
/// is read as a handrail beside a wall (a guard along a stair, its <c>top_line</c> on the stair's side, isn't read yet).
/// Nothing found is never "none": with no guard found the list is left out.</item>
/// <item>A guard found is never dropped: a value that can't be read exactly is left out, with its reason.</item>
/// <item><c>members</c>: every solid of the railing, its top rail and its handrails, each a box square to the guard (six
/// flat faces, each facing along it, across it or up), as its rectangle in the guard's elevation; anything else (a round
/// baluster, a sloped or curved rail, a mesh) leaves the members out: a rectangle around it would be bigger than it, and
/// the openings smaller than they are. <c>top</c>: the highest member's top.</item>
/// <item><c>walking_surface</c>: the top of the floor along the railing's path (a 1 in strip on one side or the other,
/// covered whole by one flat top, every top there at one height), sent only when it agrees with the railing's base
/// (its level and base offset) within 1/16 in.</item>
/// <item><c>extent</c>: the path's two ends, sent only when at each a wall or column face stands square across the
/// guard's end (within 1/16 in of it), covering it from the walking surface to the top across the members' depth:
/// the format reads past each end as solid. A guard ending in the air leaves it out.</item>
/// <item>A path that isn't one straight line, or a loaded link reaching the guard, leaves every value out.</item>
/// </list>
/// </summary>
public static class GuardReader
{
    private const double Sixteenth = InteriorReader.Sixteenth;

    /// <summary>The strip beside the path where the floor is looked for (ft).</summary>
    public const double Strip = 1.0 / 12;

    /// <summary>What a guard may end against: solid beyond.</summary>
    public static readonly IReadOnlySet<string> EndCategories = new HashSet<string>(StringComparer.Ordinal)
    {
        "OST_Walls", "OST_Columns", "OST_StructuralColumns",
    };

    /// <summary>Why no guard can be read (empty when they can). <paramref name="stairs"/> is what the flights made of the
    /// railings beside them, or null when the stairs weren't read.</summary>
    public static List<string> NotRead(RevitModel model, StairReader.RailingUse? stairs)
    {
        if (model.Interior is not { } records)
            return ["the model's inside wasn't read"];
        var why = new List<string>();
        if (MarkReading.AllGuards(model) is not true)
            why.Add($"{Marks.AllGuards.Name} is {(MarkReading.AllGuards(model) is false ? "No" : "not set")} on Project " +
                    "Information: until it says Yes, a guard not drawn as a railing would go unchecked");
        if (records.Railings is null)
            why.Add("the railings couldn't be read");
        why.AddRange(StairReader.Blockers(model));
        foreach (var r in records.Railings ?? [])
        {
            if (!SiteReader.InDesignChecked(model, r.PhaseDemolished, r.DesignOption))
                continue;
            if ((records.Stairs ?? []).FirstOrDefault(s => StairReader.OnStair(s, r)) is not { } stair)
            {
                // a railing on no stair standing beside a flight can't be told apart from a guard along that stair, which
                // isn't read yet (review round 1); with stairs drawn but not read, where it stands isn't known
                if (stairs is not null && stairs.Refused.Contains(r.UniqueId))
                    why.Add($"Railing \"{r.Name ?? r.UniqueId}\" stands beside a flight and isn't the stair's: it may be a guard along the stair, which isn't read yet");
                else if (stairs is null && (records.Stairs ?? []).Any(s => SiteReader.InDesignChecked(model, s.PhaseDemolished, s.DesignOption)))
                    why.Add($"Railing \"{r.Name ?? r.UniqueId}\": the stairs aren't read, so whether it stands beside one (a guard along a stair, not read yet) isn't known");
                // and whatever reading a flight got to (a winder, a run unread, a side refused first): by where the runs
                // and the railing are drawn, never by how far a flight was read (review round 2)
                else if (NearARun(model, records, r) is { } near)
                    why.Add($"Railing \"{r.Name ?? r.UniqueId}\" {near}: it may be a guard along the stair, which isn't read yet");
                continue;
            }
            var name = $"Railing \"{r.Name ?? r.UniqueId}\" on stair \"{stair.Name ?? stair.UniqueId}\"";
            if (stairs is null)
                why.Add($"{name}: the stairs aren't read, so whether it is a handrail beside a wall or a guard along the stair isn't known");
            else if (!stairs.BesideWall.Contains(r.UniqueId))
                why.Add($"{name} isn't read as a handrail beside a wall: a guard along a stair isn't read yet");
        }
        return why;
    }

    /// <summary>How far around a stair run a railing on no stair is held back (ft): beyond the run's own drawn extent
    /// (its width with it) in plan, and over its top by a guard's height and more.</summary>
    public const double NearRun = 1.0;

    /// <summary>The headroom over a run within which a railing counts as near it (ft): more than any guard is tall.</summary>
    public const double OverRun = 4.0;

    /// <summary>Why a railing on no stair counts as near a stair run in the design (null when it is near none): its box
    /// (path and parts, shared coordinates) within <see cref="NearRun"/> of a run's box in plan (the run's own faces and
    /// path) and its height range meeting the run's, from its base to <see cref="OverRun"/> over its top. A run whose
    /// extent can't be known (no faces read), or a railing with nothing drawn, counts as near.</summary>
    private static string? NearARun(RevitModel model, InteriorRecords records, RailingRecord r)
    {
        var t = model.InternalToShared;
        var mine = r.Path.SelectMany(c => new[] { c.Start, c.End })
            .Concat(r.Parts.SelectMany(p => p.Solids ?? []).SelectMany(s => s).SelectMany(f => f.Points)).Select(t.Apply).ToList();
        foreach (var stair in records.Stairs ?? [])
        {
            if (!SiteReader.InDesignChecked(model, stair.PhaseDemolished, stair.DesignOption))
                continue;
            foreach (var run in stair.Runs)
            {
                var pts = (run.Faces ?? []).SelectMany(f => f.Points).Concat(run.Path).Select(t.Apply).ToList();
                if (run.Faces is not { Count: > 0 } || pts.Count == 0)
                    return $"may stand near stair \"{stair.Name ?? stair.UniqueId}\", whose run's extent couldn't be read";
                if (mine.Count == 0)
                    return "has nothing drawn to tell where it stands, and stairs are drawn";
                if (mine.Min(p => p.X) <= pts.Max(p => p.X) + NearRun && mine.Max(p => p.X) >= pts.Min(p => p.X) - NearRun
                    && mine.Min(p => p.Y) <= pts.Max(p => p.Y) + NearRun && mine.Max(p => p.Y) >= pts.Min(p => p.Y) - NearRun
                    && mine.Min(p => p.Z) <= pts.Max(p => p.Z) + OverRun && mine.Max(p => p.Z) >= pts.Min(p => p.Z) - NearRun)
                    return $"stands within {NearRun:0} ft of stair \"{stair.Name ?? stair.UniqueId}\" and isn't the stair's";
            }
        }
        return null;
    }

    /// <summary>Every railing in the design checked that isn't on a stair, as a level guard (the list is the caller's to
    /// send or not).</summary>
    public static JsonArray Guards(RevitModel model, List<InteriorNote> notes, JsonObject evidence)
    {
        var guards = new JsonArray();
        var stairs = model.Interior?.Stairs ?? [];
        foreach (var r in model.Interior?.Railings ?? [])
        {
            if (!SiteReader.InDesignChecked(model, r.PhaseDemolished, r.DesignOption) || stairs.Any(s => StairReader.OnStair(s, r)))
                continue;
            guards.Add(new Guard(model, r, notes, evidence).Read());
        }
        return guards;
    }

    private sealed class Guard(RevitModel model, RailingRecord r, List<InteriorNote> notes, JsonObject evidence)
    {
        private readonly Transform3 _t = model.InternalToShared;
        private readonly JsonObject _ev = new();

        // the guard's frame in shared plan coordinates: u along its path from its start, n across it to the left
        private P2 _o;
        private P2 _u;
        private P2 _v;
        private double _u0;
        private double _u1;

        private void Out(string field, string why) => notes.Add(new(r.UniqueId, field, why));

        private void OutAll(string why)
        {
            foreach (var f in new[] { "walking_surface", "top", "extent", "members" })
                Out(f, why);
        }

        private P2 Plan(Xyz p)
        {
            var s = _t.Apply(p);
            return new P2(s.X, s.Y);
        }

        private P2 Local(P2 p) => new((p.X - _o.X) * _u.X + (p.Y - _o.Y) * _u.Y, (p.X - _o.X) * _v.X + (p.Y - _o.Y) * _v.Y);

        private Xyz Turned(Xyz n) => n.X * _t.BasisX + n.Y * _t.BasisY + n.Z * _t.BasisZ;

        private static string Named(NearbyElement e) =>
            string.IsNullOrWhiteSpace(e.Name) ? e.BuiltInCategory.Replace("OST_", "") : $"{e.BuiltInCategory.Replace("OST_", "")} \"{e.Name}\"";

        private bool Own(NearbyElement e) => e.UniqueId == r.UniqueId || r.Parts.Any(p => p.UniqueId == e.UniqueId);

        private bool InDesign(NearbyElement e) => SiteReader.InDesignChecked(model, e.PhaseDemolished, e.DesignOption);

        public JsonObject Read()
        {
            var guard = new JsonObject { ["id"] = r.UniqueId, ["name"] = r.Name ?? "Guard" };
            evidence[r.UniqueId] = _ev;
            _ev["revit_layer"] = new JsonArray(r.Diagnostics.Select(d => (JsonNode?)d).ToArray());
            if (PathProblem() is { } bad)
            {
                OutAll(bad);
                return guard;
            }
            _ev["length"] = _u1 - _u0;
            if (model.Interior!.Links.Where(l => l.Loaded && l.Box is not null && Reaches(l.Box!)).Select(l => l.Name).ToList()
                is { Count: > 0 } links)
            {
                OutAll("linked model " + string.Join(", ", links.Select(n => $"\"{n}\"")) + " reaches it, and what is in a link isn't read yet");
                return guard;
            }

            var members = Members(out var membersWhy);
            double? top = members?.Max(m => m.Z1);
            if (members is null)
            {
                Out("members", membersWhy!);
                Out("top", "read from its members, which weren't read: " + membersWhy);
            }
            else
            {
                guard["top"] = top;
                _ev["members"] = members.Count;
                _ev["depth"] = new JsonArray(members.Min(m => m.N0), members.Max(m => m.N1));
            }

            double? walk = null;
            if (r.Near is null)
                Out("walking_surface", "what is around it couldn't be looked for");
            else if (Walk(out var walkWhy) is { } w)
                walk = w;
            else
                Out("walking_surface", walkWhy!);
            if (walk is { } ws)
                guard["walking_surface"] = ws;

            if (members is null || walk is null || top is null)
                Out("extent", "what it ends against is checked over its height, from the walking surface to its top, which weren't both read");
            else if (r.Near is null)
                Out("extent", "what is around it couldn't be looked for");
            else
            {
                double n0 = members.Min(m => m.N0), n1 = members.Max(m => m.N1);
                var left = EndAt(_u0, +1, n0, n1, walk.Value, top.Value);
                var right = EndAt(_u1, -1, n0, n1, walk.Value, top.Value);
                _ev["ends"] = new JsonArray(left?.By ?? "none", right?.By ?? "none");
                if (left is null || right is null)
                    Out("extent", $"nothing solid was found at its {(left is null ? "start" : "end")} (a wall or post face square across " +
                                  "the whole guard, from the walking surface to its top, within 1/16 in of the end of its path): " +
                                  "past each end is read as solid, so a guard ending in the air isn't read");
                else
                {
                    // the faces it ends against; a member's end within a millionth of a foot of one is on it (Revit's
                    // number noise, 1e-9 ft: never a drawn gap, which 1/16 in is the measuring code's least)
                    guard["extent"] = new JsonObject { ["left"] = left.Value.U, ["right"] = right.Value.U };
                    double Snap(double u) => Math.Abs(u - left.Value.U) <= Noise ? left.Value.U : Math.Abs(u - right.Value.U) <= Noise ? right.Value.U : u;
                    members = members.Select(m => m with { U0 = Snap(m.U0), U1 = Snap(m.U1) }).ToList();
                }
            }
            // the openings are measured in one plane (the guard's elevation): only when every infill member (each under
            // the guard's top: the balusters, posts, panels and lower rails) has its face toward the walking side in one
            // plane within 1/16 in. Members at different depths projected together could block a sphere that weaves
            // between them (two staggered rows, each with 4.5 in gaps, overlap to about 2 in in elevation)
            if (members is not null && walk is not null && top is { } t && Depths(members, t) is { } depthWhy)
            {
                Out("members", depthWhy);
                members = null;
            }
            if (members is not null)
                guard["members"] = new JsonArray(members.Select(m => (JsonNode)new JsonObject
                {
                    ["left"] = m.U0, ["right"] = m.U1, ["bottom"] = m.Z0, ["top"] = m.Z1,
                }).ToArray());
            return guard;
        }

        // which side of the path the walking surface was found on: +1 (n above 0), -1, or 0 for both
        private int _walkSide;

        /// <summary>Why the infill members' faces toward the walking side aren't in one plane within 1/16 in (null when
        /// they are), naming the members and their depths. With the floor on both sides, both faces must be.</summary>
        private string? Depths(List<(double U0, double U1, double N0, double N1, double Z0, double Z1)> members, double top)
        {
            var infill = members.Where(m => m.Z1 < top - Sixteenth).ToList();
            if (infill.Count < 2)
                return null;
            foreach (var (side, face) in new (int, Func<(double U0, double U1, double N0, double N1, double Z0, double Z1), double>)[]
                     { (1, m => m.N1), (-1, m => m.N0) })
            {
                if (_walkSide != 0 && _walkSide != side)
                    continue;
                var faces = infill.Select(face).ToList();
                if (faces.Max() - faces.Min() <= Sixteenth)
                    continue;
                return "its infill members' faces toward the walking side aren't in one plane (" + string.Join("; ", infill
                           .GroupBy(m => Math.Round(face(m) * 12 * 16) / 16).OrderBy(g => g.Key)
                           .Select(g => $"{g.Count()} at {g.Key.ToString("0.###", CultureInfo.InvariantCulture)} in across the guard, " +
                                        $"from {ClearStamp.Inches(g.Min(m => m.U0))} along it")) +
                       "): a sphere could pass between members at different depths, so its openings aren't read in one plane";
            }
            return null;
        }

        /// <summary>A millionth of a foot: the most a member's end is put on the face it ends against.</summary>
        private const double Noise = 1e-6;

        /// <summary>Why the path isn't one straight line (null when it is: then the frame is set).</summary>
        private string? PathProblem()
        {
            if (r.Path.Count == 0)
                return "its path couldn't be read";
            if (r.Path.Any(c => !c.IsLine))
                return "its path has a curve: only straight guards are read";
            var pts = r.Path.SelectMany(c => new[] { Plan(c.Start), Plan(c.End) }).ToList();
            _o = pts[0];
            var d = pts[^1] - _o;
            var len = Math.Sqrt(d.X * d.X + d.Y * d.Y);
            if (len < 1e-9)
                return "its path has no length";
            _u = new P2(d.X / len, d.Y / len);
            _v = new P2(-_u.Y, _u.X);
            var local = pts.Select(Local).ToList();
            if (local.Any(p => Math.Abs(p.Y) > Sixteenth))
                return "its path isn't one straight line (it turns): only straight guards are read";
            for (var i = 1; i < r.Path.Count; i++)
                if (Math.Abs(Local(Plan(r.Path[i].Start)).X - Local(Plan(r.Path[i - 1].End)).X) > Sixteenth)
                    return "its path's pieces don't follow on from each other";
            _u0 = local.Min(p => p.X);
            _u1 = local.Max(p => p.X);
            return null;
        }

        private bool Reaches(RevitBox box)
        {
            var b = Box3.Turned(box.Min, box.Max, box.Transform is { } own ? _t.After(own) : _t);
            var corners = new[] { new P2(b.Min.X, b.Min.Y), new P2(b.Max.X, b.Min.Y), new P2(b.Max.X, b.Max.Y), new P2(b.Min.X, b.Max.Y) }.Select(Local).ToList();
            return corners.Min(p => p.X) < _u1 && corners.Max(p => p.X) > _u0 && corners.Min(p => p.Y) < 1 && corners.Max(p => p.Y) > -1;
        }

        /// <summary>Each solid of the railing's parts as a box square to the guard, (u, n, z) extents; null with why when
        /// any isn't one, or nothing is drawn.</summary>
        private List<(double U0, double U1, double N0, double N1, double Z0, double Z1)>? Members(out string? why)
        {
            why = null;
            var boxes = new List<(double U0, double U1, double N0, double N1, double Z0, double Z1)>();
            foreach (var part in r.Parts)
            {
                if (part.GeometryFailed || part.Solids is null)
                {
                    why = $"the geometry of its {Part(part)} couldn't be read exactly (a mesh, or Revit refused)";
                    return null;
                }
                foreach (var solid in part.Solids.Where(s => s.Count > 0))
                {
                    if (solid.Count != 6 || solid.Any(f => !f.Planar || f.Loops.Any(l => l.Any(c => !c.IsLine)) || !Square(f)))
                    {
                        why = $"a piece of its {Part(part)} isn't a box square to the guard (a round or turned baluster, a sloped " +
                              "or shaped rail): a rectangle around it would be bigger than it, and its openings smaller than they are";
                        return null;
                    }
                    var pts = solid.SelectMany(f => f.Points).Select(_t.Apply).ToList();
                    var plan = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                    boxes.Add((plan.Min(p => p.X), plan.Max(p => p.X), plan.Min(p => p.Y), plan.Max(p => p.Y), pts.Min(p => p.Z), pts.Max(p => p.Z)));
                }
            }
            if (boxes.Count == 0)
            {
                why = "no rail, baluster or post was found in its geometry";
                return null;
            }
            return boxes;
        }

        private static string Part(RailingPart p) => p.Kind switch
        {
            RailingPartKind.TopRail => "top rail",
            RailingPartKind.Handrail => "handrail",
            _ => "balusters, posts and rails",
        };

        /// <summary>A flat face facing along the guard, across it or up or down.</summary>
        private bool Square(SurfaceRecord f)
        {
            var n = Turned(f.Normal);
            double along = Math.Abs(n.X * _u.X + n.Y * _u.Y), across = Math.Abs(n.X * _v.X + n.Y * _v.Y);
            return along >= 1 - 1e-6 || across >= 1 - 1e-6 || Math.Abs(n.Z) >= 1 - 1e-6;
        }

        /// <summary>The walking surface: the one flat top along the path, within a foot of the railing's base, agreeing
        /// with it within 1/16 in; null with why.</summary>
        private double? Walk(out string? why)
        {
            why = null;
            if (r.BaseLevelElevation is not { } level || r.BaseOffset is not { } offset)
            {
                why = "its base level or base offset couldn't be read, so the floor under it can't be checked against them";
                return null;
            }
            var start = r.Path[0].Start;
            var claimed = _t.Apply(new Xyz(start.X, start.Y, level + offset)).Z;
            _ev["base"] = claimed;
            List<P2> Rect(double n0, double n1) => [new(_u0, n0), new(_u1, n0), new(_u1, n1), new(_u0, n1)];
            var strips = new[] { Rect(0, Strip), Rect(-Strip, 0) };
            var area = PlanGeometry.Area(strips[0]);
            var tops = new List<(double Z, List<List<P2>> Loops, string By)>();
            foreach (var e in r.Near!)
            {
                if (!InDesign(e) || Own(e) || InteriorReader.NotBuilding.Contains(e.BuiltInCategory))
                    continue;
                if (e.GeometryFailed || e.Faces is null)
                {
                    // by its box (only ever bigger than it), or, with none, wherever it is: the cautious side
                    if (e.Box is not { } box || (Box3.Turned(box.Min, box.Max, box.Transform is { } own ? _t.After(own) : _t) is var b
                                                 && b.Max.Z >= claimed - InteriorReader.SlabBand && b.Min.Z <= claimed + InteriorReader.SlabBand
                                                 && Reaches(box)))
                    {
                        why = $"the geometry of {Named(e)} near it couldn't be read";
                        return null;
                    }
                    if (e.Faces is null)
                        continue;
                }
                foreach (var f in e.Faces)
                {
                    var pts = f.Points.Select(_t.Apply).ToList();
                    if (pts.Count == 0 || pts.Max(p => p.Z) < claimed - InteriorReader.SlabBand || pts.Min(p => p.Z) > claimed + InteriorReader.SlabBand)
                        continue;
                    var plan = pts.Select(p => Local(new P2(p.X, p.Y))).ToList();
                    var hull = new List<P2> { new(plan.Min(p => p.X), plan.Min(p => p.Y)), new(plan.Max(p => p.X), plan.Min(p => p.Y)), new(plan.Max(p => p.X), plan.Max(p => p.Y)), new(plan.Min(p => p.X), plan.Max(p => p.Y)) };
                    var near = strips.Any(s => PlanGeometry.OverlapArea(s, hull) is not (null or <= 0));
                    if (!f.Planar)
                    {
                        if (near)
                        {
                            why = $"a curved face of {Named(e)} is beside it";
                            return null;
                        }
                        continue;
                    }
                    if (Turned(f.Normal).Z <= 1e-9 || f.Loops.Count == 0 || !near)
                        continue;
                    if (pts.Max(p => p.Z) - pts.Min(p => p.Z) > Sixteenth)
                    {
                        why = $"the top of {Named(e)} beside it slopes";
                        return null;
                    }
                    if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                    {
                        why = $"the top of {Named(e)} beside it has a curved edge, which isn't read exactly";
                        return null;
                    }
                    tops.Add((pts.Average(p => p.Z), f.Loops.Select(l => l.Select(c => Local(Plan(c.Start))).ToList()).OrderByDescending(PlanGeometry.Area).ToList(), Named(e)));
                }
            }
            _ev["floor_tops"] = new JsonArray(tops.Select(x => (JsonNode)$"{x.Z.ToString("0.######", CultureInfo.InvariantCulture)} {x.By}").ToArray());
            if (tops.Count == 0)
            {
                why = "no floor top was found along it within a foot of its base";
                return null;
            }
            if (tops.Max(x => x.Z) - tops.Min(x => x.Z) > Sixteenth)
            {
                why = "the floor tops along it are at different heights (" +
                      string.Join(", ", tops.Select(x => ClearStamp.Inches(x.Z - claimed) + " from its base, " + x.By).Distinct()) + ")";
                return null;
            }
            bool Covers(List<P2> s) => tops.Any(x => PlanGeometry.OverlapArea(s, x.Loops[0]) is { } a && a >= area * (1 - 1e-9)
                                                     && x.Loops.Skip(1).All(h => PlanGeometry.OverlapArea(s, h) is { } ha && ha <= area * 1e-9));
            bool above = Covers(strips[0]), below = Covers(strips[1]);
            var covered = above || below;
            _walkSide = above && below ? 0 : above ? 1 : -1;
            if (!covered)
            {
                why = "no one floor top runs its whole length beside it";
                return null;
            }
            var z = tops[0].Z;
            if (Math.Abs(z - claimed) > Sixteenth)
            {
                why = $"the floor along it ({tops[0].By}) is {ClearStamp.Inches(z - claimed)} from its base (its level and base offset): they must agree within 1/16 in";
                return null;
            }
            return z;
        }

        /// <summary>What stands across the guard's end at u (<paramref name="toward"/> +1 at its start, its face looking
        /// along the guard; -1 at its end): a wall or column face square to the guard, within 1/16 in of the end, covering
        /// n0..n1 from the walking surface to the top. Its name and where it stands along the guard, or null.</summary>
        private (string By, double U)? EndAt(double u, int toward, double n0, double n1, double walk, double top)
        {
            var need = new List<P2> { new(n0, walk), new(n1, walk), new(n1, top), new(n0, top) };
            var area = PlanGeometry.Area(need);
            foreach (var e in r.Near!.Where(e => InDesign(e) && !Own(e) && EndCategories.Contains(e.BuiltInCategory)))
            {
                foreach (var f in e.Faces ?? [])
                {
                    if (!f.Planar || f.Loops.Count == 0 || f.Loops.Any(l => l.Any(c => !c.IsLine)))
                        continue;
                    var n = Turned(f.Normal);
                    if (toward * (n.X * _u.X + n.Y * _u.Y) < 1 - 1e-6)
                        continue;                                   // not facing back along the guard
                    var pts = f.Points.Select(_t.Apply).ToList();
                    if (pts.Any(p => Math.Abs(Local(new P2(p.X, p.Y)).X - u) > Sixteenth))
                        continue;
                    var loops = f.Loops.Select(l => l.Select(c => _t.Apply(c.Start)).Select(p => new P2(Local(new P2(p.X, p.Y)).Y, p.Z)).ToList())
                        .OrderByDescending(PlanGeometry.Area).ToList();
                    if (PlanGeometry.OverlapArea(need, loops[0]) is { } a && a >= area * (1 - 1e-9)
                        && loops.Skip(1).All(h => PlanGeometry.OverlapArea(need, h) is { } ha && ha <= area * 1e-9))
                        return (Named(e), pts.Average(p => Local(new P2(p.X, p.Y)).X));
                }
            }
            return null;
        }
    }
}
