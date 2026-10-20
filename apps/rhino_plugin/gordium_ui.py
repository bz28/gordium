#! python3
"""What the architect sees: the Gordium panel, the start box, and the drawing in the viewport
(docs/design/rhino_ui_spec.md). Rhino 8's Python (3.9), Eto and display drawing only; every number and word comes
from the checker's `view` (design_checker/present.py), so nothing here decides a result.

No class here extends an Eto or Rhino class: Rhino keeps the first .NET class made for a Python class for the
whole session (gordium_rhino.Overlay explains), so the panel and the dialog are plain Eto objects built by
functions, and an update to this file takes effect at once."""

import System
import Eto.Drawing as ed
import Eto.Forms as ef
import Rhino
import Rhino.Geometry as rg

import rhino_logic as logic  # plain Python, tested in CI (on the path: gordium_rhino puts it there first)

PANEL_WIDTH = 360          # wide enough that Proposed, Required and Margin never truncate (D4)
COLUMNS = [("", 22), ("Item", 150), ("Proposed", 70), ("Req. ≥/≤", 64), ("Margin", 62)]
STALE_SECONDS = 0.3        # results older than an edit by this long are shown as out of date (F7, H1)


# ---- colors: Rhino's own for chrome; red and amber only for status, keyed to the background (J2, F8) -----------

def _dark(color):
    return 0.299 * color.R + 0.587 * color.G + 0.114 * color.B < 128


def viewport_dark():
    return _dark(Rhino.ApplicationSettings.AppearanceSettings.ViewportBackgroundColor)


def status_color(status, dark, drawing=True):
    """Red for does not comply, amber for needs review, else the plain ink (complies is never colored)."""
    if status == "does_not_comply":
        return System.Drawing.Color.FromArgb(240, 122, 112) if dark else System.Drawing.Color.FromArgb(184, 55, 31)
    if status == "needs_review":
        return System.Drawing.Color.FromArgb(233, 180, 76) if dark else System.Drawing.Color.FromArgb(138, 88, 0)
    return System.Drawing.Color.FromArgb(225, 228, 230) if dark else System.Drawing.Color.FromArgb(36, 40, 44)


def eto_status_color(status):
    dark = _dark_panel()
    c = status_color(status, dark)
    return ed.Color.FromArgb(c.R, c.G, c.B)


def _dark_panel():
    try:
        return ef.SystemColors.ControlBackground.Brightness < 0.5
    except Exception:
        return False


def backing(dark):
    """The box behind a drawn label, so it reads on any viewport background (F3)."""
    return System.Drawing.Color.FromArgb(225, 30, 33, 36) if dark else System.Drawing.Color.FromArgb(230, 255, 255, 255)


# ---- small Eto helpers ---------------------------------------------------------------------------------------

def label(text, color=None, bold=False, size=None, wrap=True):
    lab = ef.Label()
    lab.Text = text or ""
    lab.Wrap = ef.WrapMode.Word if wrap else getattr(ef.WrapMode, "None")
    if color is not None:
        lab.TextColor = color
    if bold or size:
        lab.Font = ed.Font(ed.SystemFont.Bold if bold else ed.SystemFont.Default, size or 13)
    return lab


def button(text, action, enabled=True):
    b = ef.Button()
    b.Text = text
    b.Enabled = enabled
    if action is not None:
        b.Click += lambda s, e: action()
    return b


def row(*controls):
    s = ef.StackLayout()
    s.Orientation = ef.Orientation.Horizontal
    s.Spacing = 6
    s.VerticalContentAlignment = ef.VerticalAlignment.Center
    for c in controls:
        s.Items.Add(ef.StackLayoutItem(c))
    return s


# ---- the panel (D1–D10) ------------------------------------------------------------------------------------

