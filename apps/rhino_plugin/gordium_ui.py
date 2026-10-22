#! python3
"""What the architect sees: the Gordium panel, the start box, and the drawing in the viewport
(docs/design/rhino_ui_spec.md). Rhino 8's Python (3.9), Eto and display drawing only; every number and word comes
from the checker's `view` (design_checker/present.py), so nothing here decides a result.

No class here extends an Eto or Rhino class: Rhino keeps the first .NET class made for a Python class for the
whole session (gordium_rhino.Overlay explains), so the panel and the dialog are plain Eto objects built by
functions, and an update to this file takes effect at once."""

import System
import os

import Eto.Drawing as ed
import Eto.Forms as ef
import Rhino
import Rhino.Geometry as rg

import rhino_logic as logic  # plain Python, tested in CI (on the path: gordium_rhino puts it there first)

PANEL_WIDTH = 400          # as wide as Rhino's own panels (architect's review, 2026-10-21: at 540-620 the dock took
                           # nearly half the screen); every cell wraps to two lines, so nothing is cut off at 380
# fixed widths that fit the panel: an Item column sized to its text pushed the numbers out of sight (seen in the
# Rhino window capture). The mark is the first thing in the Item cell: on the Mac the tree's expand arrows take
# the first column, which hid a column of its own.
COLUMNS = [("Item", 120), ("Proposed", 64), ("Required", 64), (logic.COLUMN_DELTA, 86)]   # Item takes the rest
ROW_HEIGHT = 36            # two lines: a long item name or "at least 1'-0" short" wraps instead of being cut off
CELL_FONT_SIZE = 12
STALE_SECONDS = 0.3        # results older than an edit by this long are shown as out of date (F7, H1)


# ---- colors: Rhino's own for chrome; red and amber only for status, keyed to the background (J2, F8) -----------

def _dark(color):
    return 0.299 * color.R + 0.587 * color.G + 0.114 * color.B < 128


# the model's highlights (rhino_logic.highlight): saturated and distinct on light and dark viewports alike, one
# transparency; red also gets a solid edge so a 1 ft strip still reads at plan scale (architect's review, 2026-10-21)
HIGHLIGHT = {"red": System.Drawing.Color.FromArgb(215, 38, 61), "amber": System.Drawing.Color.FromArgb(242, 169, 0)}
HIGHLIGHT_TRANSPARENCY = 0.45
HIGHLIGHT_EDGE = {"red": 3, "amber": 1}
HIGHLIGHT_PROUD_FT = 0.02    # each block stands this far proud of the house, so their shared faces never fight


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
    lab.TextAlignment = ef.TextAlignment.Left
    if DOCKED:                          # Rhino's docked panel on the Mac turns it right aligned as it lays the label
        lab.LoadComplete += logic.guard(  # out (read back in Rhino, 2026-10-21): left again once it is in place
            lambda sender, e: setattr(sender, "TextAlignment", ef.TextAlignment.Left), "align a label")
    if width is not None:               # wraps at this width (an unbounded label ran off the floating window)
        lab.Width = width
    if color is not None:
        lab.TextColor = color
    if bold or size:
        lab.Font = ed.Font(ed.SystemFont.Bold if bold else ed.SystemFont.Default, size or 13)
    return lab


DOCKED = False                  # set by make_panel: docked, labels stretch with Rhino's panel (no fixed width)
WRAP_AT = None                  # docked: the width labels wrap at, from the panel's own width (set by show)



def _wide(text, color=None, bold=False, size=None):
    """A label the width of the panel's content, wrapping there: the floating window's fixed width, or docked,
    whatever width the architect gives Rhino's panel."""
    return label(text, color, bold, size, True, (WRAP_AT or PANEL_WIDTH - 48) if DOCKED else PANEL_WIDTH - 48)


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

