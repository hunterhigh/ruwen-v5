from __future__ import annotations

import json
import mimetypes
import re
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .anchors import create_anchor
from .database import AnnotationNotFoundError, BatchSealedError, DatabaseError, ReaderDatabase
from .git_history import GitHistory, GitHistoryError
from .project import FileTooLargeError, ProjectReader, ProjectReaderError, UnsafePathError
from .snapshots import EmptyBatchError, ReanchorRequiredError, SnapshotManager


class ReaderApplication:
    def __init__(self, project_root: str | Path, token: str | None = None) -> None:
        self.reader = ProjectReader(project_root)
        self.database = ReaderDatabase(self.reader.root)
        self.git = GitHistory(self.reader)
        self.snapshots = SnapshotManager(self.reader, self.database)
        self.token = token or secrets.token_urlsafe(32)
        self.web_root = Path(__file__).resolve().parent / "web"
        self._validate_web_assets()

    def _validate_web_assets(self) -> None:
        required = [
            "index.html",
            "app.css",
            "app.js",
            "fonts/noto/400.css",
            "fonts/xiaowei/400.css",
            "fonts/wenkai/regular.css",
        ]
        for relative in required:
            if not (self.web_root / relative).is_file():
                raise FileNotFoundError(f"界面资源缺失：{relative}")
        for relative in required[3:]:
            stylesheet = self.web_root / relative
            urls = re.findall(r"url\(['\"]?([^)'\"]+)", stylesheet.read_text(encoding="utf-8"))
            for url in urls:
                if not (stylesheet.parent / url).resolve().is_file():
                    raise FileNotFoundError(f"字体资源缺失：{relative} → {url}")

    def close(self) -> None:
        self.database.close()


class ReaderHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], application: ReaderApplication) -> None:
        self.application = application
        super().__init__(address, ReaderRequestHandler)


def create_server(project_root: str | Path, *, port: int = 0, token: str | None = None) -> ReaderHTTPServer:
    application = ReaderApplication(project_root, token=token)
    return ReaderHTTPServer(("127.0.0.1", port), application)


