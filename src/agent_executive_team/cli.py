"""Command line entry: one bounded read from stdin, one write to stdout, fixed exit codes.

Exit 0: memo bytes on stdout. Exit 2: input rejected, stderr ``invalid_input``, stdout empty.
Exit 1: any other failure, stderr ``internal_error``. Stderr text is static and the payload is
never echoed: neither the input nor any exception message from ``validate`` is printed.
No file, network or process is touched; the streams are the only I/O. A stream that fails is
pointed at the null device so its unflushed buffer cannot fail again at interpreter exit and
change the exit code.
"""

import os
import sys

from agent_executive_team.memo import build_memo, serialize
from agent_executive_team.validation import MAX_BYTES, ValidationError, validate

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID = 2

INVALID_INPUT = b"invalid_input\n"
INTERNAL_ERROR = b"internal_error\n"


def _discard(stream):
    """Send a failed stream's descriptor to the null device (stream without one: nothing to do)."""
    try:
        descriptor = stream.fileno()
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


def main(stdin=None, stdout=None, stderr=None) -> int:
    """Run the pipeline over binary streams (default: the process's standard buffers)."""
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    stderr = sys.stderr.buffer if stderr is None else stderr
    # Handlers only record the outcome; nothing is written inside them, so no exception from
    # the failed step (whose message may hold payload) can become the context of a later one.
    failure = None
    try:
        data = stdin.read(MAX_BYTES + 1)  # one bounded read; validate rejects anything over the cap
        output = serialize(build_memo(validate(data)))
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