def open_dock(panel_id):
    """Show the Gordium panel. Not showing yet: docked as a tab beside Rhino's Layers panel (Rhino's own first
    choice is a small floating window, which cut the list off); showing already (where the architect put it, or
    where Rhino restored it): left there."""
    if Rhino.UI.Panels.IsPanelVisible(panel_id):
        return
    for beside in (Rhino.UI.PanelIds.ObjectProperties, Rhino.UI.PanelIds.Layers):
        if Rhino.UI.Panels.IsPanelVisible(beside):   # only beside one that is showing (else Rhino does nothing)
            Rhino.UI.Panels.OpenPanelAsSibling(panel_id, beside)
            if Rhino.UI.Panels.IsPanelVisible(panel_id):
                Rhino.UI.Panels.OpenPanel(panel_id)  # its tab the selected one
                return
    Rhino.UI.Panels.OpenPanel(panel_id)          # no dock showing: Rhino floats it (fit_floating sizes it)


def fit_floating(host, doc_window):
    """When Rhino shows the panel floating (no dock showing to join: Rhino makes a 200 x 200 window), that window
    is made the panel's size and placed at the right edge of the document's window. Docked, nothing changes.
    Returns "docked", "floating" or None (not shown yet)."""
    window = host.ParentWindow
    if window is None:
        return None
    if doc_window is not None and (window.Equals(doc_window) or window.Title == doc_window.Title):
        return "docked"
    window.ClientSize = ed.Size(PANEL_WIDTH, 720)
    if doc_window is not None:
        b = doc_window.Bounds
        window.Location = ed.Point(b.X + b.Width - PANEL_WIDTH - 24, b.Y + 60)
    return "floating"


class DockHost:
    """The docked panel, seen as the floating window was (Visible, Show, Close, BringToFront), so the rest of the
    plugin needs no change: Rhino's own panel system shows it, docked or floating as the architect leaves it."""

    def __init__(self, panel_id, host):
        self.panel_id, self.host = panel_id, host

    @property
    def Visible(self):
        return bool(Rhino.UI.Panels.IsPanelVisible(self.panel_id))

    def Show(self):
        open_dock(self.panel_id)

    BringToFront = Show

    def Close(self):
        self.host.Content = None             # no stale rows if Rhino shows the tab again before a check
        Rhino.UI.Panels.ClosePanel(self.panel_id)


def cell_text(text, width, bold=False):
    """A cell's text laid out as the panel draws it: wrapped by word at the cell's width (Eto FormattedText)."""
    ft = ed.FormattedText()
    ft.Text = text or ""
    ft.Font = ed.Font(ed.SystemFont.Bold if bold else ed.SystemFont.Default, CELL_FONT_SIZE)
    ft.MaximumSize = ed.SizeF(max(width - 4, 1), 1000)
    ft.Wrap = ed.FormattedTextWrapMode.Word
    return ft


_FITTED = {}


def fit_text(text, width, bold=False):
    """The text as a cell of `width` shows it: whole when it fits in two lines; otherwise cut at the end of the
    second line with "…" (the selected item's detail, below the list, always has it whole). Cached: cells paint
    often."""
    key = (text, int(width), bold)
    if key not in _FITTED:
        limit = ROW_HEIGHT - 2
        if cell_text(text, width, bold).Measure().Height <= limit:
            _FITTED[key] = text
        else:
            low, high = 0, len(text)
            while low < high:                # the longest start that fits with its "…"
                mid = (low + high + 1) // 2
                if cell_text(text[:mid].rstrip() + "…", width, bold).Measure().Height <= limit:
                    low = mid
                else:
                    high = mid - 1
            _FITTED[key] = text[:low].rstrip() + "…"
    return _FITTED[key]


def _cell_style(parts, item, index):
    """(bold, colour) of one cell: a group header bold; an item that doesn't comply or needs review in its status
    colour (the item with its mark, proposed, Delta); everything else the system's text colour."""
    tag = item.Tag if item is not None else None
    if isinstance(tag, str) and tag.startswith("group:"):
        return True, None
    found = parts["by_id"].get(tag)
    if found is not None and not parts.get("stale") and found["status"] in ("does_not_comply", "needs_review") \
            and index in (0, 1, 3):
        return False, eto_status_color(found["status"])
    return False, None


