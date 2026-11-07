r"""Plain-text memo for human readers: pure, deterministic, no I/O.

Every input string goes through ``quote``: it sits inside ``"..."`` after a constant label,
with ``\`` and ``"`` backslash-escaped and every control, format, line/paragraph separator,
unassigned, surrogate, non-ASCII space, default-ignorable (invisible) or braille-blank
code point written as ``\uXXXX``.
The frame (headings, labels, tags) is constant, so input text cannot forge it.
"""

import unicodedata

ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs", "Cn"})
# Default_Ignorable_Code_Point (Unicode 15.1, DerivedCoreProperties) plus U+2800 (braille blank):
# characters that render as nothing and could hide text from a human reader.
INVISIBLE_RANGES = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160),
    (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
    (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF), (0x2800, 0x2800),
)
KIND_LABELS = {
    "actual": "thực tế (actual)",
    "forecast": "dự báo (forecast)",
    "unknown": "không rõ (unknown)",
}

_HEADER = (
    "BẢN NHÁP MEMO QUYẾT ĐỊNH — CHỜ NGƯỜI CÓ THẨM QUYỀN QUYẾT ĐỊNH",
    "Trạng thái: chờ người quyết (needs_human_decision) · agent: cần người xem lại "
    "(needs_review) · quyết định: mới là đề nghị, chưa chốt (proposed)",
    "Bằng chứng: CHƯA XÁC MINH (unverified) — plugin không kiểm dữ liệu; "
    "chữ trong ngoặc kép là dữ liệu đầu vào, in nguyên",
)
_FOOTER = (
    "Đây là bản nháp sinh máy móc từ dữ liệu đã cho, không phải lời khuyên AI đã nghiệm thu. "
    "Người có thẩm quyền tự quyết định."
)
_WARNING_LINES = {
    "out_of_period": "- [NGOÀI KỲ] bằng chứng ngoài kỳ: ",
    "conflict": "- [MÂU THUẪN] bằng chứng mâu thuẫn: ",
}
_NO_EVIDENCE_WARNING = "- [KHÔNG CÓ BẰNG CHỨNG] không có bằng chứng nào"


def _needs_escape(char):
    code = ord(char)
    category = unicodedata.category(char)
    return (
        category in ESCAPED_CATEGORIES
        or (category == "Zs" and char != " ")
        or any(low <= code <= high for low, high in INVISIBLE_RANGES)
    )


def quote(text: str) -> str:
    """Return ``text`` as a double-quoted, escaped string; see the module docstring."""
    parts = ['"']
    for char in text:
        if char == "\\":
            parts.append("\\\\")
        elif char == '"':
            parts.append('\\"')
        elif _needs_escape(char):
            code = ord(char)
            parts.append("\\u%04x" % code if code <= 0xFFFF else "\\U%08x" % code)
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _decision_lines(decision):
    return [
        "Câu hỏi: " + quote(decision["question"]),
        "Người quyết định: " + quote(decision["owner"]),
        "Hạn quyết định: " + decision["deadline"],
        "Ngày xem lại: " + decision["review_date"],
        "Dữ liệu tính đến: " + decision["as_of"],
        "Ý kiến khác: " + quote(decision["dissent"]),
    ]


def _option_lines(options):
    lines = [
        "Phương án (%d — theo thứ tự dữ liệu vào, không xếp hạng, không khuyến nghị):"
        % len(options)
    ]
    for number, option in enumerate(options, 1):
        tag = "[GIỮ HIỆN TRẠNG] " if option["status_quo"] else ""
        lines.append("%d. %s%s" % (number, tag, quote(option["name"])))
        lines.append("   Được: " + quote(option["pros"]))
        lines.append("   Mất: " + quote(option["cons"]))
        lines.append("   Cách đảo ngược: " + quote(option["reversal"]))
        lines.append("   Việc cần làm: " + quote(option["actions"]))
    return lines


def _evidence_lines(evidence):
    if not evidence:
        return ["Bằng chứng (0): không có"]
    lines = ["Bằng chứng (%d):" % len(evidence)]
    for number, item in enumerate(evidence, 1):
        period = "[NGOÀI KỲ]" if item["period_status"] == "out_of_period" else "[TRONG KỲ]"
        group = quote(item["conflict_group"]) if item["conflict_group"] != "" else "không có"
        lines.append("%d. [CHƯA XÁC MINH] %s %s" % (number, period, quote(item["id"])))
        lines.append("   Loại: " + KIND_LABELS[item["kind"]])
        lines.append("   Chủ: " + quote(item["owner"]))
        lines.append("   Kỳ: " + quote(item["period"]))
        lines.append("   Hiệu lực: %s đến %s" % (item["effective_from"], item["effective_to"]))
        lines.append("   Nhận định: " + quote(item["claim"]))
        lines.append("   Nguồn (không truy cập): " + quote(item["source_uri"]))
        lines.append("   Nhóm mâu thuẫn: " + group)
    return lines


def _warning_lines(warnings):
    if not warnings:
        return ["Cảnh báo (0): không có"]
    lines = ["Cảnh báo (%d):" % len(warnings)]
    for warning in warnings:
        if warning["code"] == "no_evidence":
            lines.append(_NO_EVIDENCE_WARNING)
        else:
            ids = ", ".join(quote(evidence_id) for evidence_id in warning["evidence_ids"])
            lines.append(_WARNING_LINES[warning["code"]] + ids)
    return lines


def render_text(memo: dict) -> bytes:
    """Return the memo as UTF-8 text: LF line ends, one final LF, no trailing spaces.

    ``quote`` already escapes lone surrogates, so the encoding cannot fail.
    """
    blocks = [
        list(_HEADER),
        _decision_lines(memo["decision"]),
        _option_lines(memo["options"]),
        _evidence_lines(memo["evidence"]),
        _warning_lines(memo["warnings"]),
        [_FOOTER],
    ]
    text = "\n\n".join("\n".join(block) for block in blocks) + "\n"
    return text.encode("utf-8")