def make_panel(actions):
    """The Gordium panel: a header, the item list (a TreeGridView), a splitter, the selected item's detail, and a
    footer. `actions` maps names to functions (zoom, report, envelope, edit_site, survey, grade, enter, add,
    retry). Returns a dict of its parts; `show(panel, …)` fills it."""
    form = ef.Form()
    form.Title = "Gordium · Zoning"
    form.ClientSize = ed.Size(PANEL_WIDTH, 720)
    form.MinimumSize = ed.Size(PANEL_WIDTH, 420)
    form.Resizable = True
    form.Topmost = True
    tree = ef.TreeGridView()
    tree.ShowHeader = True
    tree.AllowMultipleSelection = False
    for i, (title, width) in enumerate(COLUMNS):
        col = ef.GridColumn()
        col.HeaderText = title
        col.DataCell = ef.TextBoxCell(i)
        col.Editable = False
        col.Sortable = False
        col.Width = width
        col.AutoSize = i == 1               # only Item gives way (D4); the values keep their width
        tree.Columns.Add(col)
    parts = {"form": form, "tree": tree, "actions": actions, "by_id": {}, "expanded": {}, "selected": None,
             "header": ef.DynamicLayout(), "detail": ef.DynamicLayout(), "view": None}

    def formatting(sender, e):
        item = e.Item
        tag = item.Tag if item is not None else None
        if isinstance(tag, str) and tag.startswith("group:"):
            e.Font = ed.Font(ed.SystemFont.Bold, 12)
            return
        found = parts["by_id"].get(tag)
        if found is not None and not parts.get("stale") and found["status"] in ("does_not_comply", "needs_review"):
            if e.Column.DisplayIndex in (0, 2, 4) or (e.Column.DisplayIndex == 1):
                e.ForegroundColor = eto_status_color(found["status"])

    tree.CellFormatting += formatting

    def selected(sender, e):
        item = tree.SelectedItem
        tag = item.Tag if item is not None else None
        if isinstance(tag, str) and tag.startswith("group:"):
            return                           # section headers aren't selectable (D5)
        parts["selected"] = tag
        show_detail(parts)

    tree.SelectedItemChanged += selected
    tree.CellDoubleClick += lambda s, e: actions["zoom"](parts["by_id"].get(parts["selected"]))
    split = ef.Splitter()
    split.Orientation = ef.Orientation.Vertical
    split.Panel1 = tree
    detail_scroll = ef.Scrollable()
    detail_scroll.Content = parts["detail"]
    split.Panel2 = detail_scroll
    split.Position = 380
    footer = row(_envelope_box(actions), button("?", actions["legend"]),
                 button("Zoom to", lambda: actions["zoom"](parts["by_id"].get(parts["selected"]))),
                 button("Zoning report…", actions["report"]))
    parts["zoom_button"] = footer.Items[2].Control
    layout = ef.DynamicLayout()
    layout.Padding = ed.Padding(10)
    layout.Spacing = ed.Size(6, 6)
    layout.Add(parts["header"])
    layout.Add(split, yscale=True)
    layout.Add(footer)
    form.Content = layout
    return parts


def _envelope_box(actions):
    box = ef.CheckBox()
    box.Text = "Show buildable envelope"
    box.Checked = True
    box.CheckedChanged += lambda s, e: actions["envelope"](bool(box.Checked))
    return box


def show(parts, view, stale=False, error=None, checking=False):
    """Fill the panel from the checker's view. Stale (the model changed and the check hasn't run again yet) or a
    check that couldn't run: rows keep their names but show no mark and "—", Zoom to is off (H1, H2, H5). The
    selection, which groups are open and the scroll position are kept by item id across refreshes (D8)."""
    tree = parts["tree"]
    parts["stale"] = stale or error is not None or checking
    if view is not None:
        parts["view"] = view
    view = parts["view"]
    _header(parts, view, error, checking or stale)
    if view is None:
        tree.DataStore = ef.TreeGridItemCollection()
        parts["by_id"], parts["groups"] = {}, []
        show_detail(parts)
        return
    for g in parts.get("groups") or []:      # which groups were open, kept by group (D8)
        parts["expanded"][g.Tag] = g.Expanded
    by_id = {i["id"]: i for i in view["items"]}
    parts["by_id"] = by_id
    store = ef.TreeGridItemCollection()
    selected_item = None
    parts["groups"] = []
    for g in view["groups"]:
        gi = ef.TreeGridItem()
        gi.Tag = "group:" + g["key"]
        title = ("Site · " if g["key"] == "complies" and all(by_id[i]["group"] == "site" for i in g["items"]) else "")
        gi.Values = System.Array[System.Object](["", title + g["title"] + " · " + str(len(g["items"])), "", "", ""])
        gi.Expanded = parts["expanded"].get(gi.Tag, g["key"] not in ("complies", "not_covered"))
        for item_id in g["items"]:
            i = by_id[item_id]
            stale_row = parts["stale"] and i["status"] != "not_checked"
            values = ["" if stale_row else i["mark"], i["name"] + ("" if i["group"] != "site" else " (site)"),
                      "—" if stale_row else (i["proposed"] if i["status"] != "not_checked" else "needs input"
                                             if i["id"].startswith("R-") else ""),
                      "" if stale_row else i["required"], "" if stale_row else i["margin"]]
            ci = ef.TreeGridItem()
            ci.Tag = item_id
            ci.Values = System.Array[System.Object](values)
            gi.Children.Add(ci)
            if item_id == parts["selected"]:
                selected_item = ci
        store.Add(gi)
        parts["groups"].append(gi)
    tree.DataStore = store
    if selected_item is not None:
        tree.SelectedItem = selected_item
    parts["zoom_button"].Enabled = parts["selected"] in by_id and not parts["stale"]
    show_detail(parts)


