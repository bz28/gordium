"""One drawing, written two ways: as SVG and as PDF. Plain code, no AI, no new dependency.

A sheet is a list of marks (lines, boxes, shapes, text) in points (1/72 in) from the sheet's top-left corner, y
down. `svg(page)` and `pdf(pages)` write exactly the same marks, so what a reviewer opens in either is the same
sheet. Text is Helvetica (one of the PDF's standard fonts, so nothing is embedded); its widths come from
pdfminer's copy of the Adobe metrics (pdfminer is already a dependency), so text is measured before it is placed
and never runs out of its box. Output is the same bytes for the same marks: no clock, no random ids.
"""

from dataclasses import dataclass, field

from pdfminer.fontmetrics import FONT_METRICS

PT = 72.0                                   # points per inch
_WIDTHS = {False: FONT_METRICS["Helvetica"][1], True: FONT_METRICS["Helvetica-Bold"][1]}
# characters a sheet may be given that the PDF's standard fonts (WinAnsi) can't show: plain stand-ins, used in both
# the SVG and the PDF so the two read the same
_PLAIN = {"≥": ">=", "≤": "<=", "≠": "not =", "✓": "", "✕": "x", "−": "-", "′": "'", "″": '"', "→": "->",
          " ": " ", " ": " ", " ": " "}


def plain(text: str) -> str:
    """The text as the sheet prints it: every character one the standard fonts have (cp1252), others replaced."""
    out = []
    for ch in str(text):
        ch = _PLAIN.get(ch, ch)
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            ch = "?"
        out.append(ch)
    return "".join(out)


def width(text: str, size: float, bold: bool = False) -> float:
    """The text's width in points at this size."""
    w = _WIDTHS[bold]
    return sum(w.get(ch, 556) for ch in plain(text)) * size / 1000.0


def wrap(text: str, size: float, room: float, bold: bool = False) -> list[str]:
    """The text broken into lines no wider than `room` points (a word longer than a line is broken in it)."""
    lines = []
    for para in plain(text).split("\n"):
        line = ""
        for word in para.split(" "):
            trial = f"{line} {word}" if line else word
            if width(trial, size, bold) <= room:
                line = trial
                continue
            if line:
                lines.append(line)
            while width(word, size, bold) > room and len(word) > 1:      # a long id: broken, never overflowing
                cut = max([n for n in range(1, len(word)) if width(word[:n], size, bold) <= room] or [1])
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


@dataclass
class Page:
    """One sheet: its size in inches and its marks, in the order they are drawn."""
    width_in: float
    height_in: float
    marks: list = field(default_factory=list)

    @property
    def w(self) -> float:
        return self.width_in * PT

    @property
    def h(self) -> float:
        return self.height_in * PT

    def line(self, x1, y1, x2, y2, stroke="#000000", lw=0.5, dash=None):
        self.marks.append(("line", (x1, y1, x2, y2), {"stroke": stroke, "lw": lw, "dash": dash}))

    def rect(self, x, y, w, h, stroke="#000000", fill=None, lw=0.5, dash=None):
        self.shape([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], stroke, fill, lw, dash)

    def shape(self, points, stroke="#000000", fill=None, lw=0.5, dash=None, closed=True):
        self.marks.append(("shape", [tuple(p) for p in points],
                           {"stroke": stroke, "fill": fill, "lw": lw, "dash": dash, "closed": closed}))

    def text(self, x, y, s, size=7.0, bold=False, anchor="start", fill="#000000"):
        """Text whose baseline starts (or centres, or ends) at x, y."""
        self.marks.append(("text", (x, y), {"s": plain(s), "size": size, "bold": bold, "anchor": anchor,
                                            "fill": fill}))

    def texts(self) -> list[str]:
        """Every text on the sheet, in order (what a reader of it sees)."""
        return [m[2]["s"] for m in self.marks if m[0] == "text"]