def _cell_painter(parts, index):
    def paint(sender, e):
        item = e.Item
        if item is None:
            return
        bold, colour = _cell_style(parts, item, index)
        if getattr(e, "IsSelected", False):
            colour = ed.SystemColors.HighlightText
        r = e.ClipRectangle
        text = str(item.Values[index] or "")
        shown = fit_text(text, r.Width, bold)
        parts.setdefault("painted", {})[(index, item.Tag is not None and str(item.Tag).startswith("group:"))] = r.Width
        ft = cell_text(shown, r.Width, bold)
        ft.ForegroundBrush = ed.SolidBrush(colour or ed.SystemColors.ControlText)
        e.Graphics.DrawText(ft, ed.PointF(r.X + 2, r.Y + 2))
    return paint


def make_panel(actions, host=None, context_on=True):
    """The Gordium panel: a header, the item list (a TreeGridView), a splitter, the selected item's detail, and a
    footer. `actions` maps names to functions (zoom, report, envelope, edit_site, survey, grade, enter, add,
    retry). In `host` (a DockHost: a docked Rhino panel), or a floating window when there is none. Returns a dict
    of its parts; `show(panel, …)` fills it."""
    global DOCKED
    DOCKED = host is not None
    if host is not None:
        form = host
    else:
        form = ef.Form()
        form.Title = "Gordium · Zoning"
        form.ClientSize = ed.Size(PANEL_WIDTH, 720)
        form.MinimumSize = ed.Size(PANEL_WIDTH, 420)
        form.Resizable = True
        form.Topmost = True
    tree = ef.TreeGridView()
    tree.ShowHeader = True
    tree.AllowMultipleSelection = False
    tree.RowHeight = ROW_HEIGHT
    parts = {"form": form, "tree": tree, "actions": actions, "by_id": {}, "expanded": {}, "selected": None,
             "header": ef.DynamicLayout(), "detail": ef.DynamicLayout(), "view": None}
    for i, (title, width) in enumerate(COLUMNS):
        col = ef.GridColumn()
        col.HeaderText = title
        cell = ef.DrawableCell()             # drawn here, wrapping to two lines (a text cell is one line, cut off)
        cell.Paint += logic.guard(_cell_painter(parts, i), "draw a panel row")
        col.DataCell = cell
        col.Editable = False
        col.Sortable = False
        col.Width = width
        col.AutoSize = False                # never sized to its text: every column stays in view (D4)
        col.Expand = i == 0                 # the item takes whatever width the panel has
        col.Resizable = True
        tree.Columns.Add(col)

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
    ticks = [row(_auto_box(actions, parts)), row(_envelope_box(actions)), row(_massing_box(actions)),
             row(_labels_box(actions, parts)), row(_context_box(actions, parts, context_on))]
    # while a start box is open these are off; the legend ("?") is not among them: it only shows something
    parts["greyed"] = [tree, detail_scroll, *ticks, footer.Items[0].Control, footer.Items[1].Control]
    layout = ef.DynamicLayout()
    layout.Padding = ed.Padding(10)
    layout.Spacing = ed.Size(6, 6)
    layout.Add(parts["header"])
    layout.Add(split, yscale=True)
    for t in ticks:                                 # each tick its own row: side by side they ran off at 380
        layout.Add(t)
    parts["message"] = label("", size=11)          # what the last button did, or why it couldn't (never silent)
    layout.Add(parts["message"])
    layout.Add(footer)
    if host is not None:
        host.host.Content = layout
        host.host.MinimumSize = ed.Size(PANEL_WIDTH, 420)
    else:
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


def _context_box(actions, parts, on=True):
    """Show neighbourhood: the context map (parcels, streets and footprints 1500 ft around a looked-up lot) on or
    off. Drawing only: the check never measures it. Starts as this document has it (saved in the file, like Show
    on-screen labels), set before the handler is attached so building the panel never fetches anything."""
    box = ef.CheckBox()
    box.Text = "Show neighbourhood"
    box.ToolTip = "The parcels, streets and building footprints within 750 ft of the lot (drawing only, never checked)"
    box.Checked = bool(on)

    def changed(s, e):
        if not parts.get("_setting_context"):       # set from the document (set_context_tick): not a change
            actions["context"](bool(box.Checked))

    box.CheckedChanged += logic.guard(changed, "show or hide the neighbourhood")
    parts["context_box"] = box
    return box


