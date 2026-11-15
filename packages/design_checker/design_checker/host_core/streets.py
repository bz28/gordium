"""Which edges of the lot face a street: picking them, naming them, and the one-street-or-two verdict.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""


__all__ = ['STREET_WORDS', 'address_street', 'street_name', 'street_name_after_pick', 'STREET_LABEL', 'STREET_HELP',
    'ZONE_TICK', 'street_pick_prompt', 'street_lines_after_picks', 'pick_street', 'street_lines_after_pick',
    'PIECE_TURN_DEG', 'SHORT_PIECE_FT', 'JOINT', 'is_tiny', '_same_piece', '_in_ring_order', '_piece_at',
    'generated_id', '_real_names', 'outline_names', 'street_run', 'feet_words', '_length', '_end_to_end',
    'street_words', 'STREET_ANSWER_NEEDED', 'ESC_STREET', 'so_far', 'street_more_question', 'refused_click',
    'street_pick', 'add_street_pick', 'street_lines_of', '_STREETS', '_street_lines', 'street_verdict']


STREET_WORDS = {"road": "rd", "street": "st", "avenue": "ave", "place": "pl", "drive": "dr", "lane": "ln",
                "court": "ct", "boulevard": "blvd", "terrace": "ter", "circle": "cir", "parkway": "pkwy",
                "highway": "hwy", "north": "n", "south": "s", "east": "e", "west": "w"}


def address_street(address, street):
    """The street of `address` in the address's own words ("Ithaca Road" from "106 Ithaca Road, Ithaca, NY"), when
    it is `street` (a looked-up street name: "ITHACA RD"); else None. Compared word by word with the usual
    abbreviations (Road = Rd), never by a part of a name."""
    first = str(address or "").split(",", 1)[0].split()
    while first and any(ch.isdigit() for ch in first[0]):        # the house number (106, 106A, 106-108)
        first = first[1:]

    def words(text):
        return [STREET_WORDS.get(w, w) for w in str(text or "").lower().replace(".", " ").split()]

    return " ".join(first) if first and words(" ".join(first)) == words(street) else None


def street_name(state):
    """The street the highlighted lot line is on, by name, only when that line's street is known (a lookup's
    street, or the sample's); else the line itself, so the architect checks which line it is (the street line
    sets the front, side and rear yards: never named from the address alone)."""
    return state.get("street_name") or "the highlighted line"


def street_name_after_pick(name, lines, picked, tolerance=0.5, ids=None):
    """The street's name to keep when the architect picks the street side again (`picked`: the lot line clicked,
    [[x, y], [x, y]] in feet): when the lines carry their own street names (`ids` matching them one for one,
    street_lines.matching_ids), the clicked line's own name (None if it has none: asked); else `name`, the street's
    name as found, if the line is one of that street's own `lines` (within `tolerance` ft at each end, either way
    round); else None, and the architect is asked (a name is never carried to a line it wasn't found on: a B Ave
    line never saved as A St, arch-fixes-2 review round 9)."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    own = _real_names(_street_lines().matching_ids(lines, ids))   # (Gordium's own "Street N": no name, asked: F2)
    for k, (c, d) in enumerate(lines or []):
        if (near(a, c) and near(b, d)) or (near(a, d) and near(b, c)):
            return own[k] if own is not None else (name or None)
    return None


STREET_LABEL = "Front lot line (on the street)"      # the box's row, in an architect's words (Ben, 2026-10-21)
STREET_HELP = "the highlighted blue line is the lot line on the street; Gordium measures the front yard from it"
ZONE_TICK = "This is the lot's district"


def street_pick_prompt(corner, picked):
    """What the command line asks while the architect picks the street side: on a corner lot, every lot line on a
    street, one click each, Enter when done (as Edit site lets it); otherwise the one line."""
    if corner:
        return ("Click each lot line on a street (" + str(picked) + " picked); Enter when done")
    return "Click the lot line on the street"


def street_lines_after_picks(lines, picks, corner):
    """The street lines after the architect's clicks: on a corner lot every line clicked, once each, in order (the
    yards wait for the front to be settled whatever they are: §325-19C); otherwise as street_lines_after_pick. No
    clicks (Esc, or Enter at once): the lines as they were."""
    if not picks:
        return lines
    if not corner:
        return street_lines_after_pick(lines, picks[0])
    out = []
    for p in picks:
        if not any(street_lines_after_pick([q], p) == [list(map(list, q))] for q in out):
            out.append(p)
    return out


