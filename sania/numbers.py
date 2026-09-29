"""Number to spoken-English helpers (Indian numbering system).

Money is read place by place and never rounded; identifiers are read digit by digit.
"""

from datetime import date

ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth",
    13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth",
    17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth",
    30: "thirtieth",
}


def _below_hundred(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f" {ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} hundred")
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def int_words(n: int) -> str:
    """44564 -> 'forty four thousand five hundred sixty four' (crore / lakh / thousand)."""
    if n == 0:
        return "zero"
    parts = []
    for size, label in ((10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{int_words(count)} {label}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def money_words(amount: float) -> str:
    """1250 -> 'one thousand two hundred fifty rupees'; 12.5 -> '... and fifty पैसे'."""
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    words = f"{int_words(rupees)} rupees"
    if paise:
        words += f" and {int_words(paise)} पैसे"
    return words


def digit_words(digits: str) -> str:
    """'3094' -> 'three zero nine four'. Non-digits are ignored."""
    return " ".join(ONES[int(ch)] for ch in digits if ch.isdigit())


def ordinal_words(n: int) -> str:
    if n in ORDINALS:
        return ORDINALS[n]
    tens, ones = divmod(n, 10)
    return f"{TENS[tens]} {ORDINALS[ones]}"


def date_words(d: date) -> str:
    """date(2026, 9, 15) -> 'fifteenth September'."""
    return f"{ordinal_words(d.day)} {MONTHS[d.month]}"
