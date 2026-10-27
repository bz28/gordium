# Real-input undo check, 2026-10-27 (Lane C; Rhino 8 Mac frontmost, Ben away)

**How:** real mouse clicks on the Gordium panel and start box (System Events `click at`), a real Cmd+Z (System Events keystroke), the manual edit typed at Rhino's command line (`_Line`, two points). State read after every step by a separate read-only rhinocode script (`read.py`, `read2.py`: no document change, no undo record). Setup (open a document, `gordium_check`, point the lookup at its recorded 96 Ithaca Rd answer) is scripted once before the clicks. Rhino was frontmost throughout (checked).

| Case | Head | Result |
|---|---|---|
| (a) one panel action then one Cmd+Z | check-button 540f718 | PASS. Typed a line (curves 1 to 2). Clicked Hide starting house: Gordium::Massing hidden. One Cmd+Z: Massing visible again, the typed line still there (curves 2), the panel says "Model changed since the last check - press Check" (a3_after_undo.png; command line says "Undoing Gordium: hide or show the starting house"). |
| (b) two panel actions then Cmd+Z | check-button 540f718 | PASS. Clicked Show on-screen labels (labels on), then Check after every edit (on). One Cmd+Z: Check after every edit back off, labels still on, line still there (b3). A second Cmd+Z: labels off, line still there (b4). |
| (c) re-lookup claim 2 | re-lookup 5711450 | PASS. Sample (106 Ithaca Rd) in an empty file; Edit site..., typed 96 Ithaca Rd, Ithaca, NY 14850, Look up (recorded answer, dashed preview, model unchanged), ticked This is the lot's district, Draw (96's lot drawn, the sample gone). One Cmd+Z: object ids exactly the sample's, address back to 106 Ithaca Rd (c4_after_cmdz). A second Cmd+Z then took back the earlier sample draw, one step at a time. |

**Found, not fixed (panel tick out of step after Undo):** after Cmd+Z of Hide starting house the layer is shown again but the Hide starting house tick stays ticked (a3_after_undo.png), until the next Check. Clicking it then unticks it, which runs "show" on a layer already shown (an empty undo step). Owner: the panel (#27/#15, to confirm).

Also: earlier scripted `undo_steps` / `re_lookup` claim 2 failures are the harness merging a script's records (see wip/start-box-lookup-rhino-8e9fc22); real input shows the product undoes one panel action per Cmd+Z in these cases. Covered here: massing, labels, auto_check, the re-lookup Draw. Not covered with real input: survey, enter, main, add, ground, not_ground, context.
