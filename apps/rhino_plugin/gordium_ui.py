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

PANEL_WIDTH = 480          # wide enough that Proposed, Required and Margin never truncate (D4)
# fixed widths that fit the panel: an Item column sized to its text pushed the numbers out of sight (seen in the
# Rhino window capture). The mark is the first thing in the Item cell: on the Mac the tree's expand arrows take
# the first column, which hid a column of its own.
COLUMNS = [("Item", 230), ("Proposed", 84), ("Required", 72), ("Margin", 62)]
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
    """Red or amber in the shade for the panel's own background; anything else is the system's text color (J2):
    a fixed dark ink was unreadable on the dark panel."""
    if status not in ("does_not_comply", "needs_review"):
        return ed.SystemColors.ControlText
    c = status_color(status, _dark_panel())
    return ed.Color.FromArgb(c.R, c.G, c.B)


def _dark_panel():
    """Whether the panel's background is dark, from its own red, green and blue (Eto colors are 0-1 floats and
    have no brightness property: asking for one always said "light")."""
    try:
        c = ed.SystemColors.ControlBackground
        return 0.299 * c.R + 0.587 * c.G + 0.114 * c.B < 0.5
    except Exception:
        return False


def backing(dark):
    """The box behind a drawn label, so it reads on any viewport background (F3)."""
    return System.Drawing.Color.FromArgb(225, 30, 33, 36) if dark else System.Drawing.Color.FromArgb(230, 255, 255, 255)


# ---- small Eto helpers ---------------------------------------------------------------------------------------

def label(text, color=None, bold=False, size=None, wrap=True, width=None):
    lab = ef.Label()
    lab.Text = text or ""
    lab.Wrap = ef.WrapMode.Word if wrap else getattr(ef.WrapMode, "None")
    if width is not None:               # wraps at this width, left aligned (an unbounded label ran off the panel)
        lab.Width = width
        lab.TextAlignment = ef.TextAlignment.Left
    if color is not None:
        lab.TextColor = color
    if bold or size:
        lab.Font = ed.Font(ed.SystemFont.Bold if bold else ed.SystemFont.Default, size or 13)
    return lab


def _wide(text, color=None, bold=False, size=None):
    """A label the width of the panel's content, wrapping there."""
    return label(text, color, bold, size, True, PANEL_WIDTH - 48)


def button(text, action, enabled=True):
    b = ef.Button()
    b.Text = text
    b.Enabled = enabled
    if action is not None:
        b.Click += logic.guard(lambda s, e: action(), "do " + text)
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
        col.AutoSize = False                # never sized to its text: every column stays in view (D4)
        col.Resizable = True
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
            if e.Column.DisplayIndex in (0, 1, 3):          # the item (with its mark), proposed, margin
                e.ForegroundColor = eto_status_color(found["status"])

    tree.CellFormatting += logic.guard(formatting, "color a panel row")

    def selected(sender, e):
        item = tree.SelectedItem
        tag = item.Tag if item is not None else None
        if isinstance(tag, str) and tag.startswith("group:"):
            return                           # section headers aren't selectable (D5)
        parts["selected"] = tag
        show_detail(parts)

    tree.SelectedItemChanged += logic.guard(selected, "show the selected item")
    tree.CellDoubleClick += logic.guard(lambda s, e: actions["zoom"](parts["by_id"].get(parts["selected"])), "zoom to the item")
    split = ef.Splitter()
    split.Orientation = ef.Orientation.Vertical
    split.Panel1 = tree
    detail_scroll = ef.Scrollable()
    detail_scroll.ExpandContentWidth = True      # the detail's text wraps to the panel, never runs off it
    detail_scroll.Content = parts["detail"]
    split.Panel2 = detail_scroll
    split.Position = 380
    footer = row(button("Zoom to", lambda: actions["zoom"](parts["by_id"].get(parts["selected"]))),
                 button("Zoning report…", actions["report"]), button("?", actions["legend"]))
    parts["zoom_button"] = footer.Items[0].Control
    layout = ef.DynamicLayout()
    layout.Padding = ed.Padding(10)
    layout.Spacing = ed.Size(6, 6)
    layout.Add(parts["header"])
    layout.Add(split, yscale=True)
    layout.Add(row(_envelope_box(actions), _massing_box(actions)))
    parts["message"] = label("", size=11)          # what the last button did, or why it couldn't (never silent)
    layout.Add(parts["message"])
    layout.Add(footer)
    form.Content = layout
    return parts


