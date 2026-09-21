from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "project-commercial-advisor"


class PackageStructureTests(unittest.TestCase):
    def test_manifest_has_only_real_components(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "project-commercial-advisor")
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)
        self.assertEqual(manifest["repository"], "https://github.com/hunterhigh/ruwen-writing-system")

    def test_skill_frontmatter_and_references_are_complete(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name: project-commercial-advisor$")
        self.assertRegex(text, r"(?m)^description: .{20,}$")
        self.assertNotRegex(text, r"TODO|TBD|\[TODO")
        for relative in (
            "references/evidence-and-modeling.md",
            "references/market-selection.md",
            "references/platforms/qidian.md",
            "references/platforms/17k.md",
            "references/platforms/17k-launch.md",
            "assets/commercial-state-template.md",
            "assets/market-scan-template.md",
        ):
            self.assertIn(relative, text)
            self.assertTrue((SKILL / relative).is_file(), relative)

    def test_skill_has_no_workspace_runtime_dependency(self) -> None:
        values = "\n".join(path.read_text(encoding="utf-8") for path in SKILL.rglob("*.md"))
        self.assertNotIn("C:/Users/", values)
        self.assertNotIn("C:\\Users\\", values)
        self.assertNotIn("v5ruwen", values.casefold())

    def test_qidian_reference_requires_query_time_verification(self) -> None:
        text = (SKILL / "references" / "platforms" / "qidian.md").read_text(encoding="utf-8")
        self.assertIn("当前咨询中重新打开", text)
        self.assertIn("https://help.yuewen.com/", text)
        self.assertIn("https://acts.qidian.com/", text)
        self.assertIn("不自动登录", text)

    def test_17k_reference_requires_query_time_verification(self) -> None:
        text = (SKILL / "references" / "platforms" / "17k.md").read_text(encoding="utf-8")
        self.assertIn("当前咨询中重新核验", text)
        self.assertIn("17k.com", text.casefold())
        self.assertIn("17k-launch.md", text)
        self.assertIn("不自动登录", text)
        self.assertIn("不等于订阅", text)
        self.assertNotRegex(text, r"TODO|TBD|\[TODO")

    def test_17k_launch_reference_separates_rules_from_hypotheses(self) -> None:
        text = (SKILL / "references" / "platforms" / "17k-launch.md").read_text(encoding="utf-8")
        for required in (
            "现行官方条件",
            "官方编辑经验",
            "项目内部假设",
            "8,000 字",
            "20,000 字",
            "100,000 字",
            "150,000 字",
            "分子、分母、时间窗口",
            "不代表现行统一硬门槛",
        ):
            self.assertIn(required, text)
        self.assertIn("当前合同与现行年度官方页面", text)
        self.assertNotRegex(text, r"TODO|TBD|\[TODO")

    def test_market_selection_observes_before_inducing_topics(self) -> None:
        text = (SKILL / "references" / "market-selection.md").read_text(encoding="utf-8")
        self.assertLess(text.index("建立观察面"), text.index("事后归纳"))
        self.assertIn("单次", text)
        self.assertIn("不构成趋势", text)
        self.assertIn("内部因素", text)
        self.assertIn("缺失值不是零", text)
        self.assertNotRegex(text, r"TODO|TBD|\[TODO")

    def test_market_scan_template_preserves_evidence_context(self) -> None:
        text = (SKILL / "assets" / "market-scan-template.md").read_text(encoding="utf-8")
        for required in (
            "采集时间",
            "来源链接",
            "样本进入条件",
            "证据性质",
            "访问与证据限制",
            "最小下一证据",
        ):
            self.assertIn(required, text)
        self.assertNotRegex(text, r"TODO|TBD|\[TODO")

    def test_openai_yaml_is_utf8_and_mentions_skill(self) -> None:
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("项目商业顾问", text)
        self.assertIn("$project-commercial-advisor", text)
        self.assertNotIn("�", text)


if __name__ == "__main__":
    unittest.main()
