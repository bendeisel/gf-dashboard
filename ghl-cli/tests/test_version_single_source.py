"""One version number: setup.py, `--version` and the package agree."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from click.testing import CliRunner

from cli_anything.gohighlevel import __version__
from cli_anything.gohighlevel.gohighlevel_cli import cli

ROOT = Path(__file__).resolve().parents[1]


class VersionSingleSourceTests(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_cli_reports_package_version(self):
        out = CliRunner().invoke(cli, ["--version"]).output
        self.assertIn(__version__, out)

    def test_setup_reads_package_version(self):
        setup = (ROOT / "setup.py").read_text()
        self.assertIn("version=VERSION", setup)
        self.assertNotRegex(setup, r'version="\d')


if __name__ == "__main__":
    unittest.main()