def say(parts, text):
    """One line under the list: what the last button did, or why it couldn't."""
    if parts is not None and parts.get("message") is not None:
        parts["message"].Text = text or ""


def _massing_box(actions):
    """Hide starting house: the Gordium::Massing layer off. Hidden, it is still checked (a hidden building still
    counts, as everywhere in Gordium): only drawing it is turned off."""
    box = ef.CheckBox()
    box.Text = "Hide starting house"
    box.Checked = False
    box.CheckedChanged += logic.guard(lambda s, e: actions["massing"](bool(box.Checked)), "hide the starting house")
    return box


def _envelope_box(actions):
    box = ef.CheckBox()
    box.Text = "Show buildable envelope"
    box.Checked = True
    box.CheckedChanged += logic.guard(lambda s, e: actions["envelope"](bool(box.Checked)), "show or hide the envelope")
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
        gi.Values = System.Array[System.Object]([title + g["title"] + " · " + str(len(g["items"])), "", "", ""])
        gi.Expanded = parts["expanded"].get(gi.Tag, g["key"] not in ("complies", "not_covered"))
        for item_id in g["items"]:
            i = by_id[item_id]
            stale_row = parts["stale"] and i["status"] != "not_checked"
            values = [("" if stale_row else i["mark"] + "  ") + i["name"] + ("" if i["group"] != "site" else " (site)"),
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
    if selected_item is not None:           # SelectedItem is read-only here: select by row in the visible list
        k = 0
        for gi in parts["groups"]:
            if gi.Expanded:
                for c in range(gi.Children.Count):
                    if gi.Children[c] is selected_item or gi.Children[c].Tag == selected_item.Tag:
                        tree.SelectedRow = k + 1 + c
                k += gi.Children.Count
            k += 1
    parts["zoom_button"].Enabled = parts["selected"] in by_id and not parts["stale"]
    show_detail(parts)


def _header(parts, view, error, out_of_date):
    h = parts["header"]
    h.Clear()
    a = parts["actions"]
    head = (view or {}).get("header") or {}
    h.AddRow(_wide(head.get("place") or "Gordium", bold=True, size=13))
    h.AddRow(_wide(head.get("code") or "", size=11))
    if error is not None:
        h.AddRow(row(_wide("⚠ Check could not run", eto_status_color("needs_review"), bold=True, size=15),
                     button("Retry", a["retry"])))
        h.AddRow(_wide(error, size=11))
    elif out_of_date:
        h.AddRow(_wide("Checking…", bold=True, size=15))
    else:
        h.AddRow(_wide((view or {}).get("summary") or "No check yet", bold=True, size=15))
    h.AddRow(_wide(head.get("draft") or "Draft rulebook", eto_status_color("needs_review"), size=11))
    h.AddRow(_wide(head.get("lot") or "", size=11))          # each fact on its line, its buttons below it: a
    h.AddRow(_wide(head.get("grade") or "", size=11))        # button beside a long line ran off the panel
    buttons = [button("Edit site…", a["edit_site"])]
    if "Pick survey lot lines…" in (head.get("actions") or []):
        buttons.append(button("Pick survey lot lines…", a["survey"]))
    if "Set grade…" in (head.get("actions") or []):
        buttons.append(button("Set grade…", a["grade"]))
    h.AddRow(row(*buttons))
    h.Create()


def show_detail(parts):
    """The selected item, below the splitter (E1): status, proposed vs required, why, how to comply, the code's
    words, the citation with its links, the calculation, what was measured, and the precision rule."""
    d = parts["detail"]
    d.Clear()
    a = parts["actions"]
    i = parts["by_id"].get(parts["selected"])
    if i is None:
        d.AddRow(_wide("Select an item to see the code's words, the citation and how it was measured.", size=11))
        sources = (((parts.get("view") or {}).get("header") or {}).get("sources")) or []
        if sources:                           # the site facts, each with where it came from
            d.AddRow(_wide("Site facts", bold=True, size=12))
            for s in sources:
                d.AddRow(_wide(s, size=11))
                if s.startswith("Marked as the ground"):   # the architect's word, so it can be taken back
                    d.AddRow(row(button("Not the ground", a["not_ground"])))
        d.Create()
        return
    det = i["detail"]
    words = {"does_not_comply": "Does not comply", "needs_review": "Needs review", "complies": "Complies",
             "not_checked": "Not checked"}[i["status"]]
    d.AddRow(_wide((i["mark"] + " " if i["mark"] else "") + i["name"] + " · " + words,
                   eto_status_color(i["status"]), bold=True, size=13))
    if parts.get("stale"):
        d.AddRow(_wide("Out of date: the model changed since this was checked.", size=11))
    for text in (det.get("line"), i.get("reason"), i.get("hint") if i.get("hint") not in ("Add to check…",) else None,
                 det.get("at_limit"), det.get("calc"), det.get("scope")):
        if text:
            d.AddRow(_wide(text, size=12))
    if i["id"].startswith("R-") and i["status"] == "not_checked":
        d.AddRow(row(button("Enter bedrooms and parking spaces…", a["enter"])))
    if i["id"] == "scope.not_included":
        d.AddRow(row(button("Add to check…", lambda: a["add"](i["objects"]))))
        if i.get("ground_like"):              # only the architect's word leaves it out (never a guess)
            d.AddRow(row(button("This is the ground", lambda: a["ground"](i["ground_like"]))))
    for t in det.get("definitions") or []:        # E5: the whole definitions an examiner measures height by
        d.AddRow(_wide(t["term"], bold=True, size=12))
        d.AddRow(_wide("“" + t["text"] + "”", size=11))
    if det.get("spots"):
        d.AddRow(_wide("Spot grades (" + str(len(det["spots"])) + ")", bold=True, size=12))
        for s in det["spots"]:
            d.AddRow(_wide(s, size=11))
    if det.get("diagram"):
        d.AddRow(_section(det["diagram"]))
    if det.get("zoom_note"):
        d.AddRow(_wide(det["zoom_note"], size=11))
    for q in det.get("quotes") or []:
        if q.get("text"):
            d.AddRow(_wide("“" + q["text"] + "”", size=12))
            if q.get("where"):
                d.AddRow(_wide(q["where"], size=11))
    if det.get("citation"):
        d.AddRow(_wide(det["citation"], size=11))
    for c in det.get("cited") or []:
        link = ef.LinkButton()
        link.Text = "Open " + c["citation"]
        url = c["link"]
        link.Click += logic.guard(lambda s, e, u=url: Rhino.UI.Dialogs.ShowMessage(u, "Gordium") if not _open(u) else None, "open the link")
        d.AddRow(link)
    if det.get("precision"):
        d.AddRow(_wide(det["precision"], size=11))
    d.Add(None)
    d.Create()


def _section(dg):
    """E5's section diagram, not to scale: the lot lines at both ends, the front and rear yards, the grade plane,
    the building and the height limit, each labelled with the checker's own text. Drawn ONCE into a bitmap, here,
    inside try/except, then shown as an image: never in a Paint handler, because on the Mac an error raised while
    the system draws a view aborts Rhino (it did: 2026-10-20). If drawing fails, a line of text stands in."""
    w, h = PANEL_WIDTH - 60, 150
    try:
        bmp = ed.Bitmap(w, h, ed.PixelFormat.Format32bppRgba)
        g = ed.Graphics(bmp)
        try:
            ink, faint = ed.SystemColors.ControlText, ed.SystemColors.DisabledText
            red = eto_status_color("does_not_comply")
            font = ed.Font(ed.SystemFont.Default, 9)
            ground, left, right = h - 24.0, 16.0, w - 16.0
            depth = dg.get("depth") or 0
            front, rear = dg.get("front") or 0, dg.get("rear") or 0
            span = right - left
            fx = left + (span * front / depth if depth else span * 0.25)
            rx = right - (span * rear / depth if depth else span * 0.25)
            height, limit = dg.get("height"), dg.get("limit")
            scale = (ground - 18.0) / max(v for v in (height, limit, 1.0) if v)
            text = dg.get("text") or {}
            g.DrawLine(ink, left, ground, right, ground)                     # the grade plane
            for x in (left, right):                                          # the lot lines
                g.DrawLine(faint, x, ground - 4, x, 8.0)
            if height:
                g.DrawRectangle(ink, fx, ground - height * scale, max(rx - fx, 4.0), height * scale)
                g.DrawText(font, ink, fx + 3, ground - height * scale + 2, "height " + text.get("height", ""))
            if limit:
                y = ground - limit * scale
                g.DrawLine(red, left, y, right, y)
                g.DrawText(font, red, right - 110, y - 13, "limit " + text.get("limit", ""))
            g.DrawText(font, faint, left + 2, ground + 3, "front yard " + text.get("front", ""))
            g.DrawText(font, faint, rx + 2, ground + 3, "rear yard " + text.get("rear", ""))
            g.DrawText(font, faint, left + 2, 2.0, dg.get("label") or "Diagram, not to scale")
        finally:
            g.Dispose()
        view = ef.ImageView()
        view.Image = bmp
        view.Size = ed.Size(w, h)
        return view
    except Exception as e:                   # a drawing problem never costs the panel (or Rhino)
        return _wide((dg.get("label") or "Diagram") + ": can't be drawn here (" + str(e)[:60] + ")", size=11)


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
    """The start box (spec A, as approved 2026-10-20). What it shows is rhino_logic.box_rows (tested in CI); this
    only draws it: Address, Zoning district (with its source and "I confirm", unticked on a new project), Use,
    Lot, Street side, Ground (with "No regrading near the house"), what isn't checked yet, the one amber line for
    a case it can't settle, and [Cancel] [Draw]. Returns "draw", "pick:<what>" (the caller hides it, picks, and
    shows it again) or None (closed, Esc: nothing saved). `state` is edited in place."""
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
    address.Width = 300
    zone = ef.DropDown()
    for z in options["zones"]:
        zone.Items.Add(z)
    zone.SelectedValue = next((x for x in zone.Items if x.Text == state.get("zone")), None)
    if zone.SelectedIndex < 0 and zone.Items.Count:
        zone.SelectedIndex = 0
    first_zone = zone.SelectedValue.Text if zone.SelectedValue else None
    confirm = ef.CheckBox()
    confirm.Checked = bool(state.get("district_confirmed"))
    use = ef.DropDown()
    names = list(options["uses"].items())
    for _, n in names:
        use.Items.Add(n)
    use.SelectedIndex = max(0, [k for k, _ in names].index(state.get("use")) if state.get("use") in options["uses"] else 0)
    regrade = ef.CheckBox()
    regrade.Checked = bool(state.get("no_regrading"))
    corner = ef.DropDown()                # Corner lot? never guessed: "Not answered" until the architect says
    for c in logic.CORNER_CHOICES:
        corner.Items.Add(c)
    corner.SelectedIndex = {None: 0, False: 1, True: 2}[state.get("corner_lot")]
    first = {"address": address.Text, "use": use.SelectedIndex, "corner": corner.SelectedIndex}

    checks = {}                       # row key -> its "I checked this" tick (a looked-up fact found doubtful)

    def keep():                       # what the fields say now, back into `state`; what changed is the architect's
        state["checked"] = sorted(k for k, c in checks.items() if c.Checked)
        z = zone.SelectedValue.Text if zone.SelectedValue else None
        if buffer is not None:
            state["design_buffer"] = buffer.Text
        state.update(address=address.Text, zone=z, district_confirmed=bool(confirm.Checked),
                     use=names[use.SelectedIndex][0] if names else None, no_regrading=bool(regrade.Checked),
                     corner_lot=[None, False, True][max(corner.SelectedIndex, 0)])
        if z != first_zone:
            state["zone_source"] = logic.ENTERED
        if address.Text != first["address"]:
            state["address_source"] = logic.ENTERED
        if use.SelectedIndex != first["use"]:
            state["use_source"] = logic.ENTERED
        if corner.SelectedIndex != first["corner"]:
            state["corner_source"] = logic.ENTERED


    def pick(what):
        keep()
        done("pick:" + what)

    draw = button("Draw" if mode == "start" else "Check", lambda: (keep(), done("draw")))
    reason = label(logic.draw_reason(state), size=11)
    looking = bool((state.get("lookup") or {}).get("looking"))
    draw.Enabled = logic.can_draw(state) and not looking

    def enter_looks_up(s, e):          # Enter in the address: Look up (not Draw, the box's default button)
        if e.Key == ef.Keys.Enter and not looking:
            e.Handled = True
            pick("lookup")

    address.KeyDown += logic.guard(enter_looks_up, "look up the address")
    # the design buffer sizes the starting house, so it is set when starting (GordiumStart), not in Edit site…
    buffer = ef.TextBox() if mode == "start" else None

    def confirmed(s, e):
        state["district_confirmed"] = bool(confirm.Checked)
        if buffer is not None:
            state["design_buffer"] = buffer.Text
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.draw_reason(state)

    confirm.CheckedChanged += logic.guard(confirmed, "confirm the district")
    cancel = button("Cancel", lambda: done(None))
    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 6)
    for r in logic.box_rows(state):
        key, title = r["key"], label(r["label"], bold=True)
        if key == "address":
            layout.AddRow(title, row(address, *[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            if r.get("matches"):           # several places match: pick one, then Look up again
                matches = ef.DropDown()
                matches.Items.Add("Which address?")
                for m in r["matches"]:
                    matches.Items.Add(m)
                matches.SelectedIndex = 0

                def matched(s, e, box=matches):
                    if box.SelectedIndex > 0:
                        address.Text = box.SelectedValue.Text

                matches.SelectedIndexChanged += logic.guard(matched, "pick the address")
                layout.AddRow(None, row(matches))
            if r.get("status"):            # Looking up 106 Ithaca Rd… (the box stays usable; Cancel works)
                layout.AddRow(None, row(label(r["status"], size=11)))
        elif key == "zone":
            confirm.Text = r["tick"][0]
            layout.AddRow(title, row(zone, label(r["text"].split(" · ", 1)[-1], size=11), confirm))
        elif key == "use":
            layout.AddRow(title, use)
        elif key == "ground":
            layout.AddRow(title, row(label(r["text"], size=12)))          # left aligned, as the others
            layout.AddRow(None, row(*[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            regrade.Text = r["tick"][0]
            layout.AddRow(None, regrade)
        else:                          # lot, street side: what it is, and the one way to change it
            layout.AddRow(title, row(label(r["text"], size=12),
                                     *[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            if r.get("choice"):        # the street side's question: Corner lot?
                layout.AddRow(None, row(label(r["choice"][0], size=12), corner))
        if r.get("review"):            # a looked-up fact found doubtful: why, in amber, and I checked this
            layout.AddRow(None, row(label(r["review"], eto_status_color("needs_review"), size=11, width=560)))
        if r.get("check"):
            tick = ef.CheckBox()
            tick.Text, tick.Checked = r["check"][0], r["check"][1]
            checks[key] = tick
            layout.AddRow(None, tick)
    if buffer is not None:               # Advanced: a design buffer kept back from every limit, on top of the tax map's
        buffer.Text = state.get("design_buffer") or "0'-0\""
        buffer.TextChanged += logic.guard(confirmed, "type the design buffer")
        advanced = ef.Expander()
        advanced.Header = label("Advanced", bold=True, size=12)
        advanced.Expanded = (state.get("design_buffer") or "0'-0\"") not in ("", "0'-0\"")
        advanced.Content = row(label("Design buffer", size=12), buffer,
                               label("kept back from every limit by the starting house", size=11))
        layout.AddRow(None, advanced)
    layout.AddRow(None, row(label(logic.NOT_CHECKED_YET, size=11)))
    amber = label("", eto_status_color("needs_review"), size=12)    # one line, following the answers given

    def refresh_amber(*_):
        state["corner_lot"] = [None, False, True][max(corner.SelectedIndex, 0)]
        text = logic.uncertain(state)
        amber.Text = "?  " + text if text else ""

    refresh_amber()
    corner.SelectedIndexChanged += logic.guard(refresh_amber, "answer the corner lot")
    layout.AddRow(None, row(amber))
    layout.AddRow(None, row(reason))
    layout.AddRow(None, row(cancel, draw))
    dialog.Content = layout
    dialog.DefaultButton = draw
    dialog.AbortButton = cancel
    shown = state.get("_on_shown")            # for the in-Rhino test: capture the real box, then close it
    if shown is not None:
        dialog.Shown += logic.guard(lambda s, e: shown(dialog), "run the start box hook")
    poll = state.get("_poll")                 # a lookup running in its own process: the box closes itself when it
    if looking and poll is not None:          # answers (or the time runs out), and opens again filled in
        timer = ef.UITimer()
        timer.Interval = 0.5

        def tick(s, e):
            if poll() is not None:
                timer.Stop()
                keep()
                done("pick:lookup_done")

        timer.Elapsed += logic.guard(tick, "wait for the address lookup")
        dialog.Shown += logic.guard(lambda s, e: timer.Start(), "start waiting for the lookup")
        dialog.Closed += logic.guard(lambda s, e: timer.Stop(), "stop waiting for the lookup")
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


def _signed(bits):
    """A 32-bit dash mask as Rhino takes it: a signed Int32 (a mask with its top bit set overflows otherwise:
    "value too large to convert", caught by the guard 2026-10-20, so the dashed lines never drew)."""
    return bits - (1 << 32) if bits & (1 << 31) else bits


PHANTOM = _signed(0b11111111111111000110001100000000)    # long dash, short, short: the property line
DASHED = _signed(0b11111111000000001111111100000000)
