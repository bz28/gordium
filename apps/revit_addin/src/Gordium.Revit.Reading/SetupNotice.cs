namespace Gordium.Revit.Reading;

/// <summary>
/// The Setup form's notice (why the form is shown: "Nothing was checked: the zone chooses the rules…", CheckProject's
/// words for a check that couldn't be sent) lives only as long as the state it describes (review round 1, class A: a
/// message comes from the current state, never from an earlier one). It names the facts that were missing when it was
/// made; once what is needed has changed (a Save, a value set in Properties, an undo), its words no longer hold and it
/// goes. A choice not saved yet changes nothing the check reads, so the notice stays while the architect chooses.
/// </summary>
public static class SetupNotice
{
    /// <summary>The notice to show on <paramref name="now"/>: <paramref name="notice"/> while the facts needed are the
    /// ones it was made for (<paramref name="madeFor"/>, in any order), else none.</summary>
    public static string? Keep(string? notice, IReadOnlyCollection<string>? madeFor, SetupScreen now)
    {
        ArgumentNullException.ThrowIfNull(now);
        if (notice is not { Length: > 0 } || madeFor is null)
            return null;
        return new HashSet<string>(madeFor, StringComparer.Ordinal).SetEquals(now.Needed) ? notice : null;
    }
}
