"""Launcher for the chief-of-staff skill: finds the plugin root from this file's real path and runs the CLI.

The plugin root is three levels above this file (``<root>/skills/chief-of-staff/scripts/``). The path is
resolved first, so a junction or symlink to the skill directory still leads to the real plugin. Standard
library only; stderr is the static line ``internal_error`` when the plugin source is missing.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

if not (ROOT / "src" / "agent_executive_team").is_dir():
    sys.stderr.buffer.write(b"internal_error\n")
    raise SystemExit(1)

sys.path.insert(0, str(ROOT / "src"))

try:
    from agent_executive_team.cli import main  # noqa: E402
except Exception:  # a broken install (missing module) must not print a traceback
    sys.stderr.buffer.write(b"internal_error\n")
    raise SystemExit(1)

raise SystemExit(main(argv=sys.argv[1:]))