def _header(parts, view, error, out_of_date):
    h = parts["header"]
    h.Clear()
    a = parts["actions"]
    head = (view or {}).get("header") or {}
    h.AddRow(label(head.get("place") or "Gordium", bold=True, size=13))
    h.AddRow(label(head.get("code") or "", size=11))
    if error is not None:
        h.AddRow(row(label("⚠ Check could not run", eto_status_color("needs_review"), bold=True, size=15),
                     button("Retry", a["retry"])))
        h.AddRow(label(error, size=11))
    elif out_of_date:
        h.AddRow(label("Checking…", bold=True, size=15))
    else:
        h.AddRow(label((view or {}).get("summary") or "No check yet", bold=True, size=15))
    h.AddRow(label(head.get("draft") or "Draft rulebook", eto_status_color("needs_review"), size=11))
    lot_row = [label(head.get("lot") or "", size=11)]
    if "Pick survey lot lines…" in (head.get("actions") or []):
        lot_row.append(button("Pick survey lot lines…", a["survey"]))
    h.AddRow(row(*lot_row))
    grade_row = [label(head.get("grade") or "", size=11)]
    if "Set grade…" in (head.get("actions") or []):
        grade_row.append(button("Set grade…", a["grade"]))
    h.AddRow(row(*grade_row))
    h.AddRow(row(button("Edit site…", a["edit_site"])))
    h.Create()


def show_detail(parts):
    """The selected item, below the splitter (E1): status, proposed vs required, why, how to comply, the code's
    words, the citation with its links, the calculation, what was measured, and the precision rule."""
    d = parts["detail"]
    d.Clear()
    a = parts["actions"]
    i = parts["by_id"].get(parts["selected"])
    if i is None:
        d.AddRow(label("Select an item to see the code's words, the citation and how it was measured.", size=11))
        d.Create()
        return
    det = i["detail"]
    words = {"does_not_comply": "Does not comply", "needs_review": "Needs review", "complies": "Complies",
             "not_checked": "Not checked"}[i["status"]]
    d.AddRow(label((i["mark"] + " " if i["mark"] else "") + i["name"] + " · " + words,
                   eto_status_color(i["status"]), bold=True, size=13))
    if parts.get("stale"):
        d.AddRow(label("Out of date: the model changed since this was checked.", size=11))
    for text in (det.get("line"), i.get("reason"), i.get("hint") if i.get("hint") not in ("Add to check…",) else None,
                 det.get("at_limit"), det.get("calc"), det.get("scope")):
        if text:
            d.AddRow(label(text, size=12))
    if i["id"].startswith("R-") and i["status"] == "not_checked":
        d.AddRow(row(button("Enter bedrooms and parking spaces…", a["enter"])))
    if i["id"] == "scope.not_included":
        d.AddRow(row(button("Add to check…", lambda: a["add"](i["objects"]))))
    for q in det.get("quotes") or []:
        if q.get("text"):
            d.AddRow(label("“" + q["text"] + "”", size=12))
            if q.get("where"):
                d.AddRow(label(q["where"], size=11))
    if det.get("citation"):
        d.AddRow(label(det["citation"], size=11))
    for c in det.get("cited") or []:
        link = ef.LinkButton()
        link.Text = "Open " + c["citation"]
        url = c["link"]
        link.Click += lambda s, e, u=url: Rhino.UI.Dialogs.ShowMessage(u, "Gordium") if not _open(u) else None
        d.AddRow(link)
    if det.get("precision"):
        d.AddRow(label(det["precision"], size=11))
    d.Add(None)
    d.Create()


def _open(url):
    try:
        System.Diagnostics.Process.Start("open", '"' + url + '"')
        return True
    except Exception:
        return False


