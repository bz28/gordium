namespace Gordium.Worker;

/// <summary>What this client speaks, from docs/protocol/worker_protocol_v1.md and site_description_v1.md.</summary>
public static class Protocol
{
    /// <summary>The protocol version every request names (<c>"protocol": "1.3"</c>). A 1.0 or 1.1 worker answers it
    /// too, all but what it doesn't have: <c>objects.left_out</c> (1.1, an unknown command to a 1.0 worker: refused)
    /// and <c>check_site</c>'s <c>interior</c> (1.2), which the client sends only to a worker that says 1.2 or later
    /// (an older one would ignore it: <see cref="WorkerClient.CheckSiteAsync"/>). A site slab (a left-out object's
    /// <c>slab</c>, 1.3) needs no such gate: an older worker refuses a site field it doesn't know, never drops it.</summary>
    public const string Version = "1.3";

    /// <summary>The minor version from which <c>check_site</c> reads an <c>interior</c>.</summary>
    public const int InteriorMinor = 2;

    /// <summary>The major version this client understands; a worker reporting any other is refused.</summary>
    public const int Major = 1;

    /// <summary>The site description version (<c>gordium.site/1</c>) the worker must read.</summary>
    public const string SiteSchema = "gordium.site/1";

    /// <summary>A request's own fields (protocol.py, ENVELOPE): never a command's. <c>progress</c> is for the older
    /// <c>check</c> and <c>start</c> only, which this client doesn't send.</summary>
    internal static readonly string[] Envelope = ["id", "cmd", "protocol", "progress", "want"];

    /// <summary>The older commands, answered without <c>about</c>: this client doesn't send them (Rhino does).</summary>
    internal static readonly string[] Legacy = ["check", "start", "facts", "options", "sample_site"];

    /// <summary>The model commands (worker_protocol_v1.md, hello and the model commands).</summary>
    public static readonly IReadOnlyList<string> ModelCommands = ["hello", "read_model", "check_site", "start_site"];

    /// <summary>
    /// The session commands and, for each, its parts: each part's answer names, in the order the protocol's command
    /// reference lists them (worker_protocol_v1.md, the "Answer" column). A part that refuses gives its words under
    /// <c>result.refused</c>, keyed by its first answer name. A test keeps this equal to the document.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyList<string>>> SessionCommands =
        new Dictionary<string, IReadOnlyList<IReadOnlyList<string>>>
        {
            ["facts.validate"] = [["value"], ["problem"], ["feet"]],
            ["facts.missing"] = [["missing"], ["unsettled"]],
            ["facts.suggest"] = [["suggested"], ["facts"], ["no_guess"]],
            ["facts.drop_stale"] = [["facts"]],
            ["facts.sources"] = [["sources"], ["kept"], ["row_sources"], ["typed_sources"]],
            ["facts.row"] = [["fields"], ["facts"], ["problem"]],
            ["box.view"] = [["rows"], ["can_draw"], ["draw_reason"], ["box_reason"]],
            ["box.pick"] = [["facts", "saved_ui"], ["lot_facts"], ["ticks"]],
            ["lookup.choices"] = [["facts", "saved_ui", "guide", "plan"]],
            ["lookup.preview"] = [["facts", "saved_ui", "ring"]],
            ["lookup.reset"] = [["facts", "saved_ui", "redraw_house", "guide", "plan"]],
            ["streets.pick"] = [["lines", "ids", "said", "unasked"], ["click_refused"], ["runs", "run_said", "run_unasked"]],
            ["streets.lines"] = [["lines", "ids"], ["after_picks"], ["names"]],
            ["streets.verdict"] = [["verdict", "swing"]],
            ["streets.words"] = [["words"], ["prompt"], ["so_far"]],
            ["session.freshness"] = [["recheck"], ["stale"], ["changed"], ["still"]],
            ["session.undo"] = [["words"], ["recheck"], ["dirty_at"]],
            ["report.message"] = [["message"], ["outdated"], ["cancelled"]],
            ["panel.rows"] = [["header"], ["status"], ["name"], ["cell_name", "proposed"], ["highlight"], ["detail"], ["cell"]],
            ["objects.left_out"] = [["left_out"], ["touching"], ["no_box"]],
        };
}