def pick_street(old_lines, old_ids, picked, name, tolerance=0.5, outline=None, ask=None, said=None):
    """(street lines, their street names) after the architect clicks a lot line as the street side (`picked`) and
    names its street (`name`, found or typed; None: unnamed). THE one order of steps (arch-fixes-2 review rounds
    9-11, where a name given for one line kept landing on other lines and two streets, or "one street or two?",
    became one): the name goes on the clicked line ONLY; every other line keeps the street it was known to be on,
    or none; then the street lines follow from those names (street_lines_after_pick: the clicked line's own street
    when the lines are known to be two streets, else every line). A line nobody named stays unnamed, so the
    measuring still reads it from the drawing (a corner: one street or two?, needs review). A line not among them:
    the whole street it is on along the lot `outline` (street_pick: never round a corner; an unclear end asked with
    `ask`), else that line alone. `said` (a list): gets {"words", "refused"}, what the command line says and
    whether the click was refused (a point clicked: the street lines and their name stay as they were)."""
    if said is None:
        said = []

    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    lines = [list(map(list, line)) for line in old_lines or []]
    at = _piece_at(outline, picked, tolerance) if outline else None
    if at is not None:
        # on the lot outline: every street line is one of its pieces. The saved lines are snapped to the pieces
        # they are (a lot nudged under 0.5 ft: the piece, never the stale line beside it; round 10), each with
        # the street it was known to be on; the clicked piece takes the name given, and no other. The saved
        # pieces around the click, of its own street or none, are kept as they are (never asked again, never
        # shrunk on a guess: round 10), and the street grows on from them.
        n = len(outline)
        own_ids = _real_names(_street_lines().matching_ids(lines, old_ids))   # (Gordium's own ids: no name)
        names, saved = [None] * n, set()
        for k, line in enumerate(lines):
            q = _piece_at(outline, line, tolerance)
            if q is not None:
                saved.add(q)
                names[q] = names[q] or (own_ids[k] if own_ids is not None else None)
        mine = name or names[at]
        if name:
            names[at] = name                               # the name on the clicked line only
        label = mine or "Street 1"                         # (the id its unnamed lines get: one street)
        refused = refused_click(outline, picked, tolerance)
        if refused:                                        # a point clicked, not a line: nothing changes
            said.append({"words": refused, "refused": True})
            return lines, (list(old_ids) if own_ids is not None else None)

        def with_me(q):
            return names[q] is None or (mine is not None and _street_lines().same_street(names[q], mine))

        seed = [at]
        if at in saved:
            while (seed[0] - 1) % n in saved and (seed[0] - 1) % n not in seed and with_me((seed[0] - 1) % n):
                seed.insert(0, (seed[0] - 1) % n)
            while (seed[-1] + 1) % n in saved and (seed[-1] + 1) % n not in seed and with_me((seed[-1] + 1) % n):
                seed.append((seed[-1] + 1) % n)
        got = street_pick(outline, picked, names, (), ask, label, tolerance, seed=seed)
        if got is None:                 # an outline that doesn't run end to end: the saved street, else that line
            hits = [k for k, line in enumerate(lines)
                    if (near(a, line[0]) and near(b, line[-1])) or (near(a, line[-1]) and near(b, line[0]))]
            if hits:                    # never fewer on a guess (round 11): the saved street as it was
                ids = list(own_ids or [None] * len(lines))
                if name:
                    ids[hits[0]] = name
                kept = street_lines_after_pick(lines, picked, tolerance, ids=ids)
                out = [ids[next(k for k, line in enumerate(lines) if line == q)] for q in kept]
                if street_verdict(*_end_to_end(kept, out))[0] == "one":     # (one id only for one street)
                    fill = next((i for i in out if i), None) or label           # (its known name first: D2)
                    out = [i or fill for i in out]
                why = "the lot outline doesn't run end to end in order here, so Gordium can't follow the street along it"
                said.append({"words": (f"{label}: the street lines kept as they were ({why})" if kept == lines else
                                       f"{street_words(label, kept, out)} ({why})"), "refused": False})   # (round 12)
                return kept, out
            said.append({"words": f"{label}: only the lot line clicked (the lot outline doesn't run end to end in "
                                  f"order here, so Gordium can't follow the street along it)", "refused": False})
            return [list(map(list, picked))], [label]
        said.append({"words": got[1], "refused": False})
        return street_lines_of(outline, [got[0]], names, labels=[label])
    # no outline (or a line not on it): the street lines themselves
    hits = [k for k, line in enumerate(lines)
            if (near(a, line[0]) and near(b, line[-1])) or (near(a, line[-1]) and near(b, line[0]))]
    if not hits:                                           # a line not among them: that line alone
        return [list(map(list, picked))], ([name] if name else None)
    ids = list(_street_lines().matching_ids(lines, old_ids) or [None] * len(lines))
    if name:
        ids[hits[0]] = name
    kept = street_lines_after_pick(lines, picked, tolerance, ids=ids)
    out = [ids[next(k for k, line in enumerate(lines) if line == q)] for q in kept]
    return kept, (out if any(out) else None)


