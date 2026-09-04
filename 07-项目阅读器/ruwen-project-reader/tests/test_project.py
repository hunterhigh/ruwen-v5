from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ruwen_project_reader.project import FileTooLargeError, ProjectReader, UnsafePathError


class ProjectReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "世界").mkdir()
        (self.root / "世界" / "当前态势.md").write_text("# 当前态势\n\n正文", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("secret", encoding="utf-8")
        (self.root / ".ruwen").mkdir()
        (self.root / ".ruwen" / "control.sqlite3").write_bytes(b"db")
        (self.root / "image.png").write_bytes(b"png")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_tree_keeps_real_structure_and_filters_runtime_files(self) -> None:
        reader = ProjectReader(self.root)
        tree = reader.tree()
        self.assertEqual(tree[0]["name"], "世界")
        self.assertEqual(tree[0]["children"][0]["path"], "世界/当前态势.md")
        rendered = repr(tree)
        self.assertNotIn(".git", rendered)
        self.assertNotIn(".ruwen", rendered)
        self.assertNotIn("image.png", rendered)

    def test_read_returns_content_and_hash(self) -> None:
        reader = ProjectReader(self.root)
        result = reader.read("世界/当前态势.md")
        self.assertEqual(result["content"], "# 当前态势\n\n正文")
        self.assertEqual(len(result["sha256"]), 64)

    def test_path_traversal_is_rejected(self) -> None:
        reader = ProjectReader(self.root)
        with self.assertRaises(UnsafePathError):
            reader.read("../outside.md")

    def test_symlink_escape_is_rejected_when_supported(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.md"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "escape.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        try:
            with self.assertRaises(UnsafePathError):
                ProjectReader(self.root).read("escape.md")
        finally:
            outside.unlink(missing_ok=True)

    def test_large_file_is_rejected(self) -> None:
        path = self.root / "large.md"
        path.write_text("x" * 32, encoding="utf-8")
        with self.assertRaises(FileTooLargeError):
            ProjectReader(self.root, max_file_bytes=16).read("large.md")


if __name__ == "__main__":
    unittest.main()
