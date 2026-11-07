"""Packaging checks: manifests, the single skill, repo-rule files and what must not ship.

Reads the repository files as they are (no network, no writes). Each assertion guards one
packaging promise; removing the thing it guards turns it red.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
COMMAND = "python -B -m agent_executive_team"
FORBIDDEN = ("RESEARCH_ORIGINAL", "OneDrive", "C:/Users", "C:\\Users", "workshop-records")
# Vietnamese letters that never occur in English prose.
VIETNAMESE = re.compile(
    "[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE
)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_dirs():
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()) if SKILLS_DIR.is_dir() else []


def _frontmatter_and_body(text):
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    assert match, "SKILL.md must start with a --- frontmatter block"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


def _shipped_files():
    """Every tracked-by-intent file: the repo minus VCS, caches, scratch and test-only paths."""
    skip_dirs = {".git", ".pytest_cache", ".tmp", "__pycache__", "tests"}
    skip_names = {".coverage"}
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not (set(p.relative_to(ROOT).parts) & skip_dirs)
        and p.name not in skip_names
        and p.suffix != ".pyc"
    ]


@pytest.mark.parametrize("manifest", [CLAUDE_MANIFEST, CODEX_MANIFEST], ids=["claude", "codex"])
def test_manifest_fields(manifest):
    data = _load(manifest)
    assert data["name"] == "agent-executive-team"
    assert data["version"] == "0.1.0"
    assert data["skills"] == "./skills/"
    assert data["license"] == "UNLICENSED"
    assert data["author"] == {"name": "Nguyễn Quang Đức"}
    for forbidden_key in ("homepage", "repository", "email"):
        assert forbidden_key not in data
        assert forbidden_key not in data["author"]


def test_manifests_agree_on_name_and_version():
    claude, codex = _load(CLAUDE_MANIFEST), _load(CODEX_MANIFEST)
    assert (claude["name"], claude["version"]) == (codex["name"], codex["version"])


def test_codex_capabilities_are_read_only_interactive():
    capabilities = _load(CODEX_MANIFEST)["interface"]["capabilities"]
    assert capabilities == ["Interactive", "Read"]
    assert "Write" not in capabilities


def test_exactly_one_skill_with_skill_md():
    dirs = _skill_dirs()
    assert [d.name for d in dirs] == ["chief-of-staff"]
    assert (dirs[0] / "SKILL.md").is_file()


def _skill_text():
    return (SKILLS_DIR / "chief-of-staff" / "SKILL.md").read_text(encoding="utf-8")


def test_skill_frontmatter_is_ascii_english():
    fields, _ = _frontmatter_and_body(_skill_text())
    assert fields["name"] == "chief-of-staff"
    description = fields["description"]
    assert description.isascii() and description
    assert "Use when" in description
    assert "Not " in description


def test_skill_body_is_vietnamese_and_states_limits():
    _, body = _frontmatter_and_body(_skill_text())
    assert VIETNAMESE.search(body)
    for needle in ("synthetic-demo", "needs_human_decision", "needs_review", "proposed", "unverified"):
        assert needle in body


def test_skill_and_readme_give_the_command_and_exit_codes():
    for text in (_skill_text(), README.read_text(encoding="utf-8")):
        assert COMMAND in text
        for code in ("invalid_input", "internal_error"):
            assert code in text
        for exit_code in ("exit 0", "exit 1", "exit 2"):
            assert exit_code in text


def test_readme_warns_about_scope_and_license():
    text = README.read_text(encoding="utf-8")
    assert "bản nháp xác định" in text
    assert "không phải" in text and "AI" in text
    assert "dữ liệu tổng hợp" in text
    assert "UNLICENSED" in text
    assert "chưa phát hành" in text


def test_claude_md_is_exactly_the_agents_import():
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"


def test_agents_and_gemini_exist_and_point_correctly():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for heading in ("## Phạm vi", "## Dữ liệu và quyền", "## Kiểm trước khi báo xong"):
        assert heading in agents
    gemini = (ROOT / "GEMINI.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in gemini


def test_gemini_is_a_prose_pointer_not_an_import():
    gemini = (ROOT / "GEMINI.md").read_text(encoding="utf-8")
    assert not any(line.strip().startswith("@") for line in gemini.splitlines())


def test_excluded_files_are_absent():
    for name in ("ECOSYSTEM.md", "LICENSE", "docs/CONTRACT.md"):
        assert not (ROOT / name).exists()


def test_shipped_files_have_no_private_or_source_references():
    files = _shipped_files()
    assert files, "expected shipped files to scan"
    for path in files:
        if path.suffix in {".json", ".md", ".py", ".txt", ".ini", ".gitignore", ""} or path.name.startswith("."):
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in FORBIDDEN:
                assert needle not in text, f"{needle!r} found in {path.relative_to(ROOT)}"
    assert not list(ROOT.rglob("RESEARCH_ORIGINAL*"))


# --- Step 4 fix round: README/skill numbers and commands must match the code ---

BACKSLASH = chr(92)  # written this way so the file holds no ambiguous escape
POWERSHELL_COMMAND = (
    'cmd /c "python -B -m agent_executive_team < tests' + BACKSLASH + 'fixtures' + BACKSLASH + 'valid.json"'
)


def _readme():
    return README.read_text(encoding="utf-8")


def test_readme_numbers_match_validation_constants():
    from agent_executive_team import validation as v

    text = _readme()
    words = {3: "Ba", 4: "Bốn"}
    assert f"tối đa {v.MAX_BYTES} byte" in text
    assert f"tối đa {v.MAX_TEXT} ký tự" in text
    assert f"{v.MIN_OPTIONS} đến {v.MAX_OPTIONS} phương án" in text
    assert f"0 đến {v.MAX_EVIDENCE} bằng chứng" in text
    assert f"{words[len(v._TOP_KEYS)]} khóa cấp trên cùng" in text
    assert "Ba khóa" not in text or len(v._TOP_KEYS) == 3


def test_readme_names_every_contract_key():
    from agent_executive_team import validation as v

    text = _readme()
    keys = v._TOP_KEYS | v._DECISION_KEYS | v._OPTION_KEYS | v._EVIDENCE_KEYS
    for key in sorted(keys):
        assert f"`{key}`" in text, key
    for kind in sorted(v.ALLOWED_KINDS):
        assert f"`{kind}`" in text, kind


def test_skill_numbers_match_validation_constants():
    from agent_executive_team import validation as v

    _, body = _frontmatter_and_body(_skill_text())
    assert f"từ {v.MIN_OPTIONS} đến {v.MAX_OPTIONS} phương án" in body
    assert f"tối đa {v.MAX_EVIDENCE} bằng chứng" in body


def test_powershell_command_avoids_the_bom_pipe():
    for text in (_readme(), _skill_text()):
        assert POWERSHELL_COMMAND in text
        assert "BOM" in text
        assert "Get-Content -Raw tests" not in text  # the old command that exits 2


def test_skill_points_to_readme_contract_and_explains_exit_2():
    _, body = _frontmatter_and_body(_skill_text())
    assert "README" in body and "Hợp đồng input" in body and "Hợp đồng output" in body
    assert "tự đối chiếu input" in body


def test_skill_forbids_labelling_real_data_synthetic():
    _, body = _frontmatter_and_body(_skill_text())
    assert "Cấm gắn nhãn `synthetic-demo` cho dữ liệu thật" in body
    assert "không phải phân quyền" in body


def test_exit_1_says_input_is_not_echoed():
    assert "`internal_error`, không in lại nội dung input" in _readme()
    assert "`internal_error`, không in lại input" in _skill_text()