def street_lines_after_pick(lines, picked, tolerance=0.5, ids=None):
    """The street lines after the architect clicks a lot line as the street side: the whole street as it was when
    the line is one of its own (106's eight: keeping only the one clicked measured the front yard from part of the
    street, a false pass: review round 3, F4); only that street's lines when the lines are known to be on two
    streets (`ids`); never fewer on a guess from the drawing (a street that bends, or lines nobody named: the
    measuring asks about them; review round 6, P1); a line not among them: that line."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    hits = [k for k, (c, d) in enumerate(lines or []) if (near(a, c) and near(b, d)) or (near(a, d) and near(b, c))]
    if not hits:
        return [picked]
    ids = _street_lines().matching_ids(lines, ids)        # names that don't match the lines: unnamed (round 8)
    if street_verdict(lines, ids)[0] == "two" and ids[hits[0]]:   # two streets, the clicked line's known: its own
        mine = ids[hits[0]]                                # its own lines, by street_verdict's own comparison
        return [list(map(list, line)) for k, line in enumerate(lines) if _street_lines().same_street(ids[k], mine)]
    return [list(map(list, line)) for line in lines]


# A joint between two lot-line pieces that turns no more than this is the same street's wobble: a tax-map outline
# draws a straight street in short pieces (106 Ithaca Rd: 8 pieces of about 10 ft, joints turning up to 7.5°). A
# joint turning more than street_lines.TURN_LIMIT_DEG is a corner (the measuring's own limit for one street or
# two); in between, or a run of small joints that swings past that limit in all, is unclear, and the architect is
# asked (demo 00c04f1: one click on one of the 8 pieces kept that 9.8 ft piece as the whole street).
PIECE_TURN_DEG = 15.0
SHORT_PIECE_FT = 0.5   # a piece shorter than this (6 in) has no direction of its own (is_tiny)
JOINT = 0.01      # ft: two pieces of one outline meet where they share an end (a click is matched within `tolerance`:
                  # 106's 0.24 ft piece has both ends within 0.5 ft of its neighbours' ends)


def is_tiny(line):
    """A lot-line piece shorter than SHORT_PIECE_FT (6 in): a corner point drawn twice, a slip of the
    pen or float noise, with no direction of its own: never a street of its own (it would be 0'-0" of frontage,
    the front yard read from a point), never a corner or a bend (street-run review rounds 3 to 5); passed through
    inside a street."""
    import math
    return math.dist(line[0][:2], line[-1][:2]) < SHORT_PIECE_FT


def _same_piece(line, picked, tolerance):
    (a, b), (c, d) = (line[0], line[-1]), (picked[0], picked[-1])
    near = lambda p, q: abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance   # noqa: E731
    return (near(a, c) and near(b, d)) or (near(a, d) and near(b, c))


def _in_ring_order(outline):
    """Whether the outline's pieces run end to end in order round the lot (as the measuring needs)."""
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    lines = [[list(x[0][:2]), list(x[-1][:2])] for x in outline or []]
    if len(lines) < 3:
        return False
    a, b = lines[0]
    if not (near(b, lines[1][0]) or near(b, lines[1][1])):
        a, b = b, a
    first, end = a, b
    for x, y in lines[1:]:
        if near(y, end) and not near(x, end):
            x, y = y, x
        elif not near(x, end):
            return False
        end = y
    return near(end, first)