def set_context_tick(parts, shown):
    """The Show neighbourhood tick as this document has it."""
    if parts is None or parts.get("context_box") is None:
        return
    parts["_setting_context"] = True
    try:
        parts["context_box"].Checked = bool(shown)
    finally:
        parts["_setting_context"] = False


def _auto_box(actions, parts):
    """Check after every edit: off by default (the Check button checks; Ben, 2026-10-21), remembered in the
    document; set from the document (set_auto_tick) before any change counts."""
    box = ef.CheckBox()
    box.Text = logic.AUTO_CHECK_LABEL
    box.ToolTip = logic.AUTO_CHECK_TIP
    box.Checked = False

    def changed(s, e):
        if not parts.get("_setting_auto"):          # set from the document: not a change
            actions["auto_check"](bool(box.Checked))

    box.CheckedChanged += logic.guard(changed, "turn checking after every edit on or off")
    parts["auto_box"] = box
    return box


def set_auto_tick(parts, on):
    """The Check after every edit tick as this document has it (and what the header says while out of date)."""
    if parts is None:
        return
    parts["auto_check"] = bool(on)
    if parts.get("auto_box") is None:
        return
    parts["_setting_auto"] = True
    try:
        parts["auto_box"].Checked = bool(on)
    finally:
        parts["_setting_auto"] = False


def _labels_box(actions, parts):
    """Show on-screen labels: each yard's and lot edge's label and the status box, off by default; remembered in the
    document."""
    box = ef.CheckBox()
    box.Text = "Show on-screen labels"
    box.Checked = False

    def changed(s, e):
        if not parts.get("_setting_labels"):        # set from the document (set_labels_tick): not a change
            actions["labels"](bool(box.Checked))

    box.CheckedChanged += logic.guard(changed, "show or hide the on-screen labels")
    parts["labels_box"] = box
    return box


def set_labels_tick(parts, shown):
    """The tick as this document has it."""
    if parts is None or parts.get("labels_box") is None:
        return
    parts["_setting_labels"] = True
    try:
        parts["labels_box"].Checked = bool(shown)
    finally:
        parts["_setting_labels"] = False


def _envelope_box(actions):
    box = ef.CheckBox()
    box.Text = "Show buildable envelope"
    box.Checked = True
    box.CheckedChanged += logic.guard(lambda s, e: actions["envelope"](bool(box.Checked)), "show or hide the envelope")
    return box


def _wrap_width(parts):
    """Docked: the width labels wrap at, the panel's own width less its margins (an unbounded label ran off the
    docked panel's right edge: the architect's review, 2026-10-21); never below 240 px."""
    host = getattr(parts.get("form"), "host", None)
    width = getattr(host, "Width", 0) or 0
    return max(240, width - 48) if width > 0 else None


def show(parts, view, stale=False, error=None, checking=False):
    """Fill the panel from the checker's view. Stale (the model changed and the check hasn't run again yet) or a
    check that couldn't run: rows keep their names but show no mark and "—", Zoom to is off (H1, H2, H5). The
    selection, which groups are open and the scroll position are kept by item id across refreshes (D8)."""
    global WRAP_AT
    WRAP_AT = _wrap_width(parts) if DOCKED else None
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
            values = [("" if stale_row else i["mark"] + "  ") + logic.row_name(i),
                      "—" if stale_row else (i["proposed"] if i["status"] != "not_checked" else ""),   # the name says it
                      "" if stale_row else i["required"], "" if stale_row else (i.get("delta") or "")]
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
    lines = logic.panel_header(head)
    h.AddRow(_wide(lines["above"][0], bold=True, size=13))
    if error is not None:
        h.AddRow(row(_wide("⚠ Check could not run", eto_status_color("needs_review"), bold=True, size=15),
                     button("Retry", a["retry"])))
        h.AddRow(_wide(error, size=11))
    elif out_of_date:                      # greyed rows below; a check on its way, or press Check
        h.AddRow(_wide(logic.out_of_date_line(parts.get("auto_check"), parts.get("checked_before", True)), bold=True,
                       size=15))
    else:
        h.AddRow(_wide((view or {}).get("summary") or "No check yet", bold=True, size=15))
    draft, lot, grade = lines["below"]
    h.AddRow(_wide(draft, eto_status_color("needs_review"), size=11))
    h.AddRow(_wide(lot, size=11))          # each fact on its line, its buttons below it: a
    h.AddRow(_wide(grade, size=11))        # button beside a long line ran off the panel
    if head.get("main"):                   # several buildings: which is measured, and a way to change it
        h.AddRow(_wide(head["main"], size=11))
    buttons = [button("Check", a["check"]), button("Edit site…", a["edit_site"])]
    if head.get("main"):
        buttons.append(button("Main building…", a["main"]))
    if "Pick survey lot lines…" in (head.get("actions") or []):
        buttons.append(button("Pick survey lot lines…", a["survey"]))
    if "Set grade…" in (head.get("actions") or []):
        buttons.append(button("Set grade…", a["grade"]))
    parts["box_buttons"] = buttons      # off while a start box is open (set_box_open)
    for b in buttons:
        b.Enabled = not parts.get("box_open")
    h.AddRow(row(*buttons))
    h.Create()


