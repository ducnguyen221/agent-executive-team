"""No raw invisible, bidirectional or control character may sit in a Python source file."""

import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Default_Ignorable_Code_Point (Unicode 15.1), written independently of render.py.
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160),
    (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
    (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)  # fmt: skip
_BAD_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cn", "Cs"}


def _is_bad(char):
    code = ord(char)
    if char == "\n":
        return False
    if any(low <= code <= high for low, high in _DEFAULT_IGNORABLE):
        return True
    category = unicodedata.category(char)
    return category in _BAD_CATEGORIES or (category == "Zs" and char != " ")


def _python_files():
    for folder in ("src", "tests", "skills"):
        yield from sorted((ROOT / folder).rglob("*.py"))


def test_sources_have_no_raw_invisible_characters():
    found = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.split("\n"), 1):
            for char in line:
                if _is_bad(char):
                    found.append("%s:%d U+%04X" % (path.relative_to(ROOT), number, ord(char)))
    assert found == []