def legend():
    Rhino.UI.Dialogs.ShowMessage(
        "✕ does not comply · ? needs review · ✓ complies · – not checked · ⚠ setup problem\n\n"
        "In the plan: the property line, the required yards (shaded), the buildable envelope (dashed), each yard's "
        "measured distance. Red marks only the part of the building inside a required yard or above the height "
        "limit. Values are measured to 1/8 in. and never rounded toward compliance.", "Gordium · legend")


# ---- the start box (A1–A13) ----------------------------------------------------------------------------------

def start_box(state, options, mode):
    """The start box, every field in the order an architect works (A2). `state` is a dict this edits:
    address, zone, district_confirmed, use, street (text), lot_source ("tax_map"/"survey"), lot_picked (text),
    grade ("not_set"/"terrain"/"spot"), grade_result (text), grade_is ("finished"/"existing"), floor_to_floor
    (text), massing ("both"/"envelope"), preview (text). Returns "draw", "pick:<what>" (the caller hides it,
    picks, and shows it again: A1) or None (closed, Esc: nothing saved)."""
    dialog = ef.Dialog[bool]()
    dialog.Title = "New zoning check" if mode == "start" else "Zoning check · site"
    dialog.Padding = ed.Padding(14)
    dialog.Resizable = False
    chosen = {}

    def done(what):
        chosen["what"] = what
        dialog.Close(what == "draw")

    address = ef.TextBox()
    address.Text = state.get("address") or ""
    zone = ef.DropDown()
    for z in options["zones"]:
        zone.Items.Add(z)
    zone.SelectedValue = next((x for x in zone.Items if x.Text == state.get("zone")), None)
    if zone.SelectedIndex < 0 and zone.Items.Count:
        zone.SelectedIndex = 0
    confirm = ef.CheckBox()
    confirm.Text = "I confirm the district"
    confirm.Checked = bool(state.get("district_confirmed"))
    use = ef.DropDown()
    names = list(options["uses"].items())
    for _, n in names:
        use.Items.Add(n)
    use.SelectedIndex = max(0, [k for k, _ in names].index(state.get("use")) if state.get("use") in options["uses"] else 0)
    lot = ef.RadioButtonList()
    lot.Orientation = ef.Orientation.Vertical
    lot.Items.Add("Tax map, approximate (±2'-0\")")
    lot.Items.Add("Survey")
    lot.SelectedIndex = 1 if state.get("lot_source") == "survey" else 0
    grade = ef.RadioButtonList()
    grade.Orientation = ef.Orientation.Vertical
    for g in ("Not set", "Terrain surface or mesh", "Spot grades"):
        grade.Items.Add(g)
    grade.SelectedIndex = {"not_set": 0, "terrain": 1, "spot": 2}.get(state.get("grade"), 0)
    ground = ef.DropDown()
    ground.Items.Add("Finished grade")
    ground.Items.Add("Existing grade")
    ground.SelectedIndex = 1 if state.get("grade_is") == "existing" else 0
    f2f = ef.TextBox()
    f2f.Text = state.get("floor_to_floor") or "11'-8\""
    massing = ef.RadioButtonList()
    massing.Orientation = ef.Orientation.Vertical
    massing.Items.Add("Envelope and starting massing")
    massing.Items.Add("Envelope only, no massing")
    massing.SelectedIndex = 1 if state.get("massing") == "envelope" else 0

    def keep():                       # what the fields say now, back into `state`
        state.update(address=address.Text, zone=zone.SelectedValue.Text if zone.SelectedValue else None,
                     district_confirmed=bool(confirm.Checked), use=names[use.SelectedIndex][0] if names else None,
                     lot_source="survey" if lot.SelectedIndex == 1 else "tax_map",
                     grade=["not_set", "terrain", "spot"][max(grade.SelectedIndex, 0)],
                     grade_is="existing" if ground.SelectedIndex == 1 else "finished", floor_to_floor=f2f.Text,
                     massing="envelope" if massing.SelectedIndex == 1 else "both")

    def pick(what):
        keep()
        done("pick:" + what)

    draw = button("Draw site and envelope" if state.get("massing") == "envelope" else "Draw site and massing",
                  lambda: (keep(), done("draw")))
    if mode != "start":
        draw.Text = "Check the design"
    reason = label("" if confirm.Checked else "Confirm the district to continue.", size=11)
    draw.Enabled = bool(confirm.Checked)

    def confirmed(s, e):
        draw.Enabled = bool(confirm.Checked)
        reason.Text = "" if confirm.Checked else "Confirm the district to continue."

    confirm.CheckedChanged += confirmed
    massing.SelectedIndexChanged += lambda s, e: setattr(draw, "Text", "Draw site and envelope"
                                                        if massing.SelectedIndex == 1 else "Draw site and massing") \
        if mode == "start" else None
    cancel = button("Cancel", lambda: done(None))
    note = "?  Lot from tax map: dimensions approximate. Items within 2'-0\" of a limit will need review."
    grade_note = "?  Building height and stories need review until grade is set."
    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 6)
    layout.AddRow(label("Address", bold=True), address)
    layout.AddRow(None, label("Recorded on the project and the report (lookup from the City's map comes later)", size=11))
    layout.AddRow(label("Zoning district", bold=True), row(zone, confirm))
    layout.AddRow(None, label("Entered by you · Overlays (historic, gorge, flood) are not checked in this release", size=11))
    layout.AddRow(label("Use", bold=True), use)
    layout.AddRow(label("Street frontage", bold=True), row(label(state.get("street") or "not picked", size=12),
                                                           button("Pick line…", lambda: pick("street"))))
    layout.AddRow(label("Lot lines", bold=True), lot)
    layout.AddRow(None, row(button("Pick curves…", lambda: pick("lot")), label(state.get("lot_picked") or "", size=11)))
    layout.AddRow(None, label(note if lot.SelectedIndex == 0 else "", eto_status_color("needs_review"), size=11))
    layout.AddRow(label("Grade", bold=True), grade)
    layout.AddRow(None, row(button("Pick…", lambda: pick("terrain")), button("Place points…", lambda: pick("spot")),
                            label(state.get("grade_result") or "", size=11)))
    layout.AddRow(label("Ground is", bold=True), ground)
    layout.AddRow(None, label(grade_note if grade.SelectedIndex == 0 else "", eto_status_color("needs_review"), size=11))
    layout.AddRow(label("Existing building", bold=True), row(label("None", size=12),
                                                             button("Pick existing… (coming later)", None, False)))
    if mode == "start":
        layout.AddRow(label("Floor to floor", bold=True), f2f)
        layout.AddRow(label("Roof", bold=True), label("Flat (gable and hip: coming later)", size=12))
        layout.AddRow(label("Massing", bold=True), massing)
        layout.AddRow(None, label(state.get("preview") or "", size=11))
    layout.AddRow(None, reason)
    layout.AddRow(None, row(cancel, draw))
    dialog.Content = layout
    dialog.DefaultButton = draw
    dialog.AbortButton = cancel
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return chosen.get("what")


