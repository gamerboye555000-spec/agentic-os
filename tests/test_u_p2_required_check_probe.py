"""U-P2 required-check failure probe.

This test exists only to fail deterministically so the active main ruleset
can be proven to block a pull request whose required checks fail. It must
never be merged.
"""

import unittest


class TestUP2RequiredCheckProbe(unittest.TestCase):
    def test_deterministic_probe_failure(self) -> None:
        self.fail(
            "U-P2 probe: intentional deterministic failure to prove "
            "required checks block merging. Never merge this."
        )


if __name__ == "__main__":
    unittest.main()