class ReaderRequestHandler(BaseHTTPRequestHandler):
    server: ReaderHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def app(self) -> ReaderApplication:
        return self.server.application

    def _token_valid(self, query: dict[str, list[str]]) -> bool:
        header = self.headers.get("X-Ruwen-Token", "")
        supplied = header or query.get("token", [""])[0]
        return secrets.compare_digest(supplied, self.app.token)

    def _send_bytes(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, payload: Any) -> None:
        self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str, code: str = "request_error") -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("请求内容过大")
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        return payload

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = unquote(parsed.path)
        try:
            if path == "/":
                if not self._token_valid(query):
                    self._error(HTTPStatus.FORBIDDEN, "访问令牌无效", "invalid_token")
                    return
                self._serve_index()
                return
            if path.startswith("/assets/"):
                self._serve_asset(path.removeprefix("/assets/"))
                return
            if not path.startswith("/api/"):
                self._error(HTTPStatus.NOT_FOUND, "页面不存在", "not_found")
                return
            if not self._token_valid(query):
                self._error(HTTPStatus.FORBIDDEN, "访问令牌无效", "invalid_token")
                return
            self._dispatch_api(method, path, query)
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "文件不存在", "not_found")
        except (UnsafePathError, FileTooLargeError, ProjectReaderError, GitHistoryError, ValueError, json.JSONDecodeError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error), "invalid_request")
        except AnnotationNotFoundError as error:
            self._error(HTTPStatus.NOT_FOUND, str(error), "annotation_not_found")
        except (BatchSealedError, DatabaseError, EmptyBatchError, ReanchorRequiredError, FileExistsError) as error:
            self._error(HTTPStatus.CONFLICT, str(error), "conflict")

    def _serve_index(self) -> None:
        path = self.app.web_root / "index.html"
        content = path.read_text(encoding="utf-8").replace("__RUWEN_TOKEN__", self.app.token).encode("utf-8")
        self._send_bytes(HTTPStatus.OK, content, "text/html; charset=utf-8")

    def _serve_asset(self, relative: str) -> None:
        candidate = (self.app.web_root / relative).resolve()
        try:
            candidate.relative_to(self.app.web_root.resolve())
        except ValueError as error:
            raise UnsafePathError(relative) from error
        if not candidate.is_file():
            raise FileNotFoundError(relative)
        font_types = {".woff": "font/woff", ".woff2": "font/woff2"}
        content_type = font_types.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)

    def _dispatch_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/project":
            self._json(
                HTTPStatus.OK,
                {
                    "project": {"name": self.app.reader.name, "root": str(self.app.reader.root)},
                    "tree": self.app.reader.tree(),
                    "current_batch": self.app.database.current_batch(),
                    "git_available": self.app.git.available,
                    "preferences": {
                        "last_opened_file": self.app.database.get_state("last_opened_file"),
                        "project_font": self.app.database.get_state("project_font", "xiaowei"),
                    },
                },
            )
            return
        if method == "GET" and path == "/api/file":
            relative_path = self._required_query(query, "path")
            document = self.app.reader.read(relative_path)
            self.app.database.set_state("last_opened_file", relative_path)
            self._json(HTTPStatus.OK, document)
            return
        if method == "POST" and path == "/api/preferences":
            payload = self._read_json()
            project_font = str(payload.get("project_font", ""))
            if project_font not in {"xiaowei", "wenkai", "noto"}:
                raise ValueError("无效的项目名字体")
            self.app.database.set_state("project_font", project_font)
            self._json(HTTPStatus.OK, {"project_font": project_font})
            return
        if method == "GET" and path == "/api/annotations":
            batch = int(query["batch"][0]) if query.get("batch") else None
            file_path = query.get("path", [None])[0]
            self._json(
                HTTPStatus.OK,
                {"annotations": self.app.database.list_annotations(batch_number=batch, path=file_path)},
            )
            return
        if method == "POST" and path == "/api/annotations":
            payload = self._read_json()
            file_path = str(payload.get("path", ""))
            document = self.app.reader.read(file_path)
            if payload.get("file_hash") != document["sha256"]:
                raise ValueError("文件已经变化，请重新选择批注位置")
            start = int(payload.get("selection_start", -1))
            end = int(payload.get("selection_end", -1))
            anchor = create_anchor(document["content"], start, end)
            annotation = self.app.database.add_annotation(
                path=file_path,
                body=str(payload.get("body", "")),
                anchor=anchor,
                file_hash=document["sha256"],
            )
            self._json(HTTPStatus.CREATED, annotation)
            return
        if path.startswith("/api/annotations/"):
            annotation_id = path.rsplit("/", 1)[-1]
            if method == "PATCH":
                annotation = self.app.database.update_annotation(annotation_id, str(self._read_json().get("body", "")))
                self._json(HTTPStatus.OK, annotation)
                return
            if method == "DELETE":
                self.app.database.delete_annotation(annotation_id)
                self._json(HTTPStatus.OK, {"deleted": annotation_id})
                return
        if method == "GET" and path == "/api/batches":
            self._json(HTTPStatus.OK, {"batches": self.app.database.list_batches()})
            return
        if method == "POST" and path.startswith("/api/batches/") and path.endswith("/seal"):
            number = int(path.split("/")[3])
            self._read_json()
            self._json(HTTPStatus.OK, self.app.snapshots.seal_batch(number))
            return
        if method == "GET" and path == "/api/git/history":
            self._json(HTTPStatus.OK, {"history": self.app.git.list(self._required_query(query, "path"))})
            return
        if method == "GET" and path == "/api/git/content":
            self._json(
                HTTPStatus.OK,
                {
                    "content": self.app.git.content(
                        self._required_query(query, "path"), self._required_query(query, "revision")
                    )
                },
            )
            return
        if method == "GET" and path == "/api/git/diff":
            self._json(
                HTTPStatus.OK,
                {
                    "diff": self.app.git.diff(
                        self._required_query(query, "path"),
                        self._required_query(query, "from"),
                        self._required_query(query, "to"),
                    )
                },
            )
            return
        self._error(HTTPStatus.NOT_FOUND, "接口不存在", "not_found")

    @staticmethod
    def _required_query(query: dict[str, list[str]], name: str) -> str:
        value = query.get(name, [""])[0]
        if not value:
            raise ValueError(f"缺少参数：{name}")
        return value
