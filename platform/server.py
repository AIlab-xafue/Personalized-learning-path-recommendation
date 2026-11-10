# -*- coding: utf-8 -*-
"""个性化学习路径推荐演示平台 —— 本地服务器（仅用 Python 标准库）

为什么需要它：页面用 fetch 读取 data/*.json，浏览器对 file:// 的跨源请求有限制，
直接双击 index.html 会白屏。用本脚本起一个本地 HTTP 服务即可，无需安装 Flask 等依赖。

运行：
    python server.py            # 默认 127.0.0.1:8770，自动打开浏览器
    python server.py --port 9000 --no-browser
"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
import threading
import webbrowser
from functools import partial

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # 避免演示时改了数据却看到旧缓存
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):  # 静音访问日志，只保留报错
        if args and str(args[1])[:1] in ("4", "5"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    missing = [f for f in ("graph.json", "task.json", "aggregate.json")
               if not os.path.exists(os.path.join(HERE, "data", f))]
    if missing:
        print("[!] data/ 下缺少：" + ", ".join(missing))
        print("    请先运行： python \"../Title2/10_export_platform_data.py\"")
        return

    socketserver.TCPServer.allow_reuse_address = True
    handler = partial(Handler, directory=HERE)
    with socketserver.ThreadingTCPServer((args.host, args.port), handler) as httpd:
        url = f"http://{args.host}:{args.port}/index.html"
        print("=" * 58)
        print("  个性化学习路径推荐演示平台")
        print("  " + url)
        print("  Ctrl+C 停止")
        print("=" * 58)
        if not args.no_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
