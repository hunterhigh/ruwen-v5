#!/usr/bin/env python3
"""Manage 如文5.0 engineering state without writing story meaning."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import project_readiness
import resource_registry
import approval_record


SCHEMA_VERSION = "2.0"
MIGRATABLE_SCHEMA_VERSION = "1.2"
STATE_RELATIVE = Path("authoring-ruwen-v5/state.json")
AUTHORING_RELATIVE = Path("authoring-ruwen-v5")
GENERATED_DIRS = (
    "authoring-ruwen-v5/plans",
    "authoring-ruwen-v5/projections",
    "authoring-ruwen-v5/manifests",
    "authoring-ruwen-v5/exact-text",
    "authoring-ruwen-v5/packets",
    "authoring-ruwen-v5/reports",
    "authoring-ruwen-v5/candidates",
    "authoring-ruwen-v5/snapshots",
    "authoring-ruwen-v5/snapshots/state-migrations",
    "authoring-ruwen-v5/snapshots/replacements",
)
CONTEXT_SCOPE_KEYS = {"project", "volume", "arc", "chapter", "scene_type", "pov"}


class StateError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_directory(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def copy_file_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def normalize_project_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    if not root.is_dir():
        raise StateError(f"Project root does not exist: {root}")
    return root


def resolve_under(root: Path, value: str | Path, *, must_exist: bool = True) -> Path:
    raw = Path(value)
    resolved = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise StateError(f"Path escapes project root: {resolved}") from exc
    if must_exist and not resolved.is_file():
        raise StateError(f"Missing file: {resolved}")
    return resolved


def resolve_directory_under(root: Path, value: str | Path) -> Path:
    raw = Path(value)
    resolved = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise StateError(f"Path escapes project root: {resolved}") from exc
    if not resolved.is_dir():
        raise StateError(f"Missing directory: {resolved}")
    return resolved


def require_under(path: Path, parent: Path, message: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as exc:
        raise StateError(message) from exc


def relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def artifact_ref(root: Path, path: Path) -> dict[str, str]:
    return {"path": relative_path(root, path), "sha256": sha256_file(path)}


def parse_sources(values: Iterable[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise StateError(f"Source must use role=path: {value}")
        role, path = value.split("=", 1)
        role = role.strip()
        path = path.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", role):
            raise StateError(f"Invalid source role: {role}")
        if not path:
            raise StateError(f"Empty path for source role: {role}")
        if role in seen:
            raise StateError(f"Duplicate source role: {role}")
        seen.add(role)
        result.append((role, path))
    return result


def source_refs(root: Path, values: Iterable[str]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for role, value in parse_sources(values):
        path = resolve_under(root, value)
        refs.append({"role": role, **artifact_ref(root, path)})
    return refs


def require_registered_inputs(
    root: Path, outline: Path, tracked_sources: list[dict[str, str]]
) -> None:
    try:
        registry, errors = resource_registry.validate_registry(root)
    except resource_registry.RegistryError as exc:
        raise StateError(f"资源注册表不可用：{exc}") from exc
    if errors:
        raise StateError("资源注册表无效：" + "; ".join(errors))
    by_path = {item["path"]: item for item in registry["resources"]}

    def require(path: Path, allowed_types: set[str], label: str) -> None:
        relative = relative_path(root, path)
        item = by_path.get(relative)
        if item is None:
            raise StateError(f"{label}未在资源注册表中登记：{relative}")
        if item.get("type") not in allowed_types:
            raise StateError(f"{label}职责越权：{relative}")
        if item.get("status") != "active" or item.get("approval", {}).get("status") != "approved":
            raise StateError(f"{label}尚未批准并激活：{relative}")
        if item.get("source_sha256") != sha256_file(path):
            raise StateError(f"{label}哈希与注册表不一致：{relative}")

    require(outline, {"story"}, "active outline")
    for source in tracked_sources:
        require(resolve_under(root, source["path"]), {"character", "world", "story"}, f"tracked source {source['role']}")


def validate_context_scope(value: Any, chapter: str) -> dict[str, str | None]:
    if not isinstance(value, dict) or set(value) != CONTEXT_SCOPE_KEYS:
        raise StateError("context scope必须完整包含project、volume、arc、chapter、scene_type、pov")
    if any(item is not None and not isinstance(item, str) for item in value.values()):
        raise StateError("context scope的值必须是文本或null")
    if value.get("chapter") != chapter:
        raise StateError("context scope.chapter必须与注册章节一致")
    return dict(value)


def build_rewrite_snapshot(
    root: Path, cutoff: str | None, snapshot_value: str | None
) -> dict[str, str] | None:
    if bool(cutoff) != bool(snapshot_value):
        raise StateError("rewrite-cutoff and snapshot-root must be provided together")
    if not cutoff or not snapshot_value:
        return None
    snapshot = resolve_directory_under(root, snapshot_value)
    expected = (root / "authoring-ruwen-v5/snapshots").resolve()
    require_under(
        snapshot,
        expected,
        "rewrite snapshot must live under authoring-ruwen-v5/snapshots",
    )
    return {
        "cutoff": cutoff,
        "root": relative_path(root, snapshot),
        "sha256": sha256_directory(snapshot),
    }


def require_snapshot_source(
    root: Path, state: dict[str, Any], path: Path, role: str
) -> None:
    snapshot = state.get("rewrite_snapshot")
    if snapshot is None:
        return
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("root"), str):
        raise StateError("rewrite snapshot state is invalid")
    snapshot_root = resolve_directory_under(root, snapshot["root"])
    require_under(
        path,
        snapshot_root,
        f"rewrite source {role} must live under the registered snapshot: {path}",
    )


def state_path(root: Path) -> Path:
    return root / STATE_RELATIVE


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        raise StateError(f"如文5.0 project is not initialized: {path}")
    state = read_json(path)
    version = state.get("schema_version")
    if version == MIGRATABLE_SCHEMA_VERSION:
        raise StateError(
            "State schema 1.2 requires explicit migration; run "
            "migrate-state --project-root <project> --check, then --apply"
        )
    if version != SCHEMA_VERSION:
        raise StateError(f"Unsupported state schema: {version!r}")
    if "pending_approved_candidate" not in state or not isinstance(
        state.get("approval_history"), list
    ):
        raise StateError("State schema 2.0 is missing approval lifecycle fields")
    if not isinstance(state.get("consumed_approval_ids"), list):
        raise StateError("State schema 2.0 is missing consumed approval IDs")
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path(root), state)


def migration_preview(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        raise StateError(f"如文5.0 project is not initialized: {path}")
    state = read_json(path)
    version = state.get("schema_version")
    if version == SCHEMA_VERSION:
        return {
            "status": "up-to-date",
            "from_schema": SCHEMA_VERSION,
            "to_schema": SCHEMA_VERSION,
            "changes_required": False,
        }
    if version != MIGRATABLE_SCHEMA_VERSION:
        raise StateError(f"Unsupported state schema: {version!r}")
    approved = state.get("last_approved_prose")
    approved_path = approved.get("path") if isinstance(approved, dict) else None
    candidate_path = isinstance(approved_path, str) and approved_path.startswith(
        "authoring-ruwen-v5/candidates/"
    )
    legacy = bool(state.get("pending_consolidation")) or candidate_path
    return {
        "status": "migration-required",
        "from_schema": MIGRATABLE_SCHEMA_VERSION,
        "to_schema": SCHEMA_VERSION,
        "changes_required": True,
        "backup_directory": "authoring-ruwen-v5/snapshots/state-migrations",
        "legacy_import": legacy,
        "legacy_reason": {
            "pending_consolidation": bool(state.get("pending_consolidation")),
            "last_approved_prose_is_candidate": candidate_path,
        },
    }


def migrate_state(root: Path, *, apply: bool) -> dict[str, Any]:
    preview = migration_preview(root)
    if not apply or not preview["changes_required"]:
        return preview
    path = state_path(root)
    old_state = read_json(path)
    old_hash = sha256_file(path)
    backup = (
        root
        / "authoring-ruwen-v5/snapshots/state-migrations"
        / f"state-1.2-{timestamp_token()}-{old_hash[:12]}.json"
    )
    copy_file_atomic(path, backup)
    migrated = dict(old_state)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["pending_approved_candidate"] = None
    migrated["approval_history"] = []
    migrated["consumed_approval_ids"] = []
    if preview["legacy_import"]:
        legacy_entry = {
            "event": "legacy_import",
            "imported_at": utc_now(),
            "source_schema": MIGRATABLE_SCHEMA_VERSION,
            "last_approved_prose": old_state.get("last_approved_prose"),
            "pending_consolidation": bool(old_state.get("pending_consolidation")),
            "note": "Preserved without inferring whether prose was candidate or formal.",
        }
        migrated["legacy_import"] = legacy_entry
        migrated["approval_history"].append(legacy_entry)
    save_state(root, migrated)
    return {
        "status": "migrated",
        "from_schema": MIGRATABLE_SCHEMA_VERSION,
        "to_schema": SCHEMA_VERSION,
        "backup": relative_path(root, backup),
        "backup_sha256": old_hash,
        "legacy_import": preview["legacy_import"],
    }


def current_ref_reason(root: Path, ref: dict[str, Any], label: str) -> str | None:
    value = ref.get("path")
    expected = ref.get("sha256")
    if not isinstance(value, str) or not isinstance(expected, str):
        return f"invalid {label} reference"
    try:
        path = resolve_under(root, value)
    except StateError as exc:
        return str(exc)
    actual = sha256_file(path)
    if actual != expected:
        return f"changed {label}: {value}"
    return None


def base_source_reasons(root: Path, state: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    snapshot = state.get("rewrite_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict):
            reasons.append("rewrite snapshot is invalid")
        else:
            value = snapshot.get("root")
            expected = snapshot.get("sha256")
            if not isinstance(value, str) or not isinstance(expected, str):
                reasons.append("rewrite snapshot reference is invalid")
            else:
                try:
                    directory = resolve_directory_under(root, value)
                    if sha256_directory(directory) != expected:
                        reasons.append(f"changed rewrite snapshot: {value}")
                except StateError as exc:
                    reasons.append(str(exc))
    outline = state.get("active_outline")
    if not isinstance(outline, dict):
        reasons.append("active outline is not registered")
    else:
        reason = current_ref_reason(root, outline, "outline")
        if reason:
            reasons.append(reason)
    sources = state.get("tracked_sources")
    if not isinstance(sources, list):
        reasons.append("tracked sources are invalid")
    else:
        for source in sources:
            if not isinstance(source, dict):
                reasons.append("invalid tracked source reference")
                continue
            role = source.get("role", "source")
            reason = current_ref_reason(root, source, f"source {role}")
            if reason:
                reasons.append(reason)
    approved = state.get("last_approved_prose")
    if approved is not None:
        if not isinstance(approved, dict):
            reasons.append("last approved prose reference is invalid")
        else:
            reason = current_ref_reason(root, approved, "last approved prose")
            if reason:
                reasons.append(reason)
    return reasons


def validate_generated_meta(root: Path, active: Any, label: str) -> list[str]:
    if not isinstance(active, dict):
        return [f"no active {label}"]
    meta_value = active.get("meta")
    if not isinstance(meta_value, str):
        return [f"active {label} has no metadata"]
    try:
        meta_path = resolve_under(root, meta_value)
        meta = read_json(meta_path)
    except StateError as exc:
        return [str(exc)]
    reasons: list[str] = []
    artifact = meta.get("artifact")
    if not isinstance(artifact, dict):
        reasons.append(f"invalid {label} artifact metadata")
    else:
        reason = current_ref_reason(root, artifact, label)
        if reason:
            reasons.append(reason)
    sources = meta.get("sources")
    if not isinstance(sources, list):
        reasons.append(f"invalid {label} source metadata")
    else:
        for source in sources:
            if not isinstance(source, dict):
                reasons.append(f"invalid {label} source reference")
                continue
            role = source.get("role", "source")
            reason = current_ref_reason(root, source, f"{label} source {role}")
            if reason:
                reasons.append(reason)
    return reasons


def compute_status(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    source_reasons = base_source_reasons(root, state)
    projection_reasons = list(source_reasons)
    projection_reasons.extend(
        validate_generated_meta(root, state.get("active_projection"), "projection")
    )
    projection_stale = bool(projection_reasons)
    packet_reasons: list[str] = []
    if projection_stale:
        packet_reasons.append("projection is stale")
    packet_reasons.extend(
        validate_generated_meta(root, state.get("active_packet"), "packet")
    )
    packet_stale = bool(packet_reasons)
    pending_candidate = state.get("pending_approved_candidate") is not None
    pending_consolidation = bool(state.get("pending_consolidation"))
    return {
        "initialized": True,
        "pending_approved_candidate": pending_candidate,
        "pending_consolidation": pending_consolidation,
        "projection_stale": projection_stale,
        "packet_stale": packet_stale,
        "source_reasons": source_reasons,
        "projection_reasons": projection_reasons,
        "packet_reasons": packet_reasons,
        "ready_to_compile": not source_reasons
        and not pending_candidate
        and not pending_consolidation
        and not projection_stale,
        "ready_to_draft": not pending_candidate
        and not pending_consolidation
        and not projection_stale
        and not packet_stale,
    }


CONTAMINATION_PATTERNS = (
    (re.compile(r"(?im)^\s*#{1,6}\s*(fixed|preferred|offered|inferred)\b"), "authority classification"),
    (re.compile(r"(?i)AUTHOR_DESIGN"), "author-design marker"),
    (re.compile(r"用户已批准|合并说明|完整保留|完整恢复|有意移章"), "revision or source-fidelity history"),
    (re.compile(r"本章阅读收益|本章真正要做的事|章末状态"), "predetermined chapter result"),
    (re.compile(r"(?im)^\s*\|\s*U\d+\s*\|"), "source-fidelity table"),
    (re.compile(r"(?i)current_instruction"), "free-form current instruction"),
    (re.compile(r"(?im)^\s*(LOCK|DIRECTION|OPEN)\s*[:：]"), "planning-authority label"),
    (
        re.compile(
            r"(?im)^\s*(?:#{1,6}\s*)?(?:规划理由|编辑检查|最终心理解释|预定比喻|最后画面|备选方案|"
            r"planning rationale|editorial check|final interpretation|planned metaphor|final image|alternative plan)\s*[:：]?"
        ),
        "backstage planning material",
    ),
    (
        re.compile(
            r"读者(?:应该|应当|必须)(?:感到|意识到|明白)|"
            r"(?i:the reader (?:should|must|needs to) (?:feel|realize|understand|notice))"
        ),
        "predetermined reader response",
    ),
    (
        re.compile(
            r"注意力契约|因果继承|段落(?:入口|出口)|对象变义|结尾(?:公式|结构)|"
            r"(?i:attention contract|causal inheritance|paragraph (?:entry|exit)|ending formula)"
        ),
        "literary-mechanism instruction",
    ),
    (
        re.compile(
            r"(?im)^\s*(?:[-—]\s*)?[“「『\"]\S.{1,}[”」』\"]\s*$|"
            r"^\s*(?:她|他|他们|[A-Z][A-Za-z '-]{1,30})\s*[:：]\s*[“\"]"
        ),
        "explicit dialogue line",
    ),
    (
        re.compile(
            r"(?i:(?:planned dialogue|exact wording|line to use|she says|he says)\s*[:：])|"
            r"(?:预定对白|逐字台词|此处说|让(?:她|他)说)\s*[:：]"
        ),
        "planned dialogue or wording",
    ),
    (
        re.compile(
            r"(?:这|此)(?:个|次|一)?(?:迟疑|沉默|回答|动作|决定|称呼|退出|相遇).{0,24}"
            r"(?:使|让|意味着|说明|证明|获得.{0,8}解释)"
        ),
        "predetermined interpretation",
    ),
    (
        re.compile(
            r"(?:她|他).{0,20}(?:仍然|继续).{0,30}(?:但|却|只是).{0,30}(?:不再|没有|不)"
        ),
        "defensive proof of planned behavior",
    ),
)


def projection_errors(text: str) -> list[str]:
    errors = [label for pattern, label in CONTAMINATION_PATTERNS if pattern.search(text)]
    beat_lines = re.findall(r"(?m)^\s*(?:\d+[.)、]|[-*+]\s+)\s*\S+", text)
    if len(beat_lines) >= 3:
        errors.append("numbered or bulleted beat-sheet form")
    if len(text.strip()) < 80:
        errors.append("projection is too short to establish a narrative field")
    if len(text) > 2200:
        errors.append("generation field exceeds the 如文5.0 ceiling")
    return list(dict.fromkeys(errors))


def init_state(
    root: Path,
    outline_value: str,
    source_values: Iterable[str],
    last_approved_value: str | None,
    rewrite_cutoff: str | None = None,
    snapshot_value: str | None = None,
) -> dict[str, Any]:
    path = state_path(root)
    if path.exists():
        raise StateError(f"如文5.0 project is already initialized: {path}")
    readiness = project_readiness.check(root)
    if not readiness["ready"]:
        raise StateError("项目尚未具备正式写作条件：" + "; ".join(readiness["errors"]))
    outline = resolve_under(root, outline_value)
    for relative in GENERATED_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    rewrite_snapshot = build_rewrite_snapshot(root, rewrite_cutoff, snapshot_value)
    tracked_sources = source_refs(root, source_values)
    require_registered_inputs(root, outline, tracked_sources)
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "active_outline": artifact_ref(root, outline),
        "tracked_sources": tracked_sources,
        "last_approved_prose": None,
        "pending_approved_candidate": None,
        "approval_history": [],
        "consumed_approval_ids": [],
        "rewrite_snapshot": rewrite_snapshot,
        "active_projection": None,
        "active_packet": None,
        "pending_consolidation": False,
        "stale": {"projection": True, "packet": True},
    }
    if last_approved_value:
        approved = resolve_under(root, last_approved_value)
        state["last_approved_prose"] = artifact_ref(root, approved)
    if rewrite_snapshot is not None:
        for source in tracked_sources:
            require_snapshot_source(
                root, state, resolve_under(root, source["path"]), str(source["role"])
            )
        approved_ref = state.get("last_approved_prose")
        if not isinstance(approved_ref, dict):
            raise StateError("rewrite snapshot mode requires last-approved prose")
        require_snapshot_source(
            root, state, resolve_under(root, approved_ref["path"]), "last_approved_prose"
        )
    save_state(root, state)
    return state


def register_projection(
    root: Path, projection_value: str, chapter: str, context_scope: dict[str, Any]
) -> dict[str, Any]:
    state = load_state(root)
    _, registry_errors = resource_registry.validate_registry(root)
    if registry_errors:
        raise StateError("资源治理检查失败：" + "; ".join(registry_errors))
    if state.get("pending_approved_candidate") is not None:
        raise StateError("Cannot register a generation field while promotion is pending")
    if state.get("pending_consolidation"):
        raise StateError("Cannot register a generation field while consolidation is pending")
    reasons = base_source_reasons(root, state)
    if reasons:
        raise StateError("State Reconcile changed sources first: " + "; ".join(reasons))
    projection = resolve_under(root, projection_value)
    trusted_scope = validate_context_scope(context_scope, chapter)
    require_under(
        projection,
        root / "authoring-ruwen-v5/projections",
        "Projection must live under authoring-ruwen-v5/projections",
    )
    text = projection.read_text(encoding="utf-8")
    errors = projection_errors(text)
    if errors:
        raise StateError("Projection contamination: " + "; ".join(errors))
    sources = [{"role": "outline", **state["active_outline"]}]
    sources.extend(dict(item) for item in state["tracked_sources"])
    approved = state.get("last_approved_prose")
    if isinstance(approved, dict):
        sources.append({"role": "last_approved_prose", **approved})
    meta_path = projection.with_name(projection.name + ".meta.json")
    meta = {
        "schema_version": SCHEMA_VERSION,
        "chapter": chapter,
        "context_scope": trusted_scope,
        "generated_at": utc_now(),
        "artifact": artifact_ref(root, projection),
        "sources": sources,
    }
    write_json(meta_path, meta)
    state["active_projection"] = {
        **artifact_ref(root, projection),
        "meta": relative_path(root, meta_path),
        "chapter": chapter,
        "context_scope": trusted_scope,
    }
    state["active_packet"] = None
    state["stale"] = {"projection": False, "packet": True}
    save_state(root, state)
    return meta


SILENT_FLOOR_PATTERNS = (
    re.compile(r"(?im)^\s*#{1,4}\s*(?:来源|约束|完成清单|自检|规划说明|审计)\s*$"),
    re.compile(r"(?:作为(?:AI|模型)|根据(?:以上|大纲|设定)要求|已完成(?:上述|所有)要求)"),
    re.compile(r"(?:本章|本文|本段|这一章).{0,12}(?:逐项|落实|满足|遵循|完成).{0,12}(?:大纲|要求|限制|约束|设定|指令)"),
    re.compile(r"(?:研究|资料|信息|事实).{0,10}(?:来源|出处).{0,10}(?:已|均已)?(?:核对|验证|确认)"),
    re.compile(r"(?:逐项|全部).{0,10}(?:兑现|落实|满足|完成).{0,10}(?:要求|大纲|设定|约束|任务)"),
    re.compile(r"(?:大纲|写作指令|文本约束|研究来源|设定清单|任务要求).{0,18}(?:执行|落实|遵照|依照|完成|核验|核对|满足|兑现|符合)"),
    re.compile(r"(?:执行|落实|遵照|依照|完成|核验|核对|满足|兑现|符合).{0,18}(?:大纲|写作指令|文本约束|研究来源|设定清单|任务要求)"),
    re.compile(r"(?:这段文字|这一节|正文|本章|本文|本段).{0,18}(?:已经|已)?(?:依照|照着|执行|遵循|按照).{0,12}(?:既定规则|前述规范|创作指示|写作规则|写作规范)"),
)


def candidate_prose_errors(text: str) -> list[str]:
    errors = []
    for pattern in SILENT_FLOOR_PATTERNS:
        if pattern.search(text):
            errors.append("候选正文出现治理、来源或履约元语言")
    return list(dict.fromkeys(errors))


def approval_event_path(root: Path, value: str) -> Path:
    path = resolve_under(root, value)
    require_under(path, root / "治理/审批", "批准事件必须位于治理/审批/")
    return path


def record_approved(
    root: Path, prose_value: str, version: str, approval_event_value: str
) -> dict[str, Any]:
    state = load_state(root)
    original_state = copy.deepcopy(state)
    version = version.strip()
    if not version:
        raise StateError("version must be non-empty")
    if state.get("pending_approved_candidate") is not None:
        raise StateError("An approved candidate is already pending promotion")
    if state.get("pending_consolidation"):
        raise StateError("Cannot approve another candidate while consolidation is pending")
    packet = state.get("active_packet")
    reasons = validate_generated_meta(root, packet, "packet")
    status = compute_status(root, state)
    if status["projection_stale"]:
        reasons.append("projection is stale")
    if reasons:
        raise StateError("Current packet is not valid: " + "; ".join(reasons))
    prose = resolve_under(root, prose_value)
    require_under(
        prose,
        root / "authoring-ruwen-v5/candidates",
        "Approved prose must live under authoring-ruwen-v5/candidates",
    )
    prose_errors = candidate_prose_errors(prose.read_text(encoding="utf-8"))
    if prose_errors:
        raise StateError("候选正文未通过silent floor：" + "; ".join(prose_errors))
    event_path = approval_event_path(root, approval_event_value)
    event = read_json(event_path)
    try:
        approval_record.validate_event(
            root, event, action="candidate_approve", target=prose, consume_state=state
        )
    except ValueError as exc:
        raise StateError(f"候选批准事件无效：{exc}") from exc
    reservation = approval_record.reserve_event(
        root, event, consumer="jiyi-weihuyuan"
    )
    if not isinstance(packet, dict):
        raise StateError("No active packet")
    state["pending_approved_candidate"] = {
        **artifact_ref(root, prose),
        "version": version,
        "approved_at": utc_now(),
        "approval_event": artifact_ref(root, event_path),
        "source_packet": {
            "path": packet["path"],
            "sha256": packet["sha256"],
            "meta": packet["meta"],
        },
    }
    state.setdefault("consumed_approval_ids", []).append(event["id"])
    state["active_projection"] = None
    state["active_packet"] = None
    state["stale"] = {"projection": True, "packet": True}
    try:
        save_state(root, state)
        approval_record.commit_reservation(reservation)
    except Exception as exc:
        approval_record.rollback_reservation(reservation)
        save_state(root, original_state)
        raise StateError(f"候选批准提交失败：{exc}") from exc
    return state


def replacement_archive_path(root: Path, target: Path, digest: str) -> Path:
    directory = root / "authoring-ruwen-v5/snapshots/replacements"
    base = f"{target.stem}-{timestamp_token()}-{digest[:12]}{target.suffix}"
    candidate = directory / base
    counter = 1
    while candidate.exists():
        candidate = directory / f"{Path(base).stem}-{counter}{target.suffix}"
        counter += 1
    return candidate


def promote_approved(
    root: Path,
    target_value: str,
    *,
    replace_existing: bool = False,
    expected_target_sha256: str | None = None,
) -> dict[str, Any]:
    state = load_state(root)
    pending = state.get("pending_approved_candidate")
    if not isinstance(pending, dict):
        raise StateError("No approved candidate is pending promotion")
    candidate_reason = current_ref_reason(root, pending, "approved candidate")
    if candidate_reason:
        raise StateError(candidate_reason)
    candidate = resolve_under(root, pending["path"])
    require_under(
        candidate,
        root / "authoring-ruwen-v5/candidates",
        "Approved candidate is outside authoring-ruwen-v5/candidates",
    )
    target = resolve_under(root, target_value, must_exist=False)
    if target.suffix.casefold() != ".md":
        raise StateError("Formal chapter target must be a Markdown file")
    require_under(target, root / "chapters", "Formal chapter target must live under chapters/")
    archive_ref: dict[str, str] | None = None
    replaced_ref: dict[str, str] | None = None
    if target.exists():
        if not target.is_file():
            raise StateError(f"Formal chapter target is not a file: {target}")
        if not replace_existing or not expected_target_sha256:
            raise StateError(
                "Existing target requires --replace-existing and --expected-target-sha256"
            )
        actual = sha256_file(target)
        if actual.casefold() != expected_target_sha256.strip().casefold():
            raise StateError(
                f"Target SHA-256 mismatch: expected {expected_target_sha256}, actual {actual}"
            )
        replaced_ref = artifact_ref(root, target)
        archive = replacement_archive_path(root, target, actual)
        copy_file_atomic(target, archive)
        archive_ref = artifact_ref(root, archive)
    elif replace_existing or expected_target_sha256:
        raise StateError("Replacement flags require an existing formal target")
    copy_file_atomic(candidate, target)
    formal_ref = artifact_ref(root, target)
    history_entry: dict[str, Any] = {
        "event": "approved_prose_promoted",
        "version": pending["version"],
        "approved_at": pending["approved_at"],
        "promoted_at": utc_now(),
        "candidate": {"path": pending["path"], "sha256": pending["sha256"]},
        "formal_target": formal_ref,
        "source_packet": pending["source_packet"],
        "replaced_target": replaced_ref,
        "replacement_archive": archive_ref,
    }
    state["last_approved_prose"] = formal_ref
    state["approval_history"].append(history_entry)
    state["pending_approved_candidate"] = None
    state["pending_consolidation"] = True
    state["active_projection"] = None
    state["active_packet"] = None
    state["stale"] = {"projection": True, "packet": True}
    try:
        save_state(root, state)
    except Exception:
        if archive_ref is not None:
            copy_file_atomic(root / archive_ref["path"], target)
        elif target.exists():
            target.unlink()
        raise
    return state


def reconcile_state(
    root: Path,
    outline_value: str | None,
    source_values: list[str],
    memory_preview_value: str | None,
    memory_approval_event_value: str | None,
    rewrite_cutoff: str | None = None,
    snapshot_value: str | None = None,
    clear_rewrite_snapshot: bool = False,
) -> dict[str, Any]:
    state = load_state(root)
    original_state = copy.deepcopy(state)
    memory_reservation = None
    if state.get("pending_approved_candidate") is not None:
        raise StateError("Promote the approved candidate before State Reconcile")
    outline_path = resolve_under(root, outline_value or state["active_outline"]["path"])
    if clear_rewrite_snapshot and (rewrite_cutoff is not None or snapshot_value is not None):
        raise StateError(
            "clear-rewrite-snapshot cannot be combined with rewrite-cutoff or snapshot-root"
        )
    if clear_rewrite_snapshot:
        state["rewrite_snapshot"] = None
    elif rewrite_cutoff is not None or snapshot_value is not None:
        state["rewrite_snapshot"] = build_rewrite_snapshot(
            root, rewrite_cutoff, snapshot_value
        )
    if source_values:
        refreshed_sources = source_refs(root, source_values)
    else:
        refreshed: list[dict[str, str]] = []
        for item in state.get("tracked_sources", []):
            path = resolve_under(root, item["path"])
            refreshed.append({"role": item["role"], **artifact_ref(root, path)})
        refreshed_sources = refreshed
    require_registered_inputs(root, outline_path, refreshed_sources)
    state["active_outline"] = artifact_ref(root, outline_path)
    state["tracked_sources"] = refreshed_sources
    if state.get("rewrite_snapshot") is not None:
        for source in state["tracked_sources"]:
            require_snapshot_source(
                root, state, resolve_under(root, source["path"]), str(source["role"])
            )
        approved_ref = state.get("last_approved_prose")
        if not isinstance(approved_ref, dict):
            raise StateError("rewrite snapshot mode requires last-approved prose")
        require_snapshot_source(
            root, state, resolve_under(root, approved_ref["path"]), "last_approved_prose"
        )
    if state.get("pending_consolidation"):
        if not memory_preview_value or not memory_approval_event_value:
            raise StateError("记忆合并待处理：需要变更预览和独立用户批准事件")
        preview = resolve_under(root, memory_preview_value)
        require_under(preview, root / "authoring-ruwen-v5/reports", "记忆变更预览必须位于authoring-ruwen-v5/reports/")
        event_path = approval_event_path(root, memory_approval_event_value)
        event = read_json(event_path)
        try:
            approval_record.validate_event(
                root, event, action="memory_commit", target=preview, consume_state=state
            )
        except ValueError as exc:
            raise StateError(f"记忆合并批准事件无效：{exc}") from exc
        memory_reservation = approval_record.reserve_event(
            root, event, consumer="jiyi-weihuyuan"
        )
        state.setdefault("consumed_approval_ids", []).append(event["id"])
        state["approval_history"].append({
            "event": "memory_consolidation_approved",
            "approved_at": event["approved_at"],
            "preview": artifact_ref(root, preview),
            "approval_event": artifact_ref(root, event_path),
        })
        state["pending_consolidation"] = False
    elif memory_preview_value or memory_approval_event_value:
        raise StateError("当前没有待处理的记忆合并")
    state["active_projection"] = None
    state["active_packet"] = None
    state["stale"] = {"projection": True, "packet": True}
    try:
        save_state(root, state)
        if memory_reservation is not None:
            approval_record.commit_reservation(memory_reservation)
    except Exception as exc:
        approval_record.rollback_reservation(memory_reservation)
        save_state(root, original_state)
        raise StateError(f"状态协调提交失败：{exc}") from exc
    return state


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="initialize approved 如文5.0 engineering state")
    init.add_argument("--project-root", required=True)
    init.add_argument("--outline", required=True)
    init.add_argument("--source", action="append", default=[])
    init.add_argument("--last-approved")
    init.add_argument("--rewrite-cutoff")
    init.add_argument("--snapshot-root")
    check = sub.add_parser("check", help="read-only staleness and readiness check")
    check.add_argument("--project-root", required=True)
    register = sub.add_parser(
        "register-projection", help="register a chapter-situation generation field"
    )
    register.add_argument("--project-root", required=True)
    register.add_argument("--projection", required=True)
    register.add_argument("--chapter", required=True)
    register.add_argument("--scope-file", required=True)
    approved = sub.add_parser(
        "record-approved", help="lock an explicitly approved candidate version"
    )
    approved.add_argument("--project-root", required=True)
    approved.add_argument("--prose", required=True)
    approved.add_argument("--version", required=True)
    approved.add_argument("--approval-event", required=True)
    promote = sub.add_parser(
        "promote-approved", help="promote the locked candidate to a formal chapter"
    )
    promote.add_argument("--project-root", required=True)
    promote.add_argument("--target", required=True)
    promote.add_argument("--replace-existing", action="store_true")
    promote.add_argument("--expected-target-sha256")
    migrate = sub.add_parser(
        "migrate-state", help="explicitly check or apply a state schema migration"
    )
    migrate.add_argument("--project-root", required=True)
    mode = migrate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    reconcile = sub.add_parser(
        "reconcile", help="State Reconcile: refresh sources and invalidate artifacts"
    )
    reconcile.add_argument("--project-root", required=True)
    reconcile.add_argument("--outline")
    reconcile.add_argument("--source", action="append", default=[])
    reconcile.add_argument("--memory-preview")
    reconcile.add_argument("--memory-approval-event")
    reconcile.add_argument("--rewrite-cutoff")
    reconcile.add_argument("--snapshot-root")
    reconcile.add_argument("--clear-rewrite-snapshot", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = normalize_project_root(args.project_root)
        if args.command == "init":
            print_json(
                init_state(
                    root,
                    args.outline,
                    args.source,
                    args.last_approved,
                    args.rewrite_cutoff,
                    args.snapshot_root,
                )
            )
        elif args.command == "check":
            print_json(compute_status(root, load_state(root)))
        elif args.command == "register-projection":
            scope_path = resolve_under(root, args.scope_file)
            print_json(register_projection(root, args.projection, args.chapter, read_json(scope_path)))
        elif args.command == "record-approved":
            print_json(record_approved(root, args.prose, args.version, args.approval_event))
        elif args.command == "promote-approved":
            print_json(
                promote_approved(
                    root,
                    args.target,
                    replace_existing=args.replace_existing,
                    expected_target_sha256=args.expected_target_sha256,
                )
            )
        elif args.command == "migrate-state":
            print_json(migrate_state(root, apply=args.apply))
        elif args.command == "reconcile":
            print_json(
                reconcile_state(
                    root,
                    args.outline,
                    args.source,
                    args.memory_preview,
                    args.memory_approval_event,
                    args.rewrite_cutoff,
                    args.snapshot_root,
                    args.clear_rewrite_snapshot,
                )
            )
        return 0
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