def _piece_at(outline, picked, tolerance):
    """The outline piece a click names: the one it is exactly (within JOINT), else the first within `tolerance`
    (a short piece beside another short one is never mistaken for it)."""
    for tol in (JOINT, tolerance):
        k = next((k for k, line in enumerate(outline or []) if _same_piece(line, picked, tol)), None)
        if k is not None:
            return k
    return None


def generated_id(name):
    """Whether a street id is Gordium's own ("Street 1", "Street 2"... given to a run nobody named), not a name:
    never read back as a street's identity (a new pick numbers its streets afresh: round ids, F4)."""
    return _street_lines().generated_id(name)            # (street_lines: the measuring's own comparison)


def _real_names(ids):
    return [None if generated_id(i) else i for i in ids] if isinstance(ids, list) else ids


def outline_names(outline, lines, ids, tolerance=0.5):
    """The street each piece of the lot outline is known to be on (one per piece, None where unknown): a piece that
    is one of the street lines `lines` takes that line's own name (`ids`, only when they match the lines one for one:
    street_lines.matching_ids); every other piece None."""
    own = _real_names(_street_lines().matching_ids(lines or [], ids))      # (Gordium's own ids: no name)
    out = []
    for piece in outline or []:
        k = next((k for k, line in enumerate(lines or []) if _same_piece(line, piece, tolerance)), None)
        out.append(own[k] if own is not None and k is not None else None)
    return out


