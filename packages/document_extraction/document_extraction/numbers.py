"""Every number a piece of law states, with the words that make it a limit: the comparison words before it ("not
more than"), its unit after it ("inches"), and any comparison words after that ("or more"). Used to check a book's
extracted text against a second, independent reading of the page images (text_verification.yaml in the law's folder):
both readings are put through this same code, so they are compared item by item, never by eye.

    statements("shall be not more than 8 1/4 inches (209 mm)")
    -> [{"before": "not more than", "value": "8 1/4", "unit": "inch", "after": ""},
        {"before": "", "value": "209", "unit": "mm", "after": ""}]

A number is digits ("36", "0.01", "5.7"), a fraction ("9/16"), a whole number and a fraction ("1 1/4"), a number
word ("four", "twenty"), or a part of a whole ("one-half", "a quarter", "two-thirds"; read whole, so "one-half" is never
the number one). A number fixed to letters is a name, not a quantity, and is left out: a section ("R318.7.11.1",
"P2904"), a standard ("F2090"), a table's part ("Table R401.4.1(2)"), a marker the extraction seals ("[fn2]", a
raised 2: m², ft²). So is a list item's own number at the start of a line ("1.", "3.1."). A number joined to a word
by a hyphen counts ("12-inch", "one-family"). Plain code, no AI.
"""

import re

WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
         "sixty", "seventy", "eighty", "ninety", "hundred", "thousand")
PARTS = ("half", "halves", "quarter", "quarters", "third", "thirds")     # "one-half", "a quarter circle", "two-thirds"
BEFORE = ("not less than", "not more than", "not greater than", "not exceeding", "not exceed", "not steeper than",
          "greater than", "less than", "more than", "steeper than", "by more than", "exceeding", "exceed", "minimum",
          "maximum", "at least", "between", "within", "up to", "and")
AFTER = ("or more", "or fewer", "or less", "or greater")
UNITS = {"inch": "inch", "inches": "inch", "in": "inch", "foot": "foot", "feet": "foot", "mm": "mm", "cm": "cm",
         "m": "m", "degrees": "degree", "degree": "degree", "rad": "rad", "percent": "percent", "units": "unit",
         "unit": "unit", "square": "square", "gross": "gross", "footcandle": "footcandle", "footcandles": "footcandle",
         "lux": "lux", "risers": "riser", "riser": "riser", "pounds": "pound", "lb": "pound", "psf": "psf"}
NUMBER = re.compile(r"(?<![\w.\-/\[])(?<!\w\()(?:\d+ \d+/\d+|\d+/\d+|\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?![\w/]|\.\d)"
                    r"|(?<![\w-])(?:(?:a|one|two|three)[- ])?(?:" + "|".join(PARTS) + r")(?![\w-])"
                    r"|(?<![\w-])(?:" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
LIST_ITEM = re.compile(r"^\s*\d+(?:\.\d+)*\.\s")


def statements(text: str) -> list[dict]:
    """Each number in `text` (one line, or a piece's lines joined with spaces), in reading order."""
    text = _plain(text)
    skip_to = LIST_ITEM.match(text).end() if LIST_ITEM.match(text) else 0
    out = []
    for m in NUMBER.finditer(text):
        if m.start() < skip_to:
            continue
        before_text = text[:m.start()].lower().split()[-5:]
        after_words = re.findall(r"[a-z]+|\(|\)", text[m.end():].lower())
        unit = next((UNITS[w] for w in after_words[:1] if w in UNITS), "")
        rest = " ".join(after_words[1:4] if unit else after_words[:3])
        out.append({"before": _ends_with(" ".join(before_text), BEFORE),
                    "value": m[0].lower(),
                    "unit": unit,
                    "after": next((a for a in AFTER if rest.startswith(a)), "")})
    return out


def _plain(text: str) -> str:
    """Text as the numbers are read from it: sealed markers out ("m[fn2]" -> "m"), list items inside a joined piece
    cut off as at a line start, spaces made single. A hyphen before a space is kept: "one- or two-family" is two
    numbers (joining it as a word broken at a line end would lose the "one")."""
    text = re.sub(r"\[fn[^\]]*\]", "", text)
    text = re.sub(r"(?:^|\s)\d+(?:\.\d+)*\.(?=\s+[A-Z])", " ", text)    # "1. A nosing ..." list markers
    return re.sub(r"\s+", " ", text).strip()


def _ends_with(words: str, phrases: tuple[str, ...]) -> str:
    for p in sorted(phrases, key=len, reverse=True):          # the longest first: "by more than", not "more than"
        if words == p or words.endswith(" " + p):
            return p
    return ""


def key(s: dict) -> tuple:
    """What two readings must agree on, for one number."""
    return (s["before"], s["value"], s["unit"], s["after"])


def shown(s: dict) -> str:
    """One number as a person reads it in a report: 'not more than 8 1/4 inch'."""
    return " ".join(x for x in (s["before"], s["value"], s["unit"], s["after"]) if x)
