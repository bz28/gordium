#! python3
"""What the architect sees: the Gordium panel, the start box, and the drawing in the viewport
(docs/design/rhino_ui_spec.md). Rhino 8's Python (3.9), Eto and display drawing only; every number and word comes
from the checker's `view` (design_checker/present.py), so nothing here decides a result.

No class here extends an Eto or Rhino class: Rhino keeps the first .NET class made for a Python class for the
whole session (gordium_rhino.Overlay explains), so the panel and the dialog are plain Eto objects built by
functions, and an update to this file takes effect at once."""

import System
import math
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
COLUMNS = [("Item", 106), ("Proposed", 64), ("Required", 64), (logic.COLUMN_DELTA, 100)]   # Item takes the rest
# (Delta 100 px: a tax-map lot's two lines, "+2'-0⅜"" then "worst +0'-0⅜"", each one line, measured in Rhino
# 2026-10-29: "worst +12,033 sf" needs 99 px; Item's 106 is its least, it takes whatever the panel has)
ROW_HEIGHT = 36            # two lines: a long item name or "at least 1'-0" short" wraps instead of being cut off
#                           (Eto's tree grid has one height for every row: a third line would cost rows in view, so
#                           the values are made to fit two instead: logic.cell_text)
DETAIL_MIN_HEIGHT = 160   # the selected item's detail never shorter: its name and reason on up to four lines (17 px
#                           each) and two rows of buttons (20 px, measured on the Mac) in full without scrolling (the
#                           Rhino job at 7a16aa6: with the list a fixed 380 px and a taller header, the detail was 51 px
#                           and the parking row's button 1 px under it)
LIST_MIN_HEIGHT = 3 * ROW_HEIGHT + 24   # ...nor the list: three rows and its column titles (review round 1)
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


def dim_color(status, dark):
    """A dimension's colour (logic.dim_rgb): red fails, amber needs review, neutral grey complies."""
    r, g, b = logic.dim_rgb(status, dark)
    return System.Drawing.Color.FromArgb(r, g, b)


def required_color(dark):
    """A yard's required line and its "min" tag: clear mid-grey (logic.REQUIRED_RGB)."""
    r, g, b = logic.REQUIRED_RGB[1 if dark else 0]
    return System.Drawing.Color.FromArgb(r, g, b)


def halo(dark):
    """The thin halo under a dimension: near-black on a light viewport, near-white on a dark one."""
    return System.Drawing.Color.FromArgb(220, 245, 245, 245) if dark else System.Drawing.Color.FromArgb(220, 25, 25, 25)


