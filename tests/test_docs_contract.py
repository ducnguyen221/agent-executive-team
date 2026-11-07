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


def _exit_table_rows():
    """The exit-code table of CONTRACT section 3 as an ordered list of (code, stderr cell) pairs."""
    section = _read(CONTRACT).split("## 3. ", 1)[1].split("\n## 4. ", 1)[0]
    pairs = []
    for code, cell in re.findall(r"^\| `(\d+)` \| (.*?) \| ", section, re.M):
        pairs.append((int(code), re.fullmatch(r"`([a-z_]+)`", cell).group(1) if cell.startswith("`") else cell))
    return pairs


def test_contract_exit_table_matches_cli_constants():
    expected = [
        (cli.EXIT_OK, "rỗng"),
        (cli.EXIT_INTERNAL, cli.INTERNAL_ERROR.decode().strip()),
        (cli.EXIT_INTERNAL, "thông báo của shell (không phải của chương trình)"),
        (cli.EXIT_INVALID, cli.INVALID_INPUT.decode().strip()),
        (cli.EXIT_INVALID, cli.INVALID_ARGUMENTS.decode().strip()),
        (9009, '"Python was not found" (cmd, Windows)'),
    ]
    assert _exit_table_rows() == expected


def test_python_floor_phrase_is_the_same_everywhere():
    for path in (README, SKILL, CONTRACT):
        assert "Python 3.11 trở lên" in _read(path), path.name
        assert "3.10" not in _read(path), path.name


def test_readme_names_both_install_sources_and_no_stale_remote_claim():
    text = _read(README)
    assert "chưa có remote" not in text.lower()
    assert "ducnguyen221/agent-executive-team" in text
    assert "chưa kiểm cài thật" in text


def test_skill_demands_verbatim_command_blocks():
    assert (
        "Chép **nguyên khối** phù hợp với shell, chỉ thay hai giá trị trong nháy đơn; không rút gọn, "
        "không bỏ nháy, không bỏ hay đổi các dòng đặt biến — chúng chặn đường có ký tự lạ và `python` "
        "giả ở thư mục hiện hành. Không tự viết lệnh `cmd` hay `python` khác."
    ) in _read(SKILL)


def test_skill_exit_table_names_every_accepted_argument_form():
    assert "chỉ nhận không đối số, `--format json` hoặc `--format text`" in _read(SKILL)


def test_gitignore_keeps_local_claude_settings_out_but_not_claude_md():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/settings.local.json" in lines
    assert not any(line.strip().rstrip("/") in (".claude", ".claude/*", ".claude/CLAUDE.md") for line in lines)


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


def test_changelog_has_current_and_first_release():
    import json

    text = _read(CHANGELOG)
    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert f"## {version} — " in text
    assert "SPR-02" in text
    assert "0.1.0 — 2026-11-07" in text


def test_readme_points_to_contract_and_ecosystem():
    text = _read(README)
    assert "docs/CONTRACT.md" in text and "ECOSYSTEM.md" in text and "CHANGELOG.md" in text
