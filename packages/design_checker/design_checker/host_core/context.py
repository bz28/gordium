"""The neighbourhood drawn around a looked-up lot: when to draw it, what the file keeps of it, and how a
new fetch merges with what is drawn.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""


__all__ = ['context_command', 'context_frame', 'same_frame', 'is_stored', 'context_step', 'context_record', 'DREW',
    'context_replaces', 'LIVE_ONLY', 'NOTE_WIDTH', 'NOTE_HEIGHT_FT', 'NOTE_LINE_FT', 'note_text', 'keeps_live',
    'context_merge']


def context_command(python, frame, fixture=None):
    """The context_box command for a lookup's saved frame (the box's `lookup_frame`), or None when there is no
    looked-up lot to centre it on (the sample lot, a drawn or picked lot, a file saved before the context map)."""
    frame = frame or {}
    origin, shift = frame.get("origin_epsg2261_us_survey_ft"), frame.get("shift_ft")
    if not origin or not shift or frame.get("rotation_deg") is None:
        return None
    args = [python, "-m", "design_checker.context_box", "--origin", repr(float(origin[0])), repr(float(origin[1])),
            "--rotation", repr(float(frame["rotation_deg"])), "--shift", repr(float(shift[0])), repr(float(shift[1]))]
    if frame.get("parcel_id"):
        args += ["--parcel", str(frame["parcel_id"])]
    return args + (["--fixture", fixture] if fixture else [])


def context_frame(facts, saved_ui):
    """The lookup frame to draw the neighbourhood around, only while the lot in the model is the one that lookup drew
    (still its `replaceable_lot`): a lot the architect drew, picked or surveyed, or one a later lookup couldn't
    place (no frame), has no neighbourhood drawn around an earlier address."""
    saved_ui = saved_ui or {}
    lot = (facts or {}).get("lot_id")
    frame = saved_ui.get("lookup_frame")
    if saved_ui.get("from_sample"):      # the sample lot (review round 3: it kept an earlier lookup's frame)
        return None
    return frame if frame and lot and lot == saved_ui.get("replaceable_lot") else None


def same_frame(a, b):
    """Whether two lookup frames are the same placement (one definition for every caller: context_step,
    context_merge, and through it draw_context; review round 7)."""
    return bool(a) and bool(b) and a == b


def is_stored(layer):
    """Whether a context layer's source may be kept in the file (store raw): its objects are in the .3dm. One
    definition for writing (context_objects), keeping (context_merge) and the live footprints (keeps_live)."""
    return (layer or {}).get("store") == "raw"


def context_step(frame, drawn, on):
    """What a box's Draw does to the neighbourhood: frame = the lot's (context_frame), drawn = the frame the one in
    the file was drawn around (context_record), on = the panel's tick.
    "keep": nothing to change (the same lot, or no lot of a lookup's and nothing drawn);
    "clear": the lot isn't a lookup's any more, so the earlier neighbourhood goes;
    "draw": a lookup's lot without its neighbourhood: the earlier one goes, this one is drawn;
    "off": the same, with Show neighbourhood off: the earlier one goes, and the box says it wasn't drawn."""
    if not frame:
        return "clear" if drawn else "keep"
    if same_frame(drawn, frame):
        return "keep"
    return "draw" if on else "off"


def context_record(payload, frame):
    """What the document's strings keep of a drawn neighbourhood: its snapshot (records and the storable layers'
    counts, never a live-only source's data) and the frame it was drawn around."""
    return dict((payload or {}).get("snapshot") or {}, frame=frame)


DREW = ("found", "partial")             # a context layer whose service answered (its objects are replaced)


def context_replaces(payload):
    """The sources whose saved objects a fetch replaces: each layer whose service answered (found or partial), and
    Gordium's own marks when any did. A layer whose service failed keeps what was saved (review of PR #23: one
    service down deleted every layer's objects, and the record then said they had failed)."""
    layers = (payload or {}).get("layers") or {}
    out = set(v.get("source") for v in layers.values() if v.get("status") in DREW and v.get("source"))
    return out | ({"gordium"} if out else set())


LIVE_ONLY = "shown live, not saved in this file."   # site_lookup.adapters.ithaca_city.context's mark on a live-only layer's credit line
NOTE_WIDTH = 60                          # characters per line of the Sources note (it sits inside the square)
NOTE_HEIGHT_FT = 2.5                     # its text height (about the scale bar label's): ~95 ft wide at 60 characters
NOTE_LINE_FT = 1.7 * NOTE_HEIGHT_FT      # the most one displayed line may take, spacing included (the in-Rhino claim)


def note_text(credits):
    """The Sources note: each credit line wrapped to NOTE_WIDTH characters (Rhino job's screenshots, PR #23: one long
    line ran off the view). One helper for context_box (the first draw) and context_merge (a kept layer's line)."""
    import textwrap
    out = []
    for line in credits or []:
        out += textwrap.wrap(line, NOTE_WIDTH) or [""]
    return "\n".join(out)


def keeps_live(kept, old_record):
    """Whether a live-only layer is among the kept ones (its guides on screen stay, its credit line is carried)."""
    layers = (old_record or {}).get("layers") or {}
    return any(not is_stored(layers.get(n)) for n in kept or [])


def context_merge(payload, old_record, frame, live_on_screen=False):
    """The plan for drawing a fetch over the neighbourhood already in the file: the ONE decision the panel's message,
    the record, the objects deleted and the footprints on screen all follow (review rounds 6-7). A dict:
    payload (what to draw and say), record (what the file keeps), kept (the layers kept), replace (the sources
    whose objects go: rhino_logic.context_replaces around the same frame; None, every one, around another),
    keep_guides (the footprints on screen stay).
    Around the same frame, each layer whose service failed and that is still there is kept: a stored layer is in
    the file; a live-only one (a source that may not be kept) only when its guides are on screen for this document
    (`live_on_screen`, from guides_on_screen). A kept layer's record entries (the layer, its requests, its credit
    line, when it was fetched) are carried over and the Sources dot still lists it. Around another frame (or none
    saved) nothing is carried over: the earlier address's go."""
    record = context_record(payload, frame)
    old = old_record or {}
    plan = {"payload": payload, "record": record, "kept": [], "replace": None, "keep_guides": False}
    if not same_frame(old.get("frame"), frame):
        return plan
    plan["replace"] = context_replaces(payload)
    was = old.get("layers") or {}
    kept = [n for n, v in ((payload or {}).get("layers") or {}).items()
            if v.get("status") not in DREW and (was.get(n) or {}).get("status") in DREW
            and (is_stored(was.get(n)) or live_on_screen)]
    if not kept:
        return plan
    live_kept = keeps_live(kept, old)
    sources = set(was[n]["source"] for n in kept)
    record["layers"] = dict(record.get("layers") or {}, **{n: was[n] for n in kept})
    record["sources"] = list(record.get("sources") or []) + [r for r in old.get("sources") or []
                                                              if r.get("source") in sources]
    credits = list(record.get("credits") or [])
    credits += [c for c in old.get("credits") or [] if c not in credits and (live_kept or LIVE_ONLY not in c)]
    record["credits"] = credits
    # when each layer kept in THIS fetch was really fetched (review round 6: never a layer fetched again since)
    record["kept_from"] = {n: (old.get("kept_from") or {}).get(n) or old.get("fetched") for n in kept}
    objects = []
    for o in payload.get("objects") or []:
        if o.get("source") == "gordium" and o.get("name") == "Sources":
            o = dict(o, text=note_text(credits))
        objects.append(o)
    note = "Kept the %s drawn earlier (the service didn't answer)." % " and ".join(kept)
    counts = dict(payload.get("counts") or {}, **{n: was[n]["count"] for n in kept if "count" in was[n]})
    plan.update(kept=kept, keep_guides=live_kept,
                payload=dict(payload, objects=objects, counts=counts,
                             message=((payload.get("message") or "") + " " + note).strip()))
    return plan
