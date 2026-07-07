#!/usr/bin/env python3
"""Thin entrypoint for the Agentic OS CLI."""

import sys

from agentic_os.cli import main

if __name__ == "__main__":
    sys.exit(main())
