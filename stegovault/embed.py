"""Giấu tin: mã hóa rồi nhúng vào các bit LSB của ảnh.

Bố cục luồng bit nhúng
----------------------
    mẫu 0..159          : "bootstrap" = salt (16B) || độ dài đã che (4B), nhúng tuần tự
    mẫu 160..N-1        : "thân"      = nonce (12B) || ciphertext || thẻ GCM (16B)
                          - sequential: lần lượt từ mẫu 160
                          - keyed / matching: tại các vị trí do hoán vị theo khóa quyết định

Ba phương pháp
--------------
    sequential : LSB replacement, nhúng tuần tự          (dễ làm, dễ bị dò nhất)
    keyed      : LSB replacement, vị trí rải ngẫu nhiên theo khóa
    matching   : LSB matching (±1), vị trí rải ngẫu nhiên theo khóa  (khó bị dò nhất)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

from . import crypto_layer as cl
from .errors import CapacityError, StegoError
from .image_io import ImageLike, load_rgb
from .lsb import bytes_to_bits, write_bits
from .permutation import keyed_positions

# tên phương pháp -> (chế độ ghi bit, cách chọn vị trí)
METHODS = {
    "sequential": ("replace", "sequential"),
    "keyed": ("replace", "keyed"),
    "matching": ("match", "keyed"),
}
POSITION_MODES = ("keyed", "sequential")

METHOD_LABELS = {
    "sequential": "LSB tuần tự",
    "keyed": "LSB rải ngẫu nhiên theo khóa",
    "matching": "LSB matching (±1) rải theo khóa",
}


def capacity_bytes(image: Union[ImageLike, int]) -> int:
    """Số byte tối đa của gói dữ liệu (trước khi mã hóa) mà ảnh chứa được.

    ``image`` có thể là ảnh/đường dẫn hoặc trực tiếp số mẫu (H*W*3).
    Dung lượng cho tin nhắn thực tế nhỏ hơn 2 byte (tiêu đề gói) - và lớn hơn nếu nén được.
    """
    n_samples = image if isinstance(image, int) else load_rgb(image).size
    return max(0, (n_samples - cl.BOOTSTRAP_BITS) // 8 - cl.OVERHEAD)


def payload_positions(n_samples: int, n_bits: int, key_pos: bytes, position_mode: str) -> np.ndarray:
    """Vị trí (chỉ số mẫu) của ``n_bits`` bit thân, luôn nằm sau vùng bootstrap."""
    room = n_samples - cl.BOOTSTRAP_BITS
    if n_bits > room:
        raise CapacityError("Số bit cần nhúng vượt quá số mẫu còn trống của ảnh.")
    if position_mode == "sequential":
        rel = np.arange(n_bits, dtype=np.int64)
    elif position_mode == "keyed":
        rel = keyed_positions(key_pos, room, n_bits)
    else:
        raise StegoError(f"Cách chọn vị trí không hợp lệ: {position_mode!r}")
    return cl.BOOTSTRAP_BITS + rel


@dataclass
class EmbedResult:
    stego: np.ndarray
    method: str
    kdf: str
    message_bytes: int      # kích thước dữ liệu người dùng (trước nén)
    container_bytes: int    # sau đóng gói/nén, trước mã hóa
    embedded_bits: int      # tổng bit đã nhúng (gồm bootstrap)
    samples_changed: int    # số mẫu thực sự bị đổi giá trị
    n_samples: int
    capacity_bytes: int

    @property
    def embedding_rate(self) -> float:
        """Bit nhúng trên mỗi mẫu (= bit/kênh màu). 1.0 = nhúng kín ảnh."""
        return self.embedded_bits / self.n_samples

    @property
    def bits_per_pixel(self) -> float:
        return self.embedding_rate * 3

    @property
    def utilization(self) -> float:
        return self.container_bytes / self.capacity_bytes if self.capacity_bytes else float("inf")


def embed(
    cover: ImageLike,
    message: Union[str, bytes],
    password: str,
    *,
    method: str = "matching",
    kdf: str = "scrypt",
    filename: Optional[str] = None,
    compress: bool = True,
    rng: Optional[np.random.Generator] = None,
) -> EmbedResult:
    """Mã hóa ``message`` bằng ``password`` và giấu vào ảnh ``cover``.

    ``message``: ``str`` -> tin nhắn văn bản; ``bytes`` -> một file (kèm ``filename``).
    ``rng``: chỉ ảnh hưởng tới dấu ±1 của phương pháp matching (không cần để giải mã).
    """
    if method not in METHODS:
        raise StegoError(f"Phương pháp không hợp lệ: {method!r}. Chọn một trong {list(METHODS)}.")
    arr = load_rgb(cover)
    flat = arr.reshape(-1)

    if isinstance(message, str):
        kind, data = cl.KIND_TEXT, message.encode("utf-8")
    elif isinstance(message, (bytes, bytearray)):
        kind, data = cl.KIND_FILE, bytes(message)
    else:
        raise TypeError("message phải là str (văn bản) hoặc bytes (file).")

    plain = cl.pack_payload(data, kind, filename, compress)
    cap = capacity_bytes(flat.size)
    if len(plain) > cap:
        raise CapacityError(
            f"Tin quá lớn: cần {len(plain):,} byte (sau nén) nhưng ảnh này chỉ chứa tối đa {cap:,} byte. "
            "Hãy dùng ảnh lớn hơn hoặc rút ngắn tin."
        )

    sealed = cl.seal(plain, password, kdf)
    write_mode, position_mode = METHODS[method]

    boot_bits = bytes_to_bits(sealed.bootstrap)
    body_bits = bytes_to_bits(sealed.body)
    positions = np.concatenate(
        [
            np.arange(cl.BOOTSTRAP_BITS, dtype=np.int64),
            payload_positions(flat.size, body_bits.size, sealed.keys.pos, position_mode),
        ]
    )
    bits = np.concatenate([boot_bits, body_bits])
    new_flat, changed = write_bits(flat, positions, bits, write_mode, rng)

    return EmbedResult(
        stego=new_flat.reshape(arr.shape),
        method=method,
        kdf=kdf,
        message_bytes=len(data),
        container_bytes=len(plain),
        embedded_bits=int(bits.size),
        samples_changed=changed,
        n_samples=flat.size,
        capacity_bytes=cap,
    )


def simulate_embedding(
    cover: np.ndarray,
    rate: float,
    method: str,
    rng: np.random.Generator,
) -> np.ndarray:
    """Nhúng ``rate`` * (số mẫu) bit NGẪU NHIÊN (không qua KDF) - dùng cho thí nghiệm.

    Bản mã AES-GCM không thể phân biệt với bit ngẫu nhiên đều, nên mô phỏng này cho cùng
    thống kê với nhúng thật nhưng nhanh hơn nhiều (không tốn thời gian scrypt).
    """
    if method not in METHODS:
        raise StegoError(f"Phương pháp không hợp lệ: {method!r}")
    flat = cover.reshape(-1)
    n_bits = int(min(max(rate, 0.0) * flat.size, flat.size - cl.BOOTSTRAP_BITS))
    write_mode, position_mode = METHODS[method]
    key = rng.bytes(32)
    positions = np.concatenate(
        [
            np.arange(cl.BOOTSTRAP_BITS, dtype=np.int64),
            payload_positions(flat.size, n_bits, key, position_mode),
        ]
    )
    bits = rng.integers(0, 2, size=positions.size, dtype=np.uint8)
    new_flat, _ = write_bits(flat, positions, bits, write_mode, rng)
    return new_flat.reshape(cover.shape)
