"""``python -B -m agent_executive_team``: run the CLI."""

import sys

from agent_executive_team.cli import main

raise SystemExit(main(argv=sys.argv[1:]))
