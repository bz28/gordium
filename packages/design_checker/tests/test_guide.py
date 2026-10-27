"""The user guide (apps/rhino_plugin/GUIDE.md) says what the code shows an architect: every button, tick box,
start-box row, command and command-line prompt in the code is in the guide, and every name the guide gives is in
the code, so a screen change without a guide change fails here."""
import re

from rule_format.rulebook import REPO

PLUGIN = REPO / "apps/rhino_plugin"
GUIDE = " ".join((PLUGIN / "GUIDE.md").read_text(encoding="utf-8").split())      # (line breaks are not part of a name)
UI = (PLUGIN / "gordium_ui.py").read_text(encoding="utf-8")
RHINO = (PLUGIN / "gordium_rhino.py").read_text(encoding="utf-8")
LOGIC = (REPO / "packages/design_checker/design_checker/rhino_logic.py").read_text(encoding="utf-8")
CODE = UI + RHINO + LOGIC


def _bold(text):
    return set(re.findall(r"\*\*([^*]+)\*\*", text))


def test_every_button_and_tick_box_in_the_ui_is_in_the_guide():
    names = set(re.findall(r'button\("([^"]+)"', UI)) | set(re.findall(r'\.Text = "([^"]+)"', UI))
    names |= set(re.findall(r'\(\w+, "([^"]+…?)", (?:True|not state)', LOGIC))          # the start box's row actions
    names |= {"Draw", "Check", "Cancel"}
    names = {n.strip() for n in names} - {"Gordium", ""}
    assert all('"%s"' % n in UI for n in ("Draw", "Check", "Cancel"))
    names |= {t for t in re.findall(r'"tick": \("([^"]+)"', LOGIC)} | set(re.findall(r'\("\w+", "([^"]+…)"\)', LOGIC))
    names |= {"Advanced", "Design buffer"}
    bold = _bold(GUIDE)
    missing = sorted(n for n in names if n not in bold)       # as a bold name: a word elsewhere in the prose is not it
    assert not missing, "buttons/tick boxes in the code but not shown in bold in GUIDE.md: %s" % missing


def test_the_start_box_rows_options_and_tick_are_in_the_guide():
    for label in ("Address", "Zoning district", "Use", "Lot", "Front lot line (on the street)", "Corner lot?"):
        assert "**%s**" % label in GUIDE and label in LOGIC, label
    for choice in ("Not answered", "No: one street", "Yes: two streets"):
        assert choice in GUIDE and choice in LOGIC, choice
    zone_tick = re.search(r'^ZONE_TICK = "([^"]+)"', LOGIC, re.M).group(1)
    assert zone_tick in GUIDE


def test_every_name_the_guide_gives_is_still_in_the_code():
    gone = sorted(n for n in _bold(GUIDE)
                  if n.rstrip(":").replace("…", "") not in CODE and n not in
                  {"Complies", "Does not comply", "Needs review", "Not checked", "Yes", "No", "starting house",
                   "buildable envelope", "start box", "Purpose:", "For:", "Kept current by:", "Corner lot?",
                   "Cancel", "Check", "Draw", "Zoom to", "red", "amber"})
    assert not gone, "named in GUIDE.md but not in the code: %s" % gone


def test_the_commands_are_the_command_files_and_all_in_the_guide():
    commands = {p.read_text(encoding="utf-8").splitlines()[1].strip('"# ').split(":")[0] for p in PLUGIN.glob("gordium_*.py")}
    commands = {c for c in commands if re.fullmatch(r"Gordium\w+", c)}
    assert {"GordiumStart", "GordiumCheck", "GordiumLive", "GordiumFacts", "GordiumOff", "GordiumPanel"} <= commands
    assert all("`%s`" % c in GUIDE for c in commands), sorted(c for c in commands if "`%s`" % c not in GUIDE)
    assert set(re.findall(r"`(Gordium[A-Z]\w+)`", GUIDE)) <= commands


def test_the_command_line_prompts_in_the_guide_are_the_codes():
    prompts = re.findall(r"- `([^`]+)`", GUIDE.split("## What Gordium asks you")[1].split("## What \"Needs")[0])
    assert len(prompts) >= 4
    for p in prompts:
        assert p.split(" (")[0] in CODE, p
    assert "(Enter when done)" in GUIDE and "(Enter when done)" in RHINO
    assert "(Enter keeps the blue one)" in GUIDE and "(Enter keeps the blue one)" in RHINO


def test_every_fixed_command_line_prompt_in_the_code_is_in_the_guide():
    """The other way: a prompt added to (or reworded in) the code and not in the guide fails here."""
    calls = r'(?:_pick\(doc, |_yes_no\(|_place_spots\(doc, |SetCommandPrompt\(|GetNumber\(|RhinoGet\.GetPoint\()'
    code = re.findall(calls + r'"([^"]+)"', RHINO)
    code += [v[0] for v in re.findall(r'\("([^"]+)", "(?:count|yes_no)"', LOGIC) if v]
    assert len(code) >= 10
    missing = sorted({c.split(" (Enter to skip)")[0] for c in code if c.split(" (Enter")[0] not in GUIDE and c not in GUIDE})
    assert not missing, "command-line prompts in the code but not in GUIDE.md: %s" % missing
