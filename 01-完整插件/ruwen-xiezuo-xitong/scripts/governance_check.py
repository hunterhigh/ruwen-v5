#!/usr/bin/env python3
"""运行如文5.0常态治理检查，不修改项目。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import audit_ledger
import resource_registry


AUTHOR_FIELDS = ("project_voice", "pov_lens", "relationship_lens", "expression_resource")
FORBIDDEN_PACKET_VALUES = ("研究/", "治理/", "校验/", "世界/", "故事/")


def read_jsonl(path: Path) -> list[dict]:
    values = []
    if not path.is_file():
        return values
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}第{number}行不是对象")
        values.append(value)
    return values


def check(root: Path) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        registry, registry_errors = resource_registry.validate_registry(root)
        errors.extend(registry_errors)
    except resource_registry.RegistryError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}
    by_path = {item["path"]: item for item in registry["resources"]}
    manifests = root / "authoring-ruwen-v5/manifests"
    for path in manifests.glob("*.json") if manifests.is_dir() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"manifest无效：{path.name}: {exc}")
            continue
        for field in AUTHOR_FIELDS:
            source = value.get(field)
            if source is None:
                continue
            if not isinstance(source, str) or source.startswith(FORBIDDEN_PACKET_VALUES):
                errors.append(f"{path.name}.{field}越权：{source}")
                continue
            item = by_path.get(source)
            if item is None or item.get("status") != "active" or item.get("allow_author") is not True:
                errors.append(f"{path.name}.{field}引用未激活资源：{source}")
    try:
        audit_entries = read_jsonl(root / "治理/审计账本.jsonl")
        for index, item in enumerate(audit_entries, 1):
            if set(item) != ({"time"} | audit_ledger.ALLOWED_KEYS):
                errors.append(f"审计账本第{index}行字段无效")
                continue
            event_errors = audit_ledger.validate_event({key: value for key, value in item.items() if key != "time"})
            errors.extend(f"审计账本第{index}行：{message}" for message in event_errors)
    except (ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    if (root / "治理/文学问题账本.jsonl").is_file():
        for path in manifests.glob("*.json") if manifests.is_dir() else []:
            if "文学问题账本" in path.read_text(encoding="utf-8"):
                errors.append(f"文学问题账本污染作者manifest：{path.name}")
    inactive = [item["id"] for item in registry["resources"] if item["status"] in {"superseded", "retired"}]
    if inactive:
        warnings.append("已失效资源：" + ", ".join(inactive))
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_root).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
