namespace Gordium.Revit.Reading;

/// <summary>A point (or a direction) in feet, as Revit's <c>XYZ</c>. Doubles throughout, never single precision:
/// scene 10 holds points 875,000 ft from the origin to a millionth of a foot.</summary>
public readonly record struct Xyz(double X, double Y, double Z)
{
    public static Xyz operator +(Xyz a, Xyz b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
    public static Xyz operator -(Xyz a, Xyz b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
    public static Xyz operator *(double k, Xyz a) => new(k * a.X, k * a.Y, k * a.Z);

    public double DistanceTo(Xyz b) => Math.Sqrt((X - b.X) * (X - b.X) + (Y - b.Y) * (Y - b.Y) + (Z - b.Z) * (Z - b.Z));

    public bool IsFinite => double.IsFinite(X) && double.IsFinite(Y) && double.IsFinite(Z);
}

/// <summary>A rigid move, as Revit's <c>Transform</c>: a point p goes to Origin + p.X BasisX + p.Y BasisY + p.Z BasisZ.
/// Used for the one turn from Revit's internal coordinates into the shared ones (section 3 of the design note), a
/// linked model's placement, and a box's own transform.</summary>
public sealed record Transform3(Xyz Origin, Xyz BasisX, Xyz BasisY, Xyz BasisZ)
{
    public static Transform3 Identity { get; } = new(new(0, 0, 0), new(1, 0, 0), new(0, 1, 0), new(0, 0, 1));

    public static Transform3 Translation(Xyz by) => Identity with { Origin = by };

    /// <summary>Turned about the vertical axis by <paramref name="radians"/> (anticlockwise seen from above), then
    /// moved by <paramref name="by"/>: how shared coordinates sit when true north is turned.</summary>
    public static Transform3 TurnThenMove(double radians, Xyz by)
    {
        double c = Math.Cos(radians), s = Math.Sin(radians);
        return new(by, new(c, s, 0), new(-s, c, 0), new(0, 0, 1));
    }

    public Xyz Apply(Xyz p) => Origin + p.X * BasisX + p.Y * BasisY + p.Z * BasisZ;

    /// <summary>This transform after <paramref name="first"/>: p goes to this(first(p)).</summary>
    public Transform3 After(Transform3 first) =>
        new(Apply(first.Origin), Turn(first.BasisX), Turn(first.BasisY), Turn(first.BasisZ));

    private Xyz Turn(Xyz v) => v.X * BasisX + v.Y * BasisY + v.Z * BasisZ;
}

/// <summary>A 3D box, low corner then high, in the shared coordinates the description is sent in.</summary>
public readonly record struct Box3(Xyz Min, Xyz Max)
{
    public double[] ToArray() => [Min.X, Min.Y, Min.Z, Max.X, Max.Y, Max.Z];

    /// <summary>Whether the two boxes lie apart by more than <paramref name="margin"/> feet along some axis: then
    /// nothing in one can meet anything in the other (each box holds all of what it bounds). Touching, overlapping,
    /// or apart by the margin or less is not apart; a box with a coordinate that isn't a number is never apart.</summary>
    public bool ApartFrom(Box3 b, double margin) =>
        Max.X + margin < b.Min.X || b.Max.X + margin < Min.X ||
        Max.Y + margin < b.Min.Y || b.Max.Y + margin < Min.Y ||
        Max.Z + margin < b.Min.Z || b.Max.Z + margin < Min.Z;

    public Box3 Union(Box3 b) => new(new(Math.Min(Min.X, b.Min.X), Math.Min(Min.Y, b.Min.Y), Math.Min(Min.Z, b.Min.Z)),
                                     new(Math.Max(Max.X, b.Max.X), Math.Max(Max.Y, b.Max.Y), Math.Max(Max.Z, b.Max.Z)));

    /// <summary>The box's 8 corners, each turned by <paramref name="t"/>, and the box around them. A box turned by its
    /// two opposite corners alone can come out smaller than what it holds when the turn isn't a quarter turn (true
    /// north turned 30°); around all 8 it is only ever bigger (design note, section 3).</summary>
    public static Box3 Turned(Xyz min, Xyz max, Transform3 t)
    {
        var b = new BoxBuilder();
        foreach (var x in new[] { min.X, max.X })
            foreach (var y in new[] { min.Y, max.Y })
                foreach (var z in new[] { min.Z, max.Z })
                    b.Add(t.Apply(new Xyz(x, y, z)));
        return b.Box!.Value;
    }
}

/// <summary>The box around every point added; none until a point is.</summary>
public sealed class BoxBuilder
{
    public Box3? Box { get; private set; }

    public void Add(Xyz p) => Box = Box is { } b ? b.Union(new Box3(p, p)) : new Box3(p, p);

    public void Add(Box3? box)
    {
        if (box is { } x)
            Box = Box is { } b ? b.Union(x) : x;
    }
}