# ---- the viewport (F, G) -------------------------------------------------------------------------------------

def draw_text_box(d, lines, color, x, y, dark, size=13, bold_first=True, border=None):
    """Lines of text on a backing box (F3), at screen point x, y (top left)."""
    width = max(len(t) for t in lines) * (size * 0.6) + 22
    height = len(lines) * (size + 9) + 10
    d.Draw2dRectangle(System.Drawing.Rectangle(int(x), int(y), int(width), int(height)),
                      border or color, 1, backing(dark))
    for k, t in enumerate(lines):
        ink = color if k == 0 else status_color("complies", dark)
        d.Draw2dText(t, ink, rg.Point2d(x + 11, y + 6 + k * (size + 9)), False, size if k == 0 else size - 1)
    return width, height


def label_at(d, viewport, point, text, color, dark, size=12, taken=None):
    """A screen-size, horizontal label at a model point, on its backing box (F3). With `taken` (the labels
    already drawn this frame), it moves off any it would cover and a short leader points back to its spot."""
    p = viewport.WorldToClient(point)
    width = len(text) * size * 0.58 + 14
    top = p.Y - 10 if taken is None else logic.clear_spot(taken, p.X - width / 2, p.Y - 10, width, 20)
    if abs(top - (p.Y - 10)) > 1:
        d.Draw2dLine(System.Drawing.PointF(p.X, p.Y), System.Drawing.PointF(p.X, top + (20 if top < p.Y else 0)),
                     color, 1)
    d.Draw2dRectangle(System.Drawing.Rectangle(int(p.X - width / 2), int(top), int(width), 20), color, 1,
                      backing(dark))
    d.Draw2dText(text, color, rg.Point2d(p.X - width / 2 + 7, top + 3), False, size)


PHANTOM = 0b11111111111111000110001100000000    # long dash, short, short: the property line
DASHED = 0b11111111000000001111111100000000
