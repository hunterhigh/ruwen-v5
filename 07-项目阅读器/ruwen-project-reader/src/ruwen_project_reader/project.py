from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any


class ProjectReaderError(Exception):
    """Base error for project access."""


class UnsafePathError(ProjectReaderError):
    """A requested path escapes the selected project."""


class UnsupportedFileError(ProjectReaderError):
    """A file type is not readable in the project reader."""


class FileTooLargeError(ProjectReaderError):
    """A file exceeds the configured browser reading limit."""


class ProjectReader:
    SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml"}
    IGNORED_DIRECTORIES = {".git", ".ruwen", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}

    def __init__(self, root: str | Path, *, max_file_bytes: int = 4 * 1024 * 1024) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.max_file_bytes = max_file_bytes

    @property
    def name(self) -> str:
        return self.root.name

    def _resolve(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise UnsafePathError(relative_path)
        candidate = (self.root / Path(*pure.parts)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise UnsafePathError(relative_path) from error
        return candidate

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def tree(self) -> list[dict[str, Any]]:
        return self._scan_directory(self.root)

    def _scan_directory(self, directory: Path) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        entries = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        for entry in entries:
            if entry.name.startswith(".") or entry.name in self.IGNORED_DIRECTORIES:
                continue
            if entry.is_symlink():
                try:
                    entry.resolve().relative_to(self.root)
                except ValueError:
                    continue
            if entry.is_dir():
                children = self._scan_directory(entry)
                if children:
                    nodes.append({"type": "directory", "name": entry.name, "children": children})
            elif entry.is_file() and self._is_supported(entry):
                nodes.append(
                    {
                        "type": "file",
                        "name": entry.name,
                        "path": entry.relative_to(self.root).as_posix(),
                        "extension": entry.suffix.lower(),
                    }
                )
        return nodes

    def read(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if not self._is_supported(path):
            raise UnsupportedFileError(relative_path)
        size = path.stat().st_size
        if size > self.max_file_bytes:
            raise FileTooLargeError(relative_path)
        raw = path.read_bytes()
        try:
            content = raw.decode("utf-8-sig")
            encoding = "utf-8"
        except UnicodeDecodeError:
            try:
                content = raw.decode("gb18030")
                encoding = "gb18030"
            except UnicodeDecodeError as error:
                raise UnsupportedFileError(f"无法解码：{relative_path}") from error
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        return {
            "path": relative_path.replace("\\", "/"),
            "name": path.name,
            "extension": path.suffix.lower(),
            "content": content,
            "encoding": encoding,
            "size": size,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def exists(self, relative_path: str) -> bool:
        try:
            return self._resolve(relative_path).is_file()
        except UnsafePathError:
            return False