def street_run(outline, picked, names=None, taken=(), tolerance=0.5, seed=None):
    """Where the street of the lot line the architect clicked (`picked`, [[x, y], [x, y]] in feet) runs along the lot
    outline (`outline`: its pieces in order round the lot, each [[x, y], [x, y]], as Rhino gives a closed curve's
    segments and as the measuring requires): the clicked piece and its neighbours, both ways round, for as long as
    they are surely on the same street.

    The outline is read as strokes: each long piece (SHORT_PIECE_FT or longer) is one; consecutive short pieces
    are grouped into strokes whose ends are at least SHORT_PIECE_FT apart (an arc drawn as short chords keeps its
    shape); short pieces left over between two strokes (a corner point drawn twice, a slip, a spike) have no
    direction and stand in the gap between them. Going on from the last stroke kept to the next one:
    - the next one is another click's street (`taken`): a sure stop (the gap before it is asked);
    - both are named (`names`, one per piece, None where unknown): the same street joins, however it bends;
      another street is a sure stop for it (the gap before it is asked);
    - else a joint between two long pieces with nothing between them turning more than TURN_LIMIT_DEG is a sure
      stop (a corner: never round onto the other street). Nothing else is ever a sure stop: no short piece
      decides one (street-run review round 7);
    - it joins when the joint turns PIECE_TURN_DEG or less, the run then swings no more than TURN_LIMIT_DEG in all
      and the gap is under SHORT_PIECE_FT;
    - anything else is unclear: the gap and the next stroke (and on over strokes in line with no gap, while that
      stretch swings no more than TURN_LIMIT_DEG) are returned apart, never added on a guess, so the architect
      is asked.
    `seed`: a run already kept (its pieces in order round the lot), grown on from its ends.

    {"pieces": the run's piece numbers in order round the lot, "maybe": [before, after] (the unclear pieces past
    each end, nearest first; [] where the end is sure), "turn": [the swing of each unclear stretch from the run's
    end, in degrees, or None when it is short pieces only]}; None when `picked` isn't a piece of the outline, is
    already taken, is a short piece standing alone (a point, not a line), or the outline doesn't run end to end
    in order (the measuring refuses such a lot)."""
    import math
    sl = _street_lines()
    pieces = [[list(line[0][:2]), list(line[-1][:2])] for line in outline or [] if len(line) >= 2]
    n = len(pieces)
    hit = _piece_at(pieces, picked, tolerance)
    taken = set(taken)
    if hit is None or hit in taken or n < 3:
        return None
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    # each piece turned to run round the lot (its end the next one's start): the order Rhino and the measuring use
    start, vec = [None] * n, [None] * n
    a, b = pieces[0]
    if not (near(b, pieces[1][0]) or near(b, pieces[1][1])):
        a, b = b, a
    end = b
    start[0], vec[0] = a, (b[0] - a[0], b[1] - a[1])
    for i in range(1, n):
        a, b = pieces[i]
        if near(b, end) and not near(a, end):
            a, b = b, a
        elif not near(a, end):
            return None                                    # not end to end in order: nothing extended
        start[i], vec[i], end = a, (b[0] - a[0], b[1] - a[1]), b
    if not near(end, start[0]):
        return None
    length = [math.hypot(*v) for v in vec]
    tiny = [x < SHORT_PIECE_FT for x in length]
    names = list(names) if isinstance(names, list) and len(names) == n else [None] * n

    # the strokes, in order round the lot from a long piece; each {"pieces", "dir", "long"}; gap[m]: the short
    # pieces between stroke m and stroke m + 1
    first = next((i for i in range(n) if not tiny[i]), 0)
    strokes, gap, group = [], [], []

    def close_group(final):
        nonlocal group
        while group:
            g0 = start[group[0]]
            cut = None
            for c in range(len(group)):
                e = group[c]
                tip = (start[e][0] + vec[e][0], start[e][1] + vec[e][1])
                if math.hypot(tip[0] - g0[0], tip[1] - g0[1]) >= SHORT_PIECE_FT:
                    cut = c
                    break
            if cut is None:
                if final:
                    gap[-1] += group if strokes else []
                    if not strokes:
                        strokes.append({"pieces": list(group), "dir": None, "long": False})
                        gap.append([])
                group = []
                return
            part, group = group[:cut + 1], group[cut + 1:]
            e = part[-1]
            tip = (start[e][0] + vec[e][0], start[e][1] + vec[e][1])
            strokes.append({"pieces": part, "dir": (tip[0] - g0[0], tip[1] - g0[1]), "long": False})
            gap.append([])

    for step_ in range(n):
        i = (first + step_) % n
        if tiny[i]:
            group.append(i)
            continue
        close_group(True)
        strokes.append({"pieces": [i], "dir": vec[i], "long": True})
        gap.append([])
    close_group(True)
    m_of = {}
    for m, s_ in enumerate(strokes):
        for q in s_["pieces"]:
            m_of[q] = m
    if hit not in m_of:                                    # a short piece standing alone: a point, not a line
        return None
    S = len(strokes)

    def name_of(m):
        got = {names[q] for q in strokes[m]["pieces"]}
        return got.pop() if len(got) == 1 else None

    def turn(u, v):                                        # signed, degrees, from direction u to direction v
        return math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))

    def swing(ms):                                         # the spread of the running heading over strokes
        dirs = [strokes[m]["dir"] for m in ms if strokes[m]["dir"] is not None]
        run_, low, high = 0.0, 0.0, 0.0
        for u, v in zip(dirs, dirs[1:]):
            run_ += turn(u, v)
            low, high = min(low, run_), max(high, run_)
        return high - low

    def between(m, d):                                     # the gap from stroke m to its neighbour going d
        return list(gap[m]) if d > 0 else list(reversed(gap[(m - 1) % S]))

    def pieces_of(ms):
        return [q for m in ms for q in strokes[m]["pieces"]]

    hm = m_of[hit]
    own = name_of(hm) or names[hit]
    run = [hm]
    if seed and hit in seed and not set(seed) & taken:     # the strokes the seed holds, grown out from the hit's
        held = {m_of[q] for q in seed if q in m_of}
        while (run[0] - 1) % S in held and (run[0] - 1) % S not in run:
            run.insert(0, (run[0] - 1) % S)
        while (run[-1] + 1) % S in held and (run[-1] + 1) % S not in run:
            run.append((run[-1] + 1) % S)
    held_gaps = set(seed or ()) - set(pieces_of(run))       # gap pieces a Yes already kept past the ends
    maybe, swings = [[], []], [None, None]
    for side, d in ((0, -1), (1, 1)):
        while True:
            last = run[0] if side == 0 else run[-1]
            g = [q for q in between(last, d) if q not in held_gaps]
            j = (last + d) % S
            if j in run:                                   # the lot comes round
                maybe[side] = g
                break
            jp = strokes[j]["pieces"]
            if set(jp) & taken or set(g) & taken:          # another click's street: sure; the gap is asked
                maybe[side] = [q for q in g if q not in taken] if not set(g) & taken else []
                break
            nj = name_of(j)
            order = [j] + run if side == 0 else run + [j]
            if own and nj:                                 # both named: the street's identity decides
                if sl.same_street(own, nj) and not g:
                    run[:] = order
                    continue
                if not sl.same_street(own, nj):
                    maybe[side] = g                        # another street: sure for it, the gap asked
                    break
            u, v = strokes[last]["dir"], strokes[j]["dir"]
            t = abs(turn(u, v)) if u is not None and v is not None else 180.0
            if not g and strokes[last]["long"] and strokes[j]["long"] and t > sl.TURN_LIMIT_DEG:
                break                                      # a corner, long piece to long piece
            g_len = sum(length[q] for q in g)
            # (onto a long piece only from a long one, or with one in the run already: a click on a rounded
            # corner's chord never takes the side line unasked, round 8)
            sure_dir = strokes[j]["long"] is False or strokes[last]["long"] or any(strokes[m]["long"] for m in run)
            if t <= PIECE_TURN_DEG and swing(order) <= sl.TURN_LIMIT_DEG and g_len < SHORT_PIECE_FT and sure_dir:
                run[:] = order
                if g:                                       # (the gap joins with it)
                    held_gaps.update(g)
                continue
            more_m, k = [j], j
            while True:                                    # on over strokes in line with no gap
                g2 = between(k, d)
                nxt = (k + d) % S
                if (g2 or nxt in run or nxt in more_m or set(strokes[nxt]["pieces"]) & taken
                        or t > PIECE_TURN_DEG or strokes[k]["dir"] is None or strokes[nxt]["dir"] is None
                        or abs(turn(strokes[k]["dir"], strokes[nxt]["dir"])) > PIECE_TURN_DEG
                        or (name_of(nxt) and not (own and sl.same_street(own, name_of(nxt))))
                        or swing([last] + more_m + [nxt]) > sl.TURN_LIMIT_DEG):
                    break
                more_m.append(nxt)
                k = nxt
            stretch = g + [q for m in more_m for q in (strokes[m]["pieces"] if d > 0 else
                                                       list(reversed(strokes[m]["pieces"])))]
            maybe[side] = stretch
            swings[side] = swing([last] + more_m)
            break
    flat = []
    for idx, m in enumerate(run):
        flat += strokes[m]["pieces"]
        if idx < len(run) - 1:
            flat += gap[m]
    before = [q for q in reversed(gap[(run[0] - 1) % S]) if q in held_gaps][::-1] if S > 1 else []
    after = [q for q in gap[run[-1]] if q in held_gaps] if S > 1 else []
    pieces_out = before + flat + after
    seen = set()
    pieces_out = [q for q in pieces_out if not (q in seen or seen.add(q))]
    return {"pieces": pieces_out, "maybe": maybe, "turn": swings}


