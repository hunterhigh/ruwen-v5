#!/usr/bin/env python3
"""向治理技术账本追加不含创意内容的白名单事件。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_KEYS = {"role", "resource_ids", "change", "scope", "conflict_category", "approval_status", "result"}
SCOPE_KEYS = {"project", "volume", "arc", "chapter"}


def validate_event(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != ALLOWED_KEYS:
        return ["审计事件字段必须与白名单完全一致"]
    if not isinstance(value.get("role"), str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", value["role"]):
        errors.append("role无效")
    if not isinstance(value.get("resource_ids"), list) or not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9-]{2,64}", x) for x in value["resource_ids"]):
        errors.append("resource_ids无效")
    for key in ("change", "result"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[a-z0-9_-]{2,80}", value[key]):
            errors.append(f"{key}必须是技术事件标识")
    scope = value.get("scope")
    if not isinstance(scope, dict) or set(scope) != SCOPE_KEYS or any(x is not None and not isinstance(x, str) for x in scope.values()):
        errors.append("scope必须使用固定标量字段")
    if value.get("conflict_category") is not None and (not isinstance(value["conflict_category"], str) or not re.fullmatch(r"[a-z0-9_-]{2,80}", value["conflict_category"])):
        errors.append("conflict_category无效")
    if value.get("approval_status") not in {"not_required", "pending", "approved", "rejected"}:
        errors.append("approval_status无效")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--event-json", required=True)
    args = parser.parse_args()
    value = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    errors = validate_event(value)
    if errors:
        raise SystemExit("ERROR: " + "；".join(errors))
    event = {"time": datetime.now(timezone.utc).isoformat(), **value}
    root = Path(args.project_root).resolve()
    path = root / "治理/审计账本.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(event, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
