# Gordium in Rhino: pictures

**Purpose:** a few current screenshots and one short animation of Gordium in Rhino, for people who can't run it.\
**For:** architects, shareholders, anyone new.\
**Kept current by:** the engineer who changes what the Rhino screens look like, in that same PR (replace the picture, keep the set small).

All pictures are the sample project, 106 Ithaca Rd (zone R-1b, one-family house), captured in Rhino 8 on 2026-10-20.

| Picture | What it shows |
|---|---|
| [gordium_demo.gif](gordium_demo.gif) | The whole flow in under a minute: the start box, the largest legal starting house, then a series of edits (stretch the rear wall, raise the roof, widen the house, add a shed, place spot grades), each re-checked live and then undone |
| [1_start_box.png](1_start_box.png) | The start box on an empty file, prefilled with the sample project |
| [2_starting_house.png](2_starting_house.png) | After Draw: the lot, the buildable envelope (blue, see-through) and the largest legal starting house. Status: 2 need review · 8 comply · 2 not checked |
| [3_edit_does_not_comply.png](3_edit_does_not_comply.png) | The house widened 4 ft into the side yard: red only on the part that is over, and a notice naming the 2 items that no longer comply (lot coverage, east side yard) |
| [4_panel.png](4_panel.png) | The panel: every item, bad news first, with proposed, required and margin |
| [5_zoning_report_button.png](5_zoning_report_button.png) | The panel after pressing **Zoning report…**: it writes the report in the architects' spreadsheet format, opens it and says where it was saved |
| [6_address_lookup.png](6_address_lookup.png) | The start box after **Look up** on 106 Ithaca Rd: each fact shown with its source; the zone stays a suggestion until the architect ticks **I confirm**. Being added in the start-box address lookup PR (#19); not in this branch yet |

The step-by-step instructions that produce these screens are in [the quickstart](../../apps/rhino_plugin/QUICKSTART.md).
