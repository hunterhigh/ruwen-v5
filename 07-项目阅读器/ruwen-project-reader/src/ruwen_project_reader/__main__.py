from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ruwen 本地项目阅读器")
    parser.add_argument("--project", required=True, type=Path, help="Ruwen 项目目录")
    parser.add_argument("--port", type=int, default=0, help="本地端口；默认自动选择")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    server = create_server(arguments.project, port=arguments.port)
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/?token={server.application.token}"
    print(f"Ruwen 项目阅读器：{url}", flush=True)
    if not arguments.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.application.close()


if __name__ == "__main__":
    main()