def _n(x: float) -> str:
    """A coordinate as short, exact-enough text: the same every run."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _esc_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg(page: Page, title: str) -> str:
    """The sheet as an SVG file, sized in inches so it prints at scale."""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(page.width_in)}in" height="{_n(page.height_in)}in" '
           f'viewBox="0 0 {_n(page.w)} {_n(page.h)}" font-family="Helvetica, Arial, sans-serif">',
           f"<title>{_esc_xml(plain(title))}</title>",
           f'<rect x="0" y="0" width="{_n(page.w)}" height="{_n(page.h)}" fill="#ffffff"/>']
    for kind, geo, st in page.marks:
        dash = f' stroke-dasharray="{" ".join(_n(d) for d in st["dash"])}"' if st.get("dash") else ""
        if kind == "line":
            x1, y1, x2, y2 = geo
            out.append(f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" stroke="{st["stroke"]}" '
                       f'stroke-width="{_n(st["lw"])}"{dash}/>')
        elif kind == "shape":
            pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in geo)
            tag = "polygon" if st["closed"] else "polyline"
            fill = st["fill"] or "none"
            stroke = f' stroke="{st["stroke"]}" stroke-width="{_n(st["lw"])}"' if st["stroke"] else ""
            out.append(f'<{tag} points="{pts}" fill="{fill}"{stroke}{dash}/>')
        else:
            x, y = geo
            anchor = {"start": "start", "middle": "middle", "end": "end"}[st["anchor"]]
            weight = ' font-weight="bold"' if st["bold"] else ""
            out.append(f'<text x="{_n(x)}" y="{_n(y)}" font-size="{_n(st["size"])}"{weight} '
                       f'text-anchor="{anchor}" fill="{st["fill"]}" xml:space="preserve">{_esc_xml(st["s"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _rgb(color: str) -> str:
    c = color.lstrip("#")
    return " ".join(_n(int(c[i:i + 2], 16) / 255) for i in (0, 2, 4))


def _esc_pdf(s: str) -> bytes:
    b = s.encode("cp1252")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _content(page: Page) -> bytes:
    """The page's marks as a PDF content stream (PDF's y runs up: every y is flipped)."""
    H = page.h
    out = []
    for kind, geo, st in page.marks:
        if kind in ("line", "shape"):
            dash = f"[{' '.join(_n(d) for d in st['dash'])}] 0 d" if st.get("dash") else "[] 0 d"
            out.append(f"{_n(st['lw'])} w {dash}".encode())
            if kind == "line":
                x1, y1, x2, y2 = geo
                out.append(f"{_rgb(st['stroke'])} RG {_n(x1)} {_n(H - y1)} m {_n(x2)} {_n(H - y2)} l S".encode())
                continue
            path = f"{_n(geo[0][0])} {_n(H - geo[0][1])} m " + " ".join(
                f"{_n(x)} {_n(H - y)} l" for x, y in geo[1:]) + (" h" if st["closed"] else "")
            if st["fill"] and st["stroke"]:
                out.append(f"{_rgb(st['fill'])} rg {_rgb(st['stroke'])} RG {path} B".encode())
            elif st["fill"]:
                out.append(f"{_rgb(st['fill'])} rg {path} f".encode())
            elif st["stroke"]:
                out.append(f"{_rgb(st['stroke'])} RG {path} S".encode())
        else:
            x, y = geo
            w = width(st["s"], st["size"], st["bold"])
            x -= {"start": 0, "middle": w / 2, "end": w}[st["anchor"]]
            font = "F2" if st["bold"] else "F1"
            out.append(b"BT /" + font.encode() + f" {_n(st['size'])} Tf {_rgb(st['fill'])} rg "
                       f"{_n(x)} {_n(H - y)} Td (".encode() + _esc_pdf(st["s"]) + b") Tj ET")
    return b"\n".join(out) + b"\n"


def pdf(pages: list[Page], title: str) -> bytes:
    """Every sheet as one PDF, one page each, at the sheet's size. Content is left uncompressed: the file is small,
    plain to diff and the same bytes every run (no dates in it)."""
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    catalog = add(b"")                         # filled in below, once the pages object is known
    pages_obj = add(b"")
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kids = []
    for page in pages:
        stream = _content(page)
        c = add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {_n(page.w)} {_n(page.h)}] "
                        f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {c} 0 R >>".encode()))
    objs[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    objs[pages_obj - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
                           ).encode()
    info = add(b"<< /Title (" + _esc_pdf(plain(title)) + b") /Producer (Gordium permit_sheets) >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
