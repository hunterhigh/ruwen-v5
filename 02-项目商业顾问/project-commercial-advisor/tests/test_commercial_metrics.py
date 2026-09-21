from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "commercial_metrics.py"
SPEC = importlib.util.spec_from_file_location("commercial_metrics", SCRIPT)
assert SPEC and SPEC.loader
commercial_metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(commercial_metrics)


class ChapterMetricTests(unittest.TestCase):
    def test_unsorted_chapters_produce_exact_metrics(self) -> None:
        result = commercial_metrics.summarize_chapters(
            {
                "source_timezone": "Asia/Shanghai",
                "chapters": [
                    {"id": "003", "published_at": "2026-08-03T08:00:00+08:00", "chars": 3000},
                    {"id": "001", "published_at": "2026-08-01T08:00:00+08:00", "chars": 2000},
                    {"id": "002", "published_at": "2026-08-02T08:00:00+08:00", "chars": 2500},
                ],
            }
        )
        self.assertEqual(result["classification"], "derived")
        self.assertEqual(result["chapter_count"], 3)
        self.assertEqual(result["total_chars"], 7500)
        self.assertEqual(result["mean_chars"], "2500")
        self.assertEqual(result["median_chars"], "2500")
        self.assertEqual(result["mean_update_interval_hours"], "24")
        self.assertEqual(result["daily"]["2026-08-02"], {"chapters": 1, "chars": 2500})
        self.assertEqual(result["weekly"]["2026-W31"], {"chapters": 2, "chars": 4500})

    def test_single_and_missing_values_stay_unknown(self) -> None:
        result = commercial_metrics.summarize_chapters(
            {
                "chapters": [
                    {"id": "001", "published_at": "2026-08-01T08:00:00+08:00", "chars": None},
                    {"id": "002", "published_at": None, "chars": 2100},
                ]
            }
        )
        self.assertEqual(result["chapter_count"], 2)
        self.assertEqual(result["total_chars"], 2100)
        self.assertEqual(result["mean_chars"], "2100")
        self.assertIsNone(result["mean_update_interval_hours"])
        self.assertEqual(result["missing"]["chars"], ["001"])
        self.assertEqual(result["missing"]["published_at"], ["002"])

    def test_empty_input_is_not_filled_with_zero_metrics(self) -> None:
        result = commercial_metrics.summarize_chapters({"chapters": []})
        self.assertEqual(result["chapter_count"], 0)
        self.assertIsNone(result["total_chars"])
        self.assertIsNone(result["mean_chars"])
        self.assertIsNone(result["median_chars"])

    def test_invalid_chapter_values_are_rejected(self) -> None:
        cases = [
            {"chapters": [{"id": "001", "chars": -1}]},
            {"chapters": [{"id": "001"}, {"id": "001"}]},
            {"chapters": [{"id": "001", "published_at": "2026-08-01T08:00:00"}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(commercial_metrics.InputError):
                commercial_metrics.summarize_chapters(payload)


class ProfitMetricTests(unittest.TestCase):
    def test_actual_profit_respects_completeness(self) -> None:
        result = commercial_metrics.calculate_profit(
            {
                "mode": "actual",
                "currency": "CNY",
                "settlement_complete": True,
                "costs_complete": False,
                "income_components": [{"name": "订阅结算", "amount": "1000.10"}],
                "deduction_components": [{"name": "税费", "amount": "100.01"}],
                "cost_components": [{"name": "工具", "amount": "50.05"}],
            }
        )
        self.assertEqual(result["classification"], "actual")
        self.assertEqual(result["known_cash_subtotal"], "900.09")
        self.assertEqual(result["cash_income"], "900.09")
        self.assertEqual(result["known_cost_total"], "50.05")
        self.assertIsNone(result["economic_profit"])

    def test_incomplete_settlement_is_not_called_cash_income(self) -> None:
        result = commercial_metrics.calculate_profit(
            {
                "mode": "actual",
                "currency": "CNY",
                "settlement_complete": False,
                "costs_complete": True,
                "income_components": [{"name": "已知收入", "amount": "100"}],
                "deduction_components": [],
                "cost_components": [],
            }
        )
        self.assertEqual(result["known_cash_subtotal"], "100")
        self.assertIsNone(result["cash_income"])
        self.assertIsNone(result["economic_profit"])

    def test_scenario_uses_decimal_and_user_parameters(self) -> None:
        result = commercial_metrics.calculate_profit(
            {
                "mode": "scenario",
                "currency": "CNY",
                "scenarios": [
                    {
                        "name": "基准",
                        "paid_chars": 100000,
                        "average_payers": 123,
                        "price_per_thousand": "0.05",
                        "author_share": "0.5",
                        "additional_income": "10.01",
                        "deductions": "5.02",
                        "costs": "100.03",
                        "costs_complete": True,
                    }
                ],
            }
        )
        scenario = result["scenarios"][0]
        self.assertEqual(result["classification"], "modeled")
        self.assertEqual(scenario["subscription_income"], "307.5")
        self.assertEqual(scenario["cash_income"], "312.49")
        self.assertEqual(scenario["economic_profit"], "212.46")

    def test_invalid_profit_parameters_are_rejected(self) -> None:
        payload = {
            "mode": "scenario",
            "scenarios": [
                {
                    "name": "错误",
                    "paid_chars": 1000,
                    "average_payers": 1,
                    "price_per_thousand": "0.05",
                    "author_share": "1.1",
                    "additional_income": "0",
                    "deductions": "0",
                    "costs": "0",
                    "costs_complete": True,
                }
            ],
        }
        with self.assertRaises(commercial_metrics.InputError):
            commercial_metrics.calculate_profit(payload)

    def test_cli_emits_json_without_writing_input(self) -> None:
        payload = {"chapters": [{"id": "001", "chars": 2000}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chapters.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "chapters", "--input", str(path)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["total_chars"], 2000)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
