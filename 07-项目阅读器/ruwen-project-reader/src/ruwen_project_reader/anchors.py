from __future__ import annotations

import re
from typing import Any


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _heading_chain(content: str, offset: int) -> list[str]:
    stack: list[tuple[int, str]] = []
    consumed = 0
    for line in content.splitlines(keepends=True):
        if consumed > offset:
            break
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match:
            level = len(match.group(1))
            stack = [item for item in stack if item[0] < level]
            stack.append((level, match.group(2)))
        consumed += len(line)
    return [title for _, title in stack]


def create_anchor(content: str, start: int, end: int) -> dict[str, Any]:
    if start < 0 or end < start or end > len(content):
        raise ValueError("无效选区")
    return {
        "selected_text": content[start:end],
        "prefix": content[max(0, start - 64) : start],
        "suffix": content[end : min(len(content), end + 64)],
        "line_start": _line_number(content, start),
        "line_end": _line_number(content, end),
        "heading_chain": _heading_chain(content, start),
    }


def resolve_anchor(content: str, anchor: dict[str, Any]) -> dict[str, Any]:
    selected = str(anchor.get("selected_text", ""))
    if not selected:
        return {"status": "reanchor_required", "reason": "empty_selection"}
    starts: list[int] = []
    cursor = 0
    while True:
        found = content.find(selected, cursor)
        if found < 0:
            break
        starts.append(found)
        cursor = found + max(1, len(selected))
    if len(starts) == 1:
        return {"status": "resolved", "start": starts[0], "end": starts[0] + len(selected)}
    if len(starts) > 1:
        prefix = str(anchor.get("prefix", ""))
        suffix = str(anchor.get("suffix", ""))
        contextual = []
        for start in starts:
            prefix_ok = not prefix or content[max(0, start - len(prefix)) : start] == prefix
            end = start + len(selected)
            suffix_ok = not suffix or content[end : end + len(suffix)] == suffix
            if prefix_ok and suffix_ok:
                contextual.append(start)
        if len(contextual) == 1:
            start = contextual[0]
            return {"status": "resolved", "start": start, "end": start + len(selected)}
        return {"status": "reanchor_required", "reason": "ambiguous_selection"}
    return {"status": "reanchor_required", "reason": "selection_missing"}
