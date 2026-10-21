# MVP UI: evidence from Rhino 8 (Mac), 2026-10-21

Each file below comes from a scripted run in Rhino that **asserts** its claims (the run fails loudly otherwise) and
closes its documents. Scripts live in `apps/rhino_plugin/tests/`.

| File | What it proves |
|---|---|
| `mvp_checks_results.json` | `mvp_checks_in_rhino.py`: 13 of 13 claims true. Flat ground: no Ground row in the start box, height and stories comply and say "assuming flat ground". Labels off by default (the document's setting and the tick); a failing yard's shortfall still labelled; the tick turns labels on and is saved in the document. No code-edition line in the panel header (the legend names it). The column is "Delta", in words. |
| `1_labels_off_failing_shortfall_only.png` | Top view, labels off, the house moved 10 ft back: only the failing rear yard's label shows ("✕ Rear yard 21'-2", needs 22'-6""). |
| `1_labels_on.png` | The same view with "Show on-screen labels" ticked: every yard and lot edge labelled. |
| `2_3_panel_delta_in_words_no_code_line.png` | The panel: no code-edition line in its header; Delta reads "−1'-4" short"; every row's text fits (540 wide, Item 230); "Show on-screen labels" on its own row. |
| `no_freeze_results.json` | `no_freeze_in_rhino.py`: 11 of 11 claims true. Two reloads that clear the plugin's state without turning it off leave one copy attached (baseline + 1 handlers); the earlier copy is inert; a checker that never answers, sent a 2 MB request, gives a clear error in 3.03 s (limit 3 s); a slow checker is still answered; the real checker answers afterwards; turning Gordium off leaves no handler attached. With the import-time sweep removed, the same run leaves 2 copies attached. Review round 1: a reload that keeps the plugin's state (live mode and the drawing on) leaves one copy attached, the old drawing off, and an edit noticed and re-checked (West yard 12'-0" → 11'-0"). |
| `highlight_results.json` | `highlight_in_rhino.py`: 15 of 15 claims true. The sample is a tax-map lot (±2'-0"); the start house has nothing red; moved 5 ft west, the west side yard is 7'-0" of 10'-0" and fails. Red is 1'-0" wide (over even if the line is 2 ft out: 7 + 2 = 9 < 10); amber is 4'-0" wide beside it (the rest of the band within 12 ft); both drawn 0.02 ft proud of the house. Expected widths worked out by hand. The architect's polish: highlights #D7263D / #F2A900, red with the heavier edge; the notice says "−3'-0" short"; no label (yards and lot edges) crosses a dimension, a lot edge or the house, covers another label, or leaves the view, and each is within 12 px of its own line; the Lot fact names its source once; the selected yard's detail says what red and amber mean; the same on a dark background (put back after). |
| `4_red_amber_top.png`, `4_red_amber_perspective.png` | Plan and 3D, light background: a thin red strip with a solid edge at the west wall, the amber band beside it, drawn over the envelope (not tinted by it); the notice in words. |
| `4_red_amber_top_dark.png`, `4_red_amber_perspective_dark.png` | The same on a dark viewport background. |
| `2_labels_on_off_every_line.png` | Plan with "Show on-screen labels" ticked: every yard label and lot-edge length beside its own line, none crossing a line or another label. |

Not yet checked: the red/amber drawing on **Windows** (the display conduit is the same code, but Windows draws through a
different graphics path; run `highlight_in_rhino.py` there before relying on it).
