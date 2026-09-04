from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .anchors import resolve_anchor
from .database import ReaderDatabase
from .project import ProjectReader


class SnapshotError(Exception):
    """Base snapshot error."""


class EmptyBatchError(SnapshotError):
    """An empty batch cannot be sealed."""


class ReanchorRequiredError(SnapshotError):
    """At least one annotation no longer has a reliable anchor."""


class SnapshotManager:
    CONTRACT_VERSION = "ruwen.annotation-batch.v1"

    def __init__(self, reader: ProjectReader, database: ReaderDatabase) -> None:
        self.reader = reader
        self.database = database

    def seal_current(self) -> dict[str, Any]:
        return self.seal_batch(int(self.database.current_batch()["number"]))

    def seal_batch(self, number: int) -> dict[str, Any]:
        target_relative = Path("治理") / "批注" / f"批次-{number:04d}.json"
        target = self.reader.root / target_relative
        if target.exists():
            raise FileExistsError(target)
        batch = self.database.get_batch(number)
        if batch["status"] != "draft":
            raise FileExistsError(target)
        annotations = self.database.list_annotations(batch_number=number)
        if not annotations:
            raise EmptyBatchError(str(number))

        locked_files: dict[str, dict[str, Any]] = {}
        snapshot_annotations: list[dict[str, Any]] = []
        for annotation in annotations:
            current = self.reader.read(annotation["path"])
            resolved = resolve_anchor(current["content"], annotation["anchor"])
            if current["sha256"] != annotation["file_hash"] and resolved["status"] != "resolved":
                raise ReanchorRequiredError(annotation["id"])
            locked_files[annotation["path"]] = {
                "path": annotation["path"],
                "sha256": current["sha256"],
                "size": current["size"],
            }
            snapshot_annotations.append(
                {
                    "id": annotation["id"],
                    "position": annotation["position"],
                    "path": annotation["path"],
                    "body": annotation["body"],
                    "anchor": annotation["anchor"],
                    "anchor_status": resolved["status"],
                    "created_at": annotation["created_at"],
                    "updated_at": annotation["updated_at"],
                }
            )

        payload: dict[str, Any] = {
            "contract": self.CONTRACT_VERSION,
            "project": self.reader.name,
            "batch_number": number,
            "batch_created_at": batch["created_at"],
            "annotations": snapshot_annotations,
            "locked_files": [locked_files[key] for key in sorted(locked_files)],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        snapshot_hash = hashlib.sha256(canonical).hexdigest()
        payload["snapshot_sha256"] = snapshot_hash
        output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as temporary:
                temporary.write(output)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, target)
            temporary_name = None
            self.database.seal_current(number, target_relative.as_posix(), snapshot_hash)
        except Exception:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

        return {
            "batch": self.database.get_batch(number),
            "next_batch": self.database.current_batch(),
            "snapshot_path": target_relative.as_posix(),
            "snapshot_sha256": snapshot_hash,
            "processing_prompt": self.processing_prompt(target_relative.as_posix(), number),
        }

    def processing_prompt(self, snapshot_path: str, number: int) -> str:
        return (
            f"请在隔离上下文中处理项目《{self.reader.name}》第 {number:04d} 批批注。\n"
            f"批次快照：{snapshot_path}\n"
            "先解释并归类全部批注，再依据 Ruwen 治理决定需要的设定修改、创造、维护或校验。"
            "批注不是直接修改命令；未经既有审批流程，不写入项目正典。"
        )
