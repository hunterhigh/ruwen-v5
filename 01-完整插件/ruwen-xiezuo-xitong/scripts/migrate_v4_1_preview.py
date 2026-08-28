#!/usr/bin/env python3
"""只读分析V4.1项目文件的新职责与作用域；不移动、不改写项目。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RULES = (
    ("author-voice/pov-lenses/", "character", "人物/POV镜头/", "需要人工核对人物事实与文字接口是否混合"),
    ("author-voice/relationship-lenses/", "character", "人物/关系镜头/", "需要声明POV与故事弧作用域"),
    ("author-voice/scene-modes/", "expression", "表现/能力/", "必须通过闭合风险审计和试写"),
    ("author-voice/project-core.md", "expression", "表现/项目声音.md", "必须去除来源名、例子和剧情答案"),
    ("characters/", "character", "人物/", "主角必须拆成三模型档案"),
    ("world/", "world", "世界/", "百科材料需归入世界总表或正式系统"),
    ("continuity/", "world", "世界/当前态势.md", "时间状态与稳定Canon需人工拆分"),
    ("outlines/", "story", "故事/", "保留故事设计，不进入小说作者资料包"),
)


def classify(relative: str) -> dict[str, str]:
    normalized = relative.replace("\\", "/")
    for prefix, kind, target, note in RULES:
        if normalized == prefix or normalized.startswith(prefix):
            suffix = normalized[len(prefix):] if prefix.endswith("/") else ""
            return {"type": kind, "proposed_path": target + suffix, "note": note}
    return {"type": "governance", "proposed_path": "治理/待人工归类/" + Path(normalized).name, "note": "混合或未知职责，不自动迁移"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    files = []
    for path in sorted(x for x in root.rglob("*") if x.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("authoring-v4-1/packets/") or "__pycache__" in relative:
            continue
        files.append({
            "source_path": relative,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **classify(relative),
            "action": "preview_only",
        })
    result = {"source_root": str(root), "mode": "read_only_preview", "files": files, "warnings": ["未移动或改写任何文件", "所有拆分与作用域仍需用户批准"]}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        try:
            output.relative_to(root)
        except ValueError:
            pass
        else:
            raise SystemExit("ERROR: 迁移预览输出必须位于源项目之外")
        if output.exists():
            raise SystemExit("ERROR: 迁移预览不会覆盖已有文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
