"""Hoán vị giả ngẫu nhiên theo khóa trên [0, size) - dùng để chọn vị trí nhúng bit.

Vì sao không dùng ``numpy.random``?
    Dòng số ngẫu nhiên của numpy không được đảm bảo giống nhau giữa các phiên bản. Nếu người
    giấu tin và người trích xuất dùng hai phiên bản numpy khác nhau, vị trí bit sẽ lệch và
    tin không đọc lại được. Ở đây ta tự xây một hoán vị xác định hoàn toàn từ khóa.

Cách làm:
    * Mạng Feistel cân bằng (6 vòng) trên miền 2^(2h) >= size.
    * Hàm vòng F_k(x) = 4 byte đầu của AES-128(k_vòng, x)  (PRF an toàn mật mã).
    * "Cycle walking": nếu kết quả rơi ngoài [0, size) thì áp dụng hoán vị tiếp cho tới khi
      vào trong miền  ->  vẫn là song ánh trên đúng [0, size).
    * Tính theo lô bằng numpy nên nhanh, và chỉ cần bộ nhớ O(số bit cần nhúng) thay vì
      xáo trộn cả mảng hàng chục triệu phần tử.
"""

from __future__ import annotations

import hashlib
from typing import List

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROUNDS = 6
CHUNK = 1 << 20   # số chỉ số xử lý mỗi lô (bộ nhớ tạm ≈ 16 MiB cho khối AES + vài mảng 8 MiB)


def _round_keys(key: bytes) -> List[bytes]:
    return [
        hashlib.sha256(key + b"stegovault/feistel" + bytes([r])).digest()[:16]
        for r in range(ROUNDS)
    ]


def _prf(round_key: bytes, values: np.ndarray, mask: np.uint64) -> np.ndarray:
    """F(values) = 4 byte đầu của AES_ECB(round_key, values || 0...), rồi che bằng mask."""
    n = values.size
    if n == 0:
        return values.copy()
    blocks = np.zeros((n, 16), dtype=np.uint8)
    blocks[:, :8] = values.astype("<u8").view(np.uint8).reshape(n, 8)
    enc = Cipher(algorithms.AES(round_key), modes.ECB()).encryptor()
    out = np.frombuffer(enc.update(blocks.tobytes()), dtype=np.uint8).reshape(n, 16)
    words = out[:, :4].copy().view("<u4").reshape(n).astype(np.uint64)
    return words & mask


class FeistelPermutation:
    """Hoán vị giả ngẫu nhiên P: [0, size) -> [0, size), xác định bởi ``key``."""

    def __init__(self, key: bytes, size: int):
        if size < 1:
            raise ValueError("size phải >= 1")
        self.size = int(size)
        bits = max(2, (self.size - 1).bit_length())
        if bits % 2:
            bits += 1
        self.half = bits // 2
        self._shift = np.uint64(self.half)
        self._mask = np.uint64((1 << self.half) - 1)
        self._keys = _round_keys(key)

    def _feistel(self, x: np.ndarray) -> np.ndarray:
        left = x >> self._shift
        right = x & self._mask
        for k in self._keys:
            left, right = right, left ^ _prf(k, right, self._mask)
        return (left << self._shift) | right

    def _map_chunk(self, x: np.ndarray) -> np.ndarray:
        y = self._feistel(x)
        limit = np.uint64(self.size)
        bad = y >= limit
        while bad.any():  # cycle walking
            y[bad] = self._feistel(y[bad])
            bad = y >= limit
        return y

    def map(self, indices) -> np.ndarray:
        """Áp dụng hoán vị lên mảng chỉ số (mỗi giá trị phải nằm trong [0, size)).

        Xử lý theo lô ``CHUNK`` phần tử: bộ nhớ tạm không phụ thuộc số lượng chỉ số. Hàm là phép tính theo
        từng phần tử nên kết quả y hệt bản xử lý một lượt (ảnh đã giấu bằng bản cũ vẫn giải mã được).
        """
        x = np.asarray(indices, dtype=np.uint64).reshape(-1)
        out = np.empty(x.size, dtype=np.int64)
        for start in range(0, x.size, CHUNK):
            out[start : start + CHUNK] = self._map_chunk(x[start : start + CHUNK])
        return out


def keyed_positions(key: bytes, size: int, count: int) -> np.ndarray:
    """``count`` vị trí KHÁC NHAU trong [0, size), thứ tự giả ngẫu nhiên theo ``key``."""
    if count > size:
        raise ValueError("count không được vượt quá size")
    return FeistelPermutation(key, size).map(np.arange(count, dtype=np.uint64))
