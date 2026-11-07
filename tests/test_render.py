"""Plain-text memo: exact bytes for the fixture, escaping of every input value, fixed frame."""

import copy
import re
import unicodedata
from pathlib import Path

import pytest

from agent_executive_team import render
from agent_executive_team.memo import build_memo
from conftest import build_valid_payload

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_TEXT = ROOT / "tests" / "fixtures" / "valid.text"

QUOTED = re.compile(r'"(?:\\.|[^"\\])*"')

# Hand-written, independent of render.py: what quote() must escape.
ESCAPED_GROUPS = {"Cc", "Cf", "Zl", "Zp", "Cs", "Cn"}
FILLER_CODEPOINTS = {0x115F, 0x1160, 0x3164, 0xFFA0}

SC2_CHARACTERS = [
    "\n", "\r", "\t", "\x1b", "\x7f", "\x85", "\x9b", "\xa0", "​", "‎",
    "‮", "⁦", " ", " ", "ㅤ", "﻿", "￾",
]  # fmt: skip

TEXT_FIELDS = (
    [("decision", None, key) for key in ("question", "owner", "dissent")]
    + [("options", 0, key) for key in ("name", "pros", "cons", "reversal", "actions")]
    + [("evidence", 0, key) for key in ("id", "owner", "period", "claim", "source_uri", "conflict_group")]
)


def memo_of(payload):
    return build_memo(payload)


def expected_quote(char):
    code = ord(char)
    if char == "\\":
        return '"\\\\"'
    if char == '"':
        return '"\\""'
    category = unicodedata.category(char)
    if (
        category in ESCAPED_GROUPS
        or (category == "Zs" and code != 0x20)
        or code in FILLER_CODEPOINTS
    ):
        escaped = "\\u%04x" % code if code <= 0xFFFF else "\\U%08x" % code
        return '"' + escaped + '"'
    return '"' + char + '"'


def set_field(payload, section, index, key, value):
    target = payload[section] if index is None else payload[section][index]
    target[key] = value


def test_valid_fixture_matches_expected_text():
    import json

    data = json.loads((ROOT / "tests" / "fixtures" / "valid.json").read_bytes())

    assert render.render_text(memo_of(data)) == FIXTURE_TEXT.read_bytes()


def test_quote_full_codepoint_sweep():
    for code in range(0x110000):
        char = chr(code)
        assert render.quote(char) == expected_quote(char), hex(code)


def test_quote_wraps_and_keeps_plain_text():
    assert render.quote("") == '""'
    assert render.quote("a b") == '"a b"'


def test_constants():
    assert render.ESCAPED_CATEGORIES == frozenset(ESCAPED_GROUPS)
    assert render.FILLERS == frozenset(chr(code) for code in FILLER_CODEPOINTS)
    assert render.KIND_LABELS == {
        "actual": "thực tế (actual)",
        "forecast": "dự báo (forecast)",
        "unknown": "không rõ (unknown)",
    }


@pytest.mark.parametrize("character", SC2_CHARACTERS, ids=lambda c: "U+%04X" % ord(c))
@pytest.mark.parametrize("section,index,key", TEXT_FIELDS, ids=lambda v: str(v))
def test_sc2_characters_in_every_field(character, section, index, key):
    base = build_valid_payload()
    set_field(base, section, index, key, "ab")
    baseline = render.render_text(memo_of(base))
    payload = build_valid_payload()
    set_field(payload, section, index, key, "a" + character + "b")

    out = render.render_text(memo_of(payload))

    raw = character.encode("utf-8")
    assert out.count(raw) == baseline.count(raw)
    code = ord(character)
    assert ("\\u%04x" % code).encode() in out


def test_vietnamese_and_private_use_kept():
    payload = build_valid_payload()
    payload["decision"]["question"] = "Có nên áp dụng  nhịp mới không?"

    out = render.render_text(memo_of(payload)).decode("utf-8")

    assert '"Có nên áp dụng  nhịp mới không?"' in out


