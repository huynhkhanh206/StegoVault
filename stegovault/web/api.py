"""Các hàm API thuần (dict -> dict) cho giao diện web; tách khỏi HTTP để dễ kiểm thử."""

from __future__ import annotations

import base64
import binascii
import io
import math
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image

from .. import __version__
from .. import crypto_layer as cl
from ..embed import METHOD_LABELS, METHODS, capacity_bytes, embed
from ..errors import ImageError, StegoError
from ..extract import extract
from ..image_io import load_rgb
from ..metrics import diff_stats
from ..steganalysis import analyze, lsb_plane_gray

MAX_PIXELS = 16_000_000      # chặn ảnh quá lớn (bảo vệ bộ nhớ máy người dùng)
SSIM_MAX_PIXELS = 6_000_000  # SSIM tốn bộ nhớ: bỏ qua với ảnh lớn hơn
MAX_FILE_BYTES = 64 * 1024 * 1024


# ------------------------------------------------------------------ tiện ích
def _b64decode(s: Any) -> bytes:
    if not isinstance(s, str) or not s:
        raise StegoError("Thiếu dữ liệu.")
    if s.startswith("data:") and "," in s:  # chấp nhận data URL
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        raise StegoError("Dữ liệu base64 không hợp lệ.") from None


def decode_image(b64: Any) -> Tuple[np.ndarray, bool]:
    """base64 -> (mảng RGB, có bị bỏ kênh alpha hay không)."""
    raw = _b64decode(b64) if b64 else None
    if raw is None:
        raise ImageError("Chưa chọn ảnh.")
    try:
        im = Image.open(io.BytesIO(raw))
    except Exception:
        raise ImageError("Không đọc được ảnh. Hãy dùng PNG, BMP hoặc JPG hợp lệ.") from None
    if im.width * im.height > MAX_PIXELS:
        raise ImageError(f"Ảnh quá lớn ({im.width}x{im.height}); giới hạn {MAX_PIXELS // 1_000_000} megapixel.")
    alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    return load_rgb(im), alpha


def encode_png(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def clean(obj: Any) -> Any:
    """Thay NaN/inf bằng None để JSON hợp lệ với trình duyệt."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return clean(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _metrics(cover: np.ndarray, stego: np.ndarray) -> Dict[str, Any]:
    d = diff_stats(cover, stego, with_ssim=cover.shape[0] * cover.shape[1] <= SSIM_MAX_PIXELS)
    return {
        "changed_samples": d["changed_samples"],
        "changed_ratio": d["changed_ratio"],
        "max_abs_diff": d["max_abs_diff"],
        "psnr_db": d["psnr_db"],       # inf -> None sau clean(): nghĩa là "giống hệt"
        "identical": d["changed_samples"] == 0,
        "ssim": d["ssim"],
    }


# ------------------------------------------------------------------- các API
def api_info(_req: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": __version__,
        "kdfs": list(cl.available_kdfs()),
        "methods": [{"id": m, "label": METHOD_LABELS[m]} for m in METHODS],
        "max_megapixels": MAX_PIXELS // 1_000_000,
    }


def api_capacity(req: Dict[str, Any]) -> Dict[str, Any]:
    arr, alpha = decode_image(req.get("image"))
    cap = capacity_bytes(arr.size)
    return {"width": arr.shape[1], "height": arr.shape[0], "capacity_bytes": cap, "alpha_dropped": alpha}


def api_embed(req: Dict[str, Any]) -> Dict[str, Any]:
    arr, alpha = decode_image(req.get("image"))
    password = req.get("password") or ""
    method = req.get("method") or "matching"
    kdf = req.get("kdf") or "scrypt"
    if req.get("file_b64"):
        data = _b64decode(req["file_b64"])
        if len(data) > MAX_FILE_BYTES:
            raise StegoError("File cần giấu quá lớn.")
        message, filename = data, str(req.get("filename") or "data.bin")
    else:
        message, filename = str(req.get("message") or ""), None
        if not message:
            raise StegoError("Hãy nhập tin nhắn hoặc chọn file cần giấu.")
    res = embed(arr, message, password, method=method, kdf=kdf, filename=filename)
    return {
        "stego_png": encode_png(res.stego),
        "width": arr.shape[1],
        "height": arr.shape[0],
        "alpha_dropped": alpha,
        "stats": {
            "method": method,
            "method_label": METHOD_LABELS[method],
            "kdf": kdf,
            "message_bytes": res.message_bytes,
            "container_bytes": res.container_bytes,
            "capacity_bytes": res.capacity_bytes,
            "utilization": res.utilization,
            "embedding_rate": res.embedding_rate,
            "bits_per_pixel": res.bits_per_pixel,
            "samples_changed": res.samples_changed,
        },
        "metrics": _metrics(arr, res.stego),
    }


def api_extract(req: Dict[str, Any]) -> Dict[str, Any]:
    arr, _ = decode_image(req.get("image"))
    res = extract(arr, req.get("password") or "", position_mode=req.get("mode") or "auto", kdf=req.get("kdf") or "auto")
    out: Dict[str, Any] = {"kdf": res.kdf, "position_mode": res.position_mode, "size": len(res.data)}
    if res.is_text:
        out.update(kind="text", text=res.text)
    else:
        out.update(kind="file", filename=res.filename, data_b64=base64.b64encode(res.data).decode("ascii"))
    return out


def api_analyze(req: Dict[str, Any]) -> Dict[str, Any]:
    arr, _ = decode_image(req.get("image"))
    rep = analyze(arr)
    rep["width"], rep["height"] = arr.shape[1], arr.shape[0]
    buf = io.BytesIO()
    Image.fromarray(lsb_plane_gray(arr), "L").save(buf, format="PNG")
    rep["lsb_png"] = base64.b64encode(buf.getvalue()).decode("ascii")
    return rep


def api_compare(req: Dict[str, Any]) -> Dict[str, Any]:
    a, _ = decode_image(req.get("cover"))
    b, _ = decode_image(req.get("stego"))
    if a.shape != b.shape:
        raise StegoError(f"Hai ảnh khác kích thước ({a.shape[1]}x{a.shape[0]} và {b.shape[1]}x{b.shape[0]}).")
    changed = (a != b).any(axis=2)
    buf = io.BytesIO()
    Image.fromarray((changed * 255).astype(np.uint8), "L").save(buf, format="PNG")
    return {
        "metrics": _metrics(a, b),
        "width": a.shape[1],
        "height": a.shape[0],
        "diff_png": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


ROUTES = {
    "/api/info": api_info,
    "/api/capacity": api_capacity,
    "/api/embed": api_embed,
    "/api/extract": api_extract,
    "/api/analyze": api_analyze,
    "/api/compare": api_compare,
}
