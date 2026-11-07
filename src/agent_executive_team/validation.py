"""Strict input-contract validation: bytes in, parsed dict out, one stable error for bad input.

Every input-caused failure (bad size, encoding, JSON, shape, value, scope, nesting depth) is
reported as ``ValidationError`` with the fixed code ``invalid_input``; the error never carries or
chains any part of the payload. A bug in this module is not converted: it propagates unchanged.
Input text is opaque data: nothing here follows, fetches or interprets it.
"""

import json
import re
from datetime import date

ALLOWED_TENANTS = frozenset({"synthetic-demo"})
ALLOWED_KINDS = frozenset({"actual", "forecast", "unknown"})

MAX_BYTES = 65536
MAX_TEXT = 500
MIN_OPTIONS, MAX_OPTIONS = 2, 4
MAX_EVIDENCE = 20

_BOM = b"\xef\xbb\xbf"
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_TOP_KEYS = frozenset({"version", "decision", "options", "evidence"})
_DECISION_TEXT_KEYS = ("question", "owner", "dissent")
_DECISION_DATE_KEYS = ("deadline", "review_date", "as_of")
_DECISION_KEYS = frozenset(_DECISION_TEXT_KEYS + _DECISION_DATE_KEYS)
_OPTION_TEXT_KEYS = ("name", "pros", "cons", "reversal", "actions")
_OPTION_KEYS = frozenset(_OPTION_TEXT_KEYS + ("status_quo",))
_EVIDENCE_TEXT_KEYS = ("id", "tenant", "owner", "period", "claim", "source_uri")
_EVIDENCE_KEYS = frozenset(
    _EVIDENCE_TEXT_KEYS + ("effective_from", "effective_to", "kind", "conflict_group")
)


class ValidationError(Exception):
    """Input rejected. Stable code, no payload."""

    code = "invalid_input"

    def __init__(self):
        super().__init__(self.code)


class _Invalid(Exception):
    """Internal control flow only; never escapes ``validate``."""


def _require(condition):
    if not condition:
        raise _Invalid


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reject_constant(_name):
    raise _Invalid


def _parse(data):
    _require(type(data) is bytes)
    _require(len(data) <= MAX_BYTES)  # before any decoding
    _require(not data.startswith(_BOM))
    text = data.decode("utf-8")  # strict
    return json.loads(
        text,
        object_pairs_hook=_object_without_duplicates,
        parse_constant=_reject_constant,
    )


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)
    return value


def _text(value, allow_empty=False):
    _require(isinstance(value, str))
    if allow_empty and value == "":
        return
    _require(len(value) <= MAX_TEXT)
    _require(value.strip() != "")  # also rejects "" (minimum length 1)


def parse_date(value: str) -> date:
    """Return the ``date`` of a ``YYYY-MM-DD`` string; ValueError if it is not a real day."""
    return date(int(value[0:4]), int(value[5:7]), int(value[8:10]))


def _date(value):
    _require(isinstance(value, str) and _DATE_RE.fullmatch(value) is not None)
    return parse_date(value)


def _check_decision(decision):
    _object(decision, _DECISION_KEYS)
    for key in _DECISION_TEXT_KEYS:
        _text(decision[key])
    for key in _DECISION_DATE_KEYS:
        _date(decision[key])


def _check_options(options):
    _require(type(options) is list and MIN_OPTIONS <= len(options) <= MAX_OPTIONS)
    status_quo_count = 0
    for option in options:
        _object(option, _OPTION_KEYS)
        for key in _OPTION_TEXT_KEYS:
            _text(option[key])
        _require(type(option["status_quo"]) is bool)
        status_quo_count += option["status_quo"]
    _require(status_quo_count == 1)


def _check_evidence(evidence):
    _require(type(evidence) is list and len(evidence) <= MAX_EVIDENCE)
    seen_ids = set()
    for item in evidence:
        _object(item, _EVIDENCE_KEYS)
        for key in _EVIDENCE_TEXT_KEYS:
            _text(item[key])
        _text(item["conflict_group"], allow_empty=True)
        _require(item["id"] not in seen_ids)
        seen_ids.add(item["id"])
        _require(item["tenant"] in ALLOWED_TENANTS)
        _require(isinstance(item["kind"], str) and item["kind"] in ALLOWED_KINDS)
        _require(_date(item["effective_from"]) <= _date(item["effective_to"]))


def _check(payload):
    _object(payload, _TOP_KEYS)
    _require(type(payload["version"]) is int and payload["version"] == 1)
    _check_decision(payload["decision"])
    _check_options(payload["options"])
    _check_evidence(payload["evidence"])


def validate(data: bytes) -> dict:
    """Return the parsed payload dict if ``data`` meets the contract, else raise ValidationError.

    Only input-caused failures map to ``invalid_input``: our own ``_Invalid``, ``ValueError``
    (JSONDecodeError, UnicodeDecodeError, int-digit limit, impossible calendar day) and
    ``RecursionError`` (deep nesting). Anything else is a bug and propagates unchanged, so the
    caller can report it as an internal error. Hence every type check below is explicit.
    """
    try:
        payload = _parse(data)
        _check(payload)
    except (_Invalid, ValueError, RecursionError):
        payload = None
    if payload is None:
        # Raised outside the handler so no original exception (and its payload) is chained.
        raise ValidationError()
    return payload
