"""Đo chất lượng ảnh sau khi nhúng: MSE, PSNR, SSIM và thống kê thay đổi.

Chỉ phụ thuộc numpy + scipy (SSIM tự cài đặt, khớp với scikit-image khi dùng cùng tham số).
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.ndimage import uniform_filter


def mse(a: np.ndarray, b: np.ndarray) -> float:
    d = a.astype(np.float64) - b.astype(np.float64)
    return float(np.mean(d * d))


def psnr(a: np.ndarray, b: np.ndarray, data_range: float = 255.0) -> float:
    """PSNR (dB). Hai ảnh giống hệt nhau -> +inf. Nhúng LSB thường cho > 50 dB."""
    m = mse(a, b)
    if m == 0:
        return float("inf")
    return float(10.0 * np.log10(data_range ** 2 / m))


def ssim(a: np.ndarray, b: np.ndarray, win_size: int = 7, data_range: float = 255.0) -> float:
    """Chỉ số tương đồng cấu trúc (Wang et al. 2004), cửa sổ đều, trung bình trên các kênh."""
    if a.shape != b.shape:
        raise ValueError("Hai ảnh phải cùng kích thước")
    if a.ndim == 2:
        a, b = a[..., None], b[..., None]
    if min(a.shape[0], a.shape[1]) < win_size:
        raise ValueError("Ảnh nhỏ hơn cửa sổ SSIM")
    k1, k2 = 0.01, 0.03
    c1, c2 = (k1 * data_range) ** 2, (k2 * data_range) ** 2
    npix = win_size ** 2
    cov_norm = npix / (npix - 1)  # hiệu chỉnh hiệp phương sai mẫu
    pad = (win_size - 1) // 2
    scores = []
    for ch in range(a.shape[2]):
        x = a[..., ch].astype(np.float64)
        y = b[..., ch].astype(np.float64)
        ux, uy = uniform_filter(x, win_size), uniform_filter(y, win_size)
        uxx, uyy, uxy = (
            uniform_filter(x * x, win_size),
            uniform_filter(y * y, win_size),
            uniform_filter(x * y, win_size),
        )
        vx, vy, vxy = cov_norm * (uxx - ux * ux), cov_norm * (uyy - uy * uy), cov_norm * (uxy - ux * uy)
        s = ((2 * ux * uy + c1) * (2 * vxy + c2)) / ((ux ** 2 + uy ** 2 + c1) * (vx + vy + c2))
        scores.append(s[pad:-pad, pad:-pad].mean())
    return float(np.mean(scores))


def diff_stats(cover: np.ndarray, stego: np.ndarray, with_ssim: bool = True) -> Dict[str, float]:
    """Thống kê so sánh ảnh gốc và ảnh đã nhúng (``with_ssim=False`` để bỏ SSIM cho ảnh rất lớn)."""
    if cover.shape != stego.shape:
        raise ValueError("Hai ảnh phải cùng kích thước")
    d = np.abs(cover.astype(np.int16) - stego.astype(np.int16))
    changed = int(np.count_nonzero(d))
    return {
        "samples": int(cover.size),
        "changed_samples": changed,
        "changed_ratio": changed / cover.size,
        "max_abs_diff": int(d.max()),
        "mse": mse(cover, stego),
        "psnr_db": psnr(cover, stego),
        "ssim": ssim(cover, stego) if with_ssim else float("nan"),
    }
