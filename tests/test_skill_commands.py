"""Run the command blocks written in SKILL.md, as written, from a copy of the plugin placed at a hostile path.

Only the two <placeholders> are replaced, by single-quoted real paths. The child environment never carries
``NoDefaultCurrentDirectoryInExePath``, the working directory holds a fake package and fake ``python.bat``
and ``python.cmd`` files, and the install path and input file name carry real shell payloads: any marker
file (``SHADOWED``, ``HIJACKED``, ``INJ_*``) means something other than the skill ran.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = ROOT / "skills" / "chief-of-staff" / "SKILL.md"
FIXTURES = ROOT / "tests" / "fixtures"
SKILL_PLACEHOLDER = "<thư mục skill>"
INPUT_PLACEHOLDER = "<file JSON input>"
ON_CI = os.environ.get("CI") == "true"
WINDOWS = os.name == "nt"
# On CI the shells that carry this OS's block must exist, so the tests below cannot all skip.
REQUIRED = {"bash", "powershell", "pwsh"} if WINDOWS else {"bash"}
PS_QUOTES = "'‘’‚‛"
# Windows forbids " < > : | ? * in names, so the Windows payloads avoid them; POSIX may carry a double quote.
COMMON_NAME = "a b$x%PATH%!x!&^;() é"
PAYLOADS = {
    "bash": "x'; touch INJ_SH; '$(touch INJ_SUB)",
    "powershell": "x’; New-Item INJ_PS; ’" + "x'; New-Item INJ_PS2; '" + "x&md INJ_CMD&",
}
if not WINDOWS:  # a double quote is legal in a POSIX name only
    PAYLOADS["bash"] += '"; touch INJ_DQ; "'
NO_DEFAULT_CWD = "NODEFAULTCURRENTDIRECTORYINEXEPATH"
MARKERS = ("SHADOWED", "HIJACKED", "INJ_*")


def block(kind: str) -> str:
    match = re.search(rf"^```{kind}\n(.*?)^```", SKILL_MD.read_text(encoding="utf-8"), re.M | re.S)
    assert match, f"no {kind} block in SKILL.md"
    return match.group(1)


def quote(kind: str, value: str) -> str:
    """Single-quote a path the way SKILL.md says: bash '\\'' and PowerShell '' (curly quotes doubled too)."""
    if kind == "bash":
        inner = value.replace("'", "'\\''")
    else:
        inner = "".join(c + c if c in PS_QUOTES else c for c in value)
    return f"'{inner}'"


def fill(kind: str, skill_dir: Path, input_file: Path) -> str:
    script = block(kind)
    for placeholder, value in ((SKILL_PLACEHOLDER, skill_dir), (INPUT_PLACEHOLDER, input_file)):
        token = f"'{placeholder}'"
        assert token in script, token
        script = script.replace(token, quote(kind, str(value)))
    assert SKILL_PLACEHOLDER not in script and INPUT_PLACEHOLDER not in script
    return script


def find_bash() -> str | None:
    found = shutil.which("bash")
    if WINDOWS and (found is None or "system32" in found.lower()):
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            candidate = Path(base or ".") / "Git" / "bin" / "bash.exe"
            if base and candidate.exists():
                return str(candidate)
        return None
    return found


# shell id -> (block kind, finder)
SHELLS = {"bash": ("bash", find_bash)}
if WINDOWS:  # the PowerShell block drives cmd.exe, so it only means something on Windows
    SHELLS["powershell"] = ("powershell", lambda: shutil.which("powershell"))
    SHELLS["pwsh"] = ("powershell", lambda: shutil.which("pwsh"))


def shell_or_skip(shell: str) -> str:
    exe = SHELLS[shell][1]()
    if exe:
        return exe
    if ON_CI and shell in REQUIRED:
        pytest.fail(f"CI must run the {shell} block on this OS but no {shell} was found")
    pytest.skip(f"no {shell} on this machine")