ADVERSARIAL = (
    '[GIỮ HIỆN TRẠNG] [TRONG KỲ] " \\ ``` ~~~ # ĐÃ DUYỆT [x](http://a)\n'
    '```\n~~~\n# ĐÃ DUYỆT\nBằng chứng (0): không có'
)


def adversarial_payload():
    payload = build_valid_payload()
    payload["decision"]["question"] = ADVERSARIAL
    payload["decision"]["owner"] = ADVERSARIAL
    payload["decision"]["dissent"] = ADVERSARIAL
    for option in payload["options"]:
        for key in ("name", "pros", "cons", "reversal", "actions"):
            option[key] = ADVERSARIAL
    for index, item in enumerate(payload["evidence"]):
        for key in ("owner", "period", "claim", "source_uri"):
            item[key] = ADVERSARIAL
        item["id"] = ADVERSARIAL + str(index)
    return payload


def test_frame_is_input_independent():
    import json

    fixture = json.loads((ROOT / "tests" / "fixtures" / "valid.json").read_bytes())
    expected = QUOTED.sub("", render.render_text(memo_of(fixture)).decode("utf-8"))

    out = render.render_text(memo_of(adversarial_payload())).decode("utf-8")

    assert QUOTED.sub("", out) == expected


def test_no_line_starts_with_fence():
    out = render.render_text(memo_of(adversarial_payload())).decode("utf-8")

    for line in out.split("\n"):
        assert not line.lstrip().startswith(("```", "~~~", "#"))


def test_lone_surrogate_renders():
    payload = build_valid_payload()
    payload["decision"]["question"] = "x\ud800y"

    out = render.render_text(memo_of(payload))

    assert b'"x\\ud800y"' in out
    out.decode("utf-8")


def test_no_trailing_whitespace_and_single_final_lf():
    out = render.render_text(memo_of(adversarial_payload())).decode("utf-8")

    assert out.endswith("\n") and not out.endswith("\n\n")
    assert "\r" not in out
    for line in out.split("\n"):
        assert line == line.rstrip(" \t")


def test_empty_evidence_and_no_warnings():
    payload = build_valid_payload()
    payload["evidence"] = []
    out = render.render_text(memo_of(payload)).decode("utf-8")

    assert "\nBằng chứng (0): không có\n" in out
    assert "\nCảnh báo (1):\n- [KHÔNG CÓ BẰNG CHỨNG] không có bằng chứng nào\n" in out

    payload = build_valid_payload()
    del payload["evidence"][1]
    out = render.render_text(memo_of(payload)).decode("utf-8")

    assert "\nCảnh báo (0): không có\n" in out


def test_out_of_period_and_conflict_lines():
    payload = build_valid_payload()
    template = payload["evidence"][0]
    items = []
    for name, effective_to, group in (
        ("e1", "2026-11-01", ""),
        ("e2", "2026-11-02", ""),
        ("e3", "2026-11-15", "g"),
        ("e4", "2026-11-15", "g"),
    ):
        item = copy.deepcopy(template)
        item.update(id=name, effective_to=effective_to, conflict_group=group)
        items.append(item)
    items[0]["effective_from"] = items[1]["effective_from"] = "2026-10-01"
    payload["evidence"] = items

    out = render.render_text(memo_of(payload)).decode("utf-8")

    assert out.count("[NGOÀI KỲ] \"e") == 2
    assert out.count("[TRONG KỲ] \"e") == 2
    assert '   Nhóm mâu thuẫn: "g"\n' in out
    assert (
        "Cảnh báo (2):\n"
        '- [NGOÀI KỲ] bằng chứng ngoài kỳ: "e1", "e2"\n'
        '- [MÂU THUẪN] bằng chứng mâu thuẫn: "e3", "e4"\n'
    ) in out
