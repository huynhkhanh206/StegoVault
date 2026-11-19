"""Cấu hình chung cho test: hạ tham số KDF để chạy nhanh, và cung cấp vài ảnh bìa nhỏ."""

import numpy as np
import pytest

from stegovault import crypto_layer as cl

# Tham số mặc định THẬT (ghi lại trước khi bị hạ) - dùng để kiểm tra và cho test khứ hồi "đầy đủ".
DEFAULT_KDF = {
    "SCRYPT_N": cl.SCRYPT_N,
    "SCRYPT_R": cl.SCRYPT_R,
    "SCRYPT_P": cl.SCRYPT_P,
    "ARGON2_ITERATIONS": cl.ARGON2_ITERATIONS,
    "ARGON2_LANES": cl.ARGON2_LANES,
    "ARGON2_MEMORY_KIB": cl.ARGON2_MEMORY_KIB,
}


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    """KDF thật tốn 30-60 MiB mỗi lần gọi; hạ xuống để cả bộ test chạy trong vài giây."""
    monkeypatch.setattr(cl, "SCRYPT_N", 2 ** 10)
    monkeypatch.setattr(cl, "ARGON2_MEMORY_KIB", 64)
    monkeypatch.setattr(cl, "ARGON2_ITERATIONS", 1)


@pytest.fixture
def restore_default_kdf(monkeypatch):
    for k, v in DEFAULT_KDF.items():
        monkeypatch.setattr(cl, k, v)


def textured(h=96, w=96, seed=0):
    """Ảnh bìa tổng hợp có kết cấu giống ảnh tự nhiên: gradient mượt + nhiễu nhẹ (uint8, H×W×3)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    base = 110 + 50 * np.sin(x / 9.0) + 40 * np.cos(y / 7.0)
    img = np.stack([base + 10 * c for c in range(3)], axis=-1) + rng.normal(0, 2.0, (h, w, 3))
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


@pytest.fixture
def cover():
    return textured(96, 96, seed=1)


@pytest.fixture
def big_cover():
    return textured(256, 256, seed=2)
