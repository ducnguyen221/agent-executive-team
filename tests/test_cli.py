"""CLI: bytes in, memo bytes out, stable exit codes and stderr, no side effect, no payload echo."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_executive_team import cli
from agent_executive_team.memo import serialize

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "valid.json"
MARKER = "LEAK-MARKER-7f3a"
SENTINEL_URIS = ("http://sentinel.invalid/x", "file:///C:/sentinel.txt")
INVALID_STDERR = b"invalid_input\n"
INTERNAL_STDERR = b"internal_error\n"
LIMIT = 65536


def run_main(data):
    """Run ``cli.main`` in-process on ``data``; return (exit code, stdout bytes, stderr bytes)."""
    stdin, stdout, stderr = io.BytesIO(data), io.BytesIO(), io.BytesIO()
    code = cli.main(stdin, stdout, stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def run_cli(data):
    """Run the real ``python -B -m agent_executive_team`` from the repo root."""
    env = {**os.environ, "PYTHONPATH": "src"}
    return subprocess.run(
        [sys.executable, "-B", "-m", "agent_executive_team"],
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
    canonical = json.dumps(memo, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    assert result.stdout == canonical.encode("ascii") + b"\n"


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


# --- in-process: contract details --------------------------------------------------------------


def test_main_matches_library_pipeline(valid_payload):
    from agent_executive_team.memo import build_memo

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


# --- side effects: observed from inside the process that runs the CLI --------------------------

GUARD_SCRIPT = r"""
import io, json, os, sys

events = []
WRITE_MODE = set("wax+")
WRITE_FLAGS = (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
               | getattr(os, "O_EXCL", 0))
PREFIXES = ("socket.", "urllib.", "http.client.", "ftplib.", "smtplib.", "telnetlib.",
            "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.fork", "os.system",
            "subprocess.", "os.remove", "os.rename", "os.replace", "os.mkdir", "os.rmdir",
            "os.truncate", "shutil.", "pty.", "winreg.", "ctypes.")

def hook(name, args):
    if name.startswith(PREFIXES):
        events.append(name)
    elif name == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and WRITE_MODE & set(mode)) or (
            isinstance(flags, int) and flags & WRITE_FLAGS
        ):
            events.append("open:write")

sys.addaudithook(hook)

# Positive control: the hook must see these (sys.audit only raises the event; nothing happens).
sys.audit("socket.connect", None, ("sentinel.invalid", 80))
sys.audit("open", "control.txt", "w", 577)
sys.audit("subprocess.Popen", "cmd", [], None, None)
control = list(events)
del events[:]

from agent_executive_team import cli

data = sys.stdin.buffer.read()
stdout, stderr = io.BytesIO(), io.BytesIO()
code = cli.main(io.BytesIO(data), stdout, stderr)
print(json.dumps({"control": control, "events": events, "code": code,
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

    assert report["control"] == ["socket.connect", "open:write", "subprocess.Popen"]


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
