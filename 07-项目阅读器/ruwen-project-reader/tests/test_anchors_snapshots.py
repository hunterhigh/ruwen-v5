from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ruwen_project_reader.anchors import create_anchor, resolve_anchor
from ruwen_project_reader.database import ReaderDatabase
from ruwen_project_reader.project import ProjectReader
from ruwen_project_reader.snapshots import EmptyBatchError, SnapshotManager


class AnchorAndSnapshotTests(unittest.TestCase):
    def test_anchor_resolves_after_lines_move(self) -> None:
        original = "# 当前态势\n\n第一段。\n\n北方政权保持独立意志。\n"
        selected = "北方政权保持独立意志"
        start = original.index(selected)
        anchor = create_anchor(original, start, start + len(selected))
        changed = "# 当前态势\n\n新增说明。\n\n第一段。\n\n北方政权保持独立意志。\n"
        resolved = resolve_anchor(changed, anchor)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(changed[resolved["start"] : resolved["end"]], selected)

    def test_duplicate_selection_becomes_ambiguous(self) -> None:
        anchor = {"selected_text": "重复", "prefix": "", "suffix": "", "line_start": 1, "line_end": 1}
        resolved = resolve_anchor("重复，以及重复。", anchor)
        self.assertEqual(resolved["status"], "reanchor_required")

    def test_seal_writes_immutable_snapshot_and_opens_next_batch(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "世界").mkdir()
            path = root / "世界" / "当前态势.md"
            content = "# 当前态势\n\n北方政权保持独立意志。"
            path.write_text(content, encoding="utf-8")
            reader = ProjectReader(root)
            db = ReaderDatabase(root)
            try:
                start = content.index("北方政权")
                db.add_annotation(
                    path="世界/当前态势.md",
                    body="保留这一层组织意志",
                    anchor=create_anchor(content, start, len(content)),
                    file_hash=reader.read("世界/当前态势.md")["sha256"],
                )
                result = SnapshotManager(reader, db).seal_current()
                snapshot = root / result["snapshot_path"]
                self.assertTrue(snapshot.exists())
                data = json.loads(snapshot.read_text(encoding="utf-8"))
                self.assertEqual(data["batch_number"], 1)
                self.assertEqual(data["annotations"][0]["body"], "保留这一层组织意志")
                self.assertEqual(db.current_batch()["number"], 2)
                with self.assertRaises(FileExistsError):
                    SnapshotManager(reader, db).seal_batch(1)
            finally:
                db.close()

    def test_empty_batch_cannot_be_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reader = ProjectReader(root)
            db = ReaderDatabase(root)
            try:
                with self.assertRaises(EmptyBatchError):
                    SnapshotManager(reader, db).seal_current()
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
