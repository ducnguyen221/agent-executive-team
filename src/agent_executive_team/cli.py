"""Command line entry: one bounded read from stdin, one write to stdout, fixed exit codes.

Exit 0: memo bytes on stdout (JSON by default, plain text with ``--format text``). Exit 2: input
rejected (stderr ``invalid_input``) or arguments rejected (stderr ``invalid_arguments``, checked
before stdin is read), stdout empty.
Exit 1: any other failure, stderr ``internal_error``. Stderr text is static and the payload is
never echoed: neither the input nor any exception message from ``validate`` is printed.
No file, network or process is touched; the streams are the only I/O. Only the standard streams
carry data; on a failed write the process's own stdout/stderr descriptor (fd 1 or 2) is pointed at
the null device so its unflushed buffer cannot fail again at interpreter exit and change the exit
code. Streams handed in by an embedding caller are never redirected.
"""

import os
import sys

from agent_executive_team.memo import build_memo, serialize
from agent_executive_team.render import render_text
from agent_executive_team.validation import MAX_BYTES, ValidationError, validate

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID = 2

INVALID_INPUT = b"invalid_input\n"
INTERNAL_ERROR = b"internal_error\n"
INVALID_ARGUMENTS = b"invalid_arguments\n"

_STANDARD_FDS = (1, 2)


class _BadArguments(Exception):
    """Internal control flow only: the argument list is not one of the accepted forms."""


def _parse_format(argv):
    """Return ``"json"`` or ``"text"``; accepts only no arguments, ``--format json``, ``--format text``."""
    argv = list(argv)
    if argv == []:
        return "json"
    if len(argv) == 2 and argv[0] == "--format" and argv[1] in ("json", "text"):
        return argv[1]
    raise _BadArguments


def _discard(stream):
    """Point a failed stream's descriptor at the null device, only when it is fd 1 or 2."""
    try:
        descriptor = stream.fileno()
        if descriptor not in _STANDARD_FDS:
            return
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, descriptor)
        finally:
            os.close(null)
    except Exception:  # noqa: BLE001 - no channel is left to report on
        pass


def _report(stderr, exit_code, message):
    """Write the static error line; a broken stderr changes neither the exit code nor raises."""
    try:
        stderr.write(message)
        stderr.flush()
    except Exception:  # noqa: BLE001
        _discard(stderr)
    return exit_code


def _std_buffer(name):
    """The binary buffer of ``sys.<name>``, or None when that standard stream is closed."""
    stream = getattr(sys, name)
    return None if stream is None else stream.buffer


def main(stdin=None, stdout=None, stderr=None, argv=None) -> int:
    """Run the pipeline over binary streams (default: the process's standard buffers).

    ``argv`` is the argument list without the program name; ``None`` means no arguments and
    ``sys.argv`` is never read here.
    """
    stdin = _std_buffer("stdin") if stdin is None else stdin
    stdout = _std_buffer("stdout") if stdout is None else stdout
    stderr = _std_buffer("stderr") if stderr is None else stderr
    argv = [] if argv is None else argv
    try:
        output_format = _parse_format(argv)
    except _BadArguments:
        return _report(stderr, EXIT_INVALID, INVALID_ARGUMENTS)
    # Handlers only record the outcome; nothing is written inside them, so no exception from
    # the failed step (whose message may hold payload) can become the context of a later one.
    failure = None
    try:
        data = stdin.read(MAX_BYTES + 1)  # one bounded read; validate rejects anything over the cap
        memo = build_memo(validate(data))
        output = render_text(memo) if output_format == "text" else serialize(memo)
    except ValidationError:
        failure = (EXIT_INVALID, INVALID_INPUT)
    except Exception:  # noqa: BLE001 - the message may hold payload, so report a static code only
        failure = (EXIT_INTERNAL, INTERNAL_ERROR)
    if failure is None:
        try:
            stdout.write(output)
            stdout.flush()
        except Exception:  # noqa: BLE001 - same reason; stdout may be partly written
            failure = (EXIT_INTERNAL, INTERNAL_ERROR)
            _discard(stdout)
    if failure is None:
        return EXIT_OK
    return _report(stderr, *failure)
