"""Command line entry: one bounded read from stdin, one write to stdout, fixed exit codes.

Exit 0: memo bytes on stdout. Exit 2: input rejected, stderr ``invalid_input``, stdout empty.
Exit 1: any other failure, stderr ``internal_error``. Stderr text is static and the payload is
never echoed: neither the input nor any exception message from ``validate`` is printed.
No file, network or process is touched; the streams are the only I/O.
"""

import sys

from agent_executive_team.memo import build_memo, serialize
from agent_executive_team.validation import MAX_BYTES, ValidationError, validate

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID = 2

INVALID_INPUT = b"invalid_input\n"
INTERNAL_ERROR = b"internal_error\n"


def _fail(stderr, exit_code, message):
    stderr.write(message)
    stderr.flush()
    return exit_code


def main(stdin=None, stdout=None, stderr=None) -> int:
    """Run the pipeline over binary streams (default: the process's standard buffers)."""
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    stderr = sys.stderr.buffer if stderr is None else stderr
    try:
        data = stdin.read(MAX_BYTES + 1)  # one bounded read; validate rejects anything over the cap
        output = serialize(build_memo(validate(data)))
    except ValidationError:
        return _fail(stderr, EXIT_INVALID, INVALID_INPUT)
    except Exception:  # noqa: BLE001 - the message may hold payload, so report a static code only
        return _fail(stderr, EXIT_INTERNAL, INTERNAL_ERROR)
    try:
        stdout.write(output)
        stdout.flush()
    except Exception:  # noqa: BLE001 - same reason; stdout may be partly written
        return _fail(stderr, EXIT_INTERNAL, INTERNAL_ERROR)
    return EXIT_OK
