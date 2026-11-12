"""Every number a piece of law states, with the words that make it a limit: the comparison words directly before it
("not more than"), its unit after it ("inches", "square feet", "units horizontal"), and any comparison words after
that ("or more"), also past a number and unit's conversion in brackets ("200 gross square feet (18.6 m²) or less" is
"or less" for both numbers; never across another number, a comma or a stop). Comparison words further back ("not exceeding a total floor area of 200") are not caught. Used to check a book's
extracted text against a second, independent reading of the page images (text_verification.yaml in the law's folder):
both readings are put through this same code, so they are compared item by item, never by eye.

    statements("shall be not more than 8 1/4 inches (209 mm)")
    -> [{"before": "not more than", "value": "8 1/4", "unit": "inch", "after": ""},
        {"before": "", "value": "209", "unit": "mm", "after": ""}]

A number is digits ("36", "0.01", "5.7"), a fraction ("9/16"), a whole number and a fraction ("1 1/4"), a number
word ("four", "twenty"), or a part of a whole ("one-half", "a quarter", "two-thirds", "one and one third"; read
whole, so "one-half" is never the number one). A number fixed to letters is a name, not a quantity, and is left out: a section ("R318.7.11.1",
"P2904"), a standard ("F2090"), a table's part ("Table R401.4.1(2)"), a marker the extraction seals ("[fn2]", a
raised 2: m², ft²). So is a list item's own number at the start of a line ("1.", "3.1."). A number joined to a word
by a hyphen counts ("12-inch", "one-family"). A comparison keeps a "not", "no" or "nor" printed just before it,
also across "be" ("shall not be less than", "no more than", "nor more than"): dropped, the limit would read the other
way round. Plain code, no AI.
"""

import re

WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
         "sixty", "seventy", "eighty", "ninety", "hundred", "thousand")
PARTS = ("half", "halves", "quarter", "quarters", "third", "thirds", "fourth", "fourths", "fifth", "fifths", "sixth",
         "sixths", "eighth", "eighths")                       # "one-half", "a quarter circle", "three-fourths"
TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_W = "|".join(sorted(WORDS, key=len, reverse=True))
BEFORE = ("not less than", "not more than", "not greater than", "not exceeding", "not exceed", "not steeper than",
          "greater than", "less than", "more than", "steeper than", "by more than", "exceeding", "exceed", "minimum",
          "maximum", "at least", "between", "within", "up to", "and")
NEGATIONS = ("not", "no", "nor")                       # "shall not be less than 7 feet" is never "less than 7 feet"
AFTER = ("or more", "or fewer", "or less", "or greater")
UNITS = {"inch": "inch", "inches": "inch", "in": "inch", "foot": "foot", "feet": "foot", "mm": "mm", "cm": "cm",
         "m": "m", "degrees": "degree", "degree": "degree", "rad": "rad", "percent": "percent", "units": "unit",
         "unit": "unit", "square": "square", "cubic": "cubic", "gross": "gross", "footcandle": "footcandle", "footcandles": "footcandle",
         "lux": "lux", "risers": "riser", "riser": "riser", "pounds": "pound", "lb": "pound", "psf": "psf"}
NUMBER = re.compile(r"(?<![\w.\-/\[])(?<!\w\()(?:\d+[ -]\d+/\d+|\d+/\d+|\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?![\w/]|\.\d)"
                    r"|(?<![\w-])(?:(?:" + _W + r") and )?(?:(?:a|" + _W + r")[- ])?(?:" + "|".join(PARTS) + r")(?![\w-])"
                    r"|(?<![\w-])(?:(?:" + "|".join(TENS) + r")-(?:one|two|three|four|five|six|seven|eight|nine)(?!\w)"
                    r"|(?:" + _W + r")(?!\w))", re.IGNORECASE)
TWO_WORD_UNITS = {"square", "cubic"}                  # "square feet" is one unit: never just "square"
DIRECTIONS = ("vertical", "horizontal")               # "1 unit vertical in 12 units horizontal"
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
        used = 1 if unit else 0
        if after_words[:1] and after_words[0] in TWO_WORD_UNITS and after_words[1:2] and after_words[1] in UNITS:
            unit, used = f"{after_words[0]} {UNITS[after_words[1]]}", 2
        elif after_words[:1] == ["gross"] and after_words[1:2] and after_words[1] in TWO_WORD_UNITS \
                and after_words[2:3] and after_words[2] in UNITS:
            unit, used = f"gross {after_words[1]} {UNITS[after_words[2]]}", 3     # "200 gross square feet"
        if unit == "unit" and after_words[1:2] and after_words[1] in DIRECTIONS:
            unit, used = f"unit {after_words[1]}", 2
        # What follows, with numbers and stops kept, so a comparison word is never taken across them ("4 inches
        # (102 mm), 6 or more": the "or more" is the 6's alone)
        rest_words = re.findall(r"[a-z]+|\(|\)|[,;.:]|\d[\d.,/]*", text[m.end():].lower())[used:]
        if unit and rest_words[:1] == [")"]:          # a conversion in brackets: "(18.6 m²) or less"
            rest_words = rest_words[1:]
        elif unit and rest_words[:1] == ["("] and ")" in rest_words[:5]:   # "200 square feet (18.6 m²) or less"
            rest_words = rest_words[rest_words.index(")") + 1:]
        rest = " ".join(rest_words[:3])
        out.append({"before": _negated(before_text, _ends_with(" ".join(before_text), BEFORE)),
                    "value": m[0].lower(),
                    "unit": unit,
                    "after": next((a for a in AFTER if rest.startswith(a)), "")})
    return out


def statements_of_lines(lines: list[str]) -> list[dict]:
    """Each number in a piece given as its lines: a list item's own number is cut off where the book prints it, at
    the start of a line ("2. Where ..."), never inside the text, where "not more than 2. Where" ends a sentence with
    a number that must be read."""
    return statements(" ".join(LIST_ITEM.sub("", line, count=1) for line in lines))


def _plain(text: str) -> str:
    """Text as the numbers are read from it: sealed markers out ("m[fn2]" -> "m"), spaces made single. A hyphen before a space is kept: "one- or two-family" is two
    numbers (joining it as a word broken at a line end would lose the "one")."""
    text = re.sub(r"\[fn[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _ends_with(words: str, phrases: tuple[str, ...]) -> str:
    for p in sorted(phrases, key=len, reverse=True):          # the longest first: "by more than", not "more than"
        if words == p or words.endswith(" " + p):
            return p
    return ""


def _negated(words: list[str], before: str) -> str:
    """The comparison with the "not", "no" or "nor" printed before it, also across "be": "not be less than"."""
    if not before or before.split()[0] in NEGATIONS:
        return before
    rest = words[:len(words) - len(before.split())]
    if rest[-1:] and rest[-1] in NEGATIONS:
        return f"{rest[-1]} {before}"
    if rest[-2:-1] and rest[-2] in NEGATIONS and rest[-1] == "be":
        return f"{rest[-2]} be {before}"
    return before


def key(s: dict) -> tuple:
    """What two readings must agree on, for one number."""
    return (s["before"], s["value"], s["unit"], s["after"])


def shown(s: dict) -> str:
    """One number as a person reads it in a report: 'not more than 8 1/4 inch'."""
    return " ".join(x for x in (s["before"], s["value"], s["unit"], s["after"]) if x)