def feet_words(feet):
    """A length for the command line, rounded DOWN to the nearest 1/8 in (never in the architect's favour):
    75.83 -> 75'-9 7/8"."""
    import math
    eighths = int(math.floor(feet * 96 + 1e-6))
    ft, rest = divmod(eighths, 96)
    inch, frac = divmod(rest, 8)
    if frac:
        g = math.gcd(frac, 8)
        return f"{ft}'-{inch} {frac // g}/{8 // g}\""
    return f"{ft}'-{inch}\""


def _length(lines):
    import math
    return sum(math.dist(line[0][:2], line[-1][:2]) for line in lines)


def _end_to_end(lines, ids=None):
    """(lines, ids) in order end to end along the street, as the measuring reads them (measure.Lot puts the street
    lines in outline order before its street_verdict): a click on a street line appends the rest of its street
    after the old lines (street-run review round 2). Lines that don't run end to end: as they were."""
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    n = len(lines)
    ids = list(ids) if isinstance(ids, list) and len(ids) == n else None
    ends = [(line[0], line[-1]) for line in lines]

    def touches(k, p):
        return [j for j in range(n) if j != k and (near(ends[j][0], p) or near(ends[j][1], p))]

    starts = [k for k in range(n) if not touches(k, ends[k][0]) or not touches(k, ends[k][1])]
    if not starts:
        return lines, ids
    order, k = [starts[0]], starts[0]
    at = ends[k][1] if not touches(k, ends[k][0]) else ends[k][0]
    while len(order) < n:
        nxt = [j for j in touches(k, at) if j not in order]
        if len(nxt) != 1:
            return lines, ids
        k = nxt[0]
        at = ends[k][1] if near(ends[k][0], at) else ends[k][0]
        order.append(k)
    return [lines[k] for k in order], ([ids[k] for k in order] if ids is not None else None)


