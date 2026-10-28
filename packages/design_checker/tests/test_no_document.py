"""GordiumStart and GordiumCheck with no Rhino document open (every file closed: Rhino.RhinoDoc.ActiveDoc is None).
They used to crash on the first use of the document; now they say what to do and stop, touching nothing. The
plugin's own functions run as written (their source from gordium_rhino.py), with Rhino stood in."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from design_checker import rhino_logic as logic

SRC = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")


# every command and panel button that reads the front document, with the arguments the panel gives it
COMMANDS = {"gordium_start": (), "gordium_check": (), "edit_facts": (), "toggle_live": (), "run_check": (None,),
            "set_envelope": (True,), "toggle_envelope": (), "zoom_to": ({"name": "x"},), "pick_survey": (),
            "enter_rooms": ({"keys": ["bedrooms"]},), "pick_main_building": (), "add_to_check": (["id"],),
            "this_is_the_ground": (["id"],), "not_the_ground": (), "hide_massing": (True,)}


def _world():
    said = []
    rhino = SimpleNamespace(
        RhinoDoc=SimpleNamespace(ActiveDoc=None),
        RhinoApp=SimpleNamespace(WriteLine=said.append))

    def touched(*args, **kwargs):
        raise AssertionError("the plugin touched the model or the checker with no document open")

    ns = {"Rhino": rhino, "logic": logic, "_recover": touched, "_buildings": touched, "_lot_candidates": touched,
          "ask": touched, "STATE": {}, "ui": MagicMock()}
    exec(SRC[SRC.index("def say("):].split("\ndef ", 1)[0], ns)                               # noqa: S102
    for name in COMMANDS:
        exec(SRC[SRC.index("def %s(" % name):].split("\ndef ", 1)[0], ns)                      # noqa: S102
    return ns, said


@pytest.mark.parametrize("command", list(COMMANDS))
def test_with_no_document_open_the_command_says_what_to_do_instead_of_crashing(command):
    ns, said = _world()
    ns[command](*COMMANDS[command])
    assert said and set(said) == {"Gordium: " + logic.NO_DOCUMENT}      # the message every other no-document path gives
    assert ns["STATE"]["said"][0] == logic.NO_DOCUMENT                  # and kept for the in-Rhino tests, as say() does


@pytest.mark.parametrize("command", ["gordium_start", "gordium_check"])
def test_the_two_main_commands_return_nothing(command):
    ns, _ = _world()
    assert ns[command]() is None
