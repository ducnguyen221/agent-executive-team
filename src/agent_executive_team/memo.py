"""Deterministic decision memo: a validated payload in, a draft memo dict out, bytes on request.

The three statuses are constants and never read from input. Every input string is opaque data,
copied through unchanged; nothing here follows, fetches or interprets it. ``build_memo`` assumes
its argument already passed ``validation.validate`` and does not re-check the contract.
"""

import copy
import json
from collections import Counter

from agent_executive_team.validation import parse_date

MEMO_VERSION = 1
STATUS = "needs_human_decision"
AGENT_STATUS = "needs_review"
DECISION_STATUS = "proposed"
VERIFICATION = "unverified"

IN_PERIOD = "in_period"
OUT_OF_PERIOD = "out_of_period"


def _label_evidence(item, as_of):
    labelled = copy.deepcopy(item)
    in_period = parse_date(item["effective_from"]) <= as_of <= parse_date(item["effective_to"])
    labelled["verification"] = VERIFICATION
    labelled["period_status"] = IN_PERIOD if in_period else OUT_OF_PERIOD
    return labelled


def _conflict_ids(evidence):
    sizes = Counter(item["conflict_group"] for item in evidence if item["conflict_group"] != "")
    return [item["id"] for item in evidence if sizes[item["conflict_group"]] >= 2]


def _warnings(evidence):
    warnings = []
    if not evidence:
        warnings.append({"code": "no_evidence", "evidence_ids": []})
    out_of_period = [e["id"] for e in evidence if e["period_status"] == OUT_OF_PERIOD]
    if out_of_period:
        warnings.append({"code": "out_of_period", "evidence_ids": out_of_period})
    conflict = _conflict_ids(evidence)
    if conflict:
        warnings.append({"code": "conflict", "evidence_ids": conflict})
    return warnings


def build_memo(data: dict) -> dict:
    """Return the memo for a validated payload; ``data`` is not modified."""
    as_of = parse_date(data["decision"]["as_of"])
    evidence = [_label_evidence(item, as_of) for item in data["evidence"]]
    return {
        "version": MEMO_VERSION,
        "status": STATUS,
        "agent_status": AGENT_STATUS,
        "decision_status": DECISION_STATUS,
        "decision": copy.deepcopy(data["decision"]),
        "options": copy.deepcopy(data["options"]),
        "evidence": evidence,
        "warnings": _warnings(evidence),
    }


def serialize(memo: dict) -> bytes:
    """Return the memo as ASCII JSON bytes: sorted keys, compact, one trailing LF.

    ``ensure_ascii`` escapes every non-ASCII code point, lone surrogates included, so the
    result always encodes.
    """
    text = json.dumps(memo, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8") + b"\n"
