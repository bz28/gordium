namespace Gordium.Revit.Reading;

/// <summary>
/// The model's element boxes, listed once per read in Revit's own order, so a small box's neighbours are found
/// without Revit going through every element of the model again (Snowdon Towers: each railing's, stair run's and
/// room's look round cost 15 ms, nearly all of it Revit passing over the model's ~43,000 elements, read_steps
/// 2026-11-22). It only narrows what Revit's own box filter is then run on, never decides: <see cref="Candidates"/>
/// keeps every element whose box, grown by the pad, meets the box asked about, and every element with no box at all,
/// so what Revit's filter passes is among them; and <see cref="InOrder"/> puts what it passes back in the order the
/// model gave them. Revit-free; one read at a time.
/// </summary>
public sealed class BoxIndex
{
    private readonly long[] keys;
    private readonly Box3?[] boxes;
    private readonly Dictionary<long, int> place;

    /// <summary>The elements' keys (Revit's element ids) in the model's order, each with its box (null for none).</summary>
    public BoxIndex(IReadOnlyList<(long Key, Box3? Box)> elements)
    {
        keys = new long[elements.Count];
        boxes = new Box3?[elements.Count];
        place = new Dictionary<long, int>(elements.Count);
        for (var i = 0; i < elements.Count; i++)
        {
            keys[i] = elements[i].Key;
            boxes[i] = elements[i].Box;
            place.TryAdd(elements[i].Key, i);
        }
    }

    public int Count => keys.Length;

    /// <summary>Every element whose box, grown by <paramref name="pad"/> feet on every side, meets
    /// <paramref name="box"/> (touching counts), and every element with no box or a box that isn't all numbers, in the
    /// model's order. Null when there are more than <paramref name="most"/> of them (then Revit's own pass over the
    /// model is as quick).</summary>
    public List<long>? Candidates(Box3 box, double pad, int most)
    {
        var found = new List<long>();
        for (var i = 0; i < keys.Length; i++)
        {
            if (boxes[i] is { } b && b.IsFinite && b.ApartFrom(box, pad))
                continue;
            found.Add(keys[i]);
            if (found.Count > most)
                return null;
        }
        return found;
    }

    /// <summary><paramref name="items"/> in the model's order (as Revit's pass over the model gives them), by each
    /// one's key; an item whose key isn't in the index throws (it can't be placed, so the list is never guessed).</summary>
    public List<T> InOrder<T>(IEnumerable<T> items, Func<T, long> key) =>
        items.Select(x => (Item: x, At: place.TryGetValue(key(x), out var at) ? at : throw new KeyNotFoundException($"element {key(x)} isn't in the index")))
            .OrderBy(x => x.At).Select(x => x.Item).ToList();
}