def street_words(label, lines, ids=False):
    """What the command line says a click kept: "Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage". With `ids`
    given (the lines' street names, or None: unnamed), lines that aren't surely one street (street_verdict) say so
    instead of one frontage: the measuring asks one street or two."""
    n = len(lines)
    pieces = f"{label}: {n} lot-line piece{'s' if n != 1 else ''}"
    if ids is not False and n > 1 and street_verdict(*_end_to_end(lines, ids))[0] != "one":
        return pieces + ", not surely one street: Gordium asks one street or two before measuring along them"
    return pieces + f", {feet_words(_length(lines))} of frontage"


STREET_ANSWER_NEEDED = ("Gordium needs a Yes or a No here (Esc: nothing changes): kept as street, a "
                        "line that isn't can pass lot width; left out, a line that is can pass the front yard. ")


ESC_STREET = "Esc: nothing changed — the street side is as it was; this pick wasn't kept"


def so_far(words):
    """A corner lot's street click, said while the picking goes on: kept only when Enter ends it, so "so far"
    ("Ithaca Rd: 8 lot-line pieces, 75'-10" so far — Enter when done"), never read as kept before an Esc."""
    if words.endswith(" of frontage"):
        return words[:-len(" of frontage")] + " so far — Enter when done"
    return words + " (so far — Enter when done)"


def street_more_question(label, outline, more, swing):
    """The question when it isn't clear where a street ends (street_run's "maybe" pieces past one end)."""
    lines = [outline[k] for k in more]
    n = len(lines)
    count = f"{n} more lot-line piece{'s' if n != 1 else ''}, {feet_words(_length(lines))}"
    tail = f" Is that on {label} too? (Yes or No)"
    if swing is None:                                  # short pieces only (no direction to give)
        return f"Past there is a short piece of lot line ({count}), with no direction of its own.{tail}"
    if swing > _street_lines().TURN_LIMIT_DEG:         # a corner, but with short pieces in it, or a bend
        return f"Past there the lot line turns {round(swing)}° over short pieces, a corner or a bend ({count}).{tail}"
    return f"Past there the lot line bends {round(swing)}° with no clear corner ({count}).{tail}"


def refused_click(outline, picked, tolerance=0.5):
    """What the command line says when a click can't start a street (a short piece standing alone: a point, not a
    line), or None: asked before anything else (the street's name), so nothing is asked of a refused click
    (street-run review round 9)."""
    hit = _piece_at(outline, picked, tolerance)
    if hit is not None and is_tiny(outline[hit]) and _in_ring_order(outline) \
            and street_run(outline, outline[hit], None, (), 0.0) is None:
        return "that piece is under 6 in long (a corner point drawn twice?), not a street line: click the lot line beside it"
    return None


def street_pick(outline, picked, names=None, taken=(), ask=None, label="This street", tolerance=0.5, seed=None):
    """One click on the street side, the whole street it is on: (piece numbers in order along it, what to say);
    street_run's run, with each unclear stretch past an end asked (`ask`: question -> True Yes, False No, None not
    answered) and left out only on a No. The plugin's question takes only Yes or No (round 14: neither default is
    safe, see gordium_rhino._ask_street_more); None (no one to ask: tests, headless runs) keeps it and says so.
    ([], words) when the click is on a street already kept (`taken`) or on a short piece standing alone (a point,
    not a line); None when it isn't a piece of the outline, or the outline doesn't run end to end in order."""
    found = street_run(outline, picked, names, taken, tolerance, seed=seed)
    if found is None:
        hit = _piece_at(outline, picked, tolerance)
        if hit is not None and hit in set(taken):
            return [], "that lot line is on a street already kept"
        if hit is not None and refused_click(outline, outline[hit], 0.0):
            return [], refused_click(outline, outline[hit], 0.0)
        return None
    run, closed, skipped = list(found["pieces"]), set(), False
    while True:            # each unclear stretch asked in turn; a Yes grows the street on from there, a No ends it
        grew = False
        for side in (0, 1):
            more = found["maybe"][side]
            if not more or side in closed:
                continue
            said = ask(street_more_question(label, outline, more, found["turn"][side])) if ask is not None else None
            if said is False:                              # the architect's No: the street ends there
                closed.add(side)
            else:
                run, grew = (list(reversed(more)) + run if side == 0 else run + more), True
                skipped = skipped or said is not True
        if not grew:
            break
        found = street_run(outline, picked, names, taken, tolerance, seed=run)
        run = list(found["pieces"])
    # what it says checks the street as the measuring will (a Yes past a bend: not surely one street)
    known = list(names) if isinstance(names, list) and len(names) == len(outline) else [None] * len(outline)
    words = street_words(label, [outline[k] for k in run], [known[k] for k in run])
    return run, words + ("; a bend not answered is kept as street (answer No to leave it out)" if skipped else "")


