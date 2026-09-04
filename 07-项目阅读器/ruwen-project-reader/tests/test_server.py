from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ruwen_project_reader.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "世界").mkdir()
        self.content = "# 当前态势\n\n北方政权保持独立意志。"
        (self.root / "世界" / "当前态势.md").write_text(self.content, encoding="utf-8", newline="\n")
        self.server = create_server(self.root, port=0, token="test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.application.close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path: str, *, method: str = "GET", payload: dict | None = None, token: bool = True):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Ruwen-Token"] = "test-token"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def raw_request(self, path: str, *, token: bool = True):
        headers = {"X-Ruwen-Token": "test-token"} if token else {}
        request = urllib.request.Request(self.base + path, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.headers, response.read()

    def test_api_requires_token(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/project", token=False)
        self.assertEqual(caught.exception.code, 403)

    def test_project_and_file_endpoints(self) -> None:
        status, project = self.request("/api/project")
        self.assertEqual(status, 200)
        self.assertEqual(project["project"]["name"], self.root.name)
        _, document = self.request("/api/file?path=%E4%B8%96%E7%95%8C%2F%E5%BD%93%E5%89%8D%E6%80%81%E5%8A%BF.md")
        self.assertEqual(document["content"], self.content)
        _, reopened = self.request("/api/project")
        self.assertEqual(reopened["preferences"]["last_opened_file"], "世界/当前态势.md")

    def test_project_font_preference_is_persistent(self) -> None:
        _, preference = self.request(
            "/api/preferences",
            method="POST",
            payload={"project_font": "wenkai"},
        )
        self.assertEqual(preference["project_font"], "wenkai")
        _, project = self.request("/api/project")
        self.assertEqual(project["preferences"]["project_font"], "wenkai")

    def test_shell_embeds_token_without_inline_script(self) -> None:
        status, headers, body = self.raw_request("/?key=test-token")
        html = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn('meta name="ruwen-token" content="test-token"', html)
        self.assertNotIn("window.RUWEN_TOKEN", html)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_static_assets_are_served_without_api_token(self) -> None:
        status, headers, body = self.raw_request("/assets/app.js", token=False)
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertIn(b"ruwen-token", body)

    def test_font_assets_have_browser_safe_content_type(self) -> None:
        status, headers, body = self.raw_request(
            "/assets/fonts/xiaowei/files/zcool-xiaowei-100-400-normal.woff2",
            token=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "font/woff2")
        self.assertGreater(len(body), 1_000)

    def test_annotation_and_seal_flow(self) -> None:
        _, document = self.request("/api/file?path=%E4%B8%96%E7%95%8C%2F%E5%BD%93%E5%89%8D%E6%80%81%E5%8A%BF.md")
        start = self.content.index("北方政权")
        _, created = self.request(
            "/api/annotations",
            method="POST",
            payload={
                "path": "世界/当前态势.md",
                "body": "保留组织意志",
                "file_hash": document["sha256"],
                "selection_start": start,
                "selection_end": len(self.content),
            },
        )
        self.assertEqual(created["body"], "保留组织意志")
        _, annotations = self.request("/api/annotations?path=%E4%B8%96%E7%95%8C%2F%E5%BD%93%E5%89%8D%E6%80%81%E5%8A%BF.md")
        self.assertEqual(len(annotations["annotations"]), 1)
        _, sealed = self.request("/api/batches/1/seal", method="POST", payload={})
        self.assertEqual(sealed["batch"]["status"], "sealed")
        self.assertEqual(sealed["next_batch"]["number"], 2)


if __name__ == "__main__":
    unittest.main()
