#! python3
"""Set up the Gordium commands in Rhino 8: run this once with RunPythonScript (or from the ScriptEditor).

It adds six command aliases that run the scripts in this folder:
    GordiumStart   a new project: confirm the prefilled facts, then draw the lot and the largest legal building
    GordiumCheck   check the open model, show the largest legal building, turn on live re-checking
    GordiumLive    turn live re-checking on or off
    GordiumFacts   change any lot fact, then bedrooms, parking spaces and stories
    GordiumOff     stop live mode and clear Gordium's drawing
    GordiumPanel   register the Gordium panel only (for Rhino's startup commands: a restored tab is never empty)
"""
import os

import Rhino

HERE = os.path.dirname(os.path.abspath(__file__))
COMMANDS = {"GordiumStart": "gordium_start.py", "GordiumCheck": "gordium_check.py", "GordiumLive": "gordium_live.py", "GordiumFacts": "gordium_facts.py",
            "GordiumOff": "gordium_off.py", "GordiumPanel": "gordium_panel.py"}

for alias, script in COMMANDS.items():
    macro = '! _-RunPythonScript "{}"'.format(os.path.join(HERE, script))
    aliases = Rhino.ApplicationSettings.CommandAliasList
    if aliases.IsAlias(alias):
        aliases.SetMacro(alias, macro)
    else:
        aliases.Add(alias, macro)
    Rhino.RhinoApp.WriteLine("Gordium: " + alias + " -> " + script)
# Rhino has no setting a script can change for the commands it runs at startup: say the one step to do by hand
Rhino.RhinoApp.WriteLine("Gordium: one more step, once: add GordiumPanel to Rhino's startup commands "
                         "(Mac: Rhino > Settings > General; Windows: Tools > Options > General: "
                         "\"Run these commands every time Rhino starts\").")
