#!/usr/bin/env python3
"""对项目声音与表现能力候选执行闭合和来源靠近风险预检。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


CHECKS = {
    "route": [r"(?:先|首先).{0,30}(?:再|然后|接着).{0,40}(?:最后|结尾)", r"固定(?:镜头|步骤|顺序|流程)"],
    "fulfillment": [r"每(?:段|场|章|次).{0,16}(?:必须|都要|应当)", r"逐项(?:检查|完成|体现|证明)"],
    "closed_mapping": [r"(?:政治|战斗|感情|家园|历史).{0,8}(?:等于|就是|必须通过)", r"(?:短句|对白|回家|绳|账目).{0,8}(?:代表|象征|体现)", r"情绪.{0,12}(?:不|不得|只能).{0,12}(?:命名|动作|表现)"],
    "example_anchor": [r"(?:例如|比如|譬如|可写成|示例)[：:]?", r"[“\"].{2,40}[”\"]"],
    "semantic_density": [r"(?m)^(?:\s*[-*+]\s+|\s*\d+[.、)])(?:必须|需要|应当|确保)"],
    "source_proximity": [r"(?:模仿|仿照|像).{0,12}(?:作者|作品|文风)", r"(?:山冈庄八|冰与火之歌|德川家康|雪国|金阁寺|魔戒|基地)"],
}


CHECK_NAMES = {"route", "fulfillment", "closed_mapping", "example_anchor", "semantic_density", "source_proximity"}


def audit(
    path: Path,
    *,
    resource_id: str | None = None,
    resource_version: str | None = None,
    manual_review: dict[str, object] | None = None,
) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    findings: list[dict[str, object]] = []
    for category, patterns in CHECKS.items():
        for pattern in patterns:
            hits = [match.group(0) for match in re.finditer(pattern, text, flags=re.S)]
            if hits:
                findings.append({"category": category, "count": len(hits), "samples": hits[:3]})
    density = sum(1 for line in text.splitlines() if re.match(r"\s*(?:[-*+]\s+|\d+[.、)])", line))
    if density > 12:
        findings.append({"category": "semantic_density", "count": density, "samples": ["结构化条目过密"]})
    resource_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    manual_valid = False
    if manual_review is not None:
        manual_valid = (
            set(manual_review) == {"resource_id", "resource_path", "resource_version", "resource_sha256", "reviewed_by", "checks"}
            and manual_review.get("resource_id") == resource_id
            and manual_review.get("resource_path") == str(path)
            and manual_review.get("resource_version") == resource_version
            and manual_review.get("resource_sha256") == resource_sha256
            and manual_review.get("reviewed_by") in {"user", "biaoxian-shejishi"}
            and isinstance(manual_review.get("checks"), dict)
            and set(manual_review["checks"]) == CHECK_NAMES
            and all(value == "pass" for value in manual_review["checks"].values())
        )
    passed = not findings and manual_valid
    return {
        "path": str(path),
        "sha256": resource_sha256,
        "resource_id": resource_id,
        "resource_version": resource_version,
        "manual_review": manual_review,
        "pass": passed,
        "decision": "candidate_allowed" if passed else "remain_proposed",
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--resource-version", required=True)
    parser.add_argument("--manual-review", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    review = json.loads(Path(args.manual_review).read_text(encoding="utf-8"))
    result = audit(
        Path(args.file).resolve(),
        resource_id=args.resource_id,
        resource_version=args.resource_version,
        manual_review=review,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
