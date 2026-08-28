#!/usr/bin/env python3
"""校验如文5.0资源注册表，并按作用域选择可用资料。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import approval_record


REGISTRY_RELATIVE = Path("治理/资源注册表.json")
SCHEMA_VERSION = "1.0"
TYPES = {"evidence", "character", "world", "story", "expression", "validation", "governance"}
STATUSES = {"proposed", "candidate", "active", "superseded", "retired"}
TRANSITIONS = {
    "proposed": {"candidate", "retired"},
    "candidate": {"active", "retired"},
    "active": {"superseded", "retired"},
    "superseded": set(),
    "retired": set(),
}
SCOPE_KEYS = {"project", "volumes", "arcs", "chapters", "scene_types", "povs"}
AUTHOR_PATH_PREFIXES = (
    "表现/项目声音.md",
    "表现/能力/",
    "人物/POV镜头/",
    "人物/关系镜头/",
)
FORBIDDEN_AUTHOR_PREFIXES = ("研究/", "治理/", "校验/", "世界/", "故事/")
TYPE_PATH_PREFIXES = {
    "evidence": ("研究/",),
    "character": ("人物/",),
    "world": ("世界/",),
    "story": ("故事/",),
    "expression": ("表现/",),
    "validation": ("校验/",),
    "governance": ("项目/", "治理/", "AGENTS.md"),
}


class RegistryError(ValueError):
    pass


def write_registry(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_registry(root: Path) -> dict[str, Any]:
    path = root / REGISTRY_RELATIVE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"无法读取资源注册表：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("resources"), list):
        raise RegistryError("资源注册表必须包含resources数组")
    return data


def normalize_path(root: Path, value: Any) -> tuple[Path, str]:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError("资源路径必须是非空文本")
    raw = Path(value)
    resolved = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise RegistryError(f"资源路径越出项目：{resolved}") from exc
    if not resolved.is_file():
        raise RegistryError(f"资源文件不存在：{relative}")
    return resolved, relative


def validate_scope(scope: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(scope, dict):
        return ["scope必须是对象"]
    extra = set(scope) - SCOPE_KEYS
    if extra:
        errors.append("scope含未知字段：" + ", ".join(sorted(extra)))
    project = scope.get("project")
    if project is not None and not isinstance(project, str):
        errors.append("scope.project必须是文本或null")
    for key in SCOPE_KEYS - {"project"}:
        value = scope.get(key)
        if value is not None and (not isinstance(value, list) or not all(isinstance(x, str) and x for x in value)):
            errors.append(f"scope.{key}必须是非空文本数组或null")
    return errors


def author_path_allowed(relative: str) -> bool:
    if relative.startswith(FORBIDDEN_AUTHOR_PREFIXES):
        return False
    return relative == AUTHOR_PATH_PREFIXES[0] or relative.startswith(AUTHOR_PATH_PREFIXES[1:])


def validate_closure_evidence(root: Path, resource: dict[str, Any], approval: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        evidence_path, _ = normalize_path(root, approval.get("closure_audit_path"))
        if approval.get("closure_audit_sha256") != sha256_file(evidence_path):
            errors.append("closure_audit_sha256不匹配")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        resource_path, _ = normalize_path(root, resource["path"])
        if evidence.get("pass") is not True:
            errors.append("闭合审计未通过")
        if evidence.get("resource_id") != resource.get("id") or evidence.get("resource_version") != resource.get("version"):
            errors.append("闭合审计未绑定资源ID或版本")
        if evidence.get("sha256") != resource.get("source_sha256") or Path(str(evidence.get("path"))).resolve() != resource_path:
            errors.append("闭合审计未绑定当前资源路径与哈希")
        review = evidence.get("manual_review")
        if not isinstance(review, dict) or review.get("resource_sha256") != resource.get("source_sha256"):
            errors.append("闭合审计缺少绑定当前资源的人工六项复核")
    except (RegistryError, OSError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"闭合审计证据无效：{exc}")
    return errors


def validate_trial_evidence(root: Path, resource: dict[str, Any], approval: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        report_path, _ = normalize_path(root, approval.get("trial_report_path"))
        if approval.get("trial_report_sha256") != sha256_file(report_path):
            errors.append("trial_report_sha256不匹配")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected_keys = {"resource_id", "resource_path", "resource_version", "resource_sha256", "output_path", "output_sha256", "user_accepted", "canonical"}
        if set(report) != expected_keys:
            errors.append("试写报告字段无效")
        if report.get("resource_id") != resource.get("id") or report.get("resource_path") != resource.get("path") or report.get("resource_version") != resource.get("version") or report.get("resource_sha256") != resource.get("source_sha256"):
            errors.append("试写报告未绑定当前资源")
        if report.get("user_accepted") is not True or report.get("canonical") is not False:
            errors.append("试写不是已接受的非正典文本")
        output_path, _ = normalize_path(root, report.get("output_path"))
        if report.get("output_sha256") != sha256_file(output_path):
            errors.append("试写产物哈希不匹配")
    except (RegistryError, OSError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"试写证据无效：{exc}")
    return errors


def validate_registry(root: Path, *, check_hashes: bool = True) -> tuple[dict[str, Any], list[str]]:
    data = read_registry(root)
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"不支持的注册表schema：{data.get('schema_version')!r}")
    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    resources = data["resources"]
    for index, item in enumerate(resources):
        label = f"resources[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}必须是对象")
            continue
        rid = item.get("id")
        if not isinstance(rid, str) or not rid:
            errors.append(f"{label}.id无效")
        elif rid in seen_ids:
            errors.append(f"重复资源ID：{rid}")
        else:
            seen_ids.add(rid)
        if item.get("type") not in TYPES:
            errors.append(f"{rid or label}的type无效")
        if item.get("status") not in STATUSES:
            errors.append(f"{rid or label}的status无效")
        for key in ("owner", "version"):
            if not isinstance(item.get(key), str) or not item[key]:
                errors.append(f"{rid or label}.{key}无效")
        errors.extend(f"{rid or label}: {value}" for value in validate_scope(item.get("scope")))
        readers = item.get("readers")
        if not isinstance(readers, list) or not all(isinstance(x, str) and x for x in readers):
            errors.append(f"{rid or label}.readers无效")
        if not isinstance(item.get("allow_author"), bool):
            errors.append(f"{rid or label}.allow_author必须是布尔值")
        try:
            path, relative = normalize_path(root, item.get("path"))
            previous = seen_paths.get(relative)
            if previous:
                errors.append(f"同一路径被多个资源拥有：{previous}, {rid}")
            else:
                seen_paths[relative] = str(rid)
            if item.get("allow_author") and not author_path_allowed(relative):
                errors.append(f"{rid}越权允许小说作者读取：{relative}")
            prefixes = TYPE_PATH_PREFIXES.get(item.get("type"), ())
            if not any(relative == prefix or relative.startswith(prefix) for prefix in prefixes):
                errors.append(f"{rid}的资源类型与目录职责不一致：{relative}")
            expected = item.get("source_sha256")
            if check_hashes and (not isinstance(expected, str) or sha256_file(path) != expected):
                errors.append(f"{rid}的来源哈希不匹配")
        except RegistryError as exc:
            errors.append(f"{rid or label}: {exc}")
        approval = item.get("approval")
        if not isinstance(approval, dict) or approval.get("status") not in {"unapproved", "approved"}:
            errors.append(f"{rid or label}.approval无效")
        if item.get("status") == "active" and isinstance(approval, dict) and approval.get("status") != "approved":
            errors.append(f"{rid or label}未批准却处于active")
        if item.get("status") == "active" and isinstance(approval, dict):
            try:
                event_path, _ = normalize_path(root, approval.get("approval_event_path"))
                if approval.get("approval_event_sha256") != sha256_file(event_path):
                    raise RegistryError("批准事件哈希不匹配")
                event = json.loads(event_path.read_text(encoding="utf-8"))
                resource_path, _ = normalize_path(root, item["path"])
                action = "expression_activate" if item.get("type") == "expression" else "resource_activate"
                approval_record.validate_event(root, event, action=action, target=resource_path, allow_consumed=True)
                if not approval_record.event_is_committed(root, event["id"]):
                    raise RegistryError("active资源批准事件尚未消费")
            except (RegistryError, ValueError, json.JSONDecodeError, TypeError) as exc:
                errors.append(f"{rid or label}: active资源批准事件无效：{exc}")
        if item.get("type") == "expression" and item.get("status") in {"candidate", "active"} and isinstance(approval, dict):
            errors.extend(f"{rid or label}: {message}" for message in validate_closure_evidence(root, item, approval))
            if item.get("status") == "active":
                errors.extend(f"{rid or label}: {message}" for message in validate_trial_evidence(root, item, approval))
        supersedes = item.get("supersedes")
        if supersedes is not None and not isinstance(supersedes, str):
            errors.append(f"{rid or label}.supersedes必须是资源ID或null")
    for item in resources:
        if isinstance(item, dict) and isinstance(item.get("supersedes"), str) and item["supersedes"] not in seen_ids:
            errors.append(f"{item.get('id')}引用不存在的supersedes：{item['supersedes']}")
    by_id = {item.get("id"): item for item in resources if isinstance(item, dict) and isinstance(item.get("id"), str)}
    for item in by_id.values():
        target_id = item.get("supersedes")
        if not isinstance(target_id, str):
            continue
        target = by_id.get(target_id)
        if target and target.get("type") != item.get("type"):
            errors.append(f"{item['id']}不能替代不同职责资源{target_id}")
        visited = {item["id"]}
        cursor = target
        while cursor and isinstance(cursor.get("supersedes"), str):
            next_id = cursor["supersedes"]
            if next_id in visited:
                errors.append(f"supersedes形成循环：{item['id']}")
                break
            visited.add(next_id)
            cursor = by_id.get(next_id)
    active_abilities = [
        item
        for item in by_id.values()
        if item.get("status") == "active"
        and isinstance(item.get("path"), str)
        and item["path"].startswith("表现/能力/")
    ]
    for index, left in enumerate(active_abilities):
        for right in active_abilities[index + 1 :]:
            if scopes_overlap(left["scope"], right["scope"]):
                errors.append(
                    "active表现能力作用域冲突："
                    f"{left['id']} 与 {right['id']}"
                )
    return data, errors


def scope_matches(scope: dict[str, Any], query: dict[str, str | None]) -> bool:
    if scope.get("project") is not None and scope.get("project") != query.get("project"):
        return False
    mapping = {"volumes": "volume", "arcs": "arc", "chapters": "chapter", "scene_types": "scene_type", "povs": "pov"}
    for plural, singular in mapping.items():
        allowed = scope.get(plural)
        if allowed is not None and query.get(singular) not in allowed:
            return False
    return True


def specificity(scope: dict[str, Any]) -> int:
    score = 1 if scope.get("project") is not None else 0
    return score + sum(1 for key in SCOPE_KEYS - {"project"} if scope.get(key) is not None)


def scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("project") is not None and right.get("project") is not None and left["project"] != right["project"]:
        return False
    for key in SCOPE_KEYS - {"project"}:
        a, b = left.get(key), right.get(key)
        if a is not None and b is not None and not (set(a) & set(b)):
            return False
    return True


def select(root: Path, query: dict[str, str | None], *, author_only: bool) -> list[dict[str, Any]]:
    data, errors = validate_registry(root)
    if errors:
        raise RegistryError("；".join(errors))
    values = [
        item for item in data["resources"]
        if item["status"] == "active"
        and (not author_only or item["allow_author"])
        and scope_matches(item["scope"], query)
    ]
    values.sort(key=lambda item: (-specificity(item["scope"]), item["type"], item["id"]))
    if author_only:
        expressions = [x for x in values if x["path"].startswith("表现/能力/")]
        if len(expressions) > 1:
            raise RegistryError("当前作用域同时命中多份表现能力：" + ", ".join(x["id"] for x in expressions))
    return values


def transition(
    root: Path,
    resource_id: str,
    status: str,
    *,
    approved: bool,
    approval_event: str | None = None,
    closure_audit: str | None = None,
    trial_report: str | None = None,
) -> dict[str, Any]:
    data, errors = validate_registry(root, check_hashes=True)
    if errors:
        raise RegistryError("；".join(errors))
    if status not in STATUSES:
        raise RegistryError(f"未知状态：{status}")
    resource = next((x for x in data["resources"] if x["id"] == resource_id), None)
    if resource is None:
        raise RegistryError(f"资源不存在：{resource_id}")
    current = resource["status"]
    if status not in TRANSITIONS[current]:
        raise RegistryError(f"不允许的状态转换：{current} -> {status}")
    approval_event_ref: dict[str, str] = {}
    if status == "active":
        if not approved or not approval_event:
            raise RegistryError("激活资源必须显式确认用户批准并提供独立批准事件")
        event_path, event_relative = normalize_path(root, approval_event)
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
            resource_path, _ = normalize_path(root, resource["path"])
            action = "expression_activate" if resource.get("type") == "expression" else "resource_activate"
            approval_record.validate_event(root, event, action=action, target=resource_path)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RegistryError(f"表现资源批准事件无效：{exc}") from exc
        approval_event_ref = {"approval_event_path": event_relative, "approval_event_sha256": sha256_file(event_path)}
    evidence: dict[str, str] = {}
    if status in {"candidate", "active"} and resource.get("type") == "expression":
        if not closure_audit or (status == "active" and not trial_report):
            raise RegistryError("表现资源进入candidate需要闭合审计；激活还需要非正典试写报告")
        audit_path, audit_relative = normalize_path(root, closure_audit)
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryError(f"闭合审计不是有效JSON：{exc}") from exc
        evidence = {
            "closure_audit_path": audit_relative,
            "closure_audit_sha256": sha256_file(audit_path),
        }
        closure_errors = validate_closure_evidence(root, resource, evidence)
        if closure_errors:
            raise RegistryError("；".join(closure_errors))
        if status == "active":
            trial_path, trial_relative = normalize_path(root, str(trial_report))
            evidence.update({"trial_report_path": trial_relative, "trial_report_sha256": sha256_file(trial_path)})
            trial_errors = validate_trial_evidence(root, resource, evidence)
            if trial_errors:
                raise RegistryError("；".join(trial_errors))
    if status == "active" and isinstance(resource.get("supersedes"), str):
        replaced = next(x for x in data["resources"] if x["id"] == resource["supersedes"])
        if not scopes_overlap(resource["scope"], replaced["scope"]):
            raise RegistryError("替代资源与被替代资源的作用域不相交")
    resource["status"] = status
    if status == "active" and isinstance(resource.get("supersedes"), str):
        replaced = next(x for x in data["resources"] if x["id"] == resource["supersedes"])
        replaced["status"] = "superseded"
    if approved:
        resource["approval"] = {
            "status": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": "user",
            **evidence,
            **approval_event_ref,
        }
    elif evidence:
        resource["approval"] = {
            "status": "unapproved",
            "approved_at": None,
            "approved_by": None,
            **evidence,
        }
    path = root / REGISTRY_RELATIVE
    previous = path.read_text(encoding="utf-8")
    reservation = None
    try:
        if status == "active":
            reservation = approval_record.reserve_event(
                root,
                event,
                consumer="xiangmu-zhiliyuan",
            )
        write_registry(path, data)
        if reservation is not None:
            approval_record.commit_reservation(reservation)
    except Exception as exc:
        approval_record.rollback_reservation(reservation)
        write_registry(path, json.loads(previous))
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError(f"资源状态提交失败：{exc}") from exc
    return resource


def refresh_hash(root: Path, resource_id: str, *, approved: bool) -> dict[str, Any]:
    if not approved:
        raise RegistryError("刷新资源哈希需要显式确认用户已批准本次资料修改")
    data, errors = validate_registry(root, check_hashes=False)
    if errors:
        raise RegistryError("；".join(errors))
    resource = next((x for x in data["resources"] if x["id"] == resource_id), None)
    if resource is None:
        raise RegistryError(f"资源不存在：{resource_id}")
    if resource.get("type") == "expression" and resource.get("status") == "active":
        raise RegistryError("active表现资源不能直接刷新；请建立新版本并重新审计、试写和激活")
    path, _ = normalize_path(root, resource["path"])
    resource["source_sha256"] = sha256_file(path)
    if resource.get("type") == "expression" and resource.get("status") == "candidate":
        resource["status"] = "proposed"
    resource["approval"] = {
        "status": "approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": "user",
    }
    registry_path = root / REGISTRY_RELATIVE
    write_registry(registry_path, data)
    return resource


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--project-root", required=True)
    choose = sub.add_parser("select")
    choose.add_argument("--project-root", required=True)
    choose.add_argument("--project")
    choose.add_argument("--volume")
    choose.add_argument("--arc")
    choose.add_argument("--chapter")
    choose.add_argument("--scene-type")
    choose.add_argument("--pov")
    choose.add_argument("--author-only", action="store_true")
    change = sub.add_parser("transition")
    change.add_argument("--project-root", required=True)
    change.add_argument("--resource-id", required=True)
    change.add_argument("--status", required=True)
    change.add_argument("--approved-by-user", action="store_true")
    change.add_argument("--approval-event")
    change.add_argument("--closure-audit")
    change.add_argument("--trial-report")
    refresh = sub.add_parser("refresh-hash")
    refresh.add_argument("--project-root", required=True)
    refresh.add_argument("--resource-id", required=True)
    refresh.add_argument("--approved-by-user", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    root = Path(args.project_root).resolve()
    try:
        if args.command == "validate":
            _, errors = validate_registry(root)
            print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        if args.command == "select":
            query = {key: getattr(args, key) for key in ("project", "volume", "arc", "chapter", "scene_type", "pov")}
            print(json.dumps(select(root, query, author_only=args.author_only), ensure_ascii=False, indent=2))
            return 0
        if args.command == "transition":
            result = transition(
                root,
                args.resource_id,
                args.status,
                approved=args.approved_by_user,
                approval_event=args.approval_event,
                closure_audit=args.closure_audit,
                trial_report=args.trial_report,
            )
        else:
            result = refresh_hash(root, args.resource_id, approved=args.approved_by_user)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
