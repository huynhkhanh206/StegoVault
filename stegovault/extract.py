"""Trích xuất và giải mã tin giấu trong ảnh."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from . import crypto_layer as cl
from .embed import POSITION_MODES, payload_positions
from .errors import DecryptionError, StegoError
from .image_io import ImageLike, load_rgb
from .lsb import bits_to_bytes, read_bits


@dataclass
class ExtractResult:
    payload: cl.Payload
    kdf: str
    position_mode: str  # "keyed" (gồm cả matching, không phân biệt được khi trích) hoặc "sequential"

    @property
    def is_text(self) -> bool:
        return self.payload.is_text

    @property
    def text(self) -> str:
        return self.payload.text()

    @property
    def is_bundle(self) -> bool:
        return self.payload.is_bundle

    @property
    def files(self) -> List[Tuple[str, bytes]]:
        """Mọi file lấy ra được, dạng (tên đã làm sạch, nội dung). Rỗng nếu gói là tin nhắn."""
        return self.payload.file_list()

    @property
    def data(self) -> bytes:
        if self.payload.is_bundle:
            raise StegoError("Gói này chứa nhiều file; hãy dùng .files.")
        return self.payload.data

    @property
    def filename(self) -> Optional[str]:
        if self.payload.is_bundle:
            raise StegoError("Gói này chứa nhiều file; hãy dùng .files.")
        return self.payload.filename


def extract(
    stego: ImageLike,
    password: str,
    *,
    position_mode: str = "auto",
    kdf: str = "auto",
) -> ExtractResult:
    """Trích tin từ ảnh. Mặc định tự dò KDF và cách chọn vị trí; thẻ GCM xác nhận kết quả đúng.

    Ném ``DecryptionError`` nếu sai mật khẩu / ảnh không chứa tin / ảnh đã bị chỉnh sửa.
    """
    arr = load_rgb(stego)
    flat = arr.reshape(-1)
    n = flat.size
    if n < cl.BOOTSTRAP_BITS + 8 * cl.OVERHEAD:
        raise DecryptionError("Ảnh quá nhỏ để chứa dữ liệu.")

    modes = POSITION_MODES if position_mode == "auto" else (position_mode,)
    if any(m not in POSITION_MODES for m in modes):
        raise StegoError(f"position_mode không hợp lệ: {position_mode!r}")
    kdfs = cl.available_kdfs() if kdf == "auto" else (kdf,)

    bootstrap = bits_to_bytes(read_bits(flat, np.arange(cl.BOOTSTRAP_BITS)))
    salt, masked = bootstrap[: cl.SALT_LEN], bootstrap[cl.SALT_LEN :]

    for kdf_name in kdfs:
        keys = cl.derive_keys(password, salt, kdf_name)
        body_len = cl.unmask_length(masked, keys)
        # Độ dài vô lý -> khóa sai (hoặc ảnh không chứa tin): bỏ qua, khỏi đọc cả ảnh.
        if body_len < cl.OVERHEAD or body_len * 8 > n - cl.BOOTSTRAP_BITS:
            continue
        for mode in modes:
            positions = payload_positions(n, body_len * 8, keys.pos, mode)
            body = bits_to_bytes(read_bits(flat, positions))
            try:
                plain = cl.open_sealed(bootstrap, body, keys)
            except DecryptionError:
                continue
            return ExtractResult(cl.unpack_payload(plain), kdf_name, mode)

    raise DecryptionError(
        "Không giải mã được: sai mật khẩu, ảnh không chứa dữ liệu, hoặc ảnh đã bị chỉnh sửa/nén lại."
    )
