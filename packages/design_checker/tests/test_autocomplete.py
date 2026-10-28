"""Address type-ahead in the start box, and the box's words around a lookup (Ben, 2026-10-21): ", Ithaca, NY" added
when no town is typed; after a lookup that found no lot, the box says the lot shown is still the old one. The plain
decisions by behaviour; the box (the list, its keys, the timers) pinned by its source where CI can't run Rhino
(apps/rhino_plugin/tests/autocomplete_in_rhino.py proves it in Rhino)."""
import json

from design_checker import rhino_logic as logic
from design_checker.lookup_box import main, suggest_main
from rule_format.rulebook import REPO

RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
UI = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")


def part(src, start_at, end_at):
    return src[src.index(start_at):src.index(end_at, src.index(start_at) + 1)]


# ---- what is asked, and when ---------------------------------------------------------------------------------------

def test_suggestions_wait_for_four_characters_and_never_reopen_on_the_pick():
    assert not logic.wants_suggestions("106") and not logic.wants_suggestions("   106")
    assert logic.wants_suggestions("106 ") and logic.wants_suggestions("106 I")
    assert not logic.wants_suggestions("106 Ithaca Rd, Ithaca, NY", chosen="106 Ithaca Rd, Ithaca, NY")
    assert logic.wants_suggestions("106 Ithaca Rd, Ithaca, N", chosen="106 Ithaca Rd, Ithaca, NY")
    assert logic.SUGGEST_DELAY_S == 0.3 and logic.SUGGEST_MIN_CHARS == 4


def test_a_stale_answer_is_dropped_and_offline_is_said_quietly():
    ok = {"status": "ok", "query": "106 Itha", "suggestions": ["106 Ithaca Rd, Ithaca, NY"]}
    assert logic.suggestions_shown(ok, "106 Itha") == (["106 Ithaca Rd, Ithaca, NY"], "")
    assert logic.suggestions_shown(ok, "106 Ithac") is None                  # typed on since: never shown
    for status in ("offline", "error", "timeout"):
        assert logic.suggestions_shown({"status": status, "query": "106 Itha"}, "106 Itha") == \
            ([], logic.SUGGESTIONS_UNAVAILABLE)
    # none found: no list, and a quiet note that says so (UX review 2026-10-27: silence looked broken)
    assert logic.suggestions_shown({"status": "ok", "query": "999 N", "suggestions": []}, "999 N") == \
        ([], logic.NO_MATCH)
    assert "Look up" in logic.NO_MATCH and logic.NO_MATCH != logic.SUGGESTIONS_UNAVAILABLE
    assert "type the full address and press Look up" in logic.SUGGESTIONS_UNAVAILABLE


def test_up_and_down_stay_in_the_list():
    assert logic.list_step(-1, 3, "down") == 0 and logic.list_step(0, 3, "down") == 1
    assert logic.list_step(2, 3, "down") == 2 and logic.list_step(0, 3, "up") == 0
    assert logic.list_step(2, 3, "up") == 1 and logic.list_step(-1, 0, "down") == -1


