#!/usr/bin/env python3
"""Claude Code hook runner for Agentic OS U-H1.

Invoked BY Claude Code (never by a human, never via the aos CLI) as:

    python3 /path/to/aos_hooks.py stop           # Stop: capture envelope
    python3 /path/to/aos_hooks.py session-end    # SessionEnd: publish it

Reads the official hook JSON from stdin. Writes nothing to stdout — so it
can never emit a blocking Stop decision — and stages/publishes only under
the workspace's own `.agentic-os/exports/`. `aos hooks install` wires it
into Claude Code settings; see agentic_os/hooks.py for the full contract.
"""

import sys

from agentic_os.hooks import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
