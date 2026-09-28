"""Diacritic names shared by the editor (component slots) and link_western.py (movable forms)."""

SPACING = {"ACUTE ACCENT": "´", "GRAVE ACCENT": "`", "CIRCUMFLEX ACCENT": "ˆ", "TILDE": "˜", "DIAERESIS": "¨",
           "MACRON": "¯", "BREVE": "˘", "DOT ABOVE": "˙", "RING ABOVE": "˚", "CEDILLA": "¸", "OGONEK": "˛",
           "DOUBLE ACUTE ACCENT": "˝", "CARON": "ˇ", "HOOK ABOVE": "̉", "DOT BELOW": "̣", "HORN": "̛",
           "COMMA CEDILLA": "̦"}
MARK_ZH = {"ACUTE ACCENT": "尖音符", "GRAVE ACCENT": "抑音符", "CIRCUMFLEX ACCENT": "扬抑符", "TILDE": "波浪符",
           "DIAERESIS": "分音符", "MACRON": "长音符", "BREVE": "短音符", "DOT ABOVE": "上点", "RING ABOVE": "上圈",
           "CEDILLA": "软音符", "OGONEK": "反尾形符", "DOUBLE ACUTE ACCENT": "双尖音符", "CARON": "抑扬符（钩）",
           "HOOK ABOVE": "上钩", "DOT BELOW": "下点", "HORN": "角", "COMMA CEDILLA": "软音符（逗号形）"}


def marks_of(family):
    """Family marks; the Latvian/Romanian-style cedilla of G K L N R is its own (comma-shaped) mark."""
    return ["COMMA CEDILLA" if m == "CEDILLA" and family["base"].upper() in "GKLNR" else m for m in family["marks"]]


def slots(char, family):
    """[(slot key, symbol, label)] the glyph should contain: its base letter and each separable mark
    (hook, bar, stroke … are part of the letter and have no slot of their own)."""
    out = [("mv:base", family["base"], f"基字 {family['base']}")]
    for i, m in enumerate(marks_of(family)):
        if m in SPACING:
            out.append((f"mv:mark:{i}", SPACING[m], f"{MARK_ZH.get(m, m)} {SPACING[m]}"))
    return out

# Greek and Cyrillic letters drawn exactly like a Latin letter share its form when identical.
HOMOGLYPHS = {"А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
              "Х": "X", "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "Ѕ": "S", "ѕ": "s",
              "І": "I", "і": "i", "Ј": "J", "ј": "j", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
              "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o"}
