"""Static checks of the CI workflow and its lock file (read as text; no YAML dependency, no network)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
LOCK = ROOT / "requirements-ci.txt"
LOCK_IN = ROOT / "requirements-ci.in"
TEST_COMMAND = (
    "python -B -m pytest -q -p no:cacheprovider --cov=agent_executive_team --cov-branch --cov-fail-under=80"
)


def _text():
    return WORKFLOW.read_text(encoding="utf-8")


def _lines():
    return [line.rstrip() for line in _text().splitlines()]


def test_permissions_are_contents_read_only():
    lines = _lines()
    assert "permissions:" in lines
    block = []
    for line in lines[lines.index("permissions:") + 1 :]:
        if not line.startswith(" "):
            break
        block.append(line.strip())
    assert block == ["contents: read"]
    assert len([line for line in lines if line.startswith("permissions:")]) == 1
    assert not [line for line in lines if line.strip().startswith("permissions:") and line.startswith(" ")]


def test_every_action_is_pinned_to_a_full_commit():
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", _text(), re.M)
    assert uses, "expected at least one action"
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), ref
    assert {ref.split("@")[0] for ref in uses} == {"actions/checkout", "actions/setup-python"}


def test_no_secrets_and_no_pull_request_target():
    text = _text()
    assert "pull_request_target" not in text
    assert "secrets." not in text
    assert "secrets:" not in text


def test_checkout_does_not_persist_credentials():
    assert re.search(r"actions/checkout@[0-9a-f]{40}.*\n\s+with:\n\s+persist-credentials: false", _text())


def test_matrix_is_three_os_by_three_pythons():
    text = _text()
    os_match = re.search(r"^\s+os: \[(.*?)\]\s*$", text, re.M)
    py_match = re.search(r"^\s+python-version: \[(.*?)\]\s*$", text, re.M)
    assert os_match and py_match
    assert [item.strip() for item in os_match.group(1).split(",")] == [
        "ubuntu-latest",
        "macos-latest",
        "windows-latest",
    ]
    assert [item.strip() for item in py_match.group(1).split(",")] == ['"3.11"', '"3.12"', '"3.13"']
    assert "fail-fast: false" in text
    assert "runs-on: ${{ matrix.os }}" in text


def test_tools_install_from_the_hashed_lock_file_and_suite_runs_with_coverage_gate():
    text = _text()
    assert "python -m pip install --require-hashes -r requirements-ci.txt" in text
    assert TEST_COMMAND in text
    assert "--cov-fail-under=80" in text


def test_triggers_cover_push_and_pull_request():
    lines = _lines()
    assert "on:" in lines
    assert "  push:" in lines and "  pull_request:" in lines


def test_lock_file_has_hashes_and_matches_the_input_list():
    names = [line.strip() for line in LOCK_IN.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert names == ["pytest", "pytest-cov"]
    lock = LOCK.read_text(encoding="utf-8")
    assert "--hash=sha256:" in lock
    for name in names:
        assert re.search(rf"^{re.escape(name)}==", lock, re.M), name
    for line in lock.splitlines():
        if re.match(r"^[A-Za-z0-9_.-]+==", line):
            assert line.rstrip().endswith("\\"), line
