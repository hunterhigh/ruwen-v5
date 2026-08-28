#!/usr/bin/env python3
"""检查如文5.0项目是否具备正式章节生产的最小人物、世界与治理基础。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import resource_registry


REQUIRED_FILES = (
    "AGENTS.md",
    "项目/项目章程.md",
    "人物/主角档案.md",
    "世界/世界总表.md",
    "世界/当前态势.md",
    "表现/项目声音.md",
    "治理/资源注册表.json",
    "治理/审计账本.jsonl",
    "治理/文学问题账本.jsonl",
)
PROTAGONIST_SECTIONS = ("客观存在模型", "内在组织模型", "叙述接口模型")
WORLD_SECTIONS = ("时代与空间", "物质与技术边界", "系统索引")
REQUIRED_ACTIVE_IDS = {
    "xiangmu-luyou-guize",
    "xiangmu-zhangcheng",
    "zhujue-dangan",
    "zhujue-pov-jingtou",
    "shijie-zongbiao",
    "shijie-dangqian-taishi",
    "gushi-dangqian-hu",
    "biaoxian-xiangmu-shengyin",
    "xiaoyan-yingsheding",
}
PLACEHOLDERS = ("待用户确认", "待项目初始化", "待批准材料")


def section_body(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        return ""
    tail = text.split(marker, 1)[1]
    return tail.split("\n## ", 1)[0].strip()


def check(root: Path) -> dict[str, object]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"缺少必需文件：{relative}")
    for relative in REQUIRED_FILES:
        path = root / relative
        if path.suffix.casefold() == ".md" and path.is_file():
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in PLACEHOLDERS):
                errors.append(f"必需资料仍含初始化占位：{relative}")
    protagonist = root / "人物/主角档案.md"
    if protagonist.is_file():
        text = protagonist.read_text(encoding="utf-8")
        for heading in PROTAGONIST_SECTIONS:
            body = section_body(text, heading)
            if len(body) < 40 or "待用户确认" in body:
                errors.append(f"主角档案未完成：{heading}")
    world = root / "世界/世界总表.md"
    if world.is_file():
        text = world.read_text(encoding="utf-8")
        for heading in WORLD_SECTIONS:
            if len(section_body(text, heading)) < 20:
                errors.append(f"世界总表未完成：{heading}")
    try:
        data, registry_errors = resource_registry.validate_registry(root)
        errors.extend(registry_errors)
        by_id = {item.get("id"): item for item in data["resources"]}
        for rid in sorted(REQUIRED_ACTIVE_IDS):
            item = by_id.get(rid)
            if item is None or item.get("status") != "active" or item.get("approval", {}).get("status") != "approved":
                errors.append(f"必需资源尚未批准并激活：{rid}")
        systems = [
            item for item in data["resources"]
            if item.get("type") == "world"
            and str(item.get("path", "")).startswith("世界/系统/")
            and item.get("status") == "active"
            and item.get("approval", {}).get("status") == "approved"
        ]
        if not systems:
            errors.append("至少需要一个已批准并激活的正式世界系统")
        for item in systems:
            text = (root / item["path"]).read_text(encoding="utf-8")
            if any(token in text for token in PLACEHOLDERS):
                errors.append(f"世界系统仍含初始化占位：{item['id']}")
        voices = [x for x in data["resources"] if x.get("path") == "表现/项目声音.md" and x.get("status") == "active"]
        if not voices:
            errors.append("项目声音尚未批准并激活")
    except resource_registry.RegistryError as exc:
        errors.append(str(exc))
    return {"ready": not errors, "status": "ready" if not errors else "blocked", "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_root).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