def test_the_citys_name_is_added_only_when_no_town_is_typed():
    assert logic.with_city("106 Ithaca Rd") == "106 Ithaca Rd, Ithaca, NY"
    assert logic.with_city("  106   Ithaca Rd ") == "106 Ithaca Rd, Ithaca, NY"
    assert logic.with_city("106 Ithaca Rd, Ithaca, NY") == "106 Ithaca Rd, Ithaca, NY"
    assert logic.with_city("106 Ithaca Rd, Dryden") == "106 Ithaca Rd, Dryden"      # another town stays another
    # ... without a comma too (review round 1: "Dryden, Ithaca, NY" found the City's 106 Ithaca Rd)
    assert logic.with_city("106 Ithaca Rd Dryden") == "106 Ithaca Rd Dryden"
    assert logic.with_city("12 Main St Cayuga Heights") == "12 Main St Cayuga Heights"
    assert logic.with_city("120 North Cayuga Street") == "120 North Cayuga Street, Ithaca, NY"
    assert logic.with_city("102 E Court St.") == "102 E Court St., Ithaca, NY"
    assert logic.with_city("Ithaca Rd") == "Ithaca Rd"                               # no number: as typed
    assert logic.with_city("106 Ithaca Rd Ithaca NY") == "106 Ithaca Rd Ithaca NY"
    assert logic.with_city("106 Ithaca Rd 14850") == "106 Ithaca Rd 14850"
    assert logic.with_city("106 Ithaca Rd Ithaca") == "106 Ithaca Rd Ithaca"
    assert logic.with_city("") == ""
    one = logic.with_city("106 Ithaca Rd")
    assert logic.same_site_address(one, "106 Ithaca Rd")                   # still the same address to Draw


def test_after_a_lookup_that_found_no_lot_the_box_says_which_lot_is_still_shown():
    failed = {"status": "not_found", "query": "999 Nowhere St"}
    _, saved = logic.lookup_choices(failed, {}, {"drawn_address": "106 Ithaca Rd, Ithaca, NY"})
    assert saved["_lookup"]["says"].endswith("The lot shown is still 106 Ithaca Rd's: nothing in the model changed.")
    assert saved["_lookup"]["says"].startswith("No City of Ithaca address found for 999 Nowhere St")
    _, saved = logic.lookup_choices({"status": "offline", "query": "x"}, {}, {"_box_address": "96 Ithaca Rd"})
    assert saved["_lookup"]["says"].endswith("The lot shown is still 96 Ithaca Rd's: nothing in the model changed.")
    _, saved = logic.lookup_choices({"status": "timeout", "query": "x"}, {}, {})
    assert saved["_lookup"]["says"].endswith(logic.NOTHING_CHANGED)
    found = {"status": "found", "query": "96 Ithaca Rd", "facts": {}, "details": {}}
    _, saved = logic.lookup_choices(found, {}, {"drawn_address": "106 Ithaca Rd"})
    assert "still" not in (saved["_lookup"]["says"] or "")                    # found: never said


def test_the_preview_path_says_it_too():
    facts, saved, ring = logic.preview_lookup({"status": "error", "query": "1 A St"}, {"address": "1 A St"},
                                              {"drawn_address": "106 Ithaca Rd, Ithaca, NY"})
    assert ring is None and saved["_lookup"]["says"].endswith("still 106 Ithaca Rd's: nothing in the model changed.")


# ---- the type-ahead's own process (lookup_box --suggest) -----------------------------------------------------------

def test_the_type_ahead_prints_one_line_with_city_addresses(capsys):
    assert main(["--suggest", "106 Itha", "--fixture"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0]) == {"status": "ok", "query": "106 Itha", "suggestions": ["106 Ithaca Rd, Ithaca, NY"]}


def test_the_type_ahead_offline_or_failing_says_so(monkeypatch):
    import site_lookup.suggest as s
    from site_lookup.http import Offline, ServiceError

    def offline(*a, **k):
        raise Offline("no network")
    monkeypatch.setattr(s, "suggest", offline)
    assert suggest_main("106 Itha") == {"status": "offline", "query": "106 Itha"}

    def broken(*a, **k):
        raise ServiceError("HTTP 500")
    monkeypatch.setattr(s, "suggest", broken)
    got = suggest_main("106 Itha")
    assert got["status"] == "error" and got["query"] == "106 Itha"


# ---- the box and the plugin, pinned by their source ----------------------------------------------------------------

