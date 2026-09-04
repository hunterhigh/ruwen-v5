from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .project import ProjectReader


class GitHistoryError(Exception):
    """A read-only Git operation failed."""


class GitHistory:
    REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^-]{0,199}$")

    def __init__(self, reader: ProjectReader) -> None:
        self.reader = reader
        self.git_root: Path | None = None
        try:
            output = self._run_at(reader.root, "rev-parse", "--show-toplevel")
            self.git_root = Path(output.strip()).resolve()
            reader.root.relative_to(self.git_root)
        except (GitHistoryError, ValueError):
            self.git_root = None

    @property
    def available(self) -> bool:
        return self.git_root is not None

    @staticmethod
    def _run_at(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            raise GitHistoryError(result.stderr.strip() or "Git 命令失败")
        return result.stdout

    def _git_path(self, relative_path: str) -> str:
        if self.git_root is None:
            raise GitHistoryError("项目没有可用的 Git 历史")
        resolved = self.reader._resolve(relative_path)
        return resolved.relative_to(self.git_root).as_posix()

    def _verify_revision(self, revision: str) -> str:
        if self.git_root is None or not self.REVISION_RE.fullmatch(revision):
            raise GitHistoryError("无效 Git 修订")
        return self._run_at(self.git_root, "rev-parse", "--verify", f"{revision}^{{commit}}").strip()

    def list(self, relative_path: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if self.git_root is None:
            return []
        path = self._git_path(relative_path)
        output = self._run_at(
            self.git_root,
            "log",
            "--follow",
            f"--max-count={max(1, min(limit, 200))}",
            "--format=%H%x1f%aI%x1f%s",
            "--",
            path,
        )
        history: list[dict[str, Any]] = []
        for line in output.splitlines():
            parts = line.split("\x1f", 2)
            if len(parts) == 3:
                history.append({"revision": parts[0], "authored_at": parts[1], "subject": parts[2]})
        return history

    def content(self, relative_path: str, revision: str) -> str:
        if self.git_root is None:
            raise GitHistoryError("项目没有可用的 Git 历史")
        commit = self._verify_revision(revision)
        path = self._git_path(relative_path)
        return self._run_at(self.git_root, "show", f"{commit}:{path}").replace("\r\n", "\n")

    def diff(self, relative_path: str, from_revision: str, to_revision: str) -> str:
        if self.git_root is None:
            raise GitHistoryError("项目没有可用的 Git 历史")
        old = self._verify_revision(from_revision)
        new = self._verify_revision(to_revision)
        path = self._git_path(relative_path)
        return self._run_at(
            self.git_root,
            "diff",
            "--no-ext-diff",
            "--unified=3",
            old,
            new,
            "--",
            path,
        ).replace("\r\n", "\n")
