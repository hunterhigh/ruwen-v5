#!/usr/bin/env python3
"""对章节更新和项目利润执行无网络、无持久化的确定性计算。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InputError(ValueError):
    """输入无法在不猜测数据的情况下计算。"""


def decimal_value(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise InputError(f"{label}必须是非负数")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"{label}必须是非负数") from exc
    if not result.is_finite() or result < 0:
        raise InputError(f"{label}必须是非负数")
    return result


def integer_value(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{label}必须是非负整数")
    return value


def decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def source_zone(value: Any) -> ZoneInfo | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError("source_timezone必须是IANA时区名称")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise InputError(f"未知source_timezone：{value}") from exc


def timestamp_value(value: Any, label: str, zone: ZoneInfo | None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label}必须是ISO 8601时间文本")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InputError(f"{label}不是有效ISO 8601时间") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        if zone is None:
            raise InputError(f"{label}缺少时区，且未提供source_timezone")
        result = result.replace(tzinfo=zone)
    elif zone is not None:
        result = result.astimezone(zone)
    return result


def median_decimal(values: list[int]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Decimal(ordered[middle])
    return Decimal(ordered[middle - 1] + ordered[middle]) / Decimal(2)


def finalize_buckets(values: dict[str, dict[str, int]]) -> dict[str, dict[str, int | None]]:
    result: dict[str, dict[str, int | None]] = {}
    for key in sorted(values):
        item = values[key]
        if item["missing_char_count"] == 0:
            result[key] = {"chapters": item["chapters"], "chars": item["known_chars"]}
        else:
            result[key] = {
                "chapters": item["chapters"],
                "chars": None,
                "known_chars": item["known_chars"],
                "missing_char_count": item["missing_char_count"],
            }
    return result


def add_bucket(bucket: dict[str, dict[str, int]], key: str, chars: int | None) -> None:
    item = bucket.setdefault(
        key,
        {"chapters": 0, "known_chars": 0, "missing_char_count": 0},
    )
    item["chapters"] += 1
    if chars is None:
        item["missing_char_count"] += 1
    else:
        item["known_chars"] += chars


def summarize_chapters(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("章节输入必须是对象")
    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        raise InputError("chapters必须是数组")
    zone = source_zone(payload.get("source_timezone"))
    seen: set[str] = set()
    chars_values: list[int] = []
    published: list[tuple[datetime, int | None]] = []
    missing_chars: list[str] = []
    missing_published: list[str] = []

    for index, item in enumerate(chapters):
        if not isinstance(item, dict):
            raise InputError(f"chapters[{index}]必须是对象")
        chapter_id = item.get("id")
        if not isinstance(chapter_id, str) or not chapter_id.strip():
            raise InputError(f"chapters[{index}].id必须是非空文本")
        chapter_id = chapter_id.strip()
        if chapter_id in seen:
            raise InputError(f"章节id重复：{chapter_id}")
        seen.add(chapter_id)

        raw_chars = item.get("chars")
        chars: int | None
        if raw_chars is None:
            chars = None
            missing_chars.append(chapter_id)
        else:
            chars = integer_value(raw_chars, f"chapters[{index}].chars")
            chars_values.append(chars)

        raw_published = item.get("published_at")
        if raw_published is None:
            missing_published.append(chapter_id)
        else:
            published.append(
                (timestamp_value(raw_published, f"chapters[{index}].published_at", zone), chars)
            )

    published.sort(key=lambda item: item[0].astimezone(timezone.utc))
    intervals = [
        Decimal(str((right[0].astimezone(timezone.utc) - left[0].astimezone(timezone.utc)).total_seconds()))
        / Decimal(3600)
        for left, right in zip(published, published[1:])
    ]
    daily: dict[str, dict[str, int]] = {}
    weekly: dict[str, dict[str, int]] = {}
    for timestamp, chars in published:
        add_bucket(daily, timestamp.date().isoformat(), chars)
        iso = timestamp.isocalendar()
        add_bucket(weekly, f"{iso.year:04d}-W{iso.week:02d}", chars)

    total_chars = sum(chars_values) if chars_values else None
    mean_chars = (
        Decimal(total_chars) / Decimal(len(chars_values)) if total_chars is not None else None
    )
    median_chars = median_decimal(chars_values) if chars_values else None
    mean_interval = sum(intervals, Decimal(0)) / Decimal(len(intervals)) if intervals else None

    return {
        "kind": "chapter_metrics",
        "classification": "derived",
        "chapter_count": len(chapters),
        "total_chars": total_chars,
        "mean_chars": decimal_text(mean_chars) if mean_chars is not None else None,
        "median_chars": decimal_text(median_chars) if median_chars is not None else None,
        "min_chars": min(chars_values) if chars_values else None,
        "max_chars": max(chars_values) if chars_values else None,
        "first_published_at": published[0][0].isoformat() if published else None,
        "last_published_at": published[-1][0].isoformat() if published else None,
        "mean_update_interval_hours": (
            decimal_text(mean_interval) if mean_interval is not None else None
        ),
        "daily": finalize_buckets(daily),
        "weekly": finalize_buckets(weekly),
        "missing": {
            "chars": missing_chars,
            "published_at": missing_published,
        },
    }


def component_total(value: Any, label: str) -> Decimal:
    if not isinstance(value, list):
        raise InputError(f"{label}必须是数组")
    total = Decimal(0)
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"name", "amount"}:
            raise InputError(f"{label}[{index}]必须只包含name和amount")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise InputError(f"{label}[{index}].name必须是非空文本")
        total += decimal_value(item["amount"], f"{label}[{index}].amount")
    return total


def bool_value(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise InputError(f"{label}必须是布尔值")
    return value


def actual_profit(payload: dict[str, Any], currency: str) -> dict[str, Any]:
    settlement_complete = bool_value(payload.get("settlement_complete"), "settlement_complete")
    costs_complete = bool_value(payload.get("costs_complete"), "costs_complete")
    income = component_total(payload.get("income_components"), "income_components")
    deductions = component_total(payload.get("deduction_components"), "deduction_components")
    costs = component_total(payload.get("cost_components"), "cost_components")
    known_cash = income - deductions
    cash_income = known_cash if settlement_complete else None
    economic_profit = cash_income - costs if cash_income is not None and costs_complete else None
    return {
        "kind": "profit_metrics",
        "classification": "actual",
        "currency": currency,
        "settlement_complete": settlement_complete,
        "costs_complete": costs_complete,
        "known_income_total": decimal_text(income),
        "known_deduction_total": decimal_text(deductions),
        "known_cash_subtotal": decimal_text(known_cash),
        "cash_income": decimal_text(cash_income) if cash_income is not None else None,
        "known_cost_total": decimal_text(costs),
        "economic_profit": (
            decimal_text(economic_profit) if economic_profit is not None else None
        ),
    }


def scenario_profit(payload: dict[str, Any], currency: str) -> dict[str, Any]:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise InputError("scenarios必须是非空数组")
    results: list[dict[str, Any]] = []
    required = {
        "name",
        "paid_chars",
        "average_payers",
        "price_per_thousand",
        "author_share",
        "additional_income",
        "deductions",
        "costs",
        "costs_complete",
    }
    for index, item in enumerate(scenarios):
        if not isinstance(item, dict) or set(item) != required:
            raise InputError(f"scenarios[{index}]字段不完整或包含未知字段")
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"scenarios[{index}].name必须是非空文本")
        paid_chars = integer_value(item["paid_chars"], f"scenarios[{index}].paid_chars")
        payers = decimal_value(item["average_payers"], f"scenarios[{index}].average_payers")
        price = decimal_value(
            item["price_per_thousand"], f"scenarios[{index}].price_per_thousand"
        )
        share = decimal_value(item["author_share"], f"scenarios[{index}].author_share")
        if share > 1:
            raise InputError(f"scenarios[{index}].author_share必须在0到1之间")
        additions = decimal_value(
            item["additional_income"], f"scenarios[{index}].additional_income"
        )
        deductions = decimal_value(item["deductions"], f"scenarios[{index}].deductions")
        costs = decimal_value(item["costs"], f"scenarios[{index}].costs")
        costs_complete = bool_value(item["costs_complete"], f"scenarios[{index}].costs_complete")
        subscription = Decimal(paid_chars) / Decimal(1000) * payers * price * share
        cash_income = subscription + additions - deductions
        economic_profit = cash_income - costs if costs_complete else None
        results.append(
            {
                "name": name.strip(),
                "paid_chars": paid_chars,
                "average_payers": decimal_text(payers),
                "price_per_thousand": decimal_text(price),
                "author_share": decimal_text(share),
                "subscription_income": decimal_text(subscription),
                "additional_income": decimal_text(additions),
                "deductions": decimal_text(deductions),
                "cash_income": decimal_text(cash_income),
                "costs": decimal_text(costs),
                "costs_complete": costs_complete,
                "economic_profit": (
                    decimal_text(economic_profit) if economic_profit is not None else None
                ),
            }
        )
    return {
        "kind": "profit_metrics",
        "classification": "modeled",
        "currency": currency,
        "scenarios": results,
    }


def calculate_profit(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("利润输入必须是对象")
    mode = payload.get("mode")
    currency = payload.get("currency", "CNY")
    if not isinstance(currency, str) or not currency.strip():
        raise InputError("currency必须是非空文本")
    if mode == "actual":
        return actual_profit(payload, currency.strip())
    if mode == "scenario":
        return scenario_profit(payload, currency.strip())
    raise InputError("mode必须是actual或scenario")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("chapters", "profit"):
        child = subparsers.add_parser(command)
        child.add_argument("--input", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = summarize_chapters(payload) if args.command == "chapters" else calculate_profit(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
