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
    assert logic.suggestions_shown({"status": "ok", "query": "999 N", "suggestions": []}, "999 N") == ([], "")
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