def test_the_box_asks_after_a_pause_and_stops_a_stale_request():
    box = part(UI, "def start_box(", "\ndef ")
    typed = part(box, "def address_typed(", "address.TextChanged")
    assert "wait_keys.Stop()\n            wait_keys.Start()" in typed               # restarted at every key
    # typed on: no older suggestion stays selected for Enter to pick over what is typed (review round 1)
    assert typed.index("hint_list.SelectedIndex = -1") < typed.index("wait_keys.Start()")
    # ... and the list itself goes: it was for older typing, so Down/Enter can never pick from it (review round 2)
    assert typed.index('if address.Text != hints["chosen"]:') < typed.index("hide_hints()") < \
        typed.index("wait_keys.Start()")
    keys = part(box, "def enter_looks_up(", "address.KeyDown +=")
    assert "hint_list.Visible and hint_list.SelectedIndex >= 0" in keys
    ask = part(box, "def ask_hints(", "def got_hints(")
    assert "logic.wants_suggestions(address.Text, hints[\"chosen\"])" in ask and 'suggester["start"](address.Text)' in ask
    got = part(box, "def got_hints(", "wait_keys.Elapsed")
    assert "logic.suggestions_shown(answer, address.Text)" in got and "if shown is None:" in got
    start = part(RHINO, "def _suggest_start(", "def _suggest_poll(")
    assert start.index("_suggest_stop()") < start.index("ui.spawn(")              # a stale one stopped first
    assert '"--suggest", text' in start


def test_the_list_is_kept_by_keyboard_and_mouse_and_closes_with_the_box():
    box = part(UI, "def start_box(", "\ndef ")
    keys = part(box, "def enter_looks_up(", "address.KeyDown +=")
    assert keys.index("ef.Keys.Down, ef.Keys.Up") < keys.index("ef.Keys.Escape") < keys.index("pick_hint(") \
        < keys.index('pick("lookup")')                                           # the list's keys come first
    assert "hint_list.MouseUp +=" in box and "hint_list.Activated +=" in box
    closed = part(box, "def closed(", "dialog.ShowModal(")
    assert 'suggester["stop"]()' in closed and "wait_keys.Stop()" in closed and "wait_answer.Stop()" in closed
    assert "_suggest_stop()" in part(RHINO, "def _confirm(", "GUIDE_KEEPS")
    assert "suggester = state.get(\"_suggest\") if not looking else None" in box     # none while a lookup runs


def test_look_up_asks_for_the_citys_address_when_no_town_is_typed():
    pick = part(RHINO, "def _one_pick(", "def _pick_outcome(")
    assert pick.index('facts["address"] = logic.with_city(facts["address"])') < pick.index("_lookup_start(facts")
    poll = part(RHINO, "def _suggest_poll(", "def _suggest_stop(")
    assert "logic.SUGGEST_LIMIT_S" in poll and '"timeout"' in poll


def test_the_row_pitch_is_read_from_the_table_itself():
    """Cold check of a919414 (Rhino 8's Eto.macOS.dll: ListBoxHandler is MacControl<NSTableView, ...>, so a
    ListBox's ControlObject IS the table; .DocumentView raised and the measured pitch was never used)."""
    fn = part(UI, "def list_row_px(", "def start_box(")
    assert "table = listbox.ControlObject " in fn and "DocumentView" not in fn
    assert "native_number(row_rect(table, 1).Y) - native_number(row_rect(table, 0).Y)" in fn   # (laid-out rows)
    assert "int(math.ceil(pitch - 1e-6))" in fn       # rounded up: a fractional pitch never leaves a row short
    native = part(UI, "def native_number(", "def list_row_px(")
    assert native.index("return float(value)") < native.index("return float(str(value))")   # through its text too


