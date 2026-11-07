"""Docs lock: the calling contract, README and SKILL.md agree with the code and with each other."""

import re
from pathlib import Path

import pytest

from agent_executive_team import cli

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SKILL = ROOT / "skills" / "chief-of-staff" / "SKILL.md"
CONTRACT = ROOT / "docs" / "CONTRACT.md"
ECOSYSTEM = ROOT / "ECOSYSTEM.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SHARED = ("--format", "text", "invalid_input", "invalid_arguments", "internal_error", "3.11")


def _read(path):
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [README, SKILL, CONTRACT], ids=["README", "SKILL", "CONTRACT"])
@pytest.mark.parametrize("needle", SHARED)
def test_shared_strings_are_in_every_document(path, needle):
    assert needle in _read(path)


def test_contract_frontmatter():
    match = re.match(r"---\n(.*?)\n---\n", _read(CONTRACT), re.DOTALL)
    assert match
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    assert fields == {
        "title": "agent-executive-team calling contract",
        "status": "draft",
        "api_version": '"1.1.0"',
        "schema_version": "1",
        "audience": "pipelines, schedulers, agents",
    }


def test_contract_has_the_eight_sections():
    headings = re.findall(r"^## (\d+)\. ", _read(CONTRACT), re.M)
    assert headings == [str(n) for n in range(1, 9)]


def test_contract_exit_table_matches_cli_constants():
    text = _read(CONTRACT)
    rows = dict(re.findall(r"^\| `(\d+)` \| `?([a-z_]*)`?", text, re.M))
    assert set(rows) >= {str(cli.EXIT_OK), str(cli.EXIT_INTERNAL), str(cli.EXIT_INVALID), "9009"}
    assert "`internal_error`" in text and "`invalid_input`" in text
    for constant, name in ((cli.EXIT_OK, "0"), (cli.EXIT_INTERNAL, "1"), (cli.EXIT_INVALID, "2")):
        assert str(constant) == name
    assert "exit 1 kèm thông báo shell" in text.lower() or "kèm thông báo của shell" in text


def test_contract_stderr_lines_match_cli_bytes():
    text = _read(CONTRACT)
    for line in (cli.INVALID_INPUT, cli.INVALID_ARGUMENTS, cli.INTERNAL_ERROR):
        assert f"`{line.decode().strip()}`" in text


def test_contract_names_launcher_and_module_forms():
    text = _read(CONTRACT)
    assert "scripts/executive_memo.py" in text
    assert "-m agent_executive_team" in text
    assert "không ổn định" in text


def test_ecosystem_has_five_labels():
    text = _read(ECOSYSTEM)
    for label in ("Role", "Upstream", "Downstream", "Bundles", "Handoff"):
        assert f"- **{label}:**" in text


def test_changelog_has_unreleased_and_first_release():
    text = _read(CHANGELOG)
    assert "Chưa phát hành" in text
    assert "SPR-02" in text
    assert "0.1.0 — 2026-11-07" in text


def test_readme_points_to_contract_and_ecosystem():
    text = _read(README)
    assert "docs/CONTRACT.md" in text and "ECOSYSTEM.md" in text and "CHANGELOG.md" in text
