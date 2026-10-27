#! python3
"""Set up the Gordium commands in Rhino 8: run this once with RunPythonScript (or from the ScriptEditor).

It adds five command aliases that run the scripts in this folder:
    GordiumStart   a new project: confirm the prefilled facts, then draw the lot and the largest legal building
    GordiumCheck   check the open model, show the largest legal building, turn on live re-checking
    GordiumLive    turn live re-checking on or off
    GordiumFacts   change any lot fact, then bedrooms, parking spaces and stories
    GordiumOff     stop live mode and clear Gordium's drawing
"""
import os

import Rhino

HERE = os.path.dirname(os.path.abspath(__file__))
COMMANDS = {"GordiumStart": "gordium_start.py", "GordiumCheck": "gordium_check.py", "GordiumLive": "gordium_live.py", "GordiumFacts": "gordium_facts.py",
            "GordiumOff": "gordium_off.py"}

for alias, script in COMMANDS.items():
    macro = '! _-RunPythonScript "{}"'.format(os.path.join(HERE, script))
    aliases = Rhino.ApplicationSettings.CommandAliasList
    if aliases.IsAlias(alias):
        aliases.SetMacro(alias, macro)
    else:
        aliases.Add(alias, macro)
    Rhino.RhinoApp.WriteLine("Gordium: " + alias + " -> " + script)
