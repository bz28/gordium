# The demo at e760f55 (fifth update): smoke in Rhino 8 (Mac), 2026-10-26

**Purpose:** whether the fifth demo update can go to the cofounders: each part of the smoke, pass or fail, with its evidence.\
**For:** the coordinator, Ben.\
**Kept current by:** never changed (a dated record).

Rhino 8.35 (the 8.36 update was not installed). Every run loaded Gordium from an extracted copy of e760f55
(`git archive`), one script at a time, each wait capped at 10 minutes. Results are the scripts' own JSON; the
screenshots are viewport captures (Rhino's own drawing of the view).

| Part | Script | Result |
|---|---|---|
| 1 Smoke: empty file → GordiumStart → the sample → Draw → house moved 5 ft → Check → front yard fails → Zoning report… opens on the Check sheet | `1_smoke/smoke.py` (the Rhino job's smoke, unchanged since 00c04f1) | **PASS, 7 of 7** (front yard 22'-0 7/8" against 25'-0", "does not comply"; workbook sheets Check, Inputs, Output, Rule trace, opens on Check) |
| 2 pass2, every step, incl. corner one-click (one click on one Ithaca Rd piece keeps all 8, "75'-10\""; the side street its own 2 pieces, "91'-10 3/8\""; No drops both) and claim 6 (empty file's box) | `apps/rhino_plugin/tests/pass2_in_rhino.py` | **PASS, 30 of 30** |
| 3 Notice placement (compact, clear of the model, gone when it no longer applies) | `notice_in_rhino.py` | **PASS, 5 of 5** |
| 4 The Check button (no automatic check; rows grey and "press Check" after an edit; Check brings them back; the tick) | `check_button_in_rhino.py` | **PASS, 6 of 6** |
| 5 The neighbourhood map, locks and tick | `context_in_rhino.py` | **PASS, 18 of 18** |
| 6 Re-lookup, Undo/Redo, Draw off until a typed address is looked up | `re_lookup_in_rhino.py` | **29 of 30 as shipped; 41 of 41 with a one-line test fix** (script artefact, below) |
| 7 The R-3a eave design (walls 9'-6" W / 10'-0" E, eaves 9'-0" / 6'-6" from the lines) | `7_eaves_r3a/eaves_r3a_in_rhino.py` | **PASS**: as drawn the eaves row is needs review (never a pass); with the eaves confirmed both side yards comply and "Eaves into side yard" **does not comply**, 6'-6" against 8'-0", exactly as `test_r3a_eaves_by_side.py`'s hand-worked law says |
| 8 The bend question: Enter asks again, Esc changes nothing, No, Yes | `8_bend_question/bend_question_in_rhino.py` (answers through a stand-in for GetOption) | **PASS, 5 of 5** (Enter: asked again, starting "Gordium needs a Yes or a No here (Esc: nothing changes)"; Esc: "Esc: nothing changed — the street side is as it was", street lines unchanged; No: Street 2 is 2 pieces; Yes: 4 pieces) |
| 8b The same question with Rhino's real prompt and real keys | `8_bend_question/keys_drive.py` + `keys_trial.py` | **Esc: PASS** (a real Esc at the real prompt cancels: `real_keyboard_esc.json`). **Enter, Yes, No by keyboard: left for a human** (below) |

## 6: the one re-lookup failure is the test's, not Gordium's

- Claim "4 the lot's own address (the box opened again on it): Draw goes through and checks it as it is" failed
  because the model gained objects: the Draw fetched the neighbourhood live ("Neighbourhood drawn: 209 parcels, 32
  streets, 296 buildings").
- Why: the script's `type_only` helper presses Draw without the recorded answers (`lookup_fixture`), which every
  other step uses. The earlier recorded lookup drew no neighbourhood, so Gordium (by design, `sync_context`'s
  refetch of a layer that failed) fetched it for real on this Draw. That is the context map (#23) doing its job; the
  claim was written on #26 before #23's refetch was beside it.
- Proof: the same script with `type_only` given the recorded answers (`fixture_probe.diff`, two lines) passes **41
  of 41**, Undo and Redo included (`re_lookup_fixture_probe_results.json`).
- Owner: the script `apps/rhino_plugin/tests/re_lookup_in_rhino.py` (#26 re-lookup). Not changed here.

## 8b: why the keyboard part is left for a human

Ben was using the Mac during the run (other apps kept coming to the front, and Rhino's windows were on another
desktop). Keys are sent only when Rhino is the front app, so none could land in another app. The one real Esc
reached Rhino's prompt and cancelled it. Enter (asks again), and typing Yes or No, were not sent. DEMO.md already
asks the cofounders for this keyboard check.

## Also noticed

- The smoke's close phase reported closing one document with no path; no test document was left open.
- Rhino's "Software Update" window (8.36) was up; nothing was installed.