def test_the_list_is_as_tall_as_its_rows_and_long_lines_wrap():
    """Rhino run of a3eb1d7: one suggestion sat above five empty rows; in the no-lot state the amber line was one
    ~3,200 px line that stretched the box across the screen."""
    assert logic.list_height(1) == 22 and logic.list_height(3) == 62 and logic.list_height(20) == logic.list_height(8)
    assert logic.list_height(0) == logic.list_height(1)
    box = part(UI, "def start_box(", "\ndef ")
    got = part(box, "def got_hints(", "wait_keys.Elapsed")
    assert got.index("hint_list.Height = logic.list_height(len(items), list_row_px(hint_list))") < \
        got.index("hint_list.Visible = bool(items)")
    assert logic.list_height(2, 24) == 50                                    # at the pitch Rhino lays rows out at
    assert 'amber = label("", eto_status_color("needs_review"), size=12, width=logic.BOX_TEXT_WIDTH)' in box
    assert "reason = label(logic.box_reason(state), size=11, width=logic.BOX_TEXT_WIDTH)" in box


# ---- Rhino run of ee8f2ce ------------------------------------------------------------------------------------------

def test_the_box_grows_with_the_list_so_its_buttons_stay_on_screen():
    box = part(UI, "def start_box(", "\ndef ")
    fit = part(box, "def fit_box(", "def hide_hints(")
    assert "want = (hint_list.Height + 6) if hint_list.Visible else 0" in fit
    assert "dialog.ClientSize = ed.Size(size.Width, size.Height + delta)" in fit and "keep_on_screen(dialog)" in fit
    hide = part(box, "def hide_hints(", "def pick_hint(")
    assert hide.index("hint_list.Visible = False") < hide.index("fit_box()")
    got = part(box, "def got_hints(", "wait_keys.Elapsed")
    assert got.index("hint_list.Visible = bool(items)") < got.rindex("fit_box()")
    keep = part(UI, "def keep_on_screen(", "def list_row_px(")
    assert "window.Screen.WorkingArea" in keep and "area.Bottom - window.Height" in keep


def test_a_lookup_that_found_no_lot_is_said_once():
    """The amber line says what happened, what to do and the lot still shown; the reason line under Draw never
    repeats it ("No lot found for … (the line above says why)…")."""
    _, saved = logic.lookup_choices({"status": "not_found", "query": "12345 Nowhere Blvd"}, {},
                                    {"_box_address": "106 Ithaca Rd, Ithaca, NY"})
    state = {"address": "12345 Nowhere Blvd", "lookup": saved["_lookup"], "zone": "R-1b", "district_confirmed": True,
             "known_addresses": ["106 Ithaca Rd, Ithaca, NY"]}
    assert logic.draw_reason(state).startswith("No lot found for 12345 Nowhere Blvd")     # (the line it repeated)
    assert logic.box_reason(state) == "" and not logic.can_draw(state)                     # said once; Draw still off
    assert "check the spelling and Look up again" in logic.uncertain(state)
    typed = dict(state, address="13 Other St")                    # another address typed since: its own reason
    assert logic.box_reason(typed) == logic.LOOK_UP_FIRST.format(address="13 Other St")
    assert logic.box_reason({"zone": None}) == "Pick the district to continue."


def test_a_recorded_lookup_answers_the_start_of_its_own_address():
    from design_checker.lookup_box import _fixture_http
    http, now = _fixture_http("96_ithaca_rd")
    from site_lookup.lookup import lookup
    assert lookup("96 Ithaca Rd, Ithaca, NY", http, now)["status"] == "found"      # as Look up asks it
    assert lookup("96 Ithaca Rd, Ithaca, NY 14850", http, now)["status"] == "found"


# ---- Rhino run of df08fc0 ------------------------------------------------------------------------------------------

def test_the_list_is_sized_from_where_its_rows_are_laid_out():
    """Rows were painted ~16 pt apart while RowHeight + spacing said 24: eight rows left an empty band. The pitch is
    read from the table's own row rectangles."""
    fn = part(UI, "def list_row_px(", "def start_box(")
    assert "row_rect(table, 1).Y" in fn and "row_rect(table, 0).Y" in fn
    assert fn.index("row_rect(table, 1)") < fn.index("else:") < fn.index("row_rect(table, 0).Height")
    one_row = fn[fn.index("else:"):fn.index("return int(")]
    assert "IntercellSpacing" in one_row         # a lone row's rectangle leaves out the gap under it (AppKit; cold review)