def set_box_open(parts, is_open):
    """While a start box is open, the panel's buttons that would open another (or change the site under it) are off."""
    if parts is None:
        return
    if bool(is_open) == bool(parts.get("box_open")):
        return
    parts["box_open"] = bool(is_open)
    zoom_ok = parts.get("selected") in (parts.get("by_id") or {}) and not parts.get("stale")
    others, zoom = logic.controls_enabled(is_open, zoom_ok)
    for c in list(parts.get("box_buttons") or []) + list(parts.get("greyed") or []):   # all but the legend
        c.Enabled = others
    if parts.get("zoom_button") is not None:
        parts["zoom_button"].Enabled = zoom


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
    words = logic.status_words(i)
    d.AddRow(_wide((i["mark"] + " " if i["mark"] else "") + logic.row_name(i) + " · " + words,   # the row's own name, whole
                   eto_status_color(i["status"]), bold=True, size=13))
    if parts.get("stale"):
        d.AddRow(_wide("Out of date: the model changed since this was checked.", size=11))
    for text in (det.get("line"), i.get("reason")):
        if text:
            d.AddRow(_wide(text, size=12))
    # what to do about it, right under the reason: a button where there is one (never its words twice, nor the
    # button scrolled out of sight below the measuring notes: the architect's review), else the hint's words
    buttons = []
    if i.get("needs"):                    # exactly the stated facts this row waits for, asked in turn
        buttons.append(button(logic.enter_words(i["needs"]) + "…", lambda: a["enter"](i["needs"])))
    if i.get("hint") == "Pick the main building…":
        buttons.append(button("Pick the main building…", a["main"]))
    if i["id"] == "scope.not_included":
        buttons.append(button("Add to check…", lambda: a["add"](i["objects"])))
        if i.get("ground_like"):              # only the architect's word leaves it out (never a guess)
            buttons.append(button("This is the ground", lambda: a["ground"](i["ground_like"])))
    for b in buttons:
        d.AddRow(row(b))
    words = logic.hint_text(i.get("hint"), [b.Text for b in buttons])
    if words:
        d.AddRow(_wide(words, size=12))
    for text in (det.get("at_limit"), det.get("colours"), det.get("calc"), det.get("scope")):
        if text:
            d.AddRow(_wide(text, size=12))
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
        link = ef.LinkButton()            # a link can't wrap: it fits the panel, shortened, the whole in its tip
        room = (WRAP_AT or PANEL_WIDTH - 48) if DOCKED else PANEL_WIDTH - 48
        link.Text = logic.link_text(c["citation"], int(room / 7.5))
        link.ToolTip = "Open " + c["citation"]
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


def spawn(args, run=False, **kw):
    """Every process Gordium starts from Rhino, the one place (a test checks there is no other): on Windows with no
    console window (rhino_logic.spawn_options). `run`: wait for it (subprocess.run), else start it (Popen)."""
    import subprocess
    kw.update(logic.spawn_options(os.name, subprocess))
    return subprocess.run(args, **kw) if run else subprocess.Popen(args, **kw)


