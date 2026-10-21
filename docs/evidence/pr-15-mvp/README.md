# MVP UI: evidence from Rhino 8 (Mac), 2026-10-21

Each file below comes from a scripted run in Rhino that **asserts** its claims (the run fails loudly otherwise) and
closes its documents. Scripts live in `apps/rhino_plugin/tests/`.

| File | What it proves |
|---|---|
| `mvp_checks_results.json` | `mvp_checks_in_rhino.py`: 13 of 13 claims true. Flat ground: no Ground row in the start box, height and stories comply and say "assuming flat ground". Labels off by default (the document's setting and the tick); a failing yard's shortfall still labelled; the tick turns labels on and is saved in the document. No code-edition line in the panel header (the legend names it). The column is "Delta", in words. |
| `1_labels_off_failing_shortfall_only.png` | Top view, labels off, the house moved 10 ft back: only the failing rear yard's label shows ("✕ Rear yard 21'-2", needs 22'-6""). |
| `1_labels_on.png` | The same view with "Show on-screen labels" ticked: every yard and lot edge labelled. |
| `2_3_panel_delta_in_words_no_code_line.png` | The panel: no code-edition line in its header; Delta reads "−1'-4" short"; every row's text fits (540 wide, Item 230); "Show on-screen labels" on its own row. |
| `no_freeze_results.json` | `no_freeze_in_rhino.py`: 7 of 7 claims true. Two reloads that clear the plugin's state without turning it off leave one copy attached (baseline + 1 handlers); the earlier copy is inert; a checker that never answers, sent a 2 MB request, gives a clear error in 3.03 s (limit 3 s); a slow checker is still answered; the real checker answers afterwards; turning Gordium off leaves no handler attached. With the import-time sweep removed, the same run leaves 2 copies attached. |
