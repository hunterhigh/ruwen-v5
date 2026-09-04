from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DatabaseError(Exception):
    """Base database error."""


class BatchSealedError(DatabaseError):
    """An operation attempted to mutate a sealed batch."""


class AnnotationNotFoundError(DatabaseError):
    """An annotation does not exist."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReaderDatabase:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        runtime_dir = self.project_root / ".ruwen"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self.path = runtime_dir / "control.sqlite3"
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def _migrate(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS annotation_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('draft','sealed','dispatched','processing','completed','archived')),
                    created_at TEXT NOT NULL,
                    sealed_at TEXT,
                    snapshot_path TEXT,
                    snapshot_hash TEXT,
                    thread_id TEXT
                );
                CREATE TABLE IF NOT EXISTS annotations (
                    id TEXT PRIMARY KEY,
                    batch_id INTEGER NOT NULL REFERENCES annotation_batches(id),
                    path TEXT NOT NULL,
                    body TEXT NOT NULL,
                    anchor_json TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(batch_id, position)
                );
                CREATE INDEX IF NOT EXISTS annotations_batch_path_idx
                    ON annotations(batch_id, path, position);
                PRAGMA user_version = 1;
                """
            )
            current = self.connection.execute(
                "SELECT id FROM annotation_batches WHERE status = 'draft' ORDER BY number DESC LIMIT 1"
            ).fetchone()
            if current is None:
                self.connection.execute(
                    "INSERT INTO annotation_batches(number, status, created_at) VALUES(1, 'draft', ?)",
                    (utc_now(),),
                )

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def current_batch(self) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT b.*,
                    COUNT(a.id) AS annotation_count,
                    COUNT(DISTINCT a.path) AS file_count
                FROM annotation_batches b
                LEFT JOIN annotations a ON a.batch_id = b.id
                WHERE b.status = 'draft'
                GROUP BY b.id
                ORDER BY b.number DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise DatabaseError("缺少当前草稿批次")
        return dict(row)

    def get_batch(self, number: int) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT b.*,
                    COUNT(a.id) AS annotation_count,
                    COUNT(DISTINCT a.path) AS file_count
                FROM annotation_batches b
                LEFT JOIN annotations a ON a.batch_id = b.id
                WHERE b.number = ?
                GROUP BY b.id
                """,
                (number,),
            ).fetchone()
        if row is None:
            raise DatabaseError(f"批次不存在：{number}")
        return dict(row)

    def list_batches(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT b.*,
                    COUNT(a.id) AS annotation_count,
                    COUNT(DISTINCT a.path) AS file_count
                FROM annotation_batches b
                LEFT JOIN annotations a ON a.batch_id = b.id
                GROUP BY b.id
                ORDER BY b.number DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _draft_id(self) -> int:
        return int(self.current_batch()["id"])

    def add_annotation(self, *, path: str, body: str, anchor: dict[str, Any], file_hash: str) -> dict[str, Any]:
        body = body.strip()
        if not body:
            raise ValueError("批注不能为空")
        now = utc_now()
        annotation_id = uuid.uuid4().hex
        with self._lock, self.connection:
            batch_id = self._draft_id()
            position = self.connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM annotations WHERE batch_id = ?", (batch_id,)
            ).fetchone()[0]
            self.connection.execute(
                """
                INSERT INTO annotations(id, batch_id, path, body, anchor_json, file_hash, position, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (annotation_id, batch_id, path, body, json.dumps(anchor, ensure_ascii=False), file_hash, position, now, now),
            )
        return self.get_annotation(annotation_id)

    def get_annotation(self, annotation_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT a.*, b.number AS batch_number, b.status AS batch_status
                FROM annotations a JOIN annotation_batches b ON b.id = a.batch_id
                WHERE a.id = ?
                """,
                (annotation_id,),
            ).fetchone()
        if row is None:
            raise AnnotationNotFoundError(annotation_id)
        result = dict(row)
        result["anchor"] = json.loads(result.pop("anchor_json"))
        return result

    def list_annotations(self, *, batch_number: int | None = None, path: str | None = None) -> list[dict[str, Any]]:
        if batch_number is None:
            batch_number = int(self.current_batch()["number"])
        query = """
            SELECT a.*, b.number AS batch_number, b.status AS batch_status
            FROM annotations a JOIN annotation_batches b ON b.id = a.batch_id
            WHERE b.number = ?
        """
        values: list[Any] = [batch_number]
        if path is not None:
            query += " AND a.path = ?"
            values.append(path)
        query += " ORDER BY a.position"
        with self._lock:
            rows = self.connection.execute(query, values).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["anchor"] = json.loads(item.pop("anchor_json"))
            results.append(item)
        return results

    def update_annotation(self, annotation_id: str, body: str) -> dict[str, Any]:
        body = body.strip()
        if not body:
            raise ValueError("批注不能为空")
        current = self.get_annotation(annotation_id)
        if current["batch_status"] != "draft":
            raise BatchSealedError(annotation_id)
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE annotations SET body = ?, updated_at = ? WHERE id = ?", (body, utc_now(), annotation_id)
            )
        return self.get_annotation(annotation_id)

    def delete_annotation(self, annotation_id: str) -> None:
        current = self.get_annotation(annotation_id)
        if current["batch_status"] != "draft":
            raise BatchSealedError(annotation_id)
        with self._lock, self.connection:
            self.connection.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))

    def seal_current(self, number: int, snapshot_path: str, snapshot_hash: str) -> dict[str, Any]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.connection.execute(
                    "SELECT id, status FROM annotation_batches WHERE number = ?", (number,)
                ).fetchone()
                if row is None:
                    raise DatabaseError(f"批次不存在：{number}")
                if row["status"] != "draft":
                    raise BatchSealedError(str(number))
                count = self.connection.execute(
                    "SELECT COUNT(*) FROM annotations WHERE batch_id = ?", (row["id"],)
                ).fetchone()[0]
                if count == 0:
                    raise ValueError("空批次不能封存")
                self.connection.execute(
                    """
                    UPDATE annotation_batches
                    SET status = 'sealed', sealed_at = ?, snapshot_path = ?, snapshot_hash = ?
                    WHERE id = ?
                    """,
                    (utc_now(), snapshot_path, snapshot_hash, row["id"]),
                )
                next_number = self.connection.execute(
                    "SELECT COALESCE(MAX(number), 0) + 1 FROM annotation_batches"
                ).fetchone()[0]
                self.connection.execute(
                    "INSERT INTO annotation_batches(number, status, created_at) VALUES(?, 'draft', ?)",
                    (next_number, utc_now()),
                )
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return self.get_batch(number)