def test_the_in_rhino_list_claim_needs_the_pixels():
    """Claim 2 of autocomplete_in_rhino.py: the table's numbers are what Gordium sizes from, so the claim also reads
    the drawn pixels; not seeing them, or an empty band painted under the text, is not a fit."""
    src = (REPO / "apps/rhino_plugin/tests/autocomplete_in_rhino.py").read_text(encoding="utf-8")
    space = {}
    exec(part(src, "PAINTED_GAP_PT =", "def screen_bottom("), space)
    fits = space["fits"]
    row = {"rows": 8, "rows_bottom": 128.0, "visible_h": 130.0, "pitch": 16.0}
    assert fits(dict(row, painted={"view_h": 132.0, "ink_bottom": 125.0}))
    assert not fits(dict(row, painted={"error": "AttributeError"}))                 # couldn't look: not a pass
    assert not fits(dict(row, painted={"view_h": 132.0, "ink_bottom": None}))
    assert not fits(dict(row, painted={"view_h": 196.0, "ink_bottom": 125.0}))      # rows drawn closer: empty band
    assert not fits(dict(row, visible_h=192.0, painted={"view_h": 194.0, "ink_bottom": 125.0}))
    one = {"rows": 1, "rows_bottom": 24.0, "visible_h": 26.0, "pitch": 24.0}       # table says 24, drawn at 16
    _one_row_cases(fits)


def test_the_in_rhino_pixel_scan_finds_the_lowest_text():
    """painted() of autocomplete_in_rhino.py on a stand-in bitmap (2x, top-left origin like NSBitmapImageRep): it
    reports the ink's bottom in points from the top, ignores the border, and fails rather than passes when it can't
    read the pixels (review round 4)."""
    import sys
    import types
    src = (REPO / "apps/rhino_plugin/tests/autocomplete_in_rhino.py").read_text(encoding="utf-8")
    class IntPtr(int):       # Python.NET refuses a plain int for a Mac nint argument (Rhino run of c4ad070)
        pass

    space = {"sys": sys, "System": types.SimpleNamespace(IntPtr=IntPtr)}
    exec(part(src, "def painted(", "PAINTED_GAP_PT ="), space)
    painted = space["painted"]

    class Color:
        def __init__(self, v):
            self.RedComponent = self.GreenComponent = self.BlueComponent = v

    class Rep:
        def __init__(self, high, ink_rows):
            self.PixelsWide, self.PixelsHigh, self.ink = 600, high, ink_rows

        def ColorAt(self, x, y):
            if not isinstance(x, IntPtr) or not isinstance(y, IntPtr):
                raise TypeError("'int' value cannot be converted to System.IntPtr in method NSColor ColorAt")
            border = x == 0 or y == 0 or x == self.PixelsWide - 1 or y == self.PixelsHigh - 1
            return Color(0.0 if border or (y in self.ink and 40 <= x <= 200) else 1.0)

    class View:
        def __init__(self, h_pt, ink_rows):
            self.Bounds = types.SimpleNamespace(Height=h_pt)
            self.rep = Rep(int(h_pt * 2), ink_rows)

        def BitmapImageRepForCachingDisplayInRect(self, bounds):
            return self.rep

        def CacheDisplay(self, bounds, rep):
            pass

    saved = sys.modules.get("gordium_ui")
    sys.modules["gordium_ui"] = types.SimpleNamespace(native_number=float)
    try:
        # one 16 pt row in a 26 pt list: text pixels 10..42 (5 to 21.5 pt from the top)
        got = painted(View(26.0, set(range(10, 43))))
        assert got == {"view_h": 26.0, "ink_bottom": 21.5}
        assert painted(View(26.0, set())) == {"view_h": 26.0, "ink_bottom": None}     # the border is not text
        broken = View(26.0, set())
        broken.CacheDisplay = None                                                     # can't render: an error
        assert "error" in painted(broken)
    finally:
        if saved is None:
            sys.modules.pop("gordium_ui", None)
        else:
            sys.modules["gordium_ui"] = saved


