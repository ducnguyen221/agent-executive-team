"""CLI: bytes in, memo bytes out, stable exit codes and stderr, no side effect, no payload echo."""

import io
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from agent_executive_team import cli
from agent_executive_team.memo import build_memo, serialize

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "valid.json"
MARKER = "LEAK-MARKER-7f3a"
SENTINEL_URIS = ("http://sentinel.invalid/x", "file:///C:/sentinel.txt")
INVALID_STDERR = b"invalid_input\n"
INTERNAL_STDERR = b"internal_error\n"
LIMIT = 65536


def run_main(data, argv=None):
    """Run ``cli.main`` in-process on ``data``; return (exit code, stdout bytes, stderr bytes)."""
    stdin, stdout, stderr = io.BytesIO(data), io.BytesIO(), io.BytesIO()
    code = cli.main(stdin, stdout, stderr, argv=argv)
    return code, stdout.getvalue(), stderr.getvalue()


def run_cli(data, *args):
    """Run the real ``python -B -m agent_executive_team`` from the repo root."""
    env = {**os.environ, "PYTHONPATH": "src"}
    return subprocess.run(
        [sys.executable, "-B", "-m", "agent_executive_team", *args],
        input=data,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


def compact(payload):
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def padded(payload, size):
    body = compact(payload)
    assert len(body) <= size
    return body + b" " * (size - len(body))


class FakeStdin:
    """Honours the size argument of ``read`` and records every call."""

    def __init__(self, data):
        self.data = data
        self.calls = []

    def read(self, size=-1):
        self.calls.append(size)
        return self.data if size < 0 else self.data[:size]


class RecordingStdout:
    def __init__(self):
        self.writes = []
        self.flushes = 0

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def flush(self):
        self.flushes += 1


# --- real subprocess: the shipped entry point --------------------------------------------------


def test_subprocess_valid_fixture_exits_zero_with_canonical_json():
    result = run_cli(FIXTURE.read_bytes())

    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout.endswith(b"}\n")
    assert not result.stdout.endswith(b"\n\n")
    assert b"\r" not in result.stdout
    memo = json.loads(result.stdout)
    assert memo["status"] == "needs_human_decision"
    assert memo["agent_status"] == "needs_review"
    assert memo["decision_status"] == "proposed"
    assert result.stdout == serialize(build_memo(json.loads(FIXTURE.read_bytes())))


@pytest.mark.parametrize(
    "data",
    [b"", b"not json", b'{"version": 1}', b"\xef\xbb\xbf{}", b"[" * 60000],
    ids=["empty", "syntax", "missing-keys", "bom", "deep-nesting"],
)
def test_subprocess_invalid_input_exits_two_with_static_stderr(data):
    result = run_cli(data)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == INVALID_STDERR


def test_subprocess_replay_is_byte_identical():
    data = FIXTURE.read_bytes()

    first, second = run_cli(data), run_cli(data)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stdout != b""


def test_subprocess_changing_one_option_changes_output(valid_payload):
    base = run_cli(compact(valid_payload))
    valid_payload["options"][1]["name"] = "Adopt a different cadence"
    changed = run_cli(compact(valid_payload))

    assert base.returncode == changed.returncode == 0
    assert base.stdout != changed.stdout
    assert b"Adopt a different cadence" in changed.stdout


def run_with_broken_pipe(data, broken):
    """Run the real CLI with the read end of ``broken`` ('stdout' or 'stderr') closed up front."""
    proc = subprocess.Popen(
        [sys.executable, "-B", "-m", "agent_executive_team"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    getattr(proc, broken).close()
    proc.stdin.write(data)
    proc.stdin.close()
    kept = proc.stderr if broken == "stdout" else proc.stdout
    output = kept.read()
    kept.close()
    return proc.wait(timeout=60), output


def test_subprocess_closed_stdout_exits_one_with_only_internal_error(valid_payload):
    code, stderr = run_with_broken_pipe(compact(valid_payload), "stdout")

    assert code == 1
    assert stderr == INTERNAL_STDERR


def test_subprocess_closed_stderr_still_exits_two_on_bad_input():
    code, stdout = run_with_broken_pipe(b"not json", "stderr")

    assert code == 2
    assert stdout == b""


def test_subprocess_closed_stderr_still_exits_zero_on_valid_input(valid_payload):
    code, stdout = run_with_broken_pipe(compact(valid_payload), "stderr")

    assert code == 0
    assert stdout == serialize(build_memo(valid_payload))


LEAK_SCRIPT = """
import sys
from agent_executive_team import cli

def boom(*args):
    raise RuntimeError("LEAK-MARKER-7f3a " + repr(args))

setattr(cli, sys.argv[1], boom)
raise SystemExit(cli.main())
"""


@pytest.mark.parametrize("target", ["validate", "build_memo", "serialize"])
def test_subprocess_internal_error_puts_nothing_but_the_code_on_real_streams(
    valid_payload, target
):
    valid_payload["decision"]["question"] = MARKER
    result = subprocess.run(
        [sys.executable, "-B", "-c", LEAK_SCRIPT, target],
        input=compact(valid_payload),
        capture_output=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "src"},
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == INTERNAL_STDERR


# --- in-process: contract details --------------------------------------------------------------


def test_main_matches_library_pipeline(valid_payload):
    code, out, err = run_main(compact(valid_payload))

    assert (code, err) == (0, b"")
    assert out == serialize(build_memo(valid_payload))


def test_main_reads_stdin_once_with_bounded_size(valid_payload):
    stdin, stdout, stderr = FakeStdin(compact(valid_payload)), io.BytesIO(), io.BytesIO()

    assert cli.main(stdin, stdout, stderr) == 0
    assert stdin.calls == [LIMIT + 1]


def test_main_writes_stdout_once_then_flushes(valid_payload):
    stdout = RecordingStdout()

    assert cli.main(io.BytesIO(compact(valid_payload)), stdout, io.BytesIO()) == 0
    assert len(stdout.writes) == 1
    assert stdout.writes[0].endswith(b"\n")
    assert stdout.flushes == 1


def test_main_defaults_to_standard_binary_streams(monkeypatch, valid_payload):
    stdin, stdout, stderr = io.BytesIO(compact(valid_payload)), io.BytesIO(), io.BytesIO()
    for name, raw in (("stdin", stdin), ("stdout", stdout), ("stderr", stderr)):
        monkeypatch.setattr(sys, name, io.TextIOWrapper(raw, encoding="utf-8", newline=""))

    assert cli.main() == 0
    assert stdout.getvalue().endswith(b"\n")
    assert stderr.getvalue() == b""


def test_boundary_exactly_65536_bytes_is_evaluated_and_accepted(valid_payload):
    data = padded(valid_payload, LIMIT)
    assert len(data) == LIMIT
    stdin, stdout, stderr = FakeStdin(data), io.BytesIO(), io.BytesIO()

    code = cli.main(stdin, stdout, stderr)

    assert code == 0
    assert stdin.calls == [LIMIT + 1]
    assert stdout.getvalue() == run_main(compact(valid_payload))[1]


def test_boundary_65537_bytes_is_rejected(valid_payload):
    data = padded(valid_payload, LIMIT + 1)
    assert len(data) == LIMIT + 1
    stdin, stdout, stderr = FakeStdin(data), io.BytesIO(), io.BytesIO()

    code = cli.main(stdin, stdout, stderr)

    assert code == 2
    assert stdin.calls == [LIMIT + 1]
    assert (stdout.getvalue(), stderr.getvalue()) == (b"", INVALID_STDERR)


def test_oversized_stream_is_never_read_beyond_the_limit(valid_payload):
    stdin, stdout, stderr = FakeStdin(padded(valid_payload, 3 * LIMIT)), io.BytesIO(), io.BytesIO()

    assert cli.main(stdin, stdout, stderr) == 2
    assert stdin.calls == [LIMIT + 1]
    assert (stdout.getvalue(), stderr.getvalue()) == (b"", INVALID_STDERR)


@pytest.mark.parametrize(
    "data",
    [b"[" * 60000, b'{"a":' * 12000, b"[" * 100000],
    ids=["arrays", "objects", "arrays-over-size-limit"],
)
def test_deep_nesting_is_rejected_without_traceback(data):
    code, out, err = run_main(data)

    assert (code, out, err) == (2, b"", INVALID_STDERR)


def test_lone_surrogate_is_escaped_not_an_internal_error(valid_payload):
    raw = compact(valid_payload).replace(b"Synthetic Owner", b"Lone \\ud800 here")
    assert b"\\ud800" in raw

    code, out, err = run_main(raw)

    assert (code, err) == (0, b"")
    out.decode("ascii")  # pure ASCII, always encodable
    assert b"\\ud800" in out
    assert json.loads(out)["decision"]["owner"] == "Lone \ud800 here"


def test_non_ascii_text_is_escaped_to_ascii(valid_payload):
    valid_payload["decision"]["owner"] = "Nguyễn Synthetic"

    code, out, _ = run_main(json.dumps(valid_payload, ensure_ascii=False).encode("utf-8"))

    assert code == 0
    assert out.decode("ascii").count("\\u1ec5") == 1


def test_rejected_input_never_echoes_payload(valid_payload):
    valid_payload["decision"]["question"] = MARKER
    valid_payload["unexpected"] = MARKER

    code, out, err = run_main(compact(valid_payload))

    assert (code, out, err) == (2, b"", INVALID_STDERR)


# --- internal errors: exit 1, static stderr, nothing reflected ---------------------------------


def boom(*_args, **_kwargs):
    raise RuntimeError(MARKER)


@pytest.mark.parametrize("target", ["validate", "build_memo", "serialize"])
def test_internal_error_in_pipeline_exits_one_without_leak(monkeypatch, valid_payload, target):
    monkeypatch.setattr(cli, target, boom)

    code, out, err = run_main(compact(valid_payload))

    assert (code, out, err) == (1, b"", INTERNAL_STDERR)


def test_internal_error_when_stdin_read_fails(valid_payload):
    class BrokenStdin:
        def read(self, _size):
            raise OSError(MARKER)

    stdout, stderr = io.BytesIO(), io.BytesIO()

    assert cli.main(BrokenStdin(), stdout, stderr) == 1
    assert (stdout.getvalue(), stderr.getvalue()) == (b"", INTERNAL_STDERR)


@pytest.mark.parametrize("failing", ["write", "flush"])
def test_internal_error_when_stdout_fails(valid_payload, failing):
    class BrokenStdout:
        def write(self, data):
            if failing == "write":
                raise BrokenPipeError(MARKER)
            return len(data)

        def flush(self):
            if failing == "flush":
                raise OSError(MARKER)

    stderr = io.BytesIO()

    assert cli.main(io.BytesIO(compact(valid_payload)), BrokenStdout(), stderr) == 1
    assert stderr.getvalue() == INTERNAL_STDERR


class BrokenStderr:
    """Fails on write or flush; records whether it was called from inside an ``except`` block."""

    def __init__(self, failing):
        self.failing = failing
        self.handling_exception = []

    def write(self, data):
        self.handling_exception.append(sys.exc_info()[0] is not None)
        if self.failing == "write":
            raise OSError(MARKER)
        return len(data)

    def flush(self):
        if self.failing == "flush":
            raise OSError(MARKER)


@pytest.mark.parametrize("failing", ["write", "flush"])
def test_broken_stderr_keeps_exit_two_for_rejected_input(failing):
    assert cli.main(io.BytesIO(b"not json"), io.BytesIO(), BrokenStderr(failing)) == 2


@pytest.mark.parametrize("failing", ["write", "flush"])
def test_broken_stderr_keeps_exit_one_for_internal_error(monkeypatch, valid_payload, failing):
    monkeypatch.setattr(cli, "build_memo", boom)

    code = cli.main(io.BytesIO(compact(valid_payload)), io.BytesIO(), BrokenStderr(failing))

    assert code == 1


def test_broken_stderr_does_not_change_a_successful_run(valid_payload):
    stdout = io.BytesIO()

    assert cli.main(io.BytesIO(compact(valid_payload)), stdout, BrokenStderr("write")) == 0
    assert stdout.getvalue() == serialize(build_memo(valid_payload))


@pytest.mark.parametrize("outcome", ["rejected", "internal"])
def test_stderr_is_written_outside_any_except_block(monkeypatch, valid_payload, outcome):
    data = b"not json"
    if outcome == "internal":
        monkeypatch.setattr(cli, "build_memo", boom)
        data = compact(valid_payload)
    stderr = BrokenStderr("flush")

    cli.main(io.BytesIO(data), io.BytesIO(), stderr)

    assert stderr.handling_exception == [False]


# --- side effects: observed from inside the process that runs the CLI --------------------------

GUARD_SCRIPT = r"""
import io, json, os, sys

events = []
watching = False  # reads are only meaningful while main runs; imports legitimately read files
WRITE_MODE = set("wax+")
WRITE_FLAGS = (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
               | getattr(os, "O_EXCL", 0))
ALWAYS = ("socket.", "urllib.", "http.client.", "ftplib.", "smtplib.", "telnetlib.",
          "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.fork", "os.system",
          "subprocess.", "os.remove", "os.rename", "os.replace", "os.mkdir", "os.rmdir",
          "os.truncate", "shutil.", "pty.", "winreg.", "ctypes.")
WHILE_WATCHING = ("os.listdir", "os.scandir", "os.walk", "glob.")
# os.stat and friends raise no audit event, so they are caught as builtin calls instead.
FS_PROBES = {"stat", "lstat", "listdir", "scandir", "open", "access", "readlink",
             "_path_exists", "_path_isfile", "_path_isdir", "_path_islink", "_path_isjunction",
             "_getfinalpathname", "_getfullpathname", "_getvolumepathname", "chdir", "getcwd"}

def hook(name, args):
    if name.startswith(ALWAYS):
        events.append(name)
    elif name == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and WRITE_MODE & set(mode)) or (
            isinstance(flags, int) and flags & WRITE_FLAGS
        ):
            events.append("open:write")
        elif watching:
            events.append("open:read")
    elif watching and name.startswith(WHILE_WATCHING):
        events.append(name)

def profiler(frame, event, arg):
    if event == "c_call" and getattr(arg, "__name__", "") in FS_PROBES:
        events.append("call:" + arg.__name__)

def observe(function, *args):
    global watching
    watching = True
    sys.setprofile(profiler)
    try:
        return function(*args)
    finally:
        sys.setprofile(None)
        watching = False

sys.addaudithook(hook)

# Positive control: the hooks must see these. sys.audit only raises the event (nothing happens);
# the stat/listdir calls are real but touch only the current directory.
def control():
    sys.audit("socket.connect", None, ("sentinel.invalid", 80))
    sys.audit("open", "control.txt", "w", 577)
    sys.audit("open", "control.txt", "rb", 0)
    sys.audit("subprocess.Popen", "cmd", [], None, None)
    os.stat(".")
    os.path.exists(".")
    os.listdir(".")

observe(control)
control_events = list(events)
del events[:]

from agent_executive_team import cli

data = sys.stdin.buffer.read()
stdout, stderr = io.BytesIO(), io.BytesIO()
code = observe(cli.main, io.BytesIO(data), stdout, stderr)
print(json.dumps({"control": control_events, "events": events, "code": code,
                  "stdout": stdout.getvalue().decode("ascii"),
                  "stderr": stderr.getvalue().decode("ascii")}))
"""


def run_guarded(data):
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, "-B", "-c", GUARD_SCRIPT],
        input=data,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_guard_script_observes_network_write_and_process_events(valid_payload):
    report = run_guarded(compact(valid_payload))

    seen = set(report["control"])
    assert {"socket.connect", "open:write", "open:read", "subprocess.Popen"} <= seen
    assert {"os.listdir", "call:stat"} <= seen
    assert any(event.startswith("call:_path_") or event == "call:stat" for event in seen)


def test_valid_run_has_no_network_write_or_process_event_and_never_follows_uris(valid_payload):
    valid_payload["evidence"][0]["source_uri"] = SENTINEL_URIS[0]
    valid_payload["evidence"][1]["source_uri"] = SENTINEL_URIS[1]

    report = run_guarded(compact(valid_payload))

    assert report["code"] == 0
    assert report["events"] == []
    assert report["stderr"] == ""
    memo = json.loads(report["stdout"])
    assert [e["source_uri"] for e in memo["evidence"]] == list(SENTINEL_URIS)
    assert all(e["verification"] == "unverified" for e in memo["evidence"])


def test_rejected_run_has_no_side_effect_event(valid_payload):
    valid_payload["evidence"][0]["source_uri"] = SENTINEL_URIS[0]
    valid_payload["unexpected"] = SENTINEL_URIS[1]

    report = run_guarded(compact(valid_payload))

    assert report["code"] == 2
    assert report["events"] == []
    assert report["stdout"] == ""
    assert report["stderr"] == INVALID_STDERR.decode("ascii")


# --- TK1: closed standard streams, narrow _discard, argv ignored by embedded main -------------

_NONE_STREAM_CODE = (
    "import sys; sys.{name} = None; import runpy; "
    "runpy.run_module('agent_executive_team', run_name='__main__')"
)
_STATIC_STDERR = (b"", INVALID_STDERR, INTERNAL_STDERR)


def _run_with_none_stream(name, data):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-B", "-c", _NONE_STREAM_CODE.format(name=name)],
        input=data,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


# (stream set to None, payload valid) -> (exit code, stderr)
_CLOSED_STREAM_CASES = {
    ("stdin", True): (1, INTERNAL_STDERR),
    ("stdin", False): (1, INTERNAL_STDERR),
    ("stdout", True): (1, INTERNAL_STDERR),
    ("stdout", False): (2, INVALID_STDERR),
    ("stderr", True): (0, b""),
    ("stderr", False): (2, b""),
}


@pytest.mark.parametrize("name", ["stdin", "stdout", "stderr"])
@pytest.mark.parametrize("valid", [True, False])
def test_closed_std_stream_no_traceback(name, valid):
    data = FIXTURE.read_bytes() if valid else b"not json"
    code, err = _CLOSED_STREAM_CASES[(name, valid)]
    result = _run_with_none_stream(name, data)
    assert result.returncode == code
    assert result.stderr == err
    if name == "stderr" and valid:
        assert result.stdout.startswith(b"{")
    else:
        assert result.stdout == b""


def test_all_three_streams_none_exit_one_silently():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    code = (
        "import sys; sys.stdin = sys.stdout = sys.stderr = None; import runpy; "
        "runpy.run_module('agent_executive_team', run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, cwd=ROOT, env=env, check=False
    )
    assert result.returncode == 1
    assert result.stderr == b"" and result.stdout == b""


# (redirection, payload valid) -> exit code
_POSIX_CASES = {
    ("<&-", True): 1,
    ("<&-", False): 1,
    (">&-", True): 1,
    (">&-", False): 2,
    ("2>&-", True): 0,
    ("2>&-", False): 2,
}


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell descriptor closing")
@pytest.mark.parametrize("redir", ["<&-", ">&-", "2>&-"])
@pytest.mark.parametrize("valid", [True, False])
def test_posix_shell_closed_descriptor_no_traceback(redir, valid):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    source = shlex.quote(str(FIXTURE)) if valid else "/dev/null"
    python = shlex.quote(sys.executable)
    if redir == "<&-":
        cmd = f"{python} -B -m agent_executive_team <&- 2>&1"
    elif redir == ">&-":
        cmd = f"{python} -B -m agent_executive_team < {source} 2>&1 >&-"
    else:
        cmd = f"{python} -B -m agent_executive_team < {source} 2>&- >/dev/null"
    result = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, cwd=ROOT, env=env, check=False)
    assert b"Traceback" not in result.stdout + result.stderr
    assert result.returncode == _POSIX_CASES[(redir, valid)]


def test_discard_leaves_foreign_descriptor():
    r, w = os.pipe()

    class Broken:
        def fileno(self):
            return w

        def write(self, _data):
            raise OSError("broken")

        def flush(self):
            pass

    try:
        assert cli.main(io.BytesIO(FIXTURE.read_bytes()), Broken(), io.BytesIO()) == 1
        os.write(w, b"MARK")
        os.close(w)
        assert os.read(r, 16) == b"MARK"
    finally:
        os.close(r)


def test_standard_fds_constant():
    assert cli._STANDARD_FDS == (1, 2)


def test_empty_tuple_argv_is_json():
    stdout = io.BytesIO()
    assert cli.main(io.BytesIO(FIXTURE.read_bytes()), stdout, io.BytesIO(), argv=()) == 0
    assert stdout.getvalue().startswith(b"{")


def test_main_without_argv_ignores_sys_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--format", "bogus"])
    stdout = io.BytesIO()
    assert cli.main(io.BytesIO(FIXTURE.read_bytes()), stdout, io.BytesIO()) == 0
    assert stdout.getvalue().startswith(b"{")


# --- --format ------------------------------------------------------------------------------------

FIXTURE_TEXT = ROOT / "tests" / "fixtures" / "valid.text"
INVALID_ARGUMENTS_STDERR = b"invalid_arguments\n"


def test_invalid_arguments_constant():
    assert cli.INVALID_ARGUMENTS == INVALID_ARGUMENTS_STDERR


def test_format_text_exit_zero():
    code, out, err = run_main(FIXTURE.read_bytes(), ["--format", "text"])

    assert (code, err) == (0, b"")
    assert out == FIXTURE_TEXT.read_bytes()


def test_default_and_format_json_byte_identical():
    data = FIXTURE.read_bytes()

    default = run_main(data)
    explicit = run_main(data, ["--format", "json"])

    assert default == explicit
    assert default[0] == 0
    assert default[1] == serialize(build_memo(json.loads(data)))


@pytest.mark.parametrize(
    "argv",
    [
        ["--format"],
        ["--format", "xml"],
        ["--format=text"],
        ["--FORMAT", "text"],
        ["-f", "text"],
        [""],
        ["--format", "text", "--format", "json"],
        ["x"],
    ],
    ids=repr,
)
def test_bad_arguments(argv):
    stdin, stdout, stderr = FakeStdin(FIXTURE.read_bytes()), io.BytesIO(), io.BytesIO()

    code = cli.main(stdin, stdout, stderr, argv=argv)

    assert code == 2
    assert stderr.getvalue() == INVALID_ARGUMENTS_STDERR
    assert stdout.getvalue() == b""
    assert stdin.calls == []


def test_bad_arguments_with_bad_stderr_keep_exit_two():
    class Broken:
        def write(self, _data):
            raise OSError

        def flush(self):
            raise OSError

    stdin = FakeStdin(b"")

    assert cli.main(stdin, io.BytesIO(), Broken(), argv=["x"]) == 2
    assert stdin.calls == []


def test_invalid_input_text_format():
    code, out, err = run_main(b"not json", ["--format", "text"])

    assert (code, out, err) == (2, b"", INVALID_STDERR)


def test_text_replay_byte_identical():
    data = FIXTURE.read_bytes()

    first = run_cli(data, "--format", "text")
    second = run_cli(data, "--format", "text")

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == FIXTURE_TEXT.read_bytes()


def test_subprocess_bad_arguments():
    result = run_cli(FIXTURE.read_bytes(), "--format=text")

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == INVALID_ARGUMENTS_STDERR


# --- launcher with a broken install --------------------------------------------------------------


def test_launcher_with_a_module_missing_prints_only_internal_error(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "skills").mkdir(parents=True)
    import shutil

    shutil.copytree(ROOT / "skills" / "chief-of-staff", plugin / "skills" / "chief-of-staff")
    shutil.copytree(
        ROOT / "src", plugin / "src", ignore=shutil.ignore_patterns("__pycache__", "render.py")
    )
    script = plugin / "skills" / "chief-of-staff" / "scripts" / "executive_memo.py"

    result = subprocess.run(
        [sys.executable, "-B", "-I", str(script)],
        input=FIXTURE.read_bytes(),
        capture_output=True,
        cwd=tmp_path,
    )

    assert (result.returncode, result.stdout, result.stderr) == (1, b"", b"internal_error\n")
