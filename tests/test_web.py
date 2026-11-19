import base64
import http.client
import io
import json
import threading

import numpy as np
import pytest
from PIL import Image

from stegovault.errors import ImageError, StegoError
from stegovault.web import api
from stegovault.web.server import make_server

from conftest import textured

PW = "mat-khau-web-thu"


def png_b64(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def b64cover():
    return png_b64(textured(128, 128, seed=6))


# ----------------------------------------------------------------- API thuần
def test_info():
    r = api.api_info({})
    assert "scrypt" in r["kdfs"] and {m["id"] for m in r["methods"]} == {"sequential", "keyed", "matching"}


def test_capacity_and_embed_extract_roundtrip(b64cover):
    cap = api.api_capacity({"image": b64cover})
    assert cap["width"] == 128 and cap["capacity_bytes"] > 1000 and cap["alpha_dropped"] is False
    r = api.api_embed({"image": b64cover, "password": PW, "message": "Tin nhắn web 🚀", "method": "keyed"})
    assert r["stats"]["message_bytes"] > 0 and r["metrics"]["psnr_db"] > 60 and r["metrics"]["max_abs_diff"] == 1
    out = api.api_extract({"image": r["stego_png"], "password": PW})
    assert out["kind"] == "text" and out["text"] == "Tin nhắn web 🚀"


def _f(name, data):
    return {"filename": name, "data_b64": base64.b64encode(data).decode()}


def test_file_roundtrip_via_api(b64cover):
    data = np.random.default_rng(1).bytes(800)
    r = api.api_embed({"image": b64cover, "password": PW, "files": [_f("../x.bin", data)]})
    assert r["stats"]["file_count"] == 1
    out = api.api_extract({"image": r["stego_png"], "password": PW})
    assert out["kind"] == "file" and out["size"] == 800
    assert [f["filename"] for f in out["files"]] == ["x.bin"]
    assert base64.b64decode(out["files"][0]["data_b64"]) == data


def test_many_files_roundtrip_via_api(b64cover):
    rng = np.random.default_rng(2)
    blobs = [("a.txt", rng.bytes(300)), ("b.bin", rng.bytes(200)), ("a.txt", b"trung ten"), ("rong.txt", b"")]
    r = api.api_embed({"image": b64cover, "password": PW, "method": "sequential", "files": [_f(n, d) for n, d in blobs]})
    assert r["stats"]["file_count"] == 4 and r["stats"]["message_bytes"] == 300 + 200 + 9
    out = api.api_extract({"image": r["stego_png"], "password": PW})
    assert out["kind"] == "file" and out["size"] == 509
    assert [f["filename"] for f in out["files"]] == ["a.txt", "b.bin", "a (2).txt", "rong.txt"]
    assert [base64.b64decode(f["data_b64"]) for f in out["files"]] == [d for _, d in blobs]
    assert [f["size"] for f in out["files"]] == [300, 200, 9, 0]


@pytest.mark.parametrize("files", [[], "abc", [1], [{"filename": "a"}, 5]])
def test_api_rejects_malformed_file_lists(b64cover, files):
    with pytest.raises(StegoError):
        api.api_embed({"image": b64cover, "password": PW, "files": files})


def test_api_rejects_too_many_files_and_too_much_data(b64cover, monkeypatch):
    with pytest.raises(StegoError, match="tối đa"):
        api.api_embed({"image": b64cover, "password": PW, "files": [_f(f"{i}.txt", b"x") for i in range(257)]})
    monkeypatch.setattr(api, "MAX_FILE_BYTES", 10)
    with pytest.raises(StegoError, match="quá lớn"):
        api.api_embed({"image": b64cover, "password": PW, "files": [_f("a", b"x" * 6), _f("b", b"y" * 6)]})


def test_api_errors_are_stego_errors(b64cover):
    with pytest.raises(ImageError):
        api.api_capacity({})
    with pytest.raises(ImageError):
        api.api_capacity({"image": base64.b64encode(b"not an image").decode()})
    with pytest.raises(StegoError):
        api.api_embed({"image": b64cover, "password": PW, "message": ""})
    with pytest.raises(StegoError):
        api.api_embed({"image": b64cover, "password": "", "message": "x"})
    r = api.api_embed({"image": b64cover, "password": PW, "message": "x"})
    with pytest.raises(StegoError):
        api.api_extract({"image": r["stego_png"], "password": "sai"})


def test_api_rejects_oversized_image():
    big = Image.new("RGB", (4100, 4100))     # ~16.8 megapixel > giới hạn 16
    buf = io.BytesIO(); big.save(buf, format="PNG")
    with pytest.raises(ImageError, match="quá lớn"):
        api.decode_image(base64.b64encode(buf.getvalue()).decode())


def test_analyze_and_compare_api(b64cover):
    a = api.api_analyze({"image": b64cover})
    assert a["level"] in ("none", "medium", "high") and a["width"] == 128
    assert base64.b64decode(a["lsb_png"])[:4] == b"\x89PNG"
    r = api.api_embed({"image": b64cover, "password": PW, "message": "so sánh"})
    c = api.api_compare({"cover": b64cover, "stego": r["stego_png"]})
    assert c["metrics"]["changed_samples"] == r["metrics"]["changed_samples"] > 0
    same = api.api_compare({"cover": b64cover, "stego": b64cover})
    assert same["metrics"]["identical"] is True and api.clean(same["metrics"])["psnr_db"] is None
    with pytest.raises(StegoError, match="khác kích thước"):
        api.api_compare({"cover": b64cover, "stego": png_b64(textured(64, 64))})


def test_clean_makes_json_safe():
    out = api.clean({"a": float("nan"), "b": float("inf"), "c": [np.float64(1.5), np.int64(2), np.bool_(True)], "d": (1, 2)})
    json.dumps(out)    # không ném lỗi
    assert out["a"] is None and out["b"] is None and out["c"] == [1.5, 2, True]


def test_data_url_prefix_is_accepted(b64cover):
    assert api.api_capacity({"image": "data:image/png;base64," + b64cover})["width"] == 128


# --------------------------------------------------------------- máy chủ HTTP
@pytest.fixture
def server():
    srv = make_server("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown(); srv.server_close()


def http_req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read(); hdrs = dict(r.getheaders()); c.close()
    return r.status, hdrs, data


def post_json(port, path, obj, **kw):
    return http_req(port, "POST", path, json.dumps(obj), {"Content-Type": "application/json", **kw.get("headers", {})})


def test_server_serves_index_with_security_headers(server):
    status, h, body = http_req(server, "GET", "/")
    assert status == 200 and b"StegoVault" in body
    assert h["X-Content-Type-Options"] == "nosniff" and "default-src 'none'" in h["Content-Security-Policy"]
    assert h["Cache-Control"] == "no-store"


def test_server_full_embed_extract(server, b64cover):
    s, _, body = post_json(server, "/api/embed", {"image": b64cover, "password": PW, "message": "qua HTTP"})
    assert s == 200
    stego = json.loads(body)["stego_png"]
    s, _, body = post_json(server, "/api/extract", {"image": stego, "password": PW})
    assert s == 200 and json.loads(body)["text"] == "qua HTTP"


def test_server_returns_400_with_vietnamese_message_on_wrong_password(server, b64cover):
    stego = json.loads(post_json(server, "/api/embed", {"image": b64cover, "password": PW, "message": "x"})[2])["stego_png"]
    s, _, body = post_json(server, "/api/extract", {"image": stego, "password": "sai"})
    assert s == 400 and "Không giải mã được" in json.loads(body)["error"]


def test_server_rejects_foreign_host_header(server):
    s, _, _ = http_req(server, "GET", "/", headers={"Host": "evil.example"})
    assert s == 403
    s, _, _ = post_json(server, "/api/info", {}, headers={"Host": "evil.example"})
    assert s == 403


def test_server_rejects_non_json_and_bad_json_and_unknown_route(server):
    assert http_req(server, "POST", "/api/embed", "x=1", {"Content-Type": "application/x-www-form-urlencoded"})[0] == 415
    assert http_req(server, "POST", "/api/embed", "{not json", {"Content-Type": "application/json"})[0] == 400
    assert http_req(server, "POST", "/api/embed", "[1,2]", {"Content-Type": "application/json"})[0] == 400
    assert post_json(server, "/api/nope", {})[0] == 404
    assert http_req(server, "GET", "/nope")[0] == 404


def raw_exchange(port, payload: bytes) -> bytes:
    import socket
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(payload)
    chunks = []
    try:
        while True:
            c = s.recv(65536)
            if not c:
                break
            chunks.append(c)
    except socket.timeout:
        pass
    finally:
        s.close()
    return b"".join(chunks)


@pytest.mark.parametrize("head", [
    b"POST /api/embed HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: text/plain\r\nContent-Length: 3\r\n\r\nx=1",   # 415
    b"POST /api/embed HTTP/1.1\r\nHost: evil.example\r\nContent-Type: application/json\r\nContent-Length: 3\r\n\r\nx=1",  # 403
    b"POST /api/nope HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 3\r\n\r\nx=1",   # 404
])
def test_early_rejection_closes_connection_and_does_not_desync(server, head):
    """Hồi quy: từ chối sớm mà không đọc thân yêu cầu từng làm các byte thân bị hiểu thành yêu cầu kế tiếp."""
    data = raw_exchange(server, head + b"\r\nGET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    assert b"Connection: close" in data
    assert b"Bad request syntax" not in data and data.count(b"HTTP/1.0 ") + data.count(b"HTTP/1.1 ") == 1


def test_server_rejects_oversized_and_empty_bodies(server):
    c = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    c.putrequest("POST", "/api/embed")
    c.putheader("Content-Type", "application/json"); c.putheader("Content-Length", str(10 ** 10)); c.endheaders()
    assert c.getresponse().status == 413
    c.close()
    assert http_req(server, "POST", "/api/embed", "", {"Content-Type": "application/json"})[0] == 413


@pytest.mark.parametrize("path", ["/api/samples", "/samples/camera.png", "/samples/..%2fstegovault%2fcli.py",
                                  "/samples/../pytest.ini", "/samples/%2e%2e/pytest.ini", "/samples/a.png/../../x"])
def test_server_no_longer_serves_sample_files(server, path):
    """Giao diện không còn mục ảnh mẫu, nên máy chủ cũng không phục vụ file nào từ đĩa ngoài trang chính."""
    assert http_req(server, "GET", path)[0] == 404