def child_env(pythonpath: Path | None = None) -> dict:
    """Environment of the child shell: no inherited guard variable (any letter case), optional PYTHONPATH trap."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", NO_DEFAULT_CWD)}
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return env


def install_copy(base: Path, name: str, *, with_src: bool = True) -> Path:
    """Copy skills/ (and src/) to base/name, the way a harness installs the plugin; return the plugin root."""
    plugin = base / name
    shutil.copytree(ROOT / "skills", plugin / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    if with_src:
        shutil.copytree(ROOT / "src", plugin / "src", ignore=shutil.ignore_patterns("__pycache__"))
    return plugin


def hostile_name(kind: str) -> str:
    return COMMON_NAME + PAYLOADS[kind]


def decoy_workdir(base: Path) -> Path:
    """A working directory that would hijack an import or a bare `python` lookup."""
    work = base / "work"
    package = work / "agent_executive_team"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("open('SHADOWED', 'w').close()\n", encoding="utf-8")
    (package / "cli.py").write_text("def main(argv=None):\n    return 0\n", encoding="utf-8")
    # Imported by any interpreter that honours PYTHONPATH (one started without -I).
    (work / "sitecustomize.py").write_text("open('SHADOWED', 'w').close()\n", encoding="utf-8")
    for name in ("python.bat", "python.cmd"):
        (work / name).write_bytes(b"@echo off\r\ncopy nul HIJACKED >nul\r\n")
    return work


def run_script(shell: str, script: str, work: Path) -> subprocess.CompletedProcess:
    exe = shell_or_skip(shell)
    if shell == "bash":
        argv = [exe, "-c", script]
    else:
        file = work.parent / "run.ps1"  # outside the working directory so it never counts as a stray file
        # the block leaves the CLI exit code in $LASTEXITCODE only; -File would report 0 without this line
        file.write_text(script + "\nexit $LASTEXITCODE\n", encoding="utf-8-sig")
        argv = [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(file)]
    return subprocess.run(argv, cwd=work, env=child_env(pythonpath=work), capture_output=True, timeout=120)


def stdout_bytes(shell: str, done: subprocess.CompletedProcess) -> bytes:
    # PowerShell re-emits native output line by line with CRLF; the content is otherwise unchanged.
    return done.stdout.replace(b"\r\n", b"\n") if shell != "bash" else done.stdout


def assert_no_markers(base: Path):
    for pattern in MARKERS:
        stray = list(base.rglob(pattern))
        assert not stray, f"something other than the skill ran: {stray}"


def setup_case(shell: str, base: Path, *, install_name: str | None = None):
    kind = SHELLS[shell][0]
    name = install_name or hostile_name(kind)
    plugin = install_copy(base, name)
    input_file = plugin.parent / (hostile_name(kind) + ".json")
    shutil.copyfile(FIXTURES / "valid.json", input_file)
    return plugin, input_file, decoy_workdir(base)


GOLDEN_TEXT = (FIXTURES / "valid.text").read_bytes()
ALL_SHELLS = sorted(SHELLS)


@pytest.mark.parametrize("shell", ALL_SHELLS)
def test_skill_block_prints_the_reading_from_a_hostile_install_path(shell, tmp_path):
    shell_or_skip(shell)
    plugin, input_file, work = setup_case(shell, tmp_path)
    script = fill(SHELLS[shell][0], plugin / "skills" / "chief-of-staff", input_file)
    done = run_script(shell, script, work)
    assert done.returncode == 0, f"exit {done.returncode}: {done.stderr[-400:]!r}"
    assert stdout_bytes(shell, done) == GOLDEN_TEXT
    assert_no_markers(tmp_path)


@pytest.mark.parametrize("shell", ALL_SHELLS)
def test_skill_block_works_through_a_link_to_the_skill_dir(shell, tmp_path):
    """Antigravity installs by junction: the plugin root must be found from the real path."""
    shell_or_skip(shell)
    plugin, input_file, work = setup_case(shell, tmp_path, install_name="plugin copy")
    target = plugin / "skills" / "chief-of-staff"
    link = tmp_path / "links" / "chief-of-staff"
    link.parent.mkdir()
    if WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)
    script = fill(SHELLS[shell][0], link, input_file)
    done = run_script(shell, script, work)
    assert done.returncode == 0, f"exit {done.returncode}: {done.stderr[-400:]!r}"
    assert stdout_bytes(shell, done) == GOLDEN_TEXT
    assert_no_markers(tmp_path)


@pytest.mark.skipif(not WINDOWS, reason="the save-to-file variant belongs to the PowerShell block")
@pytest.mark.parametrize("shell", [s for s in ("powershell", "pwsh")])
def test_powershell_save_to_file_keeps_bytes(shell, tmp_path):
    """Redirect inside cmd (not PowerShell's > / Out-File): no BOM, no UTF-16, bytes equal to stdout."""
    shell_or_skip(shell)
    plugin, input_file, work = setup_case(shell, tmp_path)
    out = tmp_path / "saved reading.text"
    script = fill("powershell", plugin / "skills" / "chief-of-staff", input_file)
    old = '< "%AET_INPUT%"\''
    assert old in script
    script = script.replace(old, '< "%AET_INPUT%" > "%AET_OUTPUT%"\'')
    script = script.replace("'AET_INPUT',", "'AET_INPUT', 'AET_OUTPUT',")
    script = script.replace("$env:AET_INPUT = $InputFile", f"$env:AET_INPUT = $InputFile; $env:AET_OUTPUT = '{out}'")
    assert "AET_OUTPUT" in script
    done = run_script(shell, script, work)
    assert done.returncode == 0, f"exit {done.returncode}: {done.stderr[-400:]!r}"
    data = out.read_bytes()
    assert data == GOLDEN_TEXT
    assert not data.startswith((b"\xef\xbb\xbf", b"\xff\xfe"))
    assert_no_markers(tmp_path)


@pytest.mark.parametrize("shell", ALL_SHELLS)
def test_skill_block_rejects_bad_input_with_exit_two(shell, tmp_path):
    shell_or_skip(shell)
    plugin, input_file, work = setup_case(shell, tmp_path)
    input_file.write_text("{}", encoding="utf-8")
    script = fill(SHELLS[shell][0], plugin / "skills" / "chief-of-staff", input_file)
    done = run_script(shell, script, work)
    assert done.returncode == 2, f"exit {done.returncode}: {done.stderr[-400:]!r}"
    assert b"invalid_input" in done.stderr
    assert stdout_bytes(shell, done) == b""
    assert_no_markers(tmp_path)


def test_child_env_drops_the_guard_variable_in_any_letter_case(monkeypatch):
    monkeypatch.setenv("NoDefaultCurrentDirectoryInExePath", "1")
    monkeypatch.setenv("nodefaultcurrentdirectoryinexepath", "1")
    monkeypatch.setenv("PythonPath", "x")
    assert not [k for k in child_env() if k.upper() in (NO_DEFAULT_CWD, "PYTHONPATH")]


def test_launcher_missing_src_exits_one(tmp_path):
    plugin = install_copy(tmp_path, "plugin", with_src=False)
    script = plugin / "skills" / "chief-of-staff" / "scripts" / "executive_memo.py"
    done = subprocess.run(
        [sys.executable, "-B", "-I", str(script), "--format", "text"],
        input=(FIXTURES / "valid.json").read_bytes(),
        capture_output=True,
        timeout=60,
    )
    assert done.returncode == 1
    assert done.stderr == b"internal_error\n"
    assert done.stdout == b""


def test_launcher_prints_json_without_format_flag(tmp_path):
    plugin = install_copy(tmp_path, "plugin")
    script = plugin / "skills" / "chief-of-staff" / "scripts" / "executive_memo.py"
    done = subprocess.run(
        [sys.executable, "-B", "-I", str(script)],
        input=(FIXTURES / "valid.json").read_bytes(),
        capture_output=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith(b"{") and done.stdout.endswith(b"}\n")


def test_skill_has_no_pythonpath():
    assert "PYTHONPATH" not in SKILL_MD.read_text(encoding="utf-8")


def test_quote_helper_follows_the_text_in_skill_md():
    assert quote("bash", "a'b") == "'a'\\''b'"
    assert quote("powershell", "a'b") == "'a''b'"
    assert quote("powershell", "Bob’s") == "'Bob’’s'"
    assert quote("powershell", "‘‚‛") == "'‘‘‚‚‛‛'"


def test_ci_runs_every_required_shell():
    if not ON_CI:
        pytest.skip("only enforced when CI=true")
    for shell in REQUIRED:
        assert SHELLS[shell][1](), f"{shell} is missing on this CI runner"
