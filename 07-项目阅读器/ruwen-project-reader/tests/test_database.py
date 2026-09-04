from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ruwen_project_reader.database import BatchSealedError, ReaderDatabase


class ReaderDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = ReaderDatabase(self.root)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_first_batch_is_draft(self) -> None:
        batch = self.db.current_batch()
        self.assertEqual(batch["number"], 1)
        self.assertEqual(batch["status"], "draft")

    def test_annotation_lifecycle_in_draft(self) -> None:
        annotation = self.db.add_annotation(
            path="世界/当前态势.md",
            body="保留组织意志",
            anchor={"selected_text": "北方部落"},
            file_hash="a" * 64,
        )
        self.assertEqual(annotation["position"], 1)
        updated = self.db.update_annotation(annotation["id"], "修改后的批注")
        self.assertEqual(updated["body"], "修改后的批注")
        self.db.delete_annotation(annotation["id"])
        self.assertEqual(self.db.list_annotations(), [])

    def test_sealed_batch_is_immutable_and_next_number_is_created(self) -> None:
        annotation = self.db.add_annotation(
            path="项目/项目章程.md",
            body="只保留长期约束",
            anchor={"selected_text": "发布目标"},
            file_hash="b" * 64,
        )
        self.db.seal_current(1, "治理/批注/批次-0001.json", "c" * 64)
        with self.assertRaises(BatchSealedError):
            self.db.update_annotation(annotation["id"], "不能修改")
        self.assertEqual(self.db.current_batch()["number"], 2)

    def test_state_survives_reopen(self) -> None:
        self.db.add_annotation(
            path="人物/主角档案.md",
            body="确认动机",
            anchor={"selected_text": "动机"},
            file_hash="d" * 64,
        )
        self.db.close()
        self.db = ReaderDatabase(self.root)
        self.assertEqual(len(self.db.list_annotations()), 1)


if __name__ == "__main__":
    unittest.main()
