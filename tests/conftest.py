"""Shared fixtures: a fresh, valid synthetic payload for validation, memo and CLI tests."""

import copy

import pytest

_VALID_PAYLOAD = {
    "version": 1,
    "decision": {
        "question": "Should the synthetic team adopt the new planning cadence?",
        "owner": "Synthetic Owner",
        "deadline": "2026-11-30",
        "review_date": "2026-12-01",
        "as_of": "2026-11-07",
        "dissent": "Synthetic dissent: the current cadence is already stable.",
    },
    "options": [
        {
            "name": "Keep current cadence",
            "pros": "No change cost.",
            "cons": "Known planning delays remain.",
            "reversal": "Nothing to reverse.",
            "actions": "Continue as is and re-check at the review date.",
            "status_quo": True,
        },
        {
            "name": "Adopt new cadence",
            "pros": "Shorter planning loop.",
            "cons": "Needs a one-time retraining.",
            "reversal": "Return to the old cadence after one cycle.",
            "actions": "Run a one-cycle pilot with the synthetic team.",
            "status_quo": False,
        },
    ],
    "evidence": [
        {
            "id": "ev-001",
            "tenant": "synthetic-demo",
            "owner": "Synthetic Analyst A",
            "period": "2026-11 first half",
            "effective_from": "2026-11-01",
            "effective_to": "2026-11-15",
            "kind": "actual",
            "claim": "Planning took 9 days in the synthetic sample.",
            "source_uri": "synthetic://sample/planning-log",
            "conflict_group": "",
        },
        {
            "id": "ev-002",
            "tenant": "synthetic-demo",
            "owner": "Synthetic Analyst B",
            "period": "2026-11 second half",
            "effective_from": "2026-11-20",
            "effective_to": "2026-12-15",
            "kind": "forecast",
            "claim": "A pilot may cut planning to 6 days.",
            "source_uri": "synthetic://sample/pilot-forecast",
            "conflict_group": "",
        },
    ],
}


def build_valid_payload():
    """Return a NEW valid synthetic payload (2 options, one status quo, 2 evidence)."""
    return copy.deepcopy(_VALID_PAYLOAD)


@pytest.fixture
def valid_payload():
    """A fresh valid payload dict; safe to mutate inside a test."""
    return build_valid_payload()


@pytest.fixture
def payload_factory():
    """The factory itself, for tests that need several independent payloads."""
    return build_valid_payload
