#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import closure_audit
import compile_author_packet
import governance_check
import handoff_validator
import approval_record
import problem_ledger
import project_readiness
import resource_registry
import story_state


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuwenV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        shutil.copytree(PLUGIN_ROOT / "assets/project-template", self.root)
        registry_path = self.root / "治理/资源注册表.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for item in registry["resources"]:
            item["scope"]["project"] = "test-project"
            item["source_sha256"] = digest(self.root / item["path"])
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = self.root / "authoring-ruwen-v5/manifests/author-manifest.json"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("__PROJECT_ID__", "test-project"), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def scope(self, chapter: str = "001") -> dict[str, str | None]:
        return {"project": "test-project", "volume": "v1", "arc": "arc-1", "chapter": chapter, "scene_type": "travel", "pov": "主角"}

    def make_approval(self, target: Path, action: str, event_id: str) -> str:
        directory = self.root / "治理/审批"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{event_id}.json"
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "id": event_id,
            "action": action,
            "target_path": target.relative_to(self.root).as_posix(),
            "target_sha256": digest(target),
            "approved_at": "2026-08-28T00:00:00Z",
            "approved_by": "user",
            "consumed": False,
        }, ensure_ascii=False), encoding="utf-8")
        return path.relative_to(self.root).as_posix()

    def update_resource(self, rid: str, text: str, *, active: bool = True) -> None:
        path = self.root / "治理/资源注册表.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        item = next(value for value in data["resources"] if value["id"] == rid)
        resource_path = self.root / item["path"]
        resource_path.write_text(text, encoding="utf-8")
        item["source_sha256"] = digest(resource_path)
        if active:
            item["status"] = "active"
            item["approval"] = {"status": "approved", "approved_at": "2026-08-28T00:00:00Z", "approved_by": "user"}
            approval_dir = self.root / "治理/审批"
            approval_dir.mkdir(parents=True, exist_ok=True)
            sequence = 1 + sum(
                1
                for entry in approval_record.usage_entries(self.root)
                if str(entry.get("event_id", "")).startswith(f"{rid}-activate-")
            )
            event_id = f"{rid}-activate-{sequence}"
            approval_event = approval_dir / f"{event_id}.json"
            action = "expression_activate" if item["type"] == "expression" else "resource_activate"
            approval_event.write_text(json.dumps({
                "schema_version": "1.0",
                "id": event_id,
                "action": action,
                "target_path": item["path"],
                "target_sha256": item["source_sha256"],
                "approved_at": "2026-08-28T00:00:00Z",
                "approved_by": "user",
                "consumed": False,
            }, ensure_ascii=False), encoding="utf-8")
            approval_record.consume_event(
                self.root,
                json.loads(approval_event.read_text(encoding="utf-8")),
                consumer="xiangmu-zhiliyuan",
            )
            item["approval"].update({
                "approval_event_path": approval_event.relative_to(self.root).as_posix(),
                "approval_event_sha256": digest(approval_event),
            })
            if item["type"] == "expression":
                evidence_dir = self.root / "治理/激活证据"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                audit_path = evidence_dir / f"{rid}-closure.json"
                trial_path = evidence_dir / f"{rid}-trial.json"
                trial_output = evidence_dir / f"{rid}-trial.md"
                trial_output.write_text("非正典隔离试写。", encoding="utf-8")
                manual = {
                    "resource_id": rid,
                    "resource_path": str(resource_path),
                    "resource_version": item["version"],
                    "resource_sha256": item["source_sha256"],
                    "reviewed_by": "user",
                    "checks": {key: "pass" for key in closure_audit.CHECK_NAMES},
                }
                audit_value = closure_audit.audit(resource_path, resource_id=rid, resource_version=item["version"], manual_review=manual)
                audit_path.write_text(json.dumps(audit_value, ensure_ascii=False, indent=2), encoding="utf-8")
                trial_path.write_text(json.dumps({
                    "resource_id": rid,
                    "resource_path": item["path"],
                    "resource_version": item["version"],
                    "resource_sha256": item["source_sha256"],
                    "output_path": trial_output.relative_to(self.root).as_posix(),
                    "output_sha256": digest(trial_output),
                    "user_accepted": True,
                    "canonical": False,
                }, ensure_ascii=False), encoding="utf-8")
                item["approval"].update({
                    "closure_audit_path": audit_path.relative_to(self.root).as_posix(),
                    "closure_audit_sha256": digest(audit_path),
                    "trial_report_path": trial_path.relative_to(self.root).as_posix(),
                    "trial_report_sha256": digest(trial_path),
                    "approval_event_path": approval_event.relative_to(self.root).as_posix(),
                    "approval_event_sha256": digest(approval_event),
                })
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def make_ready(self) -> None:
        self.update_resource("xiangmu-zhangcheng", "# 项目章程\n\n## 项目身份\n长篇历史幻想。\n\n## 创作来源权\n重大人物决定归用户。\n\n## 当前开放问题\n远期秩序尚未决定。\n\n## 批准状态\n已批准。\n")
        self.update_resource("zhujue-dangan", "# 主角档案\n\n## 客观存在模型\n青年行旅者，左腿旧伤改变步幅；身份使他能进驿站却不能调兵。他靠抄写换取食宿，并负有偿还旧债的义务。\n\n## 内在组织模型\n他先注意别人对秩序的微小违背，想获得容身之处又害怕被看穿来历；会把迟疑解释成谨慎，记忆在闻到湿纸时改变判断。\n\n## 叙述接口模型\n视野贴近手、步幅和声音来源；不能直接知道他人动机，受疲劳时会误认远处低语，句子在确认来源前保持短促而不下结论。\n\n## 开放未知\n低语是否全由疲劳造成仍未确定。\n")
        self.update_resource("zhujue-pov-jingtou", "注意先落在声音来源、人的手与自己的步幅。疲劳会使远处低语靠近，但他知道自己的判断可能失真，因此叙述允许感知先存在，解释稍后形成。他看不见他人的内心，只能从停顿、目光与行动后果推断。")
        self.update_resource("shijie-zongbiao", "# 世界总表\n\n## 时代与空间\n河谷诸城以驿道相连，冬季水路停航，消息按脚程延迟。\n\n## 物质与技术边界\n纸、铁器和畜力构成日常技术边界，没有远距即时通信。\n\n## 系统索引\n核心系统解释驿道、税契、身份凭证与地方武力的关系。\n")
        self.update_resource("shijie-dangqian-taishi", "# 当前态势\n\n## 活跃力量与各自运动\n两城争夺冬季粮道。\n\n## 可调用资源与现实限制\n驿马短缺，河面将封。\n\n## 相互认识、误读与无人介入时的下一步\n双方都高估对方存粮；无人介入时驿站会先限制平民换马。\n")
        self.update_resource("shijie-hexin-xitong", "# 核心世界系统\n\n## 参与者与受影响者\n驿吏、行旅、商队和地方军。\n\n## 资源流、规则、成本与限制\n凭证换马，粮秣和脚程限制流动。\n\n## 权力或知识不对称\n驿吏知道马匹状况，旅客只见是否放行。\n\n## 日常接触与不同身份的经验\n军使优先，商队付费，平民等待。\n\n## 自身运动、当前压力、误解与开放未知\n冬季短缺会自行加剧，哪座城先封路未知。\n")
        self.update_resource("gushi-dangqian-hu", "# 当前故事弧\n\n## 作用域\n第一卷、试验弧、第一至三章。\n\n## 具体故事\n主角在驿站等待换马时发现粮车改变方向；他必须决定是否继续送信。\n")
        self.update_resource("biaoxian-xiangmu-shengyin", "叙述贴近人物当下可感知的物质与社会时间。判断允许在证据之后形成，也允许人物暂时误认。外界活动不因主角停顿而停止；细节只有在改变注意、动作或关系时获得篇幅。")
        self.update_resource("xiaoyan-yingsheding", "# 硬设定校验\n\n驿道无即时通信；主角无调兵权限；人物只能知道有来源的信息。\n")

    def test_project_blocks_incomplete_protagonist(self) -> None:
        result = project_readiness.check(self.root)
        self.assertFalse(result["ready"])
        self.assertTrue(any("主角档案未完成" in value for value in result["errors"]))

    def test_ready_project_and_scope_selection(self) -> None:
        self.make_ready()
        result = project_readiness.check(self.root)
        self.assertTrue(result["ready"], result["errors"])
        chosen = resource_registry.select(self.root, {"project": "test-project", "volume": None, "arc": None, "chapter": None, "scene_type": None, "pov": "主角"}, author_only=True)
        paths = {item["path"] for item in chosen}
        self.assertIn("表现/项目声音.md", paths)
        self.assertIn("人物/POV镜头/主角.md", paths)
        self.assertNotIn("人物/主角档案.md", paths)

    def test_closure_audit_rejects_examples_and_mapping(self) -> None:
        path = self.root / "表现/能力/危险.md"
        path.write_text("政治就是对白。例如让官员先问账目，然后展示绳结，最后沉默。", encoding="utf-8")
        result = closure_audit.audit(path)
        self.assertFalse(result["pass"])
        categories = {item["category"] for item in result["findings"]}
        self.assertIn("closed_mapping", categories)
        self.assertIn("example_anchor", categories)

    def test_closure_audit_rejects_sample_derived_emotion_ban(self) -> None:
        path = self.root / "表现/能力/情绪禁令.md"
        path.write_text("情绪不应直接命名，只能通过动作表现。", encoding="utf-8")
        result = closure_audit.audit(path)
        self.assertFalse(result["pass"])
        self.assertIn("closed_mapping", {item["category"] for item in result["findings"]})

    def test_author_packet_uses_only_active_bounded_sources(self) -> None:
        self.make_ready()
        story_state.init_state(
            self.root,
            "故事/当前故事弧.md",
            ["character=人物/主角档案.md", "world=世界/世界总表.md", "situation=世界/当前态势.md"],
            None,
        )
        projection = self.root / "authoring-ruwen-v5/projections/current.md"
        projection.write_text("冬日下午，主角在河谷驿站等一匹尚未卸鞍的马，旧伤使他不愿久站。院中粮车正被驿吏改挂另一座城的木牌，车夫催促装最后一袋。主角要把封信送过封冻前的山口，却不知道改道是否意味着前路已经封锁。他必须在驿吏放出下一匹马前决定是否继续；粮车会先离开。", encoding="utf-8")
        story_state.register_projection(self.root, "authoring-ruwen-v5/projections/current.md", "001", self.scope())
        manifest_path = self.root / "authoring-ruwen-v5/manifests/author-manifest.json"
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_value["context_scope"] = self.scope()
        manifest_path.write_text(json.dumps(manifest_value, ensure_ascii=False, indent=2), encoding="utf-8")
        output, _ = compile_author_packet.compile_packet(self.root, manifest_path)
        text = output.read_text(encoding="utf-8")
        self.assertIn("# 当前章节情境", text)
        self.assertNotIn("# 主角档案", text)
        self.assertNotIn("研究/", text)
        self.assertLessEqual(len(text), 8000)

    def prepare_packet(self) -> Path:
        self.make_ready()
        story_state.init_state(
            self.root,
            "故事/当前故事弧.md",
            ["character=人物/主角档案.md", "world=世界/世界总表.md", "situation=世界/当前态势.md"],
            None,
        )
        projection = self.root / "authoring-ruwen-v5/projections/current.md"
        projection.write_text("冬日下午，主角在河谷驿站等一匹尚未卸鞍的马，旧伤使他不愿久站。院中粮车正被驿吏改挂另一座城的木牌，车夫催促装最后一袋。主角要把封信送过封冻前的山口，却不知道改道是否意味着前路已经封锁。他必须在驿吏放出下一匹马前决定是否继续；粮车会先离开。", encoding="utf-8")
        story_state.register_projection(self.root, "authoring-ruwen-v5/projections/current.md", "001", self.scope())
        manifest_path = self.root / "authoring-ruwen-v5/manifests/author-manifest.json"
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_value["context_scope"] = self.scope()
        manifest_path.write_text(json.dumps(manifest_value, ensure_ascii=False, indent=2), encoding="utf-8")
        output, _ = compile_author_packet.compile_packet(self.root, manifest_path)
        return output

    def test_approval_promotion_and_memory_gate(self) -> None:
        self.prepare_packet()
        candidate = self.root / "authoring-ruwen-v5/candidates/chapter-001.md"
        candidate.write_text("驿站中的非正典章节候选。", encoding="utf-8")
        approval = self.make_approval(candidate, "candidate_approve", "candidate-001")
        state = story_state.record_approved(self.root, "authoring-ruwen-v5/candidates/chapter-001.md", "candidate-1", approval)
        self.assertIsNotNone(state["pending_approved_candidate"])
        target = self.root / "chapters/chapter-001.md"
        state = story_state.promote_approved(self.root, "chapters/chapter-001.md")
        self.assertTrue(target.is_file())
        self.assertTrue(state["pending_consolidation"])
        with self.assertRaises(story_state.StateError):
            story_state.register_projection(self.root, "authoring-ruwen-v5/projections/current.md", "002", self.scope("002"))
        preview = self.root / "authoring-ruwen-v5/reports/memory-001.json"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(json.dumps({"changes": []}), encoding="utf-8")
        memory_approval = self.make_approval(preview, "memory_commit", "memory-001")
        state = story_state.reconcile_state(self.root, None, [], "authoring-ruwen-v5/reports/memory-001.json", memory_approval)
        self.assertFalse(state["pending_consolidation"])

    def test_existing_chapter_replacement_requires_hash_and_archive(self) -> None:
        self.prepare_packet()
        target = self.root / "chapters/chapter-001.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("旧正文", encoding="utf-8")
        candidate = self.root / "authoring-ruwen-v5/candidates/chapter-001.md"
        candidate.write_text("新正文", encoding="utf-8")
        approval = self.make_approval(candidate, "candidate_approve", "candidate-replacement-001")
        story_state.record_approved(self.root, "authoring-ruwen-v5/candidates/chapter-001.md", "replacement-1", approval)
        with self.assertRaises(story_state.StateError):
            story_state.promote_approved(self.root, "chapters/chapter-001.md")
        old_hash = digest(target)
        state = story_state.promote_approved(self.root, "chapters/chapter-001.md", replace_existing=True, expected_target_sha256=old_hash)
        archive = state["approval_history"][-1]["replacement_archive"]
        self.assertIsNotNone(archive)
        self.assertEqual((self.root / archive["path"]).read_text(encoding="utf-8"), "旧正文")

    def test_generation_field_contamination_is_rejected(self) -> None:
        text = "1. 先写人物回家\n2. 再让人物解释意义\n3. 最后总结主题"
        errors = story_state.projection_errors(text)
        self.assertIn("numbered or bulleted beat-sheet form", errors)

    def test_migration_preview_is_read_only(self) -> None:
        from migrate_v4_1_preview import classify
        source = self.root / "legacy"
        source.mkdir()
        path = source / "author-voice/project-core.md"
        path.parent.mkdir(parents=True)
        path.write_text("旧项目声音", encoding="utf-8")
        before = digest(path)
        result = classify("author-voice/project-core.md")
        self.assertEqual(result["type"], "expression")
        self.assertEqual(digest(path), before)

    def test_retired_author_resource_is_rejected(self) -> None:
        self.make_ready()
        registry_path = self.root / "治理/资源注册表.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        item = next(x for x in data["resources"] if x["id"] == "zhujue-pov-jingtou")
        item["status"] = "retired"
        registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        chosen = resource_registry.select(self.root, {"project": "test-project", "volume": None, "arc": None, "chapter": None, "scene_type": None, "pov": "主角"}, author_only=True)
        self.assertNotIn("人物/POV镜头/主角.md", {x["path"] for x in chosen})

    def test_problem_ledger_requires_cross_task_recurrence(self) -> None:
        ledger = self.root / "治理/文学问题账本.jsonl"
        base = {"location": "候选段落", "category": "解释重复动作", "condition": "关系场景", "handling": "删除", "result": "待用户评估", "status": "open"}
        one = problem_ledger.append(ledger, {**base, "task_id": "t1"})
        two = problem_ledger.append(ledger, {**base, "task_id": "t1"})
        three = problem_ledger.append(ledger, {**base, "task_id": "t2"})
        self.assertFalse(one["recurrence_candidate"])
        self.assertFalse(two["recurrence_candidate"])
        self.assertTrue(three["recurrence_candidate"])

    def test_governance_detects_manifest_leak(self) -> None:
        self.make_ready()
        manifest = self.root / "authoring-ruwen-v5/manifests/author-manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["project_voice"] = "研究/README.md"
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        result = governance_check.check(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("越权" in value for value in result["errors"]))

    def test_handoff_rejects_raw_and_translated_input_together(self) -> None:
        value = {
            "kind": "creative_brief",
            "sender": "chuangyi-xietiaoyuan",
            "recipient": "gushi-gousishi",
            "resource_ids": [],
            "scope": {"project": "test-project"},
            "approval_ref": None,
            "payload": {"fixed": [], "creative_value": "关系压力", "raw_user_input": "原始请求"},
        }
        errors = handoff_validator.validate(value)
        self.assertTrue(any("禁止字段" in item for item in errors))

    def test_consultant_cannot_run_before_learning_plan_approval(self) -> None:
        value = {
            "kind": "consultant_brief",
            "sender": "chuangyi-xietiaoyuan",
            "recipient": "waibu-zhishi-guwen",
            "resource_ids": ["shijie-zongbiao"],
            "scope": {"project": "test-project"},
            "approval_ref": None,
            "payload": {"known": "河谷驿道", "unknown": "冬季运输", "learning_goal": "补足运行关系", "boundary": "只调查制度与物质条件", "allowed_sources": ["权威资料"], "destination": "研究/"},
        }
        errors = handoff_validator.validate(value, for_execution=True, project_root=self.root)
        self.assertTrue(any("独立批准事件" in item for item in errors))

    def test_arc_scoped_expression_retires_cleanly(self) -> None:
        self.make_ready()
        ability = self.root / "表现/能力/弧线战斗.md"
        ability.write_text("身体负荷、地形和即时判断共同改变动作可行性；叙述距离随人物可确认的信息变化。", encoding="utf-8")
        registry_path = self.root / "治理/资源注册表.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        arc_audit = self.root / "治理/激活证据/arc-one-combat-closure.json"
        arc_trial = self.root / "治理/激活证据/arc-one-combat-trial.json"
        arc_output = self.root / "治理/激活证据/arc-one-combat-trial.md"
        arc_approval = self.root / "治理/审批/arc-one-combat-activate.json"
        arc_output.write_text("非正典战斗试写。", encoding="utf-8")
        arc_manual = {
            "resource_id": "arc-one-combat",
            "resource_path": str(ability),
            "resource_version": "1.0.0",
            "resource_sha256": digest(ability),
            "reviewed_by": "user",
            "checks": {key: "pass" for key in closure_audit.CHECK_NAMES},
        }
        arc_audit.write_text(json.dumps(closure_audit.audit(ability, resource_id="arc-one-combat", resource_version="1.0.0", manual_review=arc_manual), ensure_ascii=False), encoding="utf-8")
        arc_trial.write_text(json.dumps({
            "resource_id": "arc-one-combat",
            "resource_path": "表现/能力/弧线战斗.md",
            "resource_version": "1.0.0",
            "resource_sha256": digest(ability),
            "output_path": arc_output.relative_to(self.root).as_posix(),
            "output_sha256": digest(arc_output),
            "user_accepted": True,
            "canonical": False,
        }, ensure_ascii=False), encoding="utf-8")
        arc_approval.write_text(json.dumps({
            "schema_version": "1.0",
            "id": "arc-one-combat-activate",
            "action": "expression_activate",
            "target_path": "表现/能力/弧线战斗.md",
            "target_sha256": digest(ability),
            "approved_at": "2026-08-28T00:00:00Z",
            "approved_by": "user",
            "consumed": False,
        }, ensure_ascii=False), encoding="utf-8")
        approval_record.consume_event(
            self.root,
            json.loads(arc_approval.read_text(encoding="utf-8")),
            consumer="xiangmu-zhiliyuan",
        )
        data["resources"].append({
            "id": "arc-one-combat",
            "path": "表现/能力/弧线战斗.md",
            "type": "expression",
            "owner": "biaoxian-shejishi",
            "version": "1.0.0",
            "status": "active",
            "supersedes": None,
            "scope": {"project": "test-project", "volumes": None, "arcs": ["arc-1"], "chapters": None, "scene_types": ["combat"], "povs": None},
            "readers": ["xiaoshuo-zuozhe"],
            "allow_author": True,
            "source_sha256": digest(ability),
            "approval": {
                "status": "approved",
                "approved_at": "2026-08-28T00:00:00Z",
                "approved_by": "user",
                "closure_audit_path": arc_audit.relative_to(self.root).as_posix(),
                "closure_audit_sha256": digest(arc_audit),
                "trial_report_path": arc_trial.relative_to(self.root).as_posix(),
                "trial_report_sha256": digest(arc_trial)
                ,"approval_event_path": arc_approval.relative_to(self.root).as_posix()
                ,"approval_event_sha256": digest(arc_approval)
            },
        })
        registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        query = {"project": "test-project", "volume": None, "arc": "arc-1", "chapter": None, "scene_type": "combat", "pov": "主角"}
        self.assertIn("arc-one-combat", {x["id"] for x in resource_registry.select(self.root, query, author_only=True)})
        data["resources"][-1]["status"] = "retired"
        registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.assertNotIn("arc-one-combat", {x["id"] for x in resource_registry.select(self.root, query, author_only=True)})

    def test_author_core_budget_and_no_old_role_names(self) -> None:
        core = compile_author_packet.load_author_core()
        self.assertLessEqual(len(core), 420)
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for skill in ("ruwen-gushi-gousi", "ruwen-zhangjie-xiezuo")
            for path in (PLUGIN_ROOT / "skills" / skill).rglob("*.md")
        )
        for token in ("Story Steward", "Novelist", "Literary Editor", "Reality Keeper", "Creative Liaison"):
            self.assertNotIn(token, production)

    def test_manifest_cannot_self_declare_a_different_scope(self) -> None:
        self.prepare_packet()
        manifest = self.root / "authoring-ruwen-v5/manifests/author-manifest.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["context_scope"]["chapter"] = "002"
        manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.assertRaises(compile_author_packet.PacketError):
            compile_author_packet.compile_packet(self.root, manifest)

    def test_rogue_packet_and_tampered_meta_are_rejected(self) -> None:
        packet = self.prepare_packet()
        rogue = packet.parent / "rogue.md"
        rogue.write_text("伪造资料包", encoding="utf-8")
        self.assertFalse(compile_author_packet.check_packet(self.root, rogue.relative_to(self.root).as_posix())["valid"])
        meta = packet.with_name(packet.name + ".meta.json")
        value = json.loads(meta.read_text(encoding="utf-8"))
        value["schema_version"] = "forged"
        meta.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        result = compile_author_packet.check_packet(self.root, packet.relative_to(self.root).as_posix())
        self.assertFalse(result["valid"])
        self.assertTrue(any("schema" in reason for reason in result["reasons"]))

    def test_silent_floor_and_protected_promotion_target(self) -> None:
        self.prepare_packet()
        candidate = self.root / "authoring-ruwen-v5/candidates/chapter-001.md"
        candidate.write_text("根据以上要求，已完成所有要求。", encoding="utf-8")
        approval = self.make_approval(candidate, "candidate_approve", "silent-floor-001")
        with self.assertRaises(story_state.StateError):
            story_state.record_approved(self.root, candidate.relative_to(self.root).as_posix(), "candidate-1", approval)
        candidate.write_text("驿吏把木牌翻到背面，粮车仍在装袋。", encoding="utf-8")
        approval = self.make_approval(candidate, "candidate_approve", "protected-target-001")
        story_state.record_approved(self.root, candidate.relative_to(self.root).as_posix(), "candidate-2", approval)
        with self.assertRaises(story_state.StateError):
            story_state.promote_approved(self.root, "世界/世界总表.md", replace_existing=True, expected_target_sha256=digest(self.root / "世界/世界总表.md"))

    def test_candidate_approval_event_cannot_be_reused(self) -> None:
        self.prepare_packet()
        candidate = self.root / "authoring-ruwen-v5/candidates/chapter-001.md"
        candidate.write_text("粮车先出了驿门。", encoding="utf-8")
        approval_ref = self.make_approval(candidate, "candidate_approve", "single-use-001")
        state = story_state.record_approved(self.root, candidate.relative_to(self.root).as_posix(), "candidate-1", approval_ref)
        event = json.loads((self.root / approval_ref).read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            approval_record.validate_event(self.root, event, action="candidate_approve", target=candidate, consume_state=state)

    def test_reconcile_rejects_research_as_story_source(self) -> None:
        self.prepare_packet()
        with self.assertRaises(story_state.StateError):
            story_state.reconcile_state(self.root, None, ["research=研究/README.md"], None, None)

    def test_reconcile_without_pending_memory_is_valid(self) -> None:
        self.prepare_packet()
        state = story_state.reconcile_state(self.root, None, [], None, None)
        self.assertFalse(state["pending_consolidation"])
        self.assertTrue(state["stale"]["projection"])

    def test_placeholder_content_cannot_make_project_ready(self) -> None:
        self.make_ready()
        self.update_resource("zhujue-dangan", "# 主角档案\n\n待用户确认。\n")
        result = project_readiness.check(self.root)
        self.assertFalse(result["ready"])
        self.assertTrue(any("占位" in error or "未完成" in error for error in result["errors"]))

    def test_active_expression_cannot_refresh_without_new_evidence(self) -> None:
        self.make_ready()
        with self.assertRaises(resource_registry.RegistryError):
            resource_registry.refresh_hash(self.root, "biaoxian-xiangmu-shengyin", approved=True)

    def test_expression_evidence_cannot_be_reused_for_another_resource(self) -> None:
        self.make_ready()
        registry_path = self.root / "治理/资源注册表.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        source = next(item for item in data["resources"] if item["id"] == "biaoxian-xiangmu-shengyin")
        second_path = self.root / "表现/能力/复用证据.md"
        second_path.write_text("人物的感知和社会处境共同影响叙述距离。", encoding="utf-8")
        data["resources"].append({
            "id": "reused-evidence",
            "path": "表现/能力/复用证据.md",
            "type": "expression",
            "owner": "biaoxian-shejishi",
            "version": "1.0.0",
            "status": "candidate",
            "supersedes": None,
            "scope": {"project": "test-project", "volumes": None, "arcs": None, "chapters": None, "scene_types": ["combat"], "povs": None},
            "readers": ["xiaoshuo-zuozhe"],
            "allow_author": True,
            "source_sha256": digest(second_path),
            "approval": {
                "status": "unapproved",
                "approved_at": None,
                "approved_by": None,
                "closure_audit_path": source["approval"]["closure_audit_path"],
                "closure_audit_sha256": source["approval"]["closure_audit_sha256"],
            },
        })
        registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _, errors = resource_registry.validate_registry(self.root)
        self.assertTrue(any("未绑定" in error for error in errors))

    def test_generic_nested_input_key_is_rejected_from_handoff(self) -> None:
        value = {
            "kind": "creative_brief",
            "sender": "chuangyi-xietiaoyuan",
            "recipient": "gushi-gousishi",
            "resource_ids": [],
            "scope": {"project": "test-project"},
            "approval_ref": None,
            "payload": {
                "fixed": [],
                "creative_value": {"content": "用户原始整段要求"},
                "unresolved_forces": [],
                "open_realization": [],
                "destination": "故事/当前故事弧.md",
                "excluded_source": [],
            },
        }
        self.assertTrue(any("禁止字段" in error for error in handoff_validator.validate(value)))

    def test_handoff_values_are_typed_and_raw_wording_is_checked_in_memory(self) -> None:
        value = {
            "kind": "creative_brief",
            "sender": "chuangyi-xietiaoyuan",
            "recipient": "gushi-gousishi",
            "resource_ids": [],
            "scope": {"project": "test-project"},
            "approval_ref": None,
            "payload": {
                "fixed": [],
                "creative_value": "让何绫更悲伤，比如她躲开饶景行的眼神，把这个写进人物卡。",
                "unresolved_forces": ["她仍想知道答案，也怕答案真正到来"],
                "open_realization": ["动作与措辞"],
                "destination": "人物/主角档案.md",
                "excluded_source": ["example", "raw_user_wording"],
            },
        }
        raw = "让何绫更悲伤，比如她躲开饶景行的眼神，把这个写进人物卡。"
        errors = handoff_validator.validate(value, raw_source=raw)
        self.assertTrue(any("长片段重合" in error for error in errors))
        value["payload"]["creative_value"] = {"verbatim_user_request": raw}
        errors = handoff_validator.validate(value, raw_source=raw)
        self.assertTrue(any("必须是有界文本" in error for error in errors))
        value["payload"]["creative_value"] = "保留关系压力"
        value["payload"]["fixed"] = [raw]
        errors = handoff_validator.validate(value, raw_source=raw)
        self.assertTrue(any("长片段重合" in error for error in errors))

    def test_handoff_approval_is_consumed_once(self) -> None:
        payload = {
            "known": "驿道冬季运作",
            "unknown": "换马的现实边界",
            "learning_goal": "补足物质条件",
            "boundary": "只调查交通制度",
            "allowed_sources": ["权威史料"],
            "destination": "研究/交通制度.md",
        }
        snapshot = self.root / "治理/交接/consultant-001.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        event_ref = self.make_approval(snapshot, "handoff_execute", "handoff-001")
        event_path = self.root / event_ref
        value = {
            "kind": "consultant_brief",
            "sender": "chuangyi-xietiaoyuan",
            "recipient": "waibu-zhishi-guwen",
            "resource_ids": ["shijie-zongbiao"],
            "scope": {"project": "test-project"},
            "approval_ref": {"path": event_ref, "sha256": digest(event_path)},
            "payload": payload,
        }
        self.assertFalse(handoff_validator.validate(value, for_execution=True, project_root=self.root))
        handoff_validator.consume_execution_approval(value, self.root)
        self.assertTrue(handoff_validator.validate(value, for_execution=True, project_root=self.root))

    def test_approval_event_validation_rejects_empty_identity_and_time(self) -> None:
        target = self.root / "治理/交接/target.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        event = {
            "schema_version": "1.0",
            "id": "",
            "action": "handoff_execute",
            "target_path": target.relative_to(self.root).as_posix(),
            "target_sha256": digest(target),
            "approved_at": None,
            "approved_by": "user",
            "consumed": False,
        }
        with self.assertRaises(ValueError):
            approval_record.validate_event(self.root, event, action="handoff_execute", target=target)

    def test_approval_consumption_is_atomic_across_processes(self) -> None:
        target = self.root / "治理/交接/concurrent.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        event_ref = self.make_approval(target, "handoff_execute", "concurrent-approval")
        event_path = self.root / event_ref
        script_dir = PLUGIN_ROOT / "scripts"
        code = (
            "import json,sys; from pathlib import Path; import approval_record; "
            "r=Path(sys.argv[1]); e=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')); "
            "approval_record.consume_event(r,e,consumer='gushi-gousishi')"
        )
        environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(script_dir)}
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", code, str(self.root), str(event_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            for _ in range(12)
        ]
        results = [process.communicate() + (process.returncode,) for process in processes]
        self.assertEqual(sum(1 for _, _, code_value in results if code_value == 0), 1)
        markers = list((self.root / approval_record.USAGE_RELATIVE).glob("concurrent-approval.json"))
        self.assertEqual(len(markers), 1)

    def test_failed_resource_commit_does_not_burn_approval(self) -> None:
        resource_registry.transition(self.root, "xiangmu-zhangcheng", "candidate", approved=False)
        target = self.root / "项目/项目章程.md"
        approval_ref = self.make_approval(target, "resource_activate", "resource-rollback")
        original_write = resource_registry.write_registry
        calls = {"count": 0}

        def fail_once(path: Path, value: dict) -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("simulated write failure")
            original_write(path, value)

        with mock.patch.object(resource_registry, "write_registry", side_effect=fail_once):
            with self.assertRaises(resource_registry.RegistryError):
                resource_registry.transition(
                    self.root,
                    "xiangmu-zhangcheng",
                    "active",
                    approved=True,
                    approval_event=approval_ref,
                )
        self.assertFalse(approval_record.event_is_consumed(self.root, "resource-rollback"))

    def test_research_directory_cannot_masquerade_as_world_resource(self) -> None:
        registry_path = self.root / "治理/资源注册表.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        research = self.root / "研究/伪装世界.md"
        research.write_text("外部材料", encoding="utf-8")
        data["resources"].append({
            "id": "fake-world",
            "path": "研究/伪装世界.md",
            "type": "world",
            "owner": "xiangmu-zhiliyuan",
            "version": "1.0.0",
            "status": "proposed",
            "supersedes": None,
            "scope": {"project": "test-project", "volumes": None, "arcs": None, "chapters": None, "scene_types": None, "povs": None},
            "readers": ["zhangjie-qingjing-bianyiyuan"],
            "allow_author": False,
            "source_sha256": digest(research),
            "approval": {"status": "unapproved", "approved_at": None, "approved_by": None},
        })
        registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _, errors = resource_registry.validate_registry(self.root)
        self.assertTrue(any("目录职责不一致" in error for error in errors))

    def test_silent_floor_rejects_synonymous_compliance_language(self) -> None:
        samples = (
            "本章逐项落实了大纲限制，研究来源均已核对。",
            "这一节依照设定清单写全了相关信息。",
            "这段文字已经依照既定规则写成，查证了相关材料的出处。",
            "这一节照着前述规范写完，所用史料也查过出处。",
            "正文执行了全部创作指示，参考材料已经查实。",
        )
        for sample in samples:
            self.assertTrue(story_state.candidate_prose_errors(sample), sample)

    def test_migration_preview_cannot_write_inside_source(self) -> None:
        source = self.root / "legacy-source"
        source.mkdir()
        (source / "world.md").write_text("旧资料", encoding="utf-8")
        script = PLUGIN_ROOT / "scripts/migrate_v4_1_preview.py"
        result = subprocess.run(
            [sys.executable, str(script), "--project-root", str(source), "--output", str(source / "preview.json")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((source / "preview.json").exists())

    def test_project_id_injection_is_rejected(self) -> None:
        target = Path(self.temp.name) / "bad-project"
        script = PLUGIN_ROOT / "scripts/init_project.py"
        result = subprocess.run(
            [sys.executable, str(script), "--project-root", str(target), "--project-id", "bad'id"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_project_initialization_is_atomic_and_valid(self) -> None:
        target = Path(self.temp.name) / "new-project"
        script = PLUGIN_ROOT / "scripts/init_project.py"
        result = subprocess.run(
            [sys.executable, str(script), "--project-root", str(target), "--project-id", "new-project"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        registry, errors = resource_registry.validate_registry(target)
        self.assertFalse(errors, errors)
        self.assertTrue(all(item["scope"]["project"] == "new-project" for item in registry["resources"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
