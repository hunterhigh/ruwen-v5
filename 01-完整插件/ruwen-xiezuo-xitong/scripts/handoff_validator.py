#!/usr/bin/env python3
"""验证跨岗位交接物只含白名单结构且不混入原始用户输入。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import approval_record


KINDS = {
    "creative_brief",
    "consultant_brief",
    "governance_preview",
    "expression_candidate",
    "chapter_situation",
    "memory_change_preview",
}
BASE_KEYS = {"kind", "sender", "recipient", "resource_ids", "scope", "approval_ref", "payload"}
FORBIDDEN_KEYS = {
    "raw_user_input",
    "original_prompt",
    "complaint_history",
    "editor_ledger",
    "blind_review",
    "source_trace",
    "reasoning",
    "failure_log",
    "content",
    "text",
    "message",
    "prompt",
    "input",
    "instructions",
}
RECIPIENTS = {
    "creative_brief": {"gushi-gousishi", "xiangmu-zhiliyuan", "wenxue-bianji", "biaoxian-shejishi", "waibu-zhishi-guwen"},
    "consultant_brief": {"waibu-zhishi-guwen"},
    "governance_preview": {"user", "xiangmu-zhiliyuan"},
    "expression_candidate": {"user", "xiangmu-zhiliyuan", "biaoxian-shejishi"},
    "chapter_situation": {"xiaoshuo-zuozhe"},
    "memory_change_preview": {"user", "jiyi-weihuyuan", "xiangmu-zhiliyuan"},
}
PAYLOAD_SCHEMAS = {
    "creative_brief": {"fixed", "creative_value", "unresolved_forces", "open_realization", "destination", "excluded_source"},
    "consultant_brief": {"known", "unknown", "learning_goal", "boundary", "allowed_sources", "destination"},
    "governance_preview": {"changes", "conflicts", "scope_changes", "writes_requested"},
    "expression_candidate": {"resource_id", "resource_path", "resource_sha256", "scope", "status"},
    "chapter_situation": {"projection_path", "projection_sha256", "chapter", "scope"},
    "memory_change_preview": {"preview_path", "preview_sha256", "changes", "retirements"},
}
SCOPE_KEYS = {"project", "volume", "arc", "chapter", "scene_type", "pov"}
EXCLUDED_SOURCE_VALUES = {
    "raw_user_wording",
    "example",
    "complaint_language",
    "correction_history",
    "implementation_route",
    "approval_dialogue",
    "unused_option",
}


def text_ok(value: object, *, maximum: int = 1200) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def text_list_ok(value: object, *, maximum_items: int = 32, maximum_text: int = 600) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum_items
        and all(text_ok(item, maximum=maximum_text) for item in value)
    )


def scope_ok(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value).issubset(SCOPE_KEYS)
        and "project" in value
        and all(item is None or text_ok(item, maximum=120) for item in value.values())
    )


def payload_value_errors(kind: str, payload: dict) -> list[str]:
    errors: list[str] = []
    if kind == "creative_brief":
        if not text_list_ok(payload.get("fixed")):
            errors.append("creative_brief.fixed必须是有界文本数组")
        if not text_ok(payload.get("creative_value")):
            errors.append("creative_brief.creative_value必须是有界文本")
        for key in ("unresolved_forces", "open_realization"):
            if not text_list_ok(payload.get(key)):
                errors.append(f"creative_brief.{key}必须是有界文本数组")
        excluded = payload.get("excluded_source")
        if not isinstance(excluded, list) or not set(excluded).issubset(EXCLUDED_SOURCE_VALUES):
            errors.append("creative_brief.excluded_source只能使用固定来源类别")
        if not text_ok(payload.get("destination"), maximum=300):
            errors.append("creative_brief.destination无效")
    elif kind == "consultant_brief":
        for key in ("known", "unknown", "learning_goal", "boundary", "destination"):
            if not text_ok(payload.get(key)):
                errors.append(f"consultant_brief.{key}必须是有界文本")
        if not text_list_ok(payload.get("allowed_sources"), maximum_items=16, maximum_text=200):
            errors.append("consultant_brief.allowed_sources必须是有界文本数组")
    elif kind == "governance_preview":
        for key in ("changes", "conflicts", "scope_changes", "writes_requested"):
            if not text_list_ok(payload.get(key), maximum_items=64):
                errors.append(f"governance_preview.{key}必须是有界文本数组")
    elif kind == "expression_candidate":
        for key in ("resource_id", "resource_path", "resource_sha256", "status"):
            if not text_ok(payload.get(key), maximum=300):
                errors.append(f"expression_candidate.{key}无效")
        if not scope_ok(payload.get("scope")):
            errors.append("expression_candidate.scope无效")
    elif kind == "chapter_situation":
        for key in ("projection_path", "projection_sha256", "chapter"):
            if not text_ok(payload.get(key), maximum=300):
                errors.append(f"chapter_situation.{key}无效")
        if not scope_ok(payload.get("scope")):
            errors.append("chapter_situation.scope无效")
    elif kind == "memory_change_preview":
        for key in ("preview_path", "preview_sha256"):
            if not text_ok(payload.get(key), maximum=300):
                errors.append(f"memory_change_preview.{key}无效")
        for key in ("changes", "retirements"):
            if not text_list_ok(payload.get(key), maximum_items=64):
                errors.append(f"memory_change_preview.{key}必须是有界文本数组")
    return errors


def normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def payload_text_values(value: object, path: str = "payload") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, list):
        result: list[tuple[str, str]] = []
        for index, child in enumerate(value):
            result.extend(payload_text_values(child, f"{path}[{index}]"))
        return result
    if isinstance(value, dict):
        result = []
        for key, child in value.items():
            result.extend(payload_text_values(child, f"{path}.{key}"))
        return result
    return []


def source_overlap_errors(payload: dict, raw_source: str) -> list[str]:
    raw = normalized(raw_source)
    if len(raw) < 12:
        return []
    errors: list[str] = []
    grams = {raw[index : index + 20] for index in range(max(1, len(raw) - 19))}
    for path, text in payload_text_values(payload):
        candidate = normalized(text)
        if len(candidate) < 12:
            continue
        copied = raw in candidate or (len(candidate) >= 16 and candidate in raw)
        chunk = len(raw) >= 20 and any(piece in candidate for piece in grams)
        if copied or chunk:
            errors.append(f"{path}与原始用户措辞存在长片段重合")
    return errors


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for child in value.values():
            result.update(nested_keys(child))
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for child in value:
            result.update(nested_keys(child))
        return result
    return set()


def validate(
    value: object,
    *,
    for_execution: bool = False,
    project_root: Path | None = None,
    raw_source: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["交接物必须是对象"]
    if set(value) != BASE_KEYS:
        errors.append("交接物顶层字段必须与白名单完全一致")
    kind = value.get("kind")
    if kind not in KINDS:
        errors.append("未知交接物类型")
    recipient = value.get("recipient")
    if kind in RECIPIENTS and recipient not in RECIPIENTS[kind]:
        errors.append("接收岗位与交接物类型不匹配")
    if not isinstance(value.get("sender"), str) or not value.get("sender"):
        errors.append("sender无效")
    if not isinstance(value.get("resource_ids"), list) or not all(isinstance(item, str) and re.fullmatch(r"[a-z0-9-]{2,64}", item) for item in value.get("resource_ids", [])):
        errors.append("resource_ids必须是数组")
    if not scope_ok(value.get("scope")):
        errors.append("scope必须是对象")
    approval_ref = value.get("approval_ref")
    if approval_ref is not None and not isinstance(approval_ref, dict):
        errors.append("approval_ref必须是对象或null")
    if not isinstance(value.get("payload"), dict):
        errors.append("payload必须是对象")
    elif kind in PAYLOAD_SCHEMAS and set(value["payload"]) != PAYLOAD_SCHEMAS[kind]:
        errors.append("payload字段与交接物类型不匹配")
    elif kind in PAYLOAD_SCHEMAS:
        errors.extend(payload_value_errors(kind, value["payload"]))
        if raw_source is not None:
            errors.extend(source_overlap_errors(value["payload"], raw_source))
    contaminated = nested_keys(value) & FORBIDDEN_KEYS
    if contaminated:
        errors.append("交接物含禁止字段：" + ", ".join(sorted(contaminated)))
    if kind == "chapter_situation" and isinstance(value.get("payload"), dict):
        forbidden = {"research", "governance", "editor_diagnostics", "source_list", "planning_reason"}
        leaked = nested_keys(value["payload"]) & forbidden
        if leaked:
            errors.append("章节情境含下游污染：" + ", ".join(sorted(leaked)))
    if for_execution and kind in {"creative_brief", "consultant_brief", "chapter_situation"}:
        if project_root is None or not isinstance(approval_ref, dict) or set(approval_ref) != {"path", "sha256"}:
            errors.append("执行下游岗位需要独立批准事件引用")
        else:
            try:
                event_path = (project_root / str(approval_ref["path"])).resolve()
                event_path.relative_to((project_root / "治理/审批").resolve())
                event = json.loads(event_path.read_text(encoding="utf-8"))
                if hashlib.sha256(event_path.read_bytes()).hexdigest() != approval_ref["sha256"]:
                    raise ValueError("批准事件哈希不匹配")
                payload_path = (project_root / str(event.get("target_path"))).resolve()
                payload_path.relative_to((project_root / "治理/交接").resolve())
                approval_record.validate_event(
                    project_root,
                    event,
                    action="handoff_execute",
                    target=payload_path,
                )
                approved_payload = json.loads(payload_path.read_text(encoding="utf-8"))
                if approved_payload != value["payload"]:
                    raise ValueError("批准事件未绑定当前payload")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"批准事件无效：{exc}")
    return errors


def consume_execution_approval(value: dict, project_root: Path) -> dict:
    approval_ref = value["approval_ref"]
    event_path = (project_root / approval_ref["path"]).resolve()
    event = json.loads(event_path.read_text(encoding="utf-8"))
    return approval_record.consume_event(
        project_root,
        event,
        consumer=str(value["recipient"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--for-execution", action="store_true")
    parser.add_argument("--creation-check", action="store_true")
    parser.add_argument("--project-root")
    args = parser.parse_args()
    value = json.loads(Path(args.file).read_text(encoding="utf-8"))
    root = Path(args.project_root).resolve() if args.project_root else None
    if args.creation_check and args.for_execution:
        raise SystemExit("ERROR: creation-check与for-execution不能同时使用")
    raw_source = sys.stdin.read() if args.creation_check else None
    if args.creation_check and not raw_source.strip():
        raise SystemExit("ERROR: creation-check必须从标准输入接收当前原始用户表达")
    errors = validate(
        value,
        for_execution=args.for_execution,
        project_root=root,
        raw_source=raw_source,
    )
    if not errors and args.for_execution and root is not None and value.get("kind") in {"creative_brief", "consultant_brief", "chapter_situation"}:
        try:
            consume_execution_approval(value, root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"批准事件消费失败：{exc}")
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
