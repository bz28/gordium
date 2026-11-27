using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>The worker's answer for one object sent to <c>objects.left_out</c>.</summary>
/// <param name="Id">The object's id, as sent.</param>
/// <param name="LeftOut">Left out of the check (on the lot, or with no box to tell).</param>
/// <param name="Touching">May be part of the house; null when it has no box (it counts as touching).</param>
public readonly record struct LeftOutDecision(string Id, bool LeftOut, bool? Touching);

/// <summary>Who decides which objects are left out and which touch the house: the worker's session command
/// <c>objects.left_out</c> (host_core/left_out.py), the one copy of those rules every host uses. The reader never
/// decides them itself.</summary>
public interface ILeftOutAsker
{
    /// <summary>One decision per object, in the order sent. What each argument holds: host_core/left_out.py.</summary>
    Task<IReadOnlyList<LeftOutDecision>> AskAsync(JsonObject? lot, JsonArray objects, JsonArray buildings,
                                                  JsonObject definitions, CancellationToken cancel);
}

/// <summary><see cref="ILeftOutAsker"/> over a running worker (<see cref="WorkerClient.LeftOutAsync"/>). Revit's
/// internal unit is the foot, so <c>feet_per_unit</c> is always 1.</summary>
public sealed class WorkerLeftOut(WorkerClient worker) : ILeftOutAsker
{
    public async Task<IReadOnlyList<LeftOutDecision>> AskAsync(JsonObject? lot, JsonArray objects, JsonArray buildings,
                                                               JsonObject definitions, CancellationToken cancel)
    {
        var answer = await worker.LeftOutAsync(lot, objects, buildings, definitions, 1.0, cancel).ConfigureAwait(false);
        return Read(objects, answer.Get("left_out"), answer.Get("touching"));   // a refused part throws: never "none"
    }

    /// <summary>The two answers read strictly: one entry per object sent, each with that object's id in the same
    /// place, <c>left_out</c> true or false, <c>touching</c> true, false or null. Anything else is an error, never
    /// read as "nothing left out" or "not touching": the checker's answer can't be trusted (WorkerProtocolException, so
    /// the pane says so, never that Revit's read failed: UI polish PR 5 review round 6).</summary>
    internal static IReadOnlyList<LeftOutDecision> Read(JsonArray objects, JsonElement leftOut, JsonElement touching)
    {
        if (leftOut.ValueKind != JsonValueKind.Array || touching.ValueKind != JsonValueKind.Array
            || leftOut.GetArrayLength() != objects.Count || touching.GetArrayLength() != objects.Count)
            throw new WorkerProtocolException(
                $"objects.left_out answered for a different number of objects than the {objects.Count} sent");
        var out_ = new List<LeftOutDecision>(objects.Count);
        for (var i = 0; i < objects.Count; i++)
        {
            var id = objects[i]!["id"]!.GetValue<string>();
            JsonElement a = leftOut[i], t = touching[i];
            if (a.ValueKind != JsonValueKind.Object || t.ValueKind != JsonValueKind.Object
                || !a.TryGetProperty("id", out var aid) || aid.ValueKind != JsonValueKind.String || aid.GetString() != id
                || !t.TryGetProperty("id", out var tid) || tid.ValueKind != JsonValueKind.String || tid.GetString() != id)
                throw new WorkerProtocolException($"objects.left_out's answer {i + 1} isn't for {id}");
            if (!a.TryGetProperty("left_out", out var lo) || lo.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw new WorkerProtocolException($"objects.left_out gave no left_out (true or false) for {id}");
            if (!t.TryGetProperty("touching", out var to) || to.ValueKind is not (JsonValueKind.True or JsonValueKind.False or JsonValueKind.Null))
                throw new WorkerProtocolException($"objects.left_out gave no touching (true, false or null) for {id}");
            out_.Add(new LeftOutDecision(id, lo.GetBoolean(), to.ValueKind == JsonValueKind.Null ? null : to.GetBoolean()));
        }
        return out_;
    }
}