def open_target(target):
    """A file or link opened with the computer's own app (Excel, a browser): os.startfile on Windows, `open` on
    macOS (rhino_logic.open_command). (opened, why not)."""
    how, what = logic.open_command(os.name, target)
    try:
        if how == "startfile":
            os.startfile(what)
            return True, None
        done = spawn(what, run=True, capture_output=True, text=True, timeout=20, encoding="utf-8")
        return done.returncode == 0, (done.stderr or "").strip()[:160] or None
    except Exception as e:
        return False, str(e)[:160]


def _open(url):
    try:
        return open_target(url)[0]
    except Exception:
        return False


def legend(code=None):
    """The legend, with which version of the law was checked (rhino_logic.legend_text)."""
    Rhino.UI.Dialogs.ShowMessage(logic.legend_text(code), "Gordium · legend")


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
    # no district set (the City map named one Gordium has no rules for): none preselected, Draw waits for a pick
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
    buffer = ef.TextBox() if mode == "start" and not logic.FLAT_GROUND else None   # (Advanced: off with flat ground)

    def confirmed(s, e):
        state["district_confirmed"] = bool(confirm.Checked)
        if buffer is not None:
            state["design_buffer"] = buffer.Text
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.draw_reason(state)

    confirm.CheckedChanged += logic.guard(confirmed, "confirm the district")

    zone_row = {}                     # the district row's source label, once laid out

    def zone_changed(s, e):           # a district picked: set at once, so Draw, its reason and the row's source follow
        logic.zone_picked(state, zone.SelectedValue.Text if zone.SelectedValue else None, first_zone)
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.draw_reason(state)
        if "source" in zone_row:
            zone_row["source"].Text = logic.zone_row_text(state).split(" · ", 1)[-1]

    zone.SelectedIndexChanged += logic.guard(zone_changed, "pick the district")
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
            zone_row["source"] = label(r["text"].split(" · ", 1)[-1], size=11)
            layout.AddRow(title, row(zone, zone_row["source"], confirm))
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
            if r.get("help"):          # what that row is, in a sentence (the front lot line's)
                layout.AddRow(None, row(label(r["help"], size=11)))
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

def text_box_size(lines, size=13):
    """The (width, height) draw_text_box gives these lines, in screen pixels."""
    return max(len(t) for t in lines) * (size * 0.6) + 22, len(lines) * (size + 9) + 10


NORTH_PX = 36                 # the north arrow's length on screen


def north_arrow(d, viewport, at, direction, color):
    """A small north arrow at model point `at`, pointing along `direction` (true north in the plan), with "N" past
    its tip: screen size, so it reads at any zoom. Returns its box on screen (x, y, w, h)."""
    import math
    a = viewport.WorldToClient(at)
    b = viewport.WorldToClient(at + direction)
    dx, dy = b.X - a.X, b.Y - a.Y
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    tip = System.Drawing.PointF(a.X + ux * NORTH_PX, a.Y + uy * NORTH_PX)
    d.Draw2dLine(System.Drawing.PointF(a.X, a.Y), tip, color, 2)
    for side in (1, -1):                      # the head: two short strokes back from the tip
        hx = tip.X - ux * 10 + side * (-uy) * 6
        hy = tip.Y - uy * 10 + side * ux * 6
        d.Draw2dLine(tip, System.Drawing.PointF(hx, hy), color, 2)
    d.Draw2dText("N", color, rg.Point2d(tip.X + ux * 10 - 5, tip.Y + uy * 10 - 8), False, 13)
    xs, ys = (a.X, tip.X, tip.X + ux * 10), (a.Y, tip.Y, tip.Y + uy * 10)
    return min(xs) - 12, min(ys) - 14, max(xs) - min(xs) + 24, max(ys) - min(ys) + 28    # its box: labels keep off

def draw_text_box(d, lines, color, x, y, dark, size=13, bold_first=True, border=None):
    """Lines of text on a backing box (F3), at screen point x, y (top left)."""
    width, height = text_box_size(lines, size)
    d.Draw2dRectangle(System.Drawing.Rectangle(int(x), int(y), int(width), int(height)),
                      border or color, 1, backing(dark))
    for k, t in enumerate(lines):
        ink = color if k == 0 else status_color("complies", dark)
        d.Draw2dText(t, ink, rg.Point2d(x + 11, y + 6 + k * (size + 9)), False, size if k == 0 else size - 1)
    return width, height


