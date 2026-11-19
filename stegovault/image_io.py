"""Đọc / ghi ảnh dưới dạng mảng numpy RGB 8-bit.

Quy ước: mọi thuật toán làm việc trên mảng uint8 hình (H, W, 3). Chỉ số mẫu (sample) là
    index = (y * W + x) * 3 + kênh
tức là mảng được "làm phẳng" theo thứ tự hàng -> cột -> kênh màu.
"""

from __future__ import annotations

import os
from typing import Union

import numpy as np
from PIL import Image

from .errors import ImageError

ImageLike = Union[str, "os.PathLike[str]", Image.Image, np.ndarray]

# Định dạng ĐẦU RA phải không mất dữ liệu; JPEG/WebP sẽ phá hủy các bit LSB.
LOSSLESS_SUFFIXES = {".png": "PNG", ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF"}


def load_rgb(src: ImageLike) -> np.ndarray:
    """Trả về mảng uint8 (H, W, 3) liên tục trong bộ nhớ.

    - Ảnh RGBA / LA / palette được đổi sang RGB (kênh alpha bị bỏ).
    - Ảnh 16-bit hoặc dấu phẩy động chưa được hỗ trợ (sẽ mất độ chính xác khi đổi sang 8-bit).
    """
    if isinstance(src, np.ndarray):
        arr = src
        if arr.dtype != np.uint8 or arr.ndim != 3 or arr.shape[2] != 3:
            raise ImageError("Mảng ảnh phải có dtype uint8 và hình (H, W, 3).")
        return np.ascontiguousarray(arr)

    try:
        im = src if isinstance(src, Image.Image) else Image.open(src)
        im.load()
    except FileNotFoundError:
        raise ImageError(f"Không tìm thấy file ảnh: {src}") from None
    except Exception as exc:  # PIL ném nhiều loại lỗi khác nhau
        raise ImageError(f"Không đọc được ảnh: {exc}") from None

    if im.mode in ("I;16", "I;16L", "I;16B", "I", "F"):
        raise ImageError("Ảnh 16-bit / dấu phẩy động chưa được hỗ trợ. Hãy dùng ảnh 8-bit mỗi kênh.")
    return np.ascontiguousarray(np.array(im.convert("RGB"), dtype=np.uint8))


def has_alpha(src: ImageLike) -> bool:
    """True nếu ảnh gốc có kênh alpha / độ trong suốt (sẽ bị bỏ khi chuyển sang RGB)."""
    if isinstance(src, np.ndarray):
        return False
    try:
        im = src if isinstance(src, Image.Image) else Image.open(src)
        return im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    except Exception:
        return False


def save_lossless(arr: np.ndarray, path: Union[str, "os.PathLike[str]"]) -> str:
    """Lưu ảnh bằng định dạng không mất dữ liệu (PNG/BMP/TIFF). Trả về đường dẫn đã lưu."""
    path = os.fspath(path)
    suffix = os.path.splitext(path)[1].lower()
    if suffix not in LOSSLESS_SUFFIXES:
        raise ImageError(
            f"Định dạng '{suffix or '(không có đuôi)'}' làm mất dữ liệu ẩn. "
            "Hãy lưu ảnh đầu ra là .png (khuyến nghị), .bmp hoặc .tiff."
        )
    Image.fromarray(arr, "RGB").save(path, format=LOSSLESS_SUFFIXES[suffix])
    return path


def to_png_bytes(arr: np.ndarray) -> bytes:
    """Mã hóa mảng RGB thành bytes PNG (dùng cho giao diện web)."""
    import io

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()
