#!/usr/bin/env python3
"""Module entrypoint for the Agentic OS CLI: `python3 -m agentic_os`.

Absolute (not relative) import on purpose: the zipapp builder copies this
file verbatim to the archive root as __main__.py, where there is no parent
package to import from. See the U-P1 packaging contract.
"""

import sys

from agentic_os.cli import main

if __name__ == "__main__":
    sys.exit(main())
