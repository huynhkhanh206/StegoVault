"""Thao tác bit mức thấp trên mảng mẫu uint8 đã làm phẳng.

Hai cách sửa một mẫu để bit LSB của nó trở thành bit cần giấu:

* ``replace`` (LSB replacement): ghi đè thẳng bit thấp nhất.
  Hệ quả thống kê: hai giá trị (2k, 2k+1) bị "hoán đổi" qua lại nên tần suất của chúng
  tiến dần về bằng nhau  ->  bị tấn công chi-square / RS phát hiện.

* ``match`` (LSB matching, còn gọi ±1 embedding): nếu LSB chưa đúng thì cộng hoặc trừ 1
  (ngẫu nhiên). LSB cũng đúng như mong muốn, nhưng mẫu có thể dịch sang giá trị lân cận
  cả hai phía nên không tạo ra hiện tượng "cặp giá trị cân bằng" -> qua mặt chi-square.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def bytes_to_bits(data: bytes) -> np.ndarray:
    """bytes -> mảng bit uint8 (bit cao trước)."""
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """Mảng bit -> bytes (độ dài bit phải chia hết cho 8, nếu không sẽ được đệm số 0)."""
    return np.packbits(np.asarray(bits, dtype=np.uint8)).tobytes()


def read_bits(flat: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Đọc bit LSB tại các vị trí đã cho."""
    return (flat[positions] & 1).astype(np.uint8)


def write_bits(
    flat: np.ndarray,
    positions: np.ndarray,
    bits: np.ndarray,
    mode: str = "replace",
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, int]:
    """Ghi ``bits`` vào LSB của ``flat`` tại ``positions``.

    Không sửa mảng gốc. Trả về (mảng mới, số mẫu thực sự bị thay đổi).
    ``positions`` phải gồm các chỉ số KHÔNG trùng nhau.
    """
    if positions.shape != bits.shape:
        raise ValueError("positions và bits phải cùng độ dài")
    out = flat.copy()
    need = (out[positions] & 1) != bits  # chỉ những mẫu có LSB sai mới phải sửa
    idx = positions[need]

    if mode == "replace":
        out[idx] ^= 1
    elif mode == "match":
        rng = rng if rng is not None else np.random.default_rng()
        vals = out[idx].astype(np.int16)
        delta = np.where(rng.random(idx.size) < 0.5, 1, -1).astype(np.int16)
        delta[vals == 0] = 1      # không thể trừ khỏi 0
        delta[vals == 255] = -1   # không thể cộng vào 255
        out[idx] = (vals + delta).astype(np.uint8)
    else:
        raise ValueError(f"mode không hợp lệ: {mode!r}")
    return out, int(idx.size)