def faint(color):
    """A colour at the required line's faint opacity (logic.FAINT_ALPHA)."""
    return System.Drawing.Color.FromArgb(logic.FAINT_ALPHA, color.R, color.G, color.B)


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
        set_zoom(parts)                      # on as soon as a row is picked (never waiting for the next redraw)
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
    split.Panel2MinimumSize = DETAIL_MIN_HEIGHT     # the list gives way first: it scrolls, the detail's button can't
    split.Panel1MinimumSize = LIST_MIN_HEIGHT       # ...down to three rows, never gone
    footer = row(button("Zoom to", lambda: actions["zoom"](parts["by_id"].get(parts["selected"]))),
                 button("Zoning report…", actions["report"]), button("?", actions["legend"]))
    parts["zoom_button"] = footer.Items[0].Control
    ticks = [row(_auto_box(actions, parts)), row(_envelope_box(actions, parts)), row(_massing_box(actions, parts)),
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


def _tick(box, action, where, skip=lambda: False):
    """A checkbox that calls `action(ticked)`; if the action was refused (logic.REFUSED: Gordium is working, or its
    file is no longer in front), the tick goes back, so the panel always shows the setting as it is (independent
    review of #32). `skip()`: a change made by Gordium itself (set_labels_tick), not the architect's."""
    putting_back = {"on": False}

    def changed(s, e):
        if putting_back["on"] or skip():
            return
        if action(bool(box.Checked)) is logic.REFUSED:
            putting_back["on"] = True
            try:
                box.Checked = not box.Checked
            finally:
                putting_back["on"] = False

    box.CheckedChanged += logic.guard(changed, where)


def _massing_box(actions, parts):
    """Hide starting house: the Gordium::Massing layer off. Hidden, it is still checked (a hidden building still
    counts, as everywhere in Gordium): only drawing it is turned off. Ticked as the document's layer is
    (set_massing_tick), never left as last clicked (an Undo puts the layer back: the Rhino job at 540f718)."""
    box = ef.CheckBox()
    box.Text = "Hide starting house"
    box.Checked = False
    # (set from the document by set_massing_tick: not the architect's change)
    _tick(box, actions["massing"], "hide the starting house", skip=lambda: parts.get("_setting_massing"))
    parts["massing_box"] = box
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


def set_massing_tick(parts, hidden):
    """The tick as this document's starting house layer is: ticked when it is hidden."""
    if parts is None or parts.get("massing_box") is None:
        return
    parts["_setting_massing"] = True
    try:
        parts["massing_box"].Checked = bool(hidden)
    finally:
        parts["_setting_massing"] = False


def _labels_box(actions, parts):
    """Show on-screen labels: each yard's and lot edge's label and the status box, off by default; remembered in the
    document."""
    box = ef.CheckBox()
    box.Text = "Show on-screen labels"
    box.Checked = False

    # (set from the document by set_labels_tick: not the architect's change)
    _tick(box, actions["labels"], "show or hide the on-screen labels", skip=lambda: parts.get("_setting_labels"))
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


def _envelope_box(actions, parts):
    """Show buildable envelope: on by default, this Rhino session's own setting (never saved in the file): ticked as
    it is (set_envelope_tick), never left as last clicked on a panel built again."""
    box = ef.CheckBox()
    box.Text = "Show buildable envelope"
    box.Checked = True
    # (set from the session by set_envelope_tick: not the architect's change)
    _tick(box, actions["envelope"], "show or hide the envelope", skip=lambda: parts.get("_setting_envelope"))
    parts["envelope_box"] = box
    return box


def set_envelope_tick(parts, on):
    """The tick as the session's envelope setting is."""
    if parts is None or parts.get("envelope_box") is None:
        return
    parts["_setting_envelope"] = True
    try:
        parts["envelope_box"].Checked = bool(on)
    finally:
        parts["_setting_envelope"] = False


def _wrap_width(parts):
    """Docked: the width labels wrap at, the panel's own width less its margins (an unbounded label ran off the
    docked panel's right edge: the architect's review, 2026-10-21); never below 240 px."""
    host = getattr(parts.get("form"), "host", None)
    width = getattr(host, "Width", 0) or 0
    return max(240, width - 48) if width > 0 else None


def show(parts, view, stale=False, error=None, checking=False, job=None, cancelled=False, select=None):
    """Fill the panel from the checker's view. Stale (the model changed and the check hasn't run again yet: the
    header says a check is on its way, or to press Check), a check running (`checking`; `job`: its live line and
    Cancel under "Checking…"), cancelled, or one that couldn't run: rows keep their names but show no mark and "—",
    Zoom to is off (H1, H2, H5). The selection and which groups are open are kept by item id across refreshes (D8);
    the list shows its first group's heading whole at the top, scrolled only as far as the selected row needs (the
    Rhino job at 6361a3f). `select`: a row to select and scroll to instead, its group opened (a re-check's newly
    failing row: logic.newly_failing). Selecting a row in code never takes the keyboard from the Rhino viewport (no
    Focus())."""
    global WRAP_AT
    WRAP_AT = _wrap_width(parts) if DOCKED else None
    tree = parts["tree"]
    parts["stale"] = stale or error is not None or checking or cancelled or job is not None
    if view is not None:
        parts["view"] = view
    view = parts["view"]
    _header(parts, view, error, checking or stale or job is not None, job, cancelled, checking)
    if view is None:
        tree.DataStore = ef.TreeGridItemCollection()
        parts["by_id"], parts["groups"] = {}, []
        show_detail(parts)
        return
    for g in parts.get("groups") or []:      # which groups were open, kept by group (D8)
        parts["expanded"][g.Tag] = g.Expanded
    by_id = {i["id"]: i for i in view["items"]}
    parts["by_id"] = by_id
    if select in by_id:                      # the newly failing row: selected, its group open, scrolled to below
        parts["selected"] = select
        for g in view["groups"]:
            if select in g["items"]:
                parts["expanded"]["group:" + g["key"]] = True
    store = ef.TreeGridItemCollection()
    selected_item = None
    parts["groups"] = []
    for g in view["groups"]:
        gi = ef.TreeGridItem()
        gi.Tag = "group:" + g["key"]
        title = ("Site · " if g["key"] == "complies" and all(by_id[i]["group"] == "site" for i in g["items"]) else "")
        gi.Values = System.Array[System.Object]([title + g["title"] + " · " + str(len(g["items"])), "", "", ""])
        gi.Expanded = parts["expanded"].get(gi.Tag, g["key"] not in ("complies", "not_covered", "use_details"))
        for item_id in g["items"]:
            i = by_id[item_id]
            stale_row = parts["stale"] and i["status"] != "not_checked"
            # the values in the list's own short form (logic.cell_text: "34'-11⅞"–" over two lines, never cut)
            name, proposed, required, delta = logic.list_values(i)   # the use row: the use's own name as its Item;
            values = [("" if stale_row else i["mark"] + "  ") + name,   # a tax-map Delta and a span: their short forms
                      "—" if stale_row else logic.cell_text(proposed if i["status"] != "not_checked" else ""),
                      "" if stale_row else logic.cell_text(required),
                      "" if stale_row else logic.cell_text(delta)]
            ci = ef.TreeGridItem()
            ci.Tag = item_id
            ci.Values = System.Array[System.Object](values)
            gi.Children.Add(ci)
            if item_id == parts["selected"]:
                selected_item = ci
        store.Add(gi)
        parts["groups"].append(gi)
    tree.DataStore = store
    shape = tuple((gi.Tag, gi.Expanded, gi.Children.Count) for gi in parts["groups"])
    if shape != parts.get("shape"):         # a new list (first fill, rows or groups changed): its first group's heading
        _scroll_to(tree, 0, len(shape))     # whole at the top, never half under the column titles (the Rhino job at
    parts["shape"] = shape                  # 6361a3f); the same rows again (every live refresh): where it was (review)
    if selected_item is not None:           # SelectedItem is read-only here: select by row in the visible list
        k = 0
        for gi in parts["groups"]:
            if gi.Expanded:
                for c in range(gi.Children.Count):
                    if gi.Children[c] is selected_item or gi.Children[c].Tag == selected_item.Tag:
                        tree.SelectedRow = k + 1 + c
                        _scroll_to(tree, k + 1 + c, k + 2 + c)    # the selected row just into view
                k += gi.Children.Count
            k += 1
    set_zoom(parts)
    show_detail(parts)


def _scroll_to(tree, row, rows):
    """The list scrolled just enough to show `row` whole (Eto's Grid.ScrollToRow: row 0 puts the first group's
    heading under the column titles; a later row only moves the list as far as it must). Never on an empty list
    (`rows`: how many it has; Windows' Eto indexes the row), and never an error out of it: scrolling is a nicety."""
    scroll = getattr(tree, "ScrollToRow", None)
    if scroll is not None and 0 <= row < rows:
        try:
            scroll(row)
        except Exception:
            pass


def _header(parts, view, error, out_of_date, job=None, cancelled=False, checking=False):
    h = parts["header"]
    h.Clear()
    a = parts["actions"]
    head = (view or {}).get("header") or {}
    lines = logic.panel_header(head)
    parts["progress_label"], parts["progress_job"] = None, job
    h.AddRow(_wide(lines["above"][0], bold=True, size=13))
    if error is not None:
        h.AddRow(row(_wide("⚠ Check could not run", eto_status_color("needs_review"), bold=True, size=15),
                     button("Retry", a["retry"])))
        h.AddRow(_wide(error, size=11))
    elif cancelled:                        # nothing shown as checked until the next check
        h.AddRow(row(_wide(logic.CHECK_CANCELLED, eto_status_color("needs_review"), bold=True, size=15),
                     button("Check again", a["retry"])))
        h.AddRow(_wide(logic.CHECK_CANCELLED_NOTE, size=11))
    elif out_of_date and (checking or job is not None):   # a check running: what it is doing, the seconds, Cancel
        h.AddRow(_wide("Checking…", bold=True, size=15))
        if job is not None:
            parts["progress_label"] = label(progress_text(job), size=11, width=PANEL_WIDTH - 140)
            h.AddRow(row(parts["progress_label"], button("Cancel", job.cancel)))
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


def progress_text(job, limit=None):
    """A running job's line: what it is doing now, then the moving mark and the seconds so far."""
    return (job.step or "Working…") + "  " + logic.progress_line(job.elapsed(), limit)


def show_progress(parts, job):
    """The panel's live line under "Checking…", moved on (the timer that waits for the job calls this)."""
    lab = (parts or {}).get("progress_label")
    if lab is not None:
        lab.Text = progress_text(job)


def follow(parts, job):
    """The panel follows a running check: "Checking…" with this job's live line and Cancel (laid out once, on the
    first tick), then the line moved on at each tick (review round 1: a check the architect started never showed it)."""
    if parts is None:
        return
    if parts.get("progress_job") is not job or parts.get("progress_label") is None:
        show(parts, None, checking=True, job=job)
    show_progress(parts, job)


WAIT_SHOWN = None          # the in-Rhino test's hook: called with the wait window's labels each time they are set


def take_keyboard(form):
    """The wait window made the key window, so Esc reaches it: Eto's own Focus, and on the Mac the window's own
    makeKeyAndOrderFront (Rhino run of 65c07d7: Eto reported no focus after BringToFront and Focus). Never raises."""
    for step in (lambda: form.BringToFront(), lambda: form.Focus(),
                 lambda: form.ControlObject.MakeKeyAndOrderFront(form.ControlObject)):
        try:
            step()
        except Exception:
            pass


def has_keyboard(form):
    """Whether the window has the keyboard (Esc reaches it): Eto's HasFocus, or on the Mac the window being the key
    window. False when neither can be read."""
    try:
        if form.HasFocus:
            return True
    except Exception:
        pass
    try:
        return bool(form.ControlObject.IsKeyWindow)
    except Exception:
        return False


def wait(job, cancellable=False, headless=False, on_tick=None, limit=None):
    """Wait for a job (logic.Job) without ever blocking Rhino: work done within logic.WAIT_WINDOW_S shows nothing;
    longer, a small window says what Gordium is doing (the job's own step, a moving mark, the seconds so far) with
    Cancel when `cancellable` (Esc too, with this window in front: logic.STOP_HINT says so). The window is a plain one, not modal, and this loop itself keeps it current
    while it lets Rhino run (Rhino.RhinoApp.Wait: Rhino draws and answers between passes). Nothing here depends on a
    modal session or a timer: on the Mac a wait window's timer never ran and a closed dialog stayed painted when a
    modal was ended from a timer and another opened (Rhino runs of #32 aea73b8 and #33 a3eb1d7: frozen "0 s"). The
    window closes as soon as the job is done or cancelled; its own close button cancels the work, or (not
    cancellable) is refused until it is done. `on_tick(job)` runs at each pass too (the panel's live line). While it
    waits, the panel's buttons say Gordium is busy (gordium_rhino._actions); live mode starts no check (asking).
    Headless (the scripted tests): just waits."""
    if job.wait(logic.WAIT_WINDOW_S if not headless else 0):
        return
    if headless:
        while not job.wait(0.2):
            pass
        return
    form = ef.Form()
    form.Title = "Gordium"
    form.Padding = ed.Padding(16)
    form.Resizable = form.Minimizable = form.Maximizable = False
    form.Topmost = True
    step = label(job.step, bold=True, size=13, width=380)
    line = label(logic.progress_line(job.elapsed(), limit), size=11, width=380)
    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    layout.AddRow(step)
    layout.AddRow(line)
    state = {"done": False}

    def cancel():
        if job.cancel():
            step.Text = logic.CANCELLING
        if stop is not None:
            stop.Enabled = False

    stop = button("Cancel", cancel) if cancellable else None
    hint = label(logic.STOP_HINT_CLICK, size=11)   # "Esc or Cancel" only once the window has the keyboard
    if stop is not None:                  # (Esc stops it only here: elsewhere in Rhino Esc keeps its own meaning)
        layout.AddRow(row(stop, hint))

    def key(s, e):                        # Esc, with this window in front: Cancel
        if e.Key == ef.Keys.Escape and cancellable:
            e.Handled = True
            cancel()

    def closing(s, e):                    # the window's own close button: Cancel, or keep waiting
        if not state["done"]:
            if cancellable:
                cancel()
            e.Cancel = not job.finished()

    form.Content = layout
    form.KeyDown += logic.guard(key, "cancel with Esc")
    form.Closing += logic.guard(closing, "close the progress window")
    # Esc cancels only with this window in front (or Cancel clicked): an Esc elsewhere in Rhino keeps Rhino's own
    # meaning (end a command, clear a selection) and never silently cancels a check or a Draw (coordinator, 2026-10-26)
    form.Show()
    take_keyboard(form)
    try:
        while not job.finished():
            Rhino.RhinoApp.Wait()          # Rhino draws and answers (the panel, the viewports) between passes
            step.Text = job.step or ""
            line.Text = logic.progress_line(job.elapsed(), limit)
            focused = has_keyboard(form)   # Esc is promised only while it works (Rhino run of 65c07d7)
            if cancellable:
                hint.Text = logic.STOP_HINT if focused else logic.STOP_HINT_CLICK
            if WAIT_SHOWN is not None:
                WAIT_SHOWN(step.Text, line.Text, focused, hint.Text)
            if on_tick is not None:
                logic.guard(on_tick, "show what Gordium is doing")(job)
            job.wait(0.05)
    finally:
        state["done"] = True
        logic.guard(form.Close, "close the progress window")()
def set_zoom(parts):
    """Zoom to on or off for the panel as it is now, its tooltip saying why when off (logic.zoom_state)."""
    b = parts.get("zoom_button")
    if b is None:
        return
    b.Enabled, b.ToolTip = logic.zoom_state(parts.get("selected") in (parts.get("by_id") or {}),
                                            parts.get("stale"), parts.get("box_open"))


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
        set_zoom(parts)                      # (logic.zoom_state agrees with `zoom`: off while a box is open)


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
                if logic.can_switch(s):             # one larger side yard: put it on the other side (one Undo)
                    d.AddRow(row(button(logic.SWITCH_LABEL, a["switch_sides"])))
        d.Create()
        return
    det = i["detail"]
    words = logic.status_words(i)
    d.AddRow(_wide((i["mark"] + " " if i["mark"] else "") + logic.list_cells(i)[0] + " · " + words,   # the row's own name, whole
                   eto_status_color(i["status"]), bold=True, size=13))
    if parts.get("stale"):
        d.AddRow(_wide("Out of date: the model changed since this was checked.", size=11))
    for text in (det.get("line"), i.get("reason")):
        if text:
            d.AddRow(_wide(text, size=12))
    # what to do about it, right under the reason: a button where there is one (never its words twice, nor the
    # button scrolled out of sight below the measuring notes: the architect's review), else the hint's words
    buttons = []
    for words, what in logic.row_buttons(i):     # its own small dialog for the stated facts it waits on; Edit site…
        if what == "enter":                      # where a site fact is missing (logic.row_buttons)
            buttons.append(button(words, lambda: a["enter"](i["needs"])))
        else:
            buttons.append(button(words, a["edit_site"]))
    if i.get("hint") == "Pick the main building…":
        buttons.append(button("Pick the main building…", a["main"]))
    if i.get("hint") == "Pick the ADU's building…":
        buttons.append(button("Pick the ADU's building…", a["adu"]))
    if i["id"] == "scope.not_included":
        buttons.append(button("Add to check…", lambda: a["add"](i["objects"])))
        if i.get("ground_like"):              # only the architect's word leaves it out (never a guess)
            buttons.append(button("This is the ground", lambda: a["ground"](i["ground_like"])))
    for b in buttons:
        d.AddRow(row(b))
    words = logic.hint_text(i.get("hint"), [b.Text for b in buttons])
    if words:
        d.AddRow(_wide(words, size=12))
    split = logic.detail_parts(det)         # plain words in view; the formula and the chart's shorthand behind a toggle
    for text in split["notes"]:
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
    for q in split["quotes"]:
        _quote_rows(d, q)
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
    if split["worked"] or split["worked_quotes"]:       # How it's worked out: collapsed until opened, then kept open
        toggle = ef.LinkButton()
        toggle.Text = ("▾ " if parts.get("worked_out") else "▸ ") + logic.WORKED_OUT
        toggle.Click += logic.guard(lambda s, e: _toggle_worked_out(parts), "show how it's worked out")
        d.AddRow(toggle)
        if parts.get("worked_out"):
            for text in split["worked"]:
                d.AddRow(_wide(text, size=11))
            for q in split["worked_quotes"]:              # the chart's own cell, with where it is from
                _quote_rows(d, q)
    d.Add(None)
    d.Create()


def _quote_rows(d, q):
    """One quote of the code's words, and where it is from."""
    d.AddRow(_wide("“" + q["text"] + "”", size=12))
    if q.get("where"):
        d.AddRow(_wide(q["where"], size=11))


def _toggle_worked_out(parts):
    """Open or close How it's worked out (the panel remembers it while it is open, for every row)."""
    parts["worked_out"] = not parts.get("worked_out")
    show_detail(parts)


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

def native_number(value):
    """A Mac native number (NFloat, nint) as a Python float: directly, or through its text where the bridge won't
    convert it (as review_fixes_in_rhino.py reads a window number: int(str(...)))."""
    try:
        return float(value)
    except Exception:
        return float(str(value))


def keep_on_screen(window):
    """A window grown downwards moved up as far as needed to stay within its screen's working area. Never raises."""
    try:
        area = window.Screen.WorkingArea
        bottom = window.Location.Y + window.Height
        if bottom > area.Bottom:
            window.Location = ed.Point(int(window.Location.X), int(max(area.Top, area.Bottom - window.Height)))
    except Exception:
        pass


def row_rect(table, index):
    """Where an NSTableView lays out row `index`. Rhino's Mac binding names this RectForRow and takes an IntPtr
    (not RectOfRow, which only Cocoa's own spelling has, and not a plain int: Rhino run of c4ad070)."""
    return table.RectForRow(System.IntPtr(int(index)))


def list_row_px(listbox):
    """A list's row pitch in px as Rhino lays it out: on the Mac the ListBox is a table whose row height plus spacing
    is read from it; elsewhere (or if it can't be read) logic.LIST_ROW_PX."""
    try:
        table = listbox.ControlObject      # Eto.macOS: the NSTableView itself (its NSScrollView is the handler's own)
        # where the table lays its rows out, not the row height it reports (Rhino run of df08fc0: rows painted about
        # 16 pt apart while RowHeight + spacing said 24, leaving an empty band under eight rows)
        if int(native_number(table.RowCount)) >= 2:
            pitch = native_number(row_rect(table, 1).Y) - native_number(row_rect(table, 0).Y)
        else:
            pitch = native_number(row_rect(table, 0).Height) + native_number(table.IntercellSpacing.Height)   # (a row's own rect
            #   leaves out the gap under it; two rows' Y difference above already has it)
        return int(math.ceil(pitch - 1e-6)) if 10 <= pitch <= 60 else logic.LIST_ROW_PX   # up: never a row short
    except Exception:
        return logic.LIST_ROW_PX


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
    # the district's chart's uses, permitted first, and the use set even if not listed (never changed unasked)
    names = list(state.get("use_choices") or logic.district_use_names(options, state.get("zone"), state.get("use")))
    for _, n in names:
        use.Items.Add(n)
    ids = [k for k, _ in names]
    use.SelectedIndex = ids.index(state.get("use")) if state.get("use") in ids else 0
    laid_out = (state.get("zone"), names[use.SelectedIndex][0] if names else None,
                logic.gate_of(state.get("answers")))      # what the Use rows and "About this project" show
    asked = {}                        # each follow-up question's (kind, field, choices): the facts the rules need

    def answer_of(key):               # what a question's field says now: its value, or None (blank / not a number)
        kind, field, choices = asked[key]
        if choices is not None:       # a one-click dropdown: "Not answered" first, then the choices in order
            at = max(field.SelectedIndex, 0)
            return choices[at - 1][1] if at > 0 else None
        try:
            return logic.parse_answer(kind, field.Text, key)
        except ValueError:
            return None
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
        answers = dict(state.get("answers") or {})
        for key in asked:                              # a blank stays unanswered (its rules: NEEDS REVIEW)
            answers[key] = answer_of(key)
        state["answers"] = answers
        if corner.SelectedIndex != first["corner"]:
            state["corner_source"] = logic.ENTERED


    def pick(what):
        keep()
        done("pick:" + what)

    draw = button(state.get("_draw_label") or ("Draw" if mode == "start" else "Check"),   # as what it does
                  lambda: (keep(), done("draw")))
    reason = label(logic.box_reason(state), size=11, width=logic.BOX_TEXT_WIDTH)   # wraps at the box's width
    looking = bool((state.get("lookup") or {}).get("looking"))
    draw.Enabled = logic.can_draw(state) and not looking

    # type-ahead: the City's addresses starting like the one typed (logic.wants_suggestions, ~0.3 s after the last
    # key), in a list under it; Down/Up move in it, Enter or a click picks, Esc closes it; a stale answer is dropped
    # (logic.suggestions_shown) and an earlier request stopped; offline or slow: a quiet note, typing still works
    suggester = state.get("_suggest") if not looking else None
    hints = {"items": [], "chosen": None}
    hint_list = ef.ListBox()
    hint_list.Width, hint_list.Height = 300, logic.list_height(1)
    hint_list.Visible = False
    hint_note = label("", size=10)
    hint_note.Visible = False
    hint_rows = ef.StackLayout()      # the list and its note as one row, hidden while both are empty: no gap under
    hint_rows.Orientation = ef.Orientation.Vertical       # Address (the architect's review, 2026-10-28)
    hint_rows.Items.Add(ef.StackLayoutItem(hint_list))
    hint_rows.Items.Add(ef.StackLayoutItem(hint_note))
    hint_rows.Visible = False

    def show_hint_rows():
        hint_note.Visible = bool(hint_note.Text)
        hint_rows.Visible = logic.hint_rows_shown(hint_list.Visible, hint_note.Text)
    wait_keys = ef.UITimer()
    wait_keys.Interval = logic.SUGGEST_DELAY_S
    wait_answer = ef.UITimer()
    wait_answer.Interval = 0.1

    grown = {"px": 0}                 # how much taller the box is for the list now showing

    def fit_box():
        """The box grows by the list's height while it shows (and back when it goes), kept on screen, so Cancel and
        Draw never go off its bottom (Rhino run of ee8f2ce: the box kept its height and pushed them off)."""
        want = logic.hint_rows_px(hint_list.Visible, hint_list.Height, hint_note.Text)   # the note's line too
        delta = want - grown["px"]
        if delta:
            size = dialog.ClientSize
            dialog.ClientSize = ed.Size(size.Width, size.Height + delta)
            grown["px"] = want
            keep_on_screen(dialog)

    def hide_hints():
        hints["items"] = []
        hint_list.Items.Clear()
        hint_list.Visible = False
        show_hint_rows()
        fit_box()

    def pick_hint(index):
        if 0 <= index < len(hints["items"]):
            hints["chosen"] = hints["items"][index]
            hide_hints()
            address.Text = hints["chosen"]            # (TextChanged: Draw and its reason follow; no new list)
            address.Focus()

    def ask_hints(s, e):
        wait_keys.Stop()
        if suggester is None:
            return
        if not logic.wants_suggestions(address.Text, hints["chosen"]):
            suggester["stop"]()
            wait_answer.Stop()
            hint_note.Text = ""
            hide_hints()                             # (after the note is cleared: the rows fold away)
            return
        suggester["start"](address.Text)            # (stops one still running: its answer would be stale)
        wait_answer.Start()

    def got_hints(s, e):
        answer = suggester["poll"]() if suggester is not None else None
        if answer is None:
            return
        wait_answer.Stop()
        shown = logic.suggestions_shown(answer, address.Text)
        if shown is None:                            # for something no longer typed
            return
        items, note = shown
        hint_note.Text = note
        hide_hints()
        hints["items"] = items
        for item in items:
            hint_list.Items.Add(item)
        hint_list.Height = logic.list_height(len(items), list_row_px(hint_list))   # as tall as its rows, no empty rows
        hint_list.Visible = bool(items)
        show_hint_rows()
        fit_box()

    wait_keys.Elapsed += logic.guard(ask_hints, "ask for address suggestions")
    wait_answer.Elapsed += logic.guard(got_hints, "show address suggestions")
    hint_list.Tag = pick_hint                       # (the in-Rhino test picks through the list's own pick)
    hint_list.MouseUp += logic.guard(lambda s, e: pick_hint(hint_list.SelectedIndex), "pick a suggested address")
    hint_list.Activated += logic.guard(lambda s, e: pick_hint(hint_list.SelectedIndex), "pick a suggested address")

    def enter_looks_up(s, e):          # Enter in the address: Look up (not Draw, the box's default button)
        if hint_list.Visible and e.Key in (ef.Keys.Down, ef.Keys.Up):         # move in the list, keys stay here
            e.Handled = True
            hint_list.SelectedIndex = logic.list_step(hint_list.SelectedIndex, len(hints["items"]),
                                                      "down" if e.Key == ef.Keys.Down else "up")
            return
        if hint_list.Visible and e.Key == ef.Keys.Escape:                       # close the list, not the box
            e.Handled = True
            hide_hints()
            return
        if e.Key == ef.Keys.Enter and hint_list.Visible and hint_list.SelectedIndex >= 0:
            e.Handled = True                                                    # Enter picks; Enter again: Look up
            pick_hint(hint_list.SelectedIndex)
            return
        if e.Key == ef.Keys.Enter and not looking:
            e.Handled = True
            pick("lookup")

    address.KeyDown += logic.guard(enter_looks_up, "look up the address")

    def address_typed(s, e):           # Draw off for an address not looked up, on again when the known one is back
        state["address"] = address.Text
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.box_reason(state)
        if suggester is not None:      # the list waits for a pause in the typing
            if address.Text != hints["chosen"]:     # typed on: the list was for older typing, so it goes (round 2)
                hint_list.SelectedIndex = -1   # and Enter looks up what is typed, never an older pick (round 1)
                hide_hints()
            wait_keys.Stop()
            wait_keys.Start()

    address.TextChanged += logic.guard(address_typed, "follow the address typed")
    # the design buffer sizes the starting house, so it is set when starting (GordiumStart), not in Edit site…
    buffer = ef.TextBox() if mode == "start" and not logic.FLAT_GROUND else None   # (Advanced: off with flat ground)

    def confirmed(s, e):
        state["district_confirmed"] = bool(confirm.Checked)
        if buffer is not None:
            state["design_buffer"] = buffer.Text
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.box_reason(state)

    confirm.CheckedChanged += logic.guard(confirmed, "confirm the district")

    zone_row = {}                     # the district row's source label, once laid out

    def zone_changed(s, e):           # a district picked: set at once, so Draw, its reason and the row's source follow
        logic.zone_picked(state, zone.SelectedValue.Text if zone.SelectedValue else None, first_zone)
        confirm.Checked = bool(state.get("district_confirmed"))     # another district: confirm it again
        draw.Enabled = logic.can_draw(state) and not looking
        reason.Text = logic.box_reason(state)
        if "source" in zone_row:
            zone_row["source"].Text = logic.zone_row_text(state).split(" · ", 1)[-1]
        refresh_if_needed()

    def refresh_if_needed():          # another use or district: its own uses, note and questions, so the box opens
        z = zone.SelectedValue.Text if zone.SelectedValue else None       # again with them (rhino_logic decides;
        gate = logic.gate_of({k: answer_of(k) for k in logic.ASKED_AFTER.values() if k in asked})
        if not looking and logic.box_needs_refresh(                       # a lookup's answer opens it again anyway)
                options, laid_out, (z, names[use.SelectedIndex][0] if names else None, gate)):
            pick("refresh")

    zone.SelectedIndexChanged += logic.guard(zone_changed, "pick the district")

    def use_changed(s, e):
        refresh_if_needed()

    use.SelectedIndexChanged += logic.guard(use_changed, "pick the use")
    cancel = button("Cancel", lambda: done(None))
    status = {}                       # the running lookup's live line, once laid out

    def fit(text, room, **kw):        # a label that wraps at `room` px when its text is wider (logic.text_wider)
        return label(text, width=room if logic.text_wider(text, kw.get("size"), room) else None, **kw)

    def about_section(layout, questions):
        """"About this project": the facts only the architect knows that this district's rules need for the use
        (rhino_logic.follow_up_rows, from the rulebook), compact: a quick-answers dropdown, then one question a row,
        each a one-click dropdown (or, for a number, a field) that starts on "Not answered". The full question is its
        hover text. The box stays laptop-sized (logic.ABOUT_*; pinned in test_box_width.py)."""
        note = label(logic.FOLLOW_UP_HELP, size=11, width=logic.ABOUT_NOTE_WIDTH)

        def typed(s, e, plain=note.TextColor):    # an entry that isn't an answer: said at once, never kept
            text, refused = logic.answers_note([(k, kind, f.Text) for k, (kind, f, ch) in asked.items()
                                                if ch is None])
            note.Text = text
            note.TextColor = eto_status_color("needs_review") if refused else plain

        filling = []                       # non-empty while a quick answer sets several fields: one refresh at the end
        cells = []
        for q in questions:
            if q["choices"] is not None:
                field = ef.DropDown()
                for t in [logic.NOT_ANSWERED] + [w for w, _ in q["choices"]]:
                    field.Items.Add(t)
                values = [v for _, v in q["choices"]]
                field.SelectedIndex = values.index(q["value"]) + 1 if q["value"] in values else 0
                field.Width = logic.ABOUT_FIELD_WIDTH
                if q["key"] in logic.ASKED_AFTER.values():      # another question waits on this one: open it
                    field.SelectedIndexChanged += logic.guard(
                        lambda s, e: None if filling else refresh_if_needed(), "answer the question")
            else:                                  # typed: a number (any other kind is never a yes / no)
                field = ef.TextBox()
                field.Width = logic.ABOUT_TYPED_WIDTH
                field.Text = "" if q["value"] is None else str(q["value"])
                field.TextChanged += logic.guard(typed, "type the answer")
            field.ToolTip = q["label"]
            asked[q["key"]] = (q["kind"], field, q["choices"])
            name = label(q["short"], size=12, width=logic.ABOUT_LABEL_WIDTH)
            name.ToolTip = q["label"]
            cells += [name, field]
        grid = ef.DynamicLayout()
        grid.Padding = ed.Padding(0)
        grid.Spacing = ed.Size(8, 2)       # 2 px between questions: seven and the quick answers fit a laptop
                                           # (the ADU question asked up front, 2026-10-30)
        quick = logic.quick_answers([q["key"] for q in questions])
        if quick:                          # several answers in one click; the fields it fills stay editable
            picker = ef.DropDown()
            for t in [logic.QUICK_HINT] + [w for w, _ in quick]:
                picker.Items.Add(t)
            picker.SelectedIndex = 0
            picker.Width = logic.ABOUT_QUICK_WIDTH

            def quick_picked(s, e):
                at = max(picker.SelectedIndex, 0)
                if at == 0:
                    return
                filling.append(True)
                try:
                    for key, value in quick[at - 1][1].items():
                        kind, field, choices = asked[key]
                        field.SelectedIndex = [v for _, v in choices].index(value) + 1
                    picker.SelectedIndex = 0  # ready to pick another
                finally:
                    filling.clear()
                refresh_if_needed()

            picker.SelectedIndexChanged += logic.guard(quick_picked, "pick a quick answer")
            grid.AddRow(label("Quick answers", size=12, width=logic.ABOUT_LABEL_WIDTH), picker)
        for k in range(0, len(cells), 2):     # one question a row: the second column stays laptop-sized
            grid.AddRow(*cells[k:k + 2])
        # its title in the box's first column and its questions in the second, as every other row: a one-cell row
        # is NOT spread across the columns by Eto on the Mac: it sits in the first and widens it (the demo 7 Rhino run,
        # 2026-10-28: the grid there made the box 1,162 pt wide)
        title = label("About this project", bold=True)
        title.VerticalAlignment = ef.VerticalAlignment.Top     # level with its first question, never centred beside
        layout.AddRow(title, grid)                              # the whole grid (the architect's review, 2026-10-28)
        layout.AddRow(None, note)

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 6)
    for r in logic.box_rows(state):
        key, title = r["key"], label(r["label"], bold=True)
        if key == "address":
            layout.AddRow(title, row(address, *[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            if suggester is not None:      # the type-ahead list (hidden until there is one) and its quiet note
                layout.AddRow(None, hint_rows)
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
            if r.get("status"):            # Looking up 106 Ithaca Rd · Finding the address…  ○●○  3 s (live;
                status["label"] = label(r["status"], size=11, width=560)   # Cancel lookup stops it)
                layout.AddRow(None, row(status["label"]))
        elif key == "zone":
            confirm.Text = r["tick"][0]
            zone_row["source"] = fit(r["text"].split(" · ", 1)[-1], 260, size=11)
            layout.AddRow(title, row(zone, zone_row["source"], confirm))
        elif key == "use":
            layout.AddRow(title, use)
            if state.get("use_note"):  # a pick the chart doesn't permit by right: said, with the chart's page
                layout.AddRow(None, row(label(state["use_note"], eto_status_color("needs_review"), size=11,
                                              width=560)))
            questions = state.get("follow_ups") or []     # what this district's rules need for the use
            if questions:
                about_section(layout, questions)
        elif key == "ground":
            layout.AddRow(title, row(fit(r["text"], 560, size=12)))          # left aligned, as the others
            layout.AddRow(None, row(*[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            regrade.Text = r["tick"][0]
            layout.AddRow(None, regrade)
        else:                          # lot, street side: what it is, and the one way to change it
            layout.AddRow(title, row(fit(r["text"], 360, size=12),
                                     *[button(t, (lambda a=a: pick(a)), on) for a, t, on in r["actions"]]))
            if r.get("help"):          # what that row is, in a sentence (the front lot line's)
                layout.AddRow(None, row(label(r["help"], size=11, width=560)))
            if r.get("choice"):        # the street side's question: Corner lot?
                layout.AddRow(None, row(fit(r["choice"][0], 300, size=12), corner))
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
    amber = label("", eto_status_color("needs_review"), size=12, width=logic.BOX_TEXT_WIDTH)   # wraps at the box
    amber_row = row(amber)            # shown only while it asks something: empty, it was a blank line in the box
    note = label(logic.lookup_note(state) or "", size=11)             # what a found lookup tells: plain, not amber

    def refresh_amber(*_):
        state["corner_lot"] = [None, False, True][max(corner.SelectedIndex, 0)]
        text = logic.uncertain(state)
        amber.Text = "?  " + text if text else ""
        amber_row.Visible = bool(text)
        if text and dialog.Loaded:     # back after an answer was taken away: the box grows to show it (never shrinks)
            grown = logic.grown_height(dialog.ClientSize.Height, layout.GetPreferredSize().Height,
                                       dialog.Padding.Top + dialog.Padding.Bottom)
            if grown is not None:
                dialog.ClientSize = ed.Size(dialog.ClientSize.Width, grown)

    refresh_amber()
    corner.SelectedIndexChanged += logic.guard(refresh_amber, "answer the corner lot")
    layout.AddRow(None, amber_row)
    if note.Text:                     # nothing found to tell: no empty line in the box (it made the box taller)
        layout.AddRow(None, row(note))
    layout.AddRow(None, row(reason))
    layout.AddRow(None, row(cancel, draw))
    dialog.Content = layout
    dialog.DefaultButton = draw
    dialog.AbortButton = cancel
    shown = state.get("_on_shown")            # for the in-Rhino test: capture the real box, then close it
    if shown is not None:
        dialog.Shown += logic.guard(lambda s, e: shown(dialog), "run the start box hook")
    poll = state.get("_poll")                 # a lookup running in its own process: the box closes itself when it
    progress = state.get("_progress")         # answers (or the time runs out), and opens again filled in; until
    if looking and poll is not None:          # then its line says what it is doing, live
        timer = ef.UITimer()
        timer.Interval = 0.25

        def tick(s, e):
            if poll() is not None:
                timer.Stop()
                keep()
                done("pick:lookup_done")
            elif progress is not None and status.get("label") is not None:
                status["label"].Text = progress()

        timer.Elapsed += logic.guard(tick, "wait for the address lookup")
        dialog.Shown += logic.guard(lambda s, e: timer.Start(), "start waiting for the lookup")
        dialog.Closed += logic.guard(lambda s, e: timer.Stop(), "stop waiting for the lookup")

    def closed(s, e):                  # the type-ahead stops with the box
        wait_keys.Stop()
        wait_answer.Stop()
        if suggester is not None:
            suggester["stop"]()

    dialog.Closed += logic.guard(closed, "stop the address suggestions")
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return chosen.get("what")


def row_dialog(title, fields, check):
    """A row's own small dialog (logic.row_fields): one line per stated fact the row waits on, a count typed or a
    yes / no picked ("Not answered" first), and [Cancel] [OK]. OK calls `check(answers)` (answers: key -> text, "yes",
    "no" or "" for blank): words back keep the dialog open with them shown; None closes it. Returns the answers on
    OK, or None (Cancel, Esc, closed: the caller changes nothing)."""
    dialog = ef.Dialog[bool]()
    dialog.Title = title
    dialog.Padding = ed.Padding(14)
    dialog.Resizable = False
    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    asked, chosen = {}, {}
    for q in fields:
        if q["kind"] == "yes_no":
            field = ef.DropDown()
            for t in (logic.NOT_ANSWERED,) + logic.yes_no_words(q["key"]):
                field.Items.Add(t)
            field.SelectedIndex = logic.row_choice(q["value"])
            field.Width = logic.ANSWER_WIDTH           # every dropdown the same width: lined up
        else:                                  # a count: typed, blank when not answered (never 0)
            field = ef.TextBox()
            field.Width = 60
            field.Text = "" if q["value"] is None else str(q["value"])
        asked[q["key"]] = (q["kind"], field)
        layout.AddRow(row(label(q["label"], size=12, width=logic.QUESTION_WIDTH), field))
    note = label(logic.FOLLOW_UP_HELP, size=11, width=logic.QUESTION_WIDTH + 80)
    layout.AddRow(row(note))

    def answers():
        return {k: logic.row_choice_text(f.SelectedIndex) if kind == "yes_no" else f.Text
                for k, (kind, f) in asked.items()}

    def ok():
        got = answers()
        problem = check(got)
        if problem:                            # not an answer: said, and the dialog stays open (nothing saved)
            note.Text = problem
            note.TextColor = eto_status_color("needs_review")
            return
        chosen["answers"] = got
        dialog.Close(True)

    done = button("OK", ok)
    cancel = button("Cancel", lambda: dialog.Close(False))
    layout.AddRow(row(cancel, done))
    dialog.Content = layout
    dialog.DefaultButton = done
    dialog.AbortButton = cancel
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return chosen.get("answers")


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




def label_box(viewport, point, text, size=12, taken=None, along=None, obstacles=(), keep=None, dims=(), solids=(),
              cache=None):
    """Where label_at puts a label (screen pixels): (left, top, width, the top it wanted, its lines, whether it is led
    to its line, its text size, whether a HARD rule had to give). With `along` (its dimension line): by
    logic.place_dim_label's one set of rules. HARD: on screen, over no building or coloured part (`solids`: their
    outlines on screen) and none of `keep` (the notice, the status box, the north arrow), on neither its own line nor
    another yard's (`dims`). SOFT: the labels already placed (`taken` beyond `keep`), then the lot's lines
    (`obstacles` beyond `dims`). Takes its spot in `taken`. `cache` (draw_screen's, while nothing on screen moved):
    the same placement again, never worked out every frame. The in-Rhino checks read this placement (STATE["drawn"])."""
    p = viewport.WorldToClient(point)
    if along is not None:
        a, b = (viewport.WorldToClient(q) for q in along)
        own = ((a.X, a.Y), (b.X, b.Y))
        view = (viewport.Size.Width, viewport.Size.Height)
        key = (text, size, tuple(round(v, 1) for q in own for v in q))
        got = cache.get(key) if cache is not None else None
        if got is None:
            fixed = list(keep or [])
            dim_lines = [tuple(map(tuple, d)) for d in dims or []]
            got = logic.place_dim_label(own, text, size, view, hard_boxes=fixed, hard_lines=dim_lines,
                                        soft_boxes=[t for t in (taken or []) if t not in fixed],
                                        soft_lines=[o for o in obstacles if tuple(map(tuple, o)) not in dim_lines],
                                        hard_shapes=list(solids or []))
            if cache is not None:
                cache[key] = got
        if taken is not None:
            taken.append((got["left"], got["top"], got["w"], got["h"]))
        return got["left"], got["top"], got["w"], got["top"], got["rows"], got["led"], got["size"], got["forced"]
    width = logic.label_width(text, size)
    left, want = p.X - width / 2, p.Y - 10
    top = want if taken is None else logic.clear_spot(taken, left, want, width, 20)
    return left, top, width, want, [text], abs(top - want) > 1, size, False


def label_at(d, viewport, point, text, color, dark, size=12, taken=None, along=None, obstacles=(), leader=False,
             keep=None, dims=(), solids=(), cache=None):
    """A screen-size, horizontal label at a model point, on its backing box (F3). With `taken` (the labels
    already drawn this frame), it moves off any it would cover and a short leader points back to its spot. With
    `along` (a dimension line's two model points), it sits beside that line, never on it (on two lines if it must;
    near its line with a leader when nothing beside it is clear: logic.place_near); with `leader` too, a
    line shorter on screen than its label gets a short leader from its middle to the label (a lot edge:
    logic.needs_leader). Returns where it went: (left, top, width, height, the top it wanted, its lines, whether a
    leader was drawn to it)."""
    p = viewport.WorldToClient(point)
    left, top, width, want, rows, led, size, forced = label_box(viewport, point, text, size, taken, along, obstacles,
                                                              keep, dims, solids, cache)
    h = logic.label_height(len(rows), size)
    if led:                                  # moved off its spot: a leader from it to the label's nearest edge
        end = logic.leader_end((p.X, p.Y), (left, top, width, h))
        d.Draw2dLine(System.Drawing.PointF(p.X, p.Y), System.Drawing.PointF(end[0], end[1]), color, 1)
    if leader and along is not None and not led:     # (its leader already drawn above)
        a, b = (viewport.WorldToClient(q) for q in along)
        if logic.needs_leader(((b.X - a.X) ** 2 + (b.Y - a.Y) ** 2) ** 0.5, width):
            mid = ((a.X + b.X) / 2, (a.Y + b.Y) / 2)
            end = logic.leader_end(mid, (left, top, width, h))
            d.Draw2dLine(System.Drawing.PointF(mid[0], mid[1]), System.Drawing.PointF(end[0], end[1]), color, 1)
    d.Draw2dRectangle(System.Drawing.Rectangle(int(left), int(top), int(width), int(h)), color, 1, backing(dark))
    for k, row in enumerate(rows):
        d.Draw2dText(row, color, rg.Point2d(left + 7, top + 3 + (size + 5) * k), False, size)
    return left, top, width, h, want, rows, led, size, forced


def paint_label(d, at, got, color, dark, edge_leader=False, line=None):
    """A placed plan label drawn (no search here: logic.place_labels placed it, outside the drawing loop): its
    leader from `at` (its line's middle on screen) when it is led, or, for a lot edge shorter than its label
    (`edge_leader`, logic.needs_leader), a short one; its box and its lines at its size."""
    left, top, width, rows, size = got["left"], got["top"], got["w"], got["rows"], got["size"]
    h = logic.label_height(len(rows), size)
    (xa, ya), (xb, yb) = line or got["line"]          # the line as it is on screen now (it may have moved)
    if got["led"] or (edge_leader and logic.needs_leader(((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5, width)):
        end = logic.leader_end(at, (left, top, width, h))
        d.Draw2dLine(System.Drawing.PointF(at[0], at[1]), System.Drawing.PointF(end[0], end[1]), color, 1)
    d.Draw2dRectangle(System.Drawing.Rectangle(int(left), int(top), int(width), int(h)), color, 1, backing(dark))
    for k, row in enumerate(rows):
        d.Draw2dText(row, color, rg.Point2d(left + 7, top + 3 + (size + 5) * k), False, size)


def _signed(bits):
    """A 32-bit dash mask as Rhino takes it: a signed Int32 (a mask with its top bit set overflows otherwise:
    "value too large to convert", caught by the guard 2026-10-20, so the dashed lines never drew)."""
    return bits - (1 << 32) if bits & (1 << 31) else bits


PHANTOM = _signed(0b11111111111111000110001100000000)    # long dash, short, short: the property line
DASHED = _signed(0b11111111000000001111111100000000)