def _one_row_cases(fits):
    one = {"rows": 1, "rows_bottom": 24.0, "visible_h": 26.0, "pitch": 24.0}       # table says 24, drawn at 16
    assert not fits(dict(one, painted={"view_h": 28.0, "ink_bottom": 13.0}))        # half a row empty: not a fit
    assert fits(dict(one, painted={"view_h": 28.0, "ink_bottom": 21.0}))
    # as sized (24 + 2 pt), text drawn in a 16 pt row, descender at 15.3 pt: 9.7 pt empty under it (round 3)
    assert not fits(dict(one, painted={"view_h": 26.0, "ink_bottom": 16.3}))
    assert fits(dict(one, painted={"view_h": 26.0, "ink_bottom": 21.6}))                       # a fit: 4.4 pt


def test_the_found_address_reads_cleanly():
    assert logic.clean_address("96 Ithaca Road, Ithaca, NY, 14850") == "96 Ithaca Road, Ithaca, NY 14850"
    assert logic.clean_address("96 Ithaca Road, Ithaca, NY, 14850-1234") == "96 Ithaca Road, Ithaca, NY 14850-1234"
    assert logic.clean_address("96 Ithaca Rd, Ithaca, NY") == "96 Ithaca Rd, Ithaca, NY"
    found = {"status": "found", "query": "96 Ithaca Rd", "details": {},
             "facts": {"address": {"value": "96 Ithaca Road, Ithaca, NY, 14850"}}}
    facts, _ = logic.lookup_choices(found, {}, {})
    assert facts["address"] == "96 Ithaca Road, Ithaca, NY 14850"
    assert logic.same_address(facts["address"], "96 Ithaca Rd, Ithaca, NY")


# ---- Rhino run of c4ad070 ------------------------------------------------------------------------------------------

def _mac_list_row_px(rows, pitch, gap=0):
    """list_row_px run on a stand-in for Rhino 8's Mac table, which has what the Rhino run listed
    (docs/evidence/pr-33/rhino-c4ad070/table_methods.json): RowCount, and RectForRow taking an IntPtr (a plain int is
    refused, as Python.NET refuses it) -- and no RectOfRow."""
    import math
    import types

    class IntPtr(int):
        pass

    class Rect:
        def __init__(self, y, h):
            self.Y, self.Height = y, h

    class Table:
        RowCount = rows
        IntercellSpacing = Rect(0, gap)

        def RectForRow(self, index):
            if not isinstance(index, IntPtr):
                raise TypeError("'int' value cannot be converted to System.IntPtr")
            return Rect(index * pitch, pitch - gap)     # (AppKit: a row's rect leaves out the spacing under it)

    ns = {"math": math, "logic": logic, "System": types.SimpleNamespace(IntPtr=IntPtr)}
    exec(part(UI, "def native_number(", "def start_box("), ns)
    return ns["list_row_px"](types.SimpleNamespace(ControlObject=Table()))


def test_the_row_pitch_is_read_through_the_macs_own_row_rectangle():
    """Rhino's Mac table spells it RectForRow(IntPtr); the plugin called RectOfRow, always failed into the 20 px
    fallback, and the list (and the box) came out taller than the rows Rhino painted (16 pt apart)."""
    assert logic.LIST_ROW_PX == 20
    assert _mac_list_row_px(8, 16) == 16 and _mac_list_row_px(1, 16) == 16 and _mac_list_row_px(3, 17.2) == 18
    assert _mac_list_row_px(1, 18, gap=2) == 18 and _mac_list_row_px(5, 18, gap=2) == 18   # one row = many rows
    assert ".RectOfRow(" not in UI