LINE_H = 16                              # one line of a plan label (11-12 px text), in screen pixels


def label_box(viewport, point, text, size=12, taken=None, along=None, obstacles=()):
    """Where label_at puts a label (screen pixels): (left, top, width, the top it wanted, its lines). Takes its spot
    in `taken`. With `along` (its dimension line) it goes beside that line, off every line in `obstacles` (the
    other dimensions, the lot's and the house's edges) and every label already placed, on screen; when no spot
    beside the line is clear for it on one line, on two (its name, then its numbers: logic.label_lines). Its height
    is 4 + LINE_H per line. The in-Rhino checks measure this very placement."""
    p = viewport.WorldToClient(point)
    width = logic.label_width(text, size)
    if along is not None:
        a, b = (viewport.WorldToClient(q) for q in along)
        own = ((a.X, a.Y), (b.X, b.Y))
        view = (viewport.Size.Width, viewport.Size.Height)
        left, top, clear = logic.place_label(own, width, 20, obstacles, taken or [], view=view)
        rows = [text]
        two = logic.label_lines(text)
        if not clear and len(two) == 2:          # too long to sit clear beside its line: name, then numbers
            w2 = max(logic.label_width(t, size) for t in two)
            l2, t2, c2 = logic.place_label(own, w2, 4 + 2 * LINE_H, obstacles, taken or [], view=view)
            if c2:
                left, top, width, clear, rows = l2, t2, w2, True, two
        h = 4 + LINE_H * len(rows)
        if not clear:                        # nowhere clear: at least off its own line and the other labels
            top = logic.clear_spot(taken if taken is not None else [], left, top, width, h, (own,))
        elif taken is not None:
            taken.append((left, top, width, h))
        return left, top, width, top, rows
    left, want = p.X - width / 2, p.Y - 10
    top = want if taken is None else logic.clear_spot(taken, left, want, width, 20)
    return left, top, width, want, [text]


def label_at(d, viewport, point, text, color, dark, size=12, taken=None, along=None, obstacles=(), leader=False):
    """A screen-size, horizontal label at a model point, on its backing box (F3). With `taken` (the labels
    already drawn this frame), it moves off any it would cover and a short leader points back to its spot. With
    `along` (a dimension line's two model points), it sits beside that line, never on it (on two lines if it must);
    with `leader` too, a line shorter on screen than its label gets a short leader from its middle to the label (a
    lot edge: logic.needs_leader)."""
    p = viewport.WorldToClient(point)
    left, top, width, want, rows = label_box(viewport, point, text, size, taken, along, obstacles)
    h = 4 + LINE_H * len(rows)
    if abs(top - want) > 1:
        d.Draw2dLine(System.Drawing.PointF(p.X, p.Y), System.Drawing.PointF(p.X, top + (h if top < p.Y else 0)),
                     color, 1)
    if leader and along is not None:
        a, b = (viewport.WorldToClient(q) for q in along)
        if logic.needs_leader(((b.X - a.X) ** 2 + (b.Y - a.Y) ** 2) ** 0.5, width):
            mid = ((a.X + b.X) / 2, (a.Y + b.Y) / 2)
            end = logic.leader_end(mid, (left, top, width, h))
            d.Draw2dLine(System.Drawing.PointF(mid[0], mid[1]), System.Drawing.PointF(end[0], end[1]), color, 1)
    d.Draw2dRectangle(System.Drawing.Rectangle(int(left), int(top), int(width), int(h)), color, 1, backing(dark))
    for k, row in enumerate(rows):
        d.Draw2dText(row, color, rg.Point2d(left + 7, top + 3 + LINE_H * k), False, size)


def _signed(bits):
    """A 32-bit dash mask as Rhino takes it: a signed Int32 (a mask with its top bit set overflows otherwise:
    "value too large to convert", caught by the guard 2026-10-20, so the dashed lines never drew)."""
    return bits - (1 << 32) if bits & (1 << 31) else bits


PHANTOM = _signed(0b11111111111111000110001100000000)    # long dash, short, short: the property line
DASHED = _signed(0b11111111000000001111111100000000)
