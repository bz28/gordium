# Rhino tools (the local Rhino job's helpers)

**Purpose:** how the Rhino job runs scripts in Ben's Rhino 8 and captures its windows, kept here so the tools
can't vanish with a scratchpad (they were deleted once, 2026-10-25).\
**For:** whoever runs RHINO_QUEUE on Ben's Mac.

| File | What it does |
|---|---|
| `rc.py` | `python rc.py script <file.py>` runs a Python script in the running Rhino 8 through Rhino's own `rhinocode` tool, and returns at once. A script may open a modal box, so the caller waits for the files the script writes. `python rc.py list` shows the running Rhino instances. |
| `rhino_windows.swift` | `swift rhino_windows.swift` lists every Rhino window, on screen or not (id, title, size). A window behind another app can still be captured by its id: `screencapture -x -o -l<id> out.png`. Use the newest id for a title. |
| `onscreen_windows.swift` | The same, on-screen windows only. |
| `locked.swift` | Whether the screen is locked. A locked screen stops scripts from running in Rhino. |

Rules for runs (RHINO_QUEUE):
- Run each head from an extracted copy (`git archive <sha> | tar -x -C <dir>`, plus a `.venv` symlink), never a
  working tree.
- One job in Rhino at a time. Close every document a script opens (in a `finally`). Never use interactive
  commands. Leave one empty document.
- If Rhino stops answering, a modal panel may be up. One Esc sent to Rhino frees it:
  `osascript -e 'tell application "Rhino 8" to activate' -e 'tell application "System Events" to key code 53'`.
