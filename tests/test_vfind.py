from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import vfind


def ns(**overrides: object) -> argparse.Namespace:
    values = {
        "paths": [],
        "type": None,
        "group": None,
        "include_init": False,
        "vcsignore": None,
        "noise": None,
        "recursive": None,
        "null": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class VfindTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd = mock.patch("vfind.fd_backend", return_value="fd")
        self._fd.start()
        self.addCleanup(self._fd.stop)

    def test_default_python_selection_excludes_init(self) -> None:
        args = vfind.build_fd_args(ns(), vfind.load_config())

        self.assertIn("-e", args)
        self.assertIn("py", args)
        self.assertIn("__init__.py", args)

    def test_include_init_removes_default_init_exclusion(self) -> None:
        args = vfind.build_fd_args(ns(include_init=True), vfind.load_config())

        self.assertNotIn("__init__.py", args)

    def test_type_list_expands_multiple_extensions(self) -> None:
        args = vfind.build_fd_args(ns(type=["py,md"]), vfind.load_config())

        self.assertEqual(args.count("-e"), 3)
        self.assertIn("py", args)
        self.assertIn("md", args)
        self.assertIn("markdown", args)

    def test_group_uses_configured_type_group(self) -> None:
        args = vfind.build_fd_args(ns(group=["web"]), vfind.load_config())

        for extension in ("js", "ts", "tsx", "jsx", "css", "html"):
            self.assertIn(extension, args)

    def test_project_config_extends_global_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xdg = root / "xdg"
            global_cfg = xdg / "v"
            global_cfg.mkdir(parents=True)
            (global_cfg / "config.toml").write_text(
                '[types]\ndata = ["json"]\n',
                encoding="utf-8",
            )
            project = root / "project"
            project.mkdir()
            (project / ".git").mkdir()
            (project / ".v.toml").write_text(
                '[types]\ndata = ["toml"]\nnotes = ["md"]\n',
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}, clear=False):
                config = vfind.load_config(project)

        self.assertEqual(config["types"]["data"], ["toml"])
        self.assertEqual(config["types"]["notes"], ["md"])

    def test_flags_map_to_fd_arguments(self) -> None:
        args = vfind.build_fd_args(
            ns(vcsignore=False, noise=False, recursive=False, null=True, paths=["src"]),
            vfind.load_config(),
        )

        self.assertIn("--no-ignore-vcs", args)
        self.assertIn("--max-depth", args)
        self.assertIn("--print0", args)
        self.assertNotIn("-E", args)
        self.assertEqual(args[-2:], [".", "src"])

    def test_unknown_group_errors(self) -> None:
        with self.assertRaises(vfind.VfindError):
            vfind.resolve_extensions(vfind.load_config(), None, ["missing"])


if __name__ == "__main__":
    unittest.main()

