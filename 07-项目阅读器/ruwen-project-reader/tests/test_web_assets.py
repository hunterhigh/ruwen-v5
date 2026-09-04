from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "src" / "ruwen_project_reader" / "web"


class WebAssetTests(unittest.TestCase):
    def test_required_assets_are_present(self) -> None:
        for relative in (
            "index.html",
            "app.css",
            "app.js",
            "fonts/noto/400.css",
            "fonts/xiaowei/400.css",
            "fonts/wenkai/regular.css",
            "fonts/noto/LICENSE",
            "fonts/xiaowei/LICENSE",
            "fonts/wenkai/OFL.txt",
            "fonts/THIRD_PARTY.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((WEB_ROOT / relative).is_file())

    def test_frontend_has_no_remote_dependencies(self) -> None:
        source = "\n".join(
            (WEB_ROOT / name).read_text(encoding="utf-8")
            for name in ("index.html", "app.css", "app.js")
        )
        self.assertIsNone(re.search(r"https?://", source))

    def test_font_stylesheets_resolve_to_local_files(self) -> None:
        for folder, stylesheet in (
            ("noto", "400.css"),
            ("xiaowei", "400.css"),
            ("wenkai", "regular.css"),
        ):
            css_path = WEB_ROOT / "fonts" / folder / stylesheet
            css = css_path.read_text(encoding="utf-8")
            urls = re.findall(r"url\(['\"]?([^)'\"]+)", css)
            self.assertTrue(urls)
            for url in urls:
                with self.subTest(stylesheet=str(css_path), url=url):
                    self.assertTrue((css_path.parent / url).resolve().is_file())


if __name__ == "__main__":
    unittest.main()
