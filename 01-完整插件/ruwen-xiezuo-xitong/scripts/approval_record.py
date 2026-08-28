#!/usr/bin/env python3
"""创建与具体目标哈希绑定、不可覆盖的用户批准事件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


ACTIONS = {
    "handoff_execute",
    "candidate_approve",
    "memory_commit",
    "resource_activate",
    "expression_activate",
}
USAGE_RELATIVE = Path("治理/审批/已使用")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_under(root: Path, value: str, *, must_exist: bool = True) -> tuple[Path, str]:
    path = (root / value).resolve()
    try:
        relative = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("批准目标越出项目") from exc
    if must_exist and not path.is_file():
        raise ValueError(f"批准目标不存在：{relative}")
    return path, relative


def usage_entries(root: Path) -> list[dict]:
    directory = root / USAGE_RELATIVE
    if not directory.is_dir():
        return []
    entries: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"批准消费标记无效：{path.name}")
        entries.append(value)
    return entries


def event_is_consumed(root: Path, event_id: str) -> bool:
    directory = root / USAGE_RELATIVE
    return (directory / f"{event_id}.json").is_file() or (directory / f".{event_id}.pending").exists()


def event_is_committed(root: Path, event_id: str) -> bool:
    return (root / USAGE_RELATIVE / f"{event_id}.json").is_file()


def reserve_event(root: Path, event: dict, *, consumer: str) -> dict:
    event_id = str(event.get("id", ""))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", event_id):
        raise ValueError("批准事件ID无效")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", consumer):
        raise ValueError("批准消费岗位标识无效")
    directory = root / USAGE_RELATIVE
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / f"{event_id}.json"
    pending_path = directory / f".{event_id}.pending"
    if final_path.exists():
        raise ValueError("批准事件已经使用")
    entry = {
        "event_id": event_id,
        "action": event["action"],
        "target_path": event["target_path"],
        "target_sha256": event["target_sha256"],
        "consumer": consumer,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with pending_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError("批准事件正在被另一岗位使用") from exc
    if final_path.exists():
        pending_path.unlink(missing_ok=True)
        raise ValueError("批准事件已经使用")
    return {"entry": entry, "pending_path": pending_path, "final_path": final_path}


def commit_reservation(reservation: dict) -> dict:
    pending = Path(reservation["pending_path"])
    final = Path(reservation["final_path"])
    if final.exists():
        pending.unlink(missing_ok=True)
        raise ValueError("批准事件已经使用")
    os.replace(pending, final)
    return reservation["entry"]


def rollback_reservation(reservation: dict | None) -> None:
    if isinstance(reservation, dict):
        Path(reservation["pending_path"]).unlink(missing_ok=True)


def consume_event(root: Path, event: dict, *, consumer: str) -> dict:
    reservation = reserve_event(root, event, consumer=consumer)
    return commit_reservation(reservation)


def validate_event(
    root: Path,
    value: object,
    *,
    action: str,
    target: Path,
    consume_state: dict | None = None,
    allow_consumed: bool = False,
) -> dict:
    if not isinstance(value, dict):
        raise ValueError("批准事件必须是对象")
    required = {"schema_version", "id", "action", "target_path", "target_sha256", "approved_at", "approved_by", "consumed"}
    if set(value) != required:
        raise ValueError("批准事件字段不完整或含额外字段")
    if value["schema_version"] != "1.0" or value["action"] != action or value["approved_by"] != "user":
        raise ValueError("批准事件身份或动作不匹配")
    if not isinstance(value["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", value["id"]):
        raise ValueError("批准事件ID无效")
    if not isinstance(value["approved_at"], str):
        raise ValueError("批准时间无效")
    try:
        datetime.fromisoformat(value["approved_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("批准时间无效") from exc
    if not isinstance(value["target_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["target_sha256"]):
        raise ValueError("批准目标哈希无效")
    if value["consumed"] is not False:
        raise ValueError("批准事件已经使用")
    expected = target.resolve().relative_to(root.resolve()).as_posix()
    if value["target_path"] != expected or value["target_sha256"] != sha256_file(target):
        raise ValueError("批准事件没有绑定当前目标版本")
    if consume_state is not None and value["id"] in consume_state.get("consumed_approval_ids", []):
        raise ValueError("批准事件已在项目状态中消费")
    if not allow_consumed and event_is_consumed(root, value["id"]):
        raise ValueError("批准事件已在批准消费账本中使用")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS))
    parser.add_argument("--target", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_by_user:
        raise SystemExit("ERROR: 必须显式确认用户已经批准")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", args.event_id):
        raise SystemExit("ERROR: event-id格式无效")
    root = Path(args.project_root).resolve()
    target, relative = resolve_under(root, args.target)
    directory = root / "治理/审批"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{args.event_id}.json"
    if output.exists():
        raise SystemExit("ERROR: 批准事件已存在，不允许覆盖")
    value = {
        "schema_version": "1.0",
        "id": args.event_id,
        "action": args.action,
        "target_path": relative,
        "target_sha256": sha256_file(target),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": "user",
        "consumed": False,
    }
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "recorded", "event": output.relative_to(root).as_posix()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
