#!/usr/bin/env python3
"""从最小章节情境编译有边界的如文5.0小说作者资料包。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import story_state
import resource_registry


REQUIRED_MANIFEST_KEYS = {
    "projection",
    "project_voice",
    "pov_lens",
    "relationship_lens",
    "expression_resource",
    "approved_prose_tail",
    "context_scope",
    "output",
}
OPTIONAL_MANIFEST_KEYS = {"maximum_context_characters", "user_authored_text"}
TAIL_KEYS = {"path", "chars"}
EXACT_TEXT_KEYS = {"path", "confirmed_verbatim"}
CONTEXT_SCOPE_KEYS = {"project", "volume", "arc", "chapter", "scene_type", "pov"}
FORBIDDEN_ROLE_STEMS = {
    "research",
    "report",
    "reports",
    "diagnostic",
    "diagnostics",
    "notes",
    "untitled",
    "document",
}


class PacketError(ValueError):
    pass


BUNDLE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = BUNDLE_ROOT / "skills" if (BUNDLE_ROOT / "skills").is_dir() else BUNDLE_ROOT
SOUL_PATH = SKILLS_ROOT / "ruwen-zhangjie-xiezuo" / "CREATIVE-SOUL.md"
AUTHOR_CORE_START = "<!-- AUTHOR_CORE_START -->"
AUTHOR_CORE_END = "<!-- AUTHOR_CORE_END -->"


def manifest_keys(value: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_MANIFEST_KEYS - set(value))
    extra = sorted(set(value) - REQUIRED_MANIFEST_KEYS - OPTIONAL_MANIFEST_KEYS)
    if missing:
        raise PacketError(f"manifest is missing fields: {', '.join(missing)}")
    if extra:
        raise PacketError(f"manifest has unsupported fields: {', '.join(extra)}")


def exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    missing = sorted(allowed - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise PacketError(f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        raise PacketError(f"{label} has unsupported fields: {', '.join(extra)}")


def load_author_core() -> str:
    text = SOUL_PATH.read_text(encoding="utf-8")
    if text.count(AUTHOR_CORE_START) != 1 or text.count(AUTHOR_CORE_END) != 1:
        raise PacketError("章节写作创作核心必须且只能包含一组小说作者核心标记")
    core = text.split(AUTHOR_CORE_START, 1)[1].split(AUTHOR_CORE_END, 1)[0].strip()
    if not core:
        raise PacketError("小说作者核心 is empty")
    if len(core) > 420:
        raise PacketError(f"小说作者核心 exceeds the 如文5.0 budget ({len(core)} > 420)")
    return core


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PacketError(f"{label} must be non-empty text")
    return value.strip()


def source_path(root: Path, value: Any, role: str, *, projection: bool = False) -> Path:
    path = story_state.resolve_under(root, require_text(value, f"manifest.{role}"))
    if projection:
        expected = (root / "authoring-ruwen-v5/projections").resolve()
        try:
            path.relative_to(expected)
        except ValueError as exc:
            raise PacketError("Projection source must live under authoring-ruwen-v5/projections") from exc
    return path


def author_voice_relative(root: Path, state: dict[str, Any], path: Path) -> Path:
    snapshot = state.get("rewrite_snapshot")
    if snapshot is None:
        return Path(story_state.relative_path(root, path))
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("root"), str):
        raise PacketError("rewrite snapshot state is invalid")
    snapshot_root = story_state.resolve_directory_under(root, snapshot["root"])
    try:
        return path.resolve().relative_to(snapshot_root)
    except ValueError as exc:
        raise PacketError(f"Author source must live under the registered snapshot: {path}") from exc


def require_author_role_path(
    root: Path, state: dict[str, Any], path: Path, role: str
) -> None:
    relative = author_voice_relative(root, state, path)
    exact = {
        "project_voice": Path("表现/项目声音.md"),
    }
    directories = {
        "pov_lens": Path("人物/POV镜头"),
        "relationship_lens": Path("人物/关系镜头"),
        "expression_resource": Path("表现/能力"),
    }
    if role in exact:
        if relative != exact[role]:
            raise PacketError(
                f"{role} must be exactly {exact[role].as_posix()}"
            )
        return
    expected = directories.get(role)
    if expected is None:
        raise PacketError(f"Unsupported author source role: {role}")
    try:
        child = relative.relative_to(expected)
    except ValueError as exc:
        raise PacketError(
            f"{role} must live under {expected.as_posix()}/"
        ) from exc
    if len(child.parts) != 1 or child.suffix.casefold() != ".md":
        raise PacketError(
            f"{role} must be a direct Markdown child of {expected.as_posix()}/"
        )
    if child.stem.casefold() in FORBIDDEN_ROLE_STEMS:
        raise PacketError(f"{role} uses a non-role source filename: {child.name}")


def require_active_registered_source(
    root: Path, state: dict[str, Any], path: Path, role: str, query: dict[str, str | None]
) -> None:
    try:
        data, errors = resource_registry.validate_registry(root, check_hashes=False)
    except resource_registry.RegistryError as exc:
        raise PacketError(f"资源注册表不可用：{exc}") from exc
    if errors:
        raise PacketError("资源注册表无效：" + "; ".join(errors))
    relative = author_voice_relative(root, state, path).as_posix()
    matches = [item for item in data["resources"] if item.get("path") == relative]
    if len(matches) != 1:
        raise PacketError(f"{role}必须由资源注册表中的唯一资源拥有：{relative}")
    resource = matches[0]
    if resource.get("status") != "active" or resource.get("allow_author") is not True:
        raise PacketError(f"{role}尚未激活或无权进入小说作者资料包：{relative}")
    if resource.get("source_sha256") != story_state.sha256_file(path):
        raise PacketError(f"{role}与资源注册表哈希不一致：{relative}")
    if not resource_registry.scope_matches(resource.get("scope", {}), query):
        raise PacketError(f"{role}不适用于当前章节作用域：{relative}")
    expected_types = {
        "project_voice": "expression",
        "pov_lens": "character",
        "relationship_lens": "character",
        "expression_resource": "expression",
    }
    if resource.get("type") != expected_types[role]:
        raise PacketError(f"{role}的资源类型错误：{resource.get('type')}")


def require_unique_role_sources(role_paths: list[tuple[str, Path]]) -> None:
    seen: dict[Path, str] = {}
    for role, path in role_paths:
        canonical = path.resolve()
        previous = seen.get(canonical)
        if previous is not None:
            raise PacketError(
                f"One file cannot serve multiple packet roles: {previous}, {role}"
            )
        seen[canonical] = role


def exact_text_path(root: Path, value: Any) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PacketError("user_authored_text must be null or an object")
    exact_keys(value, EXACT_TEXT_KEYS, "user_authored_text")
    if value["confirmed_verbatim"] is not True:
        raise PacketError("user_authored_text requires confirmed_verbatim=true")
    path = story_state.resolve_under(
        root, require_text(value["path"], "manifest.user_authored_text.path")
    )
    expected = (root / "authoring-ruwen-v5/exact-text").resolve()
    try:
        path.relative_to(expected)
    except ValueError as exc:
        raise PacketError(
            "user_authored_text must live under authoring-ruwen-v5/exact-text"
        ) from exc
    return path


def add_source(
    root: Path,
    sources: list[dict[str, Any]],
    role: str,
    path: Path,
    selection: dict[str, Any],
) -> None:
    sources.append({"role": role, **story_state.artifact_ref(root, path), "selection": selection})


def compile_packet(root: Path, manifest_path: Path) -> tuple[Path, list[str]]:
    state = story_state.load_state(root)
    status = story_state.compute_status(root, state)
    if status["pending_approved_candidate"]:
        raise PacketError("Approved candidate promotion is pending")
    if status["pending_consolidation"]:
        raise PacketError("Memory consolidation is pending")
    if status["projection_stale"]:
        raise PacketError("Narrative projection is stale: " + "; ".join(status["projection_reasons"]))

    manifest_path = manifest_path.resolve()
    expected_manifest_parent = (root / "authoring-ruwen-v5/manifests").resolve()
    try:
        manifest_path.relative_to(expected_manifest_parent)
    except ValueError as exc:
        raise PacketError("Author manifest must live under authoring-ruwen-v5/manifests") from exc

    manifest = story_state.read_json(manifest_path)
    manifest_keys(manifest)
    context_scope = manifest["context_scope"]
    if not isinstance(context_scope, dict) or set(context_scope) != CONTEXT_SCOPE_KEYS:
        raise PacketError("context_scope必须完整包含project、volume、arc、chapter、scene_type、pov")
    if any(value is not None and not isinstance(value, str) for value in context_scope.values()):
        raise PacketError("context_scope的值必须是文本或null")
    maximum_context = manifest.get("maximum_context_characters", 8000)
    if not isinstance(maximum_context, int) or not 3000 <= maximum_context <= 8000:
        raise PacketError("maximum_context_characters must be an integer between 3000 and 8000")

    projection = source_path(root, manifest["projection"], "projection", projection=True)
    active = state.get("active_projection")
    if not isinstance(active, dict) or active.get("path") != story_state.relative_path(root, projection):
        raise PacketError("Manifest projection is not the registered active projection")
    if active.get("context_scope") != context_scope:
        raise PacketError("manifest context_scope与已注册章节情境的可信作用域不一致")

    core = source_path(root, manifest["project_voice"], "project_voice")
    pov = source_path(root, manifest["pov_lens"], "pov_lens")
    require_author_role_path(root, state, core, "project_voice")
    require_author_role_path(root, state, pov, "pov_lens")
    require_active_registered_source(root, state, core, "project_voice", context_scope)
    require_active_registered_source(root, state, pov, "pov_lens", context_scope)
    story_state.require_snapshot_source(root, state, core, "project_voice")
    story_state.require_snapshot_source(root, state, pov, "pov_lens")
    optional: list[tuple[str, Path]] = []
    for key in ("relationship_lens", "expression_resource"):
        value = manifest[key]
        if value is not None:
            optional_path = source_path(root, value, key)
            require_author_role_path(root, state, optional_path, key)
            require_active_registered_source(root, state, optional_path, key, context_scope)
            story_state.require_snapshot_source(root, state, optional_path, key)
            optional.append((key, optional_path))
    exact_text = exact_text_path(root, manifest.get("user_authored_text"))

    projection_text = projection.read_text(encoding="utf-8").strip()
    contamination = story_state.projection_errors(projection_text)
    if contamination:
        raise PacketError("Projection contamination: " + "; ".join(contamination))
    if len(projection_text) > 2200:
        raise PacketError(
            f"generation field exceeds its 如文5.0 ceiling ({len(projection_text)} > 2200)"
        )

    sections: list[tuple[str, str]] = []
    sources: list[dict[str, Any]] = []
    add_source(root, sources, "author_manifest", manifest_path, {"kind": "full"})
    tail = manifest["approved_prose_tail"]
    if tail is not None:
        if not isinstance(tail, dict):
            raise PacketError("approved_prose_tail must be null or an object")
        exact_keys(tail, TAIL_KEYS, "approved_prose_tail")
        chars = tail["chars"]
        if not isinstance(chars, int) or not 200 <= chars <= 2400:
            raise PacketError("approved_prose_tail.chars must be between 200 and 2400")
        prose = source_path(root, tail["path"], "approved_prose_tail")
        story_state.require_snapshot_source(
            root, state, prose, "approved_prose_tail"
        )
        approved_ref = state.get("last_approved_prose")
        if not isinstance(approved_ref, dict) or approved_ref.get("path") != story_state.relative_path(root, prose):
            raise PacketError("approved_prose_tail must use the state's last approved prose")
        if approved_ref.get("sha256") != story_state.sha256_file(prose):
            raise PacketError("approved_prose_tail hash no longer matches state")
        prose_text = prose.read_text(encoding="utf-8")
        selected = prose_text[-chars:]
        sections.append(("最近批准正文", selected))
        add_source(root, sources, "approved_prose_tail", prose, {"kind": "tail", "chars": chars})

    role_paths = [("projection", projection), ("project_voice", core), ("pov_lens", pov)]
    role_paths.extend(optional)
    if tail is not None:
        role_paths.append(("approved_prose_tail", prose))
    if exact_text is not None:
        role_paths.append(("user_authored_text", exact_text))
    require_unique_role_sources(role_paths)

    sections.append(("当前章节情境", projection_text))
    add_source(root, sources, "projection", projection, {"kind": "full"})

    if exact_text is not None:
        text = exact_text.read_text(encoding="utf-8")
        if not text.strip():
            raise PacketError(f"Empty user_authored_text: {exact_text}")
        if len(text) > 600:
            raise PacketError(
                f"user_authored_text exceeds its 如文5.0 ceiling ({len(text)} > 600)"
            )
        sections.append(("用户要求逐字保留的文本", text.rstrip("\r\n")))
        add_source(root, sources, "user_authored_text", exact_text, {"kind": "full"})

    for role, path, title, hard_max in (
        ("project_voice", core, "项目声音", 1200),
        ("pov_lens", pov, "当前POV镜头", 900),
    ):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise PacketError(f"Empty {role}: {path}")
        if len(text) > hard_max:
            raise PacketError(f"{role} exceeds its 如文5.0 ceiling ({len(text)} > {hard_max})")
        sections.append((title, text))
        add_source(root, sources, role, path, {"kind": "full"})

    for role, path in optional:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise PacketError(f"Empty {role}: {path}")
        if len(text) > 900:
            raise PacketError(f"{role} exceeds its 如文5.0 ceiling ({len(text)} > 900)")
        title = "必要关系镜头" if role == "relationship_lens" else "当前表现能力"
        sections.append((title, text))
        add_source(root, sources, role, path, {"kind": "full"})

    body = [
        "# 如文·小说作者资料包",
        "",
        "# 创作核心",
        "",
        load_author_core(),
        "",
        "只在这个有限处境中写一个被人物实际经历的章节。保留明确事件与锁定顺序，但不要把情境句当作逐项覆盖清单；不要浏览项目记忆。",
        "",
    ]
    for title, text in sections:
        body.extend([f"# {title}", "", text, ""])
    rendered = "\n".join(body).rstrip() + "\n"
    warnings: list[str] = []
    if len(rendered) > maximum_context:
        raise PacketError(
            f"packet exceeds maximum context ({len(rendered)} > {maximum_context}); "
            "remove inactive or duplicated input"
        )

    output = story_state.resolve_under(root, manifest["output"], must_exist=False)
    expected_parent = (root / "authoring-ruwen-v5/packets").resolve()
    try:
        output.relative_to(expected_parent)
    except ValueError as exc:
        raise PacketError("Packet output must live under authoring-ruwen-v5/packets") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    meta_path = output.with_name(output.name + ".meta.json")
    meta = {
        "schema_version": story_state.SCHEMA_VERSION,
        "generated_at": story_state.utc_now(),
        "artifact": story_state.artifact_ref(root, output),
        "manifest": story_state.artifact_ref(root, manifest_path),
        "sources": sources,
        "warnings": warnings,
    }
    story_state.write_json(meta_path, meta)
    state["active_packet"] = {
        **story_state.artifact_ref(root, output),
        "meta": story_state.relative_path(root, meta_path),
    }
    state["stale"] = {"projection": False, "packet": False}
    story_state.save_state(root, state)
    return output, warnings


def check_packet(root: Path, packet_value: str) -> dict[str, Any]:
    packet = story_state.resolve_under(root, packet_value)
    expected_parent = (root / "authoring-ruwen-v5/packets").resolve()
    try:
        packet.relative_to(expected_parent)
    except ValueError:
        return {"valid": False, "reasons": ["packet不在authoring-ruwen-v5/packets目录"]}
    state = story_state.load_state(root)
    active_packet = state.get("active_packet")
    if not isinstance(active_packet, dict) or active_packet.get("path") != story_state.relative_path(root, packet):
        return {"valid": False, "reasons": ["packet不是项目状态登记的active packet"]}
    if active_packet.get("sha256") != story_state.sha256_file(packet):
        return {"valid": False, "reasons": ["active packet哈希不匹配"]}
    meta_path = packet.with_name(packet.name + ".meta.json")
    if not meta_path.is_file():
        return {"valid": False, "reasons": ["packet metadata is missing"]}
    meta = story_state.read_json(meta_path)
    expected_meta_keys = {"schema_version", "generated_at", "artifact", "manifest", "sources", "warnings"}
    reasons: list[str] = []
    if set(meta) != expected_meta_keys:
        reasons.append("packet metadata字段不完整或含额外字段")
    if meta.get("schema_version") != story_state.SCHEMA_VERSION:
        reasons.append("packet metadata schema版本不匹配")
    if active_packet.get("meta") != story_state.relative_path(root, meta_path):
        reasons.append("packet metadata不是active packet登记版本")
    reasons.extend(story_state.validate_generated_meta(root, active_packet, "packet"))
    manifest_ref = meta.get("manifest")
    if not isinstance(manifest_ref, dict):
        reasons.append("packet metadata缺少manifest引用")
    else:
        try:
            manifest_path = story_state.resolve_under(root, manifest_ref.get("path", ""))
            if manifest_ref.get("sha256") != story_state.sha256_file(manifest_path):
                reasons.append("packet manifest哈希不匹配")
        except story_state.StateError as exc:
            reasons.append(str(exc))
    sources = meta.get("sources")
    if not isinstance(sources, list):
        reasons.append("packet sources无效")
    else:
        roles = [item.get("role") for item in sources if isinstance(item, dict)]
        required_roles = {"author_manifest", "projection", "project_voice", "pov_lens"}
        allowed_roles = required_roles | {"relationship_lens", "expression_resource", "approved_prose_tail", "user_authored_text"}
        for item in sources:
            if not isinstance(item, dict) or set(item) != {"role", "path", "sha256", "selection"}:
                reasons.append("packet来源引用字段无效")
                continue
            if not isinstance(item.get("selection"), dict):
                reasons.append("packet来源选择说明无效")
        if not required_roles.issubset(set(roles)):
            reasons.append("packet缺少必需来源角色")
        if len(roles) != len(set(roles)) or any(role not in allowed_roles for role in roles):
            reasons.append("packet来源角色重复或越权")
    status = story_state.compute_status(root, state)
    if status["projection_stale"]:
        reasons.append("projection is stale")
    if status["pending_consolidation"]:
        reasons.append("memory consolidation is pending")
    if status["pending_approved_candidate"]:
        reasons.append("approved candidate promotion is pending")
    return {"valid": not reasons, "reasons": reasons}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--project-root", required=True)
    compile_cmd.add_argument("--manifest", required=True)
    check_cmd = sub.add_parser("check")
    check_cmd.add_argument("--project-root", required=True)
    check_cmd.add_argument("--packet", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = story_state.normalize_project_root(args.project_root)
        if args.command == "compile":
            manifest = story_state.resolve_under(root, args.manifest)
            output, warnings = compile_packet(root, manifest)
            print(json.dumps({"status": "compiled", "output": str(output), "warnings": warnings}, ensure_ascii=False, indent=2))
        else:
            result = check_packet(root, args.packet)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["valid"] else 1
        return 0
    except (PacketError, story_state.StateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

