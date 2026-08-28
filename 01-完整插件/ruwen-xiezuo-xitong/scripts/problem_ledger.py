#!/usr/bin/env python3
"""维护文学编辑私有问题账本，并只向治理层输出匿名聚合统计。"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REQUIRED = {"location", "category", "condition", "handling", "result", "task_id", "status"}


def read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"第{number}行不是对象")
            result.append(value)
    return result


def append(path: Path, value: dict) -> dict:
    if set(value) != REQUIRED:
        raise ValueError("问题条目字段必须与白名单完全一致")
    if not all(isinstance(value[key], str) and 0 < len(value[key]) <= 1000 for key in REQUIRED):
        raise ValueError("问题条目字段必须是有长度限制的文本")
    now = datetime.now(timezone.utc).isoformat()
    previous = read_entries(path)
    same = [x for x in previous if x.get("category") == value["category"]]
    tasks = {x.get("task_id") for x in same} | {value["task_id"]}
    entry = {
        **value,
        "first_seen": same[0].get("first_seen", same[0].get("recorded_at")) if same else now,
        "last_seen": now,
        "recorded_at": now,
        "recurrence_count": len(same) + 1,
        "recurrence_candidate": len(same) + 1 >= 3 and len(tasks) >= 2,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def summary(path: Path) -> dict:
    entries = read_entries(path)
    counts = Counter(str(x.get("category")) for x in entries)
    tasks: dict[str, set[str]] = defaultdict(set)
    for item in entries:
        tasks[str(item.get("category"))].add(str(item.get("task_id")))
    return {
        "total": len(entries),
        "categories": [
            {"category": key, "count": count, "task_count": len(tasks[key]), "recurrence_candidate": count >= 3 and len(tasks[key]) >= 2}
            for key, count in sorted(counts.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("append")
    add.add_argument("--project-root", required=True)
    add.add_argument("--entry-json", required=True)
    report = sub.add_parser("summary")
    report.add_argument("--project-root", required=True)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    path = root / "治理/文学问题账本.jsonl"
    if args.command == "append":
        result = append(path, json.loads(Path(args.entry_json).read_text(encoding="utf-8")))
    else:
        result = summary(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
