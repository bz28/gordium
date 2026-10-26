# PR #33 checked in Rhino at c4ad070: the suggestion list's size

**Purpose:** what `autocomplete_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, with the start box captured on screen.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Run | Result |
|---|---|
| As written | 1 of 2, then it stops at claim 2 (`{'one': None, 'eight': None}`) |
| Copy that records every claim and logs why the layout is None (`autocomplete_results.json`) | **13 of 15**; claim 6 (`same_address`) passes |

## Why claim 2 has no layout: `RectOfRow` doesn't exist (in the plugin too)

The copy logged the error: `'EtoListBoxTableView' object has no attribute 'RectOfRow'`. In Rhino 8's Mac binding,
Eto's list table has **`RectForRow`**, which takes an `IntPtr`: `RectForRow(System.IntPtr(0))`, as
`table_methods.json` lists. `RectForRow(0)` with a plain int fails ("'int' value cannot be converted to
System.IntPtr").

The plugin's own `list_row_px` calls the same `RectOfRow` inside a `try`, so on the Mac it **always falls back to
`LIST_ROW_PX` = 20**. That gives the measured heights: 22 pt for one row (20 + 2) and 162 pt for eight (8 × 20 + 2).
The second failure, "the box grows with the list" (345 → 351 pt), needs that layout too.

**The painted gap (expected about 2–5 pt) was not logged,** because `laid_out` raised before measuring it. By eye it
is larger (below).

## To an architect's eye (`list_open_sheet.png`: "106 Itha" above, "200 " below)

- **Cancel and Check are visible** with the list open, for one row and for eight.
  - With one row they sit flush with the window's bottom edge: the box grew only 6 pt for a 22 pt list, so the
    buttons lost their bottom margin.
- **The eight-row list still has an empty band,** roughly 25–30 pt under "200 Hazel St, Ithaca, NY". The list is
  about 160 pt tall, while eight rows painted about 16 pt apart need about 128 pt. It is smaller than at df08fc0
  (about 60–70 pt).
- No grid lines show in the empty space; it is the list's plain dark background.
- The one-row list fits its row.

## Left for a human (keys can't be scripted in Eto; the screen was locked)

In the address field:
1. Type "106 Itha", press Down, press Enter (picked), then Enter again (Look up).
2. Type "120 N Cay" and click a suggestion.
3. With the list open, press Esc: it should close the list and not the box.