def add_street_pick(runs, outline, picked, names=None, ask=None, tolerance=0.5):
    """A corner lot's street side, one click at a time: (`runs` with the clicked street's run added, what to say).
    Each click keeps the whole street it is on (street_pick), never one already kept; the street is called by its
    known name, else "Street 1", "Street 2"... in click order."""
    hit = _piece_at(outline, picked, tolerance)
    own = names[hit] if hit is not None and isinstance(names, list) and len(names) == len(outline) else None
    label = own or f"Street {len(runs) + 1}"
    got = street_pick(outline, picked, names, {k for run in runs for k in run}, ask, label, tolerance)
    if got is None:
        if hit is None:
            return runs, "that isn't one of the lot's lines"
        return runs + [[hit]], (f"{label}: only the lot line clicked (the lot outline doesn't run end to end in "
                                f"order here, so Gordium can't follow the street along it: click each street line)")
    run, words = got
    return (runs + [run] if run else runs), words


def street_lines_of(outline, runs, names=None, clicks=None, labels=None):
    """(street lines, their street ids, one per line) from the runs kept (piece numbers), in click order, each piece
    once (the measuring reads a corner lot's streets from the ids, never from the drawing: #18): a piece's own name
    where it is known (`names`; Gordium's own "Street N" ids are no name), else its run's: the run's known name,
    else `labels[i]`, else "Street 1", "Street 2"... by the run's place in the click order (as the command line
    calls it), but only where the run is surely one street (street_verdict): else its unnamed lines stay unnamed,
    and the measuring asks, never one frontage along two streets. No run (no click was a piece of the outline): the lines
    clicked, each its own street; every click refused: nothing ([], None)."""
    if not any(runs) and clicks:
        if all(_piece_at(outline, c, JOINT) is None for c in clicks):   # none is a piece of the outline
            lines = street_lines_after_picks(None, clicks, True)
            return lines, [f"Street {i + 1}" for i in range(len(lines))]
        return [], None          # every click refused (a point, a street already kept): nothing changes (round 8)
    names = list(names) if isinstance(names, list) and len(names) == len(outline or []) else [None] * len(outline or [])
    seen, lines, ids = set(), [], []
    for i, run in enumerate(runs):
        mine = [k for k in run if k not in seen]
        # a run gets one id only where it is surely one street (street_verdict over its lines and known names,
        # the measuring's own test): else its unnamed lines stay unnamed and the measuring asks (round ids: a
        # Yes round a rounded corner, a name across a corner, never one id for two streets)
        sure = street_verdict(*_end_to_end([outline[k] for k in mine], [names[k] for k in mine]))[0] == "one" \
            if mine else False
        known = next((names[k] for k in mine if names[k]), None)
        base = known or (labels[i] if labels and i < len(labels) and labels[i] else f"Street {i + 1}")
        for k in mine:
            seen.add(k)
            lines.append([list(outline[k][0][:2]), list(outline[k][-1][:2])])
            ids.append(names[k] or (base if sure else None))
    return lines, (ids if lines else None)


_STREETS = {}


def _street_lines():
    """model_measurement/street_lines.py, the one decision of one street or two (the measuring's too), loaded by
    its path: inside Rhino only this folder is on the path."""
    if "m" not in _STREETS:
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "model_measurement",
                            "model_measurement", "street_lines.py")
        spec = importlib.util.spec_from_file_location("gordium_street_lines", os.path.normpath(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _STREETS["m"] = module
    return _STREETS["m"]


def street_verdict(lines, ids=None):
    """("one" | "two" | "unsure", total swing): street_lines.street_verdict, the measuring's own."""
    return _street_lines().street_verdict(lines, ids)
