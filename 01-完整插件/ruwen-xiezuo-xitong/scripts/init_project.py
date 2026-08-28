#!/usr/bin/env python3
"""从如文5.0模板建立不覆盖现有文件的新项目骨架。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", args.project_id):
        raise SystemExit("ERROR: project-id只允许3-64位小写字母、数字和连字符")
    root = Path(args.project_root).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit("ERROR: 目标目录必须不存在或为空；不会覆盖已有项目")
    template = Path(__file__).resolve().parent.parent / "assets/project-template"
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(tempfile.mkdtemp(prefix=".ruwen-init-", dir=root.parent))
    work = temporary_parent / "project"
    shutil.copytree(template, work)
    registry_path = work / "治理/资源注册表.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for item in registry["resources"]:
        item["scope"]["project"] = args.project_id
        item["source_sha256"] = hashlib.sha256((work / item["path"]).read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = work / "authoring-ruwen-v5/manifests/author-manifest.json"
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_value["context_scope"]["project"] = args.project_id
    manifest.write_text(json.dumps(manifest_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = work / "治理/审计账本.jsonl"
    event = {"time": datetime.now(timezone.utc).isoformat(), "role": "xiangmu-zhiliyuan", "resource_ids": [], "change": "project_scaffold_created", "scope": {"project": args.project_id, "volume": None, "arc": None, "chapter": None}, "conflict_category": None, "approval_status": "not_required", "result": "candidate_scaffold"}
    audit.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
    if root.exists():
        root.rmdir()
    work.replace(root)
    temporary_parent.rmdir()
    print(json.dumps({"status": "created", "project_root": str(root), "project_id": args.project_id, "readiness": "blocked_until_user_approval"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
