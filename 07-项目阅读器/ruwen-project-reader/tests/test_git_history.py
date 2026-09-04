from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ruwen_project_reader.git_history import GitHistory
from ruwen_project_reader.project import ProjectReader


class GitHistoryTests(unittest.TestCase):
    def test_history_content_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "当前态势.md"
            self._git(root, "init")
            self._git(root, "config", "user.email", "reader@example.invalid")
            self._git(root, "config", "user.name", "Reader Test")
            path.write_text("# 当前态势\n\n第一版", encoding="utf-8")
            self._git(root, "add", "当前态势.md")
            self._git(root, "commit", "-m", "first")
            first = self._git(root, "rev-parse", "HEAD").strip()
            path.write_text("# 当前态势\n\n第二版", encoding="utf-8")
            self._git(root, "add", "当前态势.md")
            self._git(root, "commit", "-m", "second")
            second = self._git(root, "rev-parse", "HEAD").strip()

            history = GitHistory(ProjectReader(root))
            self.assertTrue(history.available)
            self.assertEqual([item["subject"] for item in history.list("当前态势.md")], ["second", "first"])
            self.assertIn("第一版", history.content("当前态势.md", first))
            diff = history.diff("当前态势.md", first, second)
            self.assertIn("-第一版", diff)
            self.assertIn("+第二版", diff)

    def test_non_git_project_degrades_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            history = GitHistory(ProjectReader(folder))
            self.assertFalse(history.available)
            self.assertEqual(history.list("missing.md"), [])

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        return result.stdout


if __name__ == "__main__":
    unittest.main()
