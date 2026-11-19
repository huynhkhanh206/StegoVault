"""Máy chủ HTTP cục bộ cho giao diện web (chỉ dùng thư viện chuẩn).

Bảo mật:
    * Mặc định chỉ lắng nghe 127.0.0.1.
    * Từ chối yêu cầu có header Host lạ (chống DNS-rebinding) và POST không phải JSON.
    * Giới hạn kích thước body; không ghi gì ra đĩa; mật khẩu chỉ nằm trong bộ nhớ khi xử lý.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from ..errors import StegoError
from .api import ROUTES, clean

MAX_BODY = 160 * 1024 * 1024
INDEX_PATH = Path(__file__).with_name("index.html")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; img-src 'self' data: blob:; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'"
    ),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "StegoVault"
    protocol_version = "HTTP/1.1"

    # --- tiện ích
    def log_message(self, fmt, *args):  # im lặng, trừ khi bật verbose
        if getattr(self.server, "verbose", False):
            sys.stderr.write("[web] " + (fmt % args) + "\n")

    def _host_ok(self) -> bool:
        if getattr(self.server, "allow_any_host", False):
            return True
        host = self.headers.get("Host", "")
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.rsplit("]", 1)[0] + "]"
        return name.lower() in LOCAL_HOSTS

    def _send(self, status: int, body: bytes, ctype: str, close: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if close:
            # Thân yêu cầu CHƯA được đọc: nếu giữ kết nối (keep-alive), các byte còn lại sẽ bị hiểu nhầm thành
            # yêu cầu kế tiếp (mất đồng bộ giao thức). Đóng kết nối để tránh điều đó.
            self.send_header("Connection", "close")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload, close: bool = False) -> None:
        self._send(status, json.dumps(clean(payload), ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", close)

    # --- định tuyến
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Host không hợp lệ."}, close=True)
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            return self._send(200, INDEX_PATH.read_bytes(), "text/html; charset=utf-8")
        path = self.path.split("?", 1)[0]
        if path == "/api/info":
            return self._json(200, ROUTES["/api/info"]({}))
        self._json(404, {"error": "Không tìm thấy."})

    def do_POST(self):
        # Mọi nhánh từ chối TRƯỚC khi đọc thân yêu cầu đều phải đóng kết nối (close=True), xem _send().
        if not self._host_ok():
            return self._json(403, {"error": "Host không hợp lệ."}, close=True)
        handler = ROUTES.get(self.path.split("?", 1)[0])
        if handler is None:
            return self._json(404, {"error": "Không tìm thấy."}, close=True)
        if "application/json" not in self.headers.get("Content-Type", ""):
            return self._json(415, {"error": "Yêu cầu phải là application/json."}, close=True)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error": "Content-Length không hợp lệ."}, close=True)
        if length <= 0 or length > MAX_BODY:
            return self._json(413, {"error": f"Dữ liệu gửi lên quá lớn (tối đa {MAX_BODY // (1024 * 1024)} MB)."}, close=True)
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(req, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "JSON không hợp lệ."})
        try:
            self._json(200, handler(req))
        except StegoError as exc:
            self._json(400, {"error": str(exc)})
        except MemoryError:
            self._json(507, {"error": "Hết bộ nhớ khi xử lý ảnh này. Hãy thử ảnh nhỏ hơn."})
        except Exception:  # lỗi không lường trước: không lộ chi tiết nội bộ ra trình duyệt
            traceback.print_exc()
            self._json(500, {"error": "Lỗi nội bộ khi xử lý. Xem cửa sổ dòng lệnh để biết chi tiết."})


def make_server(host: str = "127.0.0.1", port: int = 8765, verbose: bool = False, allow_any_host: bool = False):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.verbose = verbose
    srv.allow_any_host = allow_any_host
    return srv


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"⚠ Bạn đang mở máy chủ ở {host}: người khác trong mạng có thể truy cập. "
              "Công cụ này dành cho dùng cục bộ.", file=sys.stderr)
    srv = make_server(host, port, verbose=True, allow_any_host=host not in ("127.0.0.1", "localhost", "::1"))
    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{srv.server_address[1]}/"
    print(f"StegoVault đang chạy tại {url}   (Ctrl+C để dừng)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    finally:
        srv.server_close()
