"""Every number a piece of law states, with the words that make it a limit: the comparison words directly before it
("not more than"), its unit straight after it ("inches", "square feet", "units horizontal"; never across a stop, a
comma or a bracket, and never a sentence's capitalised "In"), and any comparison words after
that ("or more"), also past a number and unit's conversion in brackets ("200 gross square feet (18.6 m²) or less" is
"or less" for both numbers; never across another number, a comma or a stop). Comparison words further back ("not
exceeding a total floor area of 200", "a minimum tread depth of 5 inches") are not caught. Used to check a book's
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
by a hyphen counts ("12-inch", "one-family"). A comparison keeps a "not", "no", "nor" or "cannot" printed up to eight
words before it, with the words between ("shall not be less than", "no more than", "shall not have a vertical rise
greater than"): dropped, the limit would read the other way round. That reach stops at a stop, a comma, another
number and a word that often starts another clause ("and", "or", "where"), so it is a rule of thumb, not grammar: it
can take a "not" that is another verb's ("not required for stairs having more than 3 risers") or miss one across an
"or" joining two nouns ("not have a rise or a run greater than"). So what the recorded words mean is checked by a
reading that never goes through this code: comparison() turns each recorded number into a symbol (">=", "<=", ...)
and text_verification.yaml holds a person's symbol for each, read from the whole printed sentence. Plain code, no AI.
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
NEGATIONS = ("not", "no", "nor", "cannot")                       # "shall not be less than 7 feet" is never "less than 7 feet"
CLAUSE_STARTS = ("and", "or", "where", "when", "unless", "if", "except", "that", "which", "but")
NEGATION_REACH = 8          # R318.7.2: "not project horizontally into the required headroom more than" is 6 words
AFTER = ("or more", "or fewer", "or less", "or greater")
UNITS = {"inch": "inch", "inches": "inch", "in": "inch", "foot": "foot", "feet": "foot", "mm": "mm", "cm": "cm",
         "m": "m", "degrees": "degree", "degree": "degree", "rad": "rad", "percent": "percent", "units": "unit",
         "unit": "unit", "square": "square", "cubic": "cubic", "gross": "gross", "footcandle": "footcandle", "footcandles": "footcandle",
         "lux": "lux", "risers": "riser", "riser": "riser", "pounds": "pound", "pound": "pound", "lb": "pound", "psf": "psf",
         "kg": "kg"}
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
        after_words = _unit_words(text[m.end():])
        unit = next((UNITS[w] for w in after_words[:1] if w in UNITS), "")
        used = 1 if unit else 0
        if after_words[:1] and after_words[0] in TWO_WORD_UNITS and after_words[1:2] and after_words[1] in UNITS:
            unit, used = f"{after_words[0]} {UNITS[after_words[1]]}", 2
        elif after_words[:1] in (["gross"], ["net"]) and after_words[1:2] and after_words[1] in TWO_WORD_UNITS \
                and after_words[2:3] and after_words[2] in UNITS:
            # "200 gross square feet"; "30 net square feet" (BCNYS 407.10, Chapter 4 part c's conversion check)
            unit, used = f"{after_words[0]} {after_words[1]} {UNITS[after_words[2]]}", 3
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
        out.append({"before": _negated(text[:m.start()].lower().split()[-(NEGATION_REACH + 4):], _ends_with(" ".join(before_text), BEFORE)),
                    "value": m[0].lower(),
                    "unit": unit,
                    "after": next((a for a in AFTER if rest.startswith(a)), "")})
    return out


UNIT_STOPS = re.compile(r"[A-Za-z]+|[()]|[,;:!?]|\.(?!\d)")


def _unit_words(after: str) -> list[str]:
    """The words straight after a number that can be its unit, lowercased: those before any stop, comma, colon,
    semicolon or bracket. A unit is never taken across a sentence's or a list item's end ("less than 50. 3. In
    courtrooms" is 50 with no unit, never 50 inches), and a capitalised "In" is a word starting a sentence, never
    inches (a table's "IN." is). "12-inch" is still 12 inches: a hyphen joins, it does not stop; nor do digits
    (the book's "(22 860 mm)" stays as it was read)."""
    words = []
    for t in UNIT_STOPS.findall(after):
        if not t[0].isalpha() or t == "In":
            break
        words.append(t.lower())
    return words


def statements_of_lines(lines: list[str]) -> list[dict]:
    """Each number in a piece given as its lines: a list item's own number is cut off where the book prints it, at
    the start of a line ("2. Where ..."), never inside the text, where "not more than 2. Where" ends a sentence with
    a number that must be read."""
    return statements(" ".join(LIST_ITEM.sub("", line, count=1) for line in lines))


def _plain(text: str) -> str:
    """Text as the numbers are read from it: sealed markers out ("m[fn2]" -> "m"; a note letter's before a slash ends a
    cell, so "0.5[fnc]/1[fnd]" is "0.5 / 1"), spaces made single. A hyphen before a space is kept: "one- or two-family" is two
    numbers (joining it as a word broken at a line end would lose the "one")."""
    # a note letter's marker before a slash ends a table cell: "0.5[fnc]/1[fnd]" (Table 1020.2: 0.5 with note c, 1
    # with note d) is two numbers either side of a slash, never the fraction "0.5/1" (which reads as neither); a
    # raised digit before a slash is a stacked fraction's top ("2 1[fn1]/ 2", "[fn5]/8 IN."), left as it was
    text = re.sub(r"\[fn[a-z][^\]]*\]/", " / ", text)
    text = re.sub(r"\[fn[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _ends_with(words: str, phrases: tuple[str, ...]) -> str:
    for p in sorted(phrases, key=len, reverse=True):          # the longest first: "by more than", not "more than"
        if words == p or words.endswith(" " + p):
            return p
    return ""


def _negated(words: list[str], before: str) -> str:
    """The comparison with a "not", "no", "nor" or "cannot" printed up to eight words before it in the same clause, and
    the words between, as printed: "not be less than", "not project more than", "not to exceed". Never across a stop,
    a comma, a word that starts another clause ("and", "or", "where", ...) or another number, whose "not" it is ("not
    less than two occupants for one bedroom and one")."""
    if not before or before.split()[0] in NEGATIONS:
        return before
    rest = words[:len(words) - len(before.split())]
    for k in range(1, min(NEGATION_REACH, len(rest)) + 1):
        w = rest[-k]
        if w[-1:] in ",;.:)" or w in CLAUSE_STARTS or NUMBER.search(w):
            return before
        if w in NEGATIONS:
            return " ".join(rest[-k:] + [before])
    return before


SYMBOL = {"less than": "<", "more than": ">", "greater than": ">", "by more than": ">", "steeper than": ">",
          "exceeding": ">", "exceed": ">", "minimum": ">=", "at least": ">=", "maximum": "<=", "up to": "<=",
          "within": "<=", "between": "between", "and": "and",
          "or more": ">=", "or greater": ">=", "or less": "<=", "or fewer": "<="}
FLIP = {"<": ">=", ">": "<=", ">=": "<", "<=": ">"}
COMPARISONS = (">=", "<=", ">", "<", "between", "none")


def comparison(shown_number: str, previous: str = "none") -> str:
    """What a recorded number's words say of it, as a symbol: "not less than 36 inch" is ">=", "more than 3 riser"
    is ">", "36 inch" is "none". A "not" flips it ("not have a vertical rise greater than 12 foot" is "<="), unless
    it waives the limit ("not be required to be within 3/8 inch" is "none"). "and" ends a range only after
    "between" (previous: the comparison of the number before it). Read from the recorded words alone, so a second
    reading's comparisons (a person's, from the printed sentence) can be checked against them: two readings put
    through this same code would share any word it drops, so they cannot check its meaning."""
    words = shown_number.split()
    # the recorded words before the number: the longest start of it holding no number and ending in a comparison
    before = next((" ".join(words[:k]) for k in range(len(words), 0, -1)
                   if not NUMBER.search(" ".join(words[:k])) and _ends_with(" ".join(words[:k]), BEFORE)), "")
    after = next((a for a in AFTER if shown_number.endswith(" " + a)), "")
    if not before:
        return SYMBOL[after] if after else "none"
    if re.match(r"(?:not|no) (?:be )?required\b", before):
        return "none"                                   # "shall not be required to be within": no limit
    base = _ends_with(before, BEFORE)
    negated = before.split()[0] in NEGATIONS
    base = base[4:] if base.startswith("not ") else base     # "not less than" is "less than", negated
    symbol = SYMBOL[base]
    if symbol == "and":
        return "between" if previous == "between" else "none"
    return FLIP.get(symbol, symbol) if negated else symbol


def comparisons(shown_numbers: list[str]) -> list[str]:
    """comparison() of each recorded number of a piece, in order."""
    out = []
    for s in shown_numbers:
        out.append(comparison(s, out[-1] if out else "none"))
    return out


def key(s: dict) -> tuple:
    """What two readings must agree on, for one number."""
    return (s["before"], s["value"], s["unit"], s["after"])


def shown(s: dict) -> str:
    """One number as a person reads it in a report: 'not more than 8 1/4 inch'."""
    return " ".join(x for x in (s["before"], s["value"], s["unit"], s["after"]) if x)
