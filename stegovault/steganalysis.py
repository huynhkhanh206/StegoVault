"""Steganalysis - phía người dò: phát hiện ảnh có giấu tin bằng LSB.

Gồm ba công cụ:

1. ``lsb_plane``          : trực quan hóa mặt phẳng bit thấp nhất.
2. ``chi_square_*``       : tấn công chi-square của Westfeld & Pfitzmann (2000).
3. ``rs_analysis``        : phân tích RS của Fridrich, Goljan & Du (2001) - ước lượng độ dài tin.

Giới hạn (cần nói rõ khi báo cáo): cả hai bài kiểm tra thống kê này nhắm vào *LSB replacement*.
LSB matching (±1) về cơ bản qua mặt được chúng; muốn dò nó cần các đặc trưng bậc cao hơn
(SPAM/SRM + bộ phân loại, hoặc mạng nơ-ron sâu).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.stats import chi2 as _chi2

# Ngưỡng quyết định mặc định
CHI_ALPHA = 0.05      # p-value (xác suất "các cặp giá trị đã cân bằng") > ngưỡng => nghi có tin giấu
RS_THRESHOLD = 0.05   # độ dài tin ước lượng (bit/mẫu) > ngưỡng => nghi có tin giấu
PROG_MIN_RUN = 3      # chi-square tiền tố: cần ít nhất ngần này điểm LIÊN TIẾP có p > CHI_ALPHA


# --------------------------------------------------------------- mặt phẳng LSB
def lsb_plane(arr: np.ndarray, channel: int | None = None) -> np.ndarray:
    """Ảnh 0/255 của mặt phẳng LSB. ``channel=None`` -> trả về ảnh RGB gồm LSB của 3 kênh."""
    if channel is None:
        return ((arr & 1) * 255).astype(np.uint8)
    return ((arr[..., channel] & 1) * 255).astype(np.uint8)


def lsb_plane_gray(arr: np.ndarray) -> np.ndarray:
    """Ảnh xám 4 mức: tổng bit LSB của 3 kênh (0, 85, 170, 255). Gọn và dễ nhìn hơn ảnh RGB."""
    return ((arr & 1).sum(axis=2) * 85).astype(np.uint8)


# ----------------------------------------------------------------- chi-square
@dataclass(frozen=True)
class ChiResult:
    chi2: float
    df: int
    p: float  # xác suất để các cặp (2k, 2k+1) có tần suất bằng nhau; gần 1 = nghi có tin giấu


def _chi_from_hist(hist: np.ndarray, min_expected: float = 5.0) -> ChiResult:
    even, odd = hist[0::2], hist[1::2]
    expected = (even + odd) / 2.0
    keep = expected >= min_expected      # bỏ các cặp quá ít mẫu (xấp xỉ chi-square kém)
    k = int(keep.sum())
    if k < 2:
        return ChiResult(float("nan"), 0, float("nan"))
    stat = float((((even[keep] - expected[keep]) ** 2) / expected[keep]).sum())
    return ChiResult(stat, k - 1, float(_chi2.sf(stat, k - 1)))


def chi_square_pov(values: np.ndarray, min_expected: float = 5.0) -> ChiResult:
    """Kiểm định chi-square "cặp giá trị" (pairs of values) trên các mẫu ``values``.

    Ý tưởng: sau khi ghi đè LSB bằng bit ngẫu nhiên, mỗi cặp (2k, 2k+1) có tần suất gần bằng nhau.
    Ảnh tự nhiên gốc thì không như vậy -> thống kê chi-square rất lớn -> p ≈ 0.
    """
    hist = np.bincount(np.asarray(values).reshape(-1), minlength=256).astype(np.float64)
    return _chi_from_hist(hist, min_expected)


def chi_square_progressive(
    arr: np.ndarray, n_points: int = 40, start_fraction: float = 0.02
) -> Tuple[np.ndarray, np.ndarray]:
    """p-value của chi-square trên các "tiền tố" tăng dần của dãy mẫu (hình đặc trưng của Westfeld).

    Với nhúng tuần tự, p ≈ 1 trong vùng đã nhúng rồi tụt xuống đúng chỗ tin kết thúc.
    Trả về (phần trăm ảnh đã xét, p-value) - cả hai là mảng 1 chiều cùng độ dài.
    """
    flat = arr.reshape(-1)
    n = flat.size
    edges = np.unique(np.linspace(max(int(n * start_fraction), 256), n, n_points).astype(np.int64))
    hist = np.zeros(256, dtype=np.float64)
    prev = 0
    fractions, ps = [], []
    for e in edges:
        hist += np.bincount(flat[prev:e], minlength=256)
        prev = int(e)
        fractions.append(e / n)
        ps.append(_chi_from_hist(hist).p)
    return np.array(fractions), np.array(ps)


# -------------------------------------------------------------------- RS
def _disc(groups: np.ndarray) -> np.ndarray:
    """Hàm "độ mượt" của nhóm: tổng |chênh lệch| giữa các mẫu liền kề."""
    return np.abs(np.diff(groups, axis=1)).sum(axis=1)


def _flip(groups: np.ndarray, cols: np.ndarray, sign: int) -> np.ndarray:
    out = groups.copy()
    if sign > 0:   # F1: 2k <-> 2k+1
        out[:, cols] = groups[:, cols] ^ 1
    else:          # F-1: 2k-1 <-> 2k (dịch lệch một đơn vị)
        out[:, cols] = ((groups[:, cols] + 1) ^ 1) - 1
    return out


def _rs_fractions(groups: np.ndarray, cols: np.ndarray) -> Tuple[float, float, float, float]:
    f0 = _disc(groups)
    fp, fn = _disc(_flip(groups, cols, +1)), _disc(_flip(groups, cols, -1))
    g = groups.shape[0]
    return (
        float((fp > f0).sum() / g), float((fp < f0).sum() / g),   # R_M,  S_M
        float((fn > f0).sum() / g), float((fn < f0).sum() / g),   # R_-M, S_-M
    )


def rs_analysis(arr: np.ndarray, group_size: int = 4) -> Dict[str, float]:
    """Ước lượng độ dài tin (bit/mẫu) bằng phân tích RS.

    Nhóm ``group_size`` mẫu liền kề được lật LSB theo mặt nạ M = [0,1,1,0]. Ở ảnh sạch, lật theo M
    làm nhóm "nhiễu hơn" (Regular) nhiều hơn "mượt hơn" (Singular), còn lật theo -M thì ngược lại
    - hai đại lượng đối xứng. Nhúng LSB phá vỡ sự đối xứng đó, và độ lệch cho phép giải ra tỉ lệ
    nhúng p qua một phương trình bậc hai.
    """
    if group_size != 4:
        raise ValueError("Bản cài đặt này dùng nhóm 4 mẫu với mặt nạ [0,1,1,0].")
    mask_cols = np.array([1, 2])
    per_channel = []
    for c in range(arr.shape[2]):
        v = arr[..., c].reshape(-1)
        g = v.size // group_size
        per_channel.append(v[: g * group_size].reshape(g, group_size).astype(np.int16))
    groups = np.concatenate(per_channel, axis=0)

    rm, sm, rn, sn = _rs_fractions(groups, mask_cols)
    rm1, sm1, rn1, sn1 = _rs_fractions(groups ^ 1, mask_cols)   # ảnh với TOÀN BỘ LSB bị lật
    d0, d_0 = rm - sm, rn - sn
    d1, d_1 = rm1 - sm1, rn1 - sn1

    a = 2.0 * (d1 + d0)
    b = d_0 - d_1 - d1 - 3.0 * d0
    c = d0 - d_0
    if abs(a) < 1e-12:
        x = -c / b if abs(b) > 1e-12 else 0.0
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            x = -b / (2 * a)
        else:
            r1, r2 = (-b + np.sqrt(disc)) / (2 * a), (-b - np.sqrt(disc)) / (2 * a)
            x = r1 if abs(r1) < abs(r2) else r2
    denom = x - 0.5
    p = x / denom if abs(denom) > 1e-12 else float("nan")
    return {
        "p": float(p),
        "p_clipped": float(min(max(p, 0.0), 1.0)) if np.isfinite(p) else float("nan"),
        "R_M": rm, "S_M": sm, "R_negM": rn, "S_negM": sn,
    }


# --------------------------------------------------------------- tổng hợp
def longest_run(mask: np.ndarray) -> int:
    """Độ dài đoạn True liên tiếp dài nhất của một mảng bool."""
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def progressive_flag(ps: np.ndarray, alpha: float = CHI_ALPHA, min_run: int = PROG_MIN_RUN) -> Tuple[bool, int]:
    """Chi-square tiền tố báo dương tính khi p-value > alpha TRÊN MỘT ĐOẠN LIÊN TIẾP >= min_run điểm.

    Lấy "p lớn nhất" trên ~40 điểm sẽ tự sinh dương tính giả (so sánh nhiều lần: chỉ cần một tiền tố
    ngắn ngẫu nhiên có p cao). Nhúng tuần tự thật sự thì p cao KÉO DÀI suốt đoạn đã nhúng.
    """
    ps = np.asarray(ps, dtype=float)
    run = longest_run(np.isfinite(ps) & (ps > alpha))
    return run >= min_run, run


def analyze(arr: np.ndarray, alpha: float = CHI_ALPHA, rs_threshold: float = RS_THRESHOLD) -> Dict:
    """Chạy toàn bộ bộ dò trên một ảnh và đưa ra kết luận (tiếng Việt)."""
    flat = arr.reshape(-1)
    chi = chi_square_pov(flat)
    fractions, ps = chi_square_progressive(arr)
    finite = np.isfinite(ps)
    p_max = float(np.max(ps[finite])) if finite.any() else float("nan")
    rs = rs_analysis(arr)

    chi_flag = bool(np.isfinite(chi.p) and chi.p > alpha)
    prog_flag, prog_run = progressive_flag(ps, alpha)
    rs_flag = bool(np.isfinite(rs["p"]) and rs["p"] > rs_threshold)
    n_flags = int(chi_flag or prog_flag) + int(rs_flag)

    if n_flags == 2:
        level = "high"
        verdict = "NGHI CAO có tin giấu bằng LSB replacement: cả chi-square lẫn RS đều báo dương tính."
    elif n_flags == 1:
        level = "medium"
        verdict = "NGHI NGỜ có tin giấu: một trong hai bài kiểm tra báo dương tính."
    else:
        level = "none"
        verdict = (
            "Không phát hiện dấu hiệu LSB replacement. Lưu ý: điều này KHÔNG chứng minh ảnh sạch - "
            "LSB matching hoặc kỹ thuật khác có thể qua mặt các bài kiểm tra này."
        )

    return {
        "n_samples": int(flat.size),
        "ones_ratio": float((flat & 1).mean()),
        "chi_square": {"chi2": chi.chi2, "df": chi.df, "p": chi.p, "flag": chi_flag},
        "progressive": {
            "fractions": fractions.tolist(),
            "p": [None if not np.isfinite(v) else float(v) for v in ps],
            "p_max": p_max,
            "longest_run": prog_run,
            "min_run": PROG_MIN_RUN,
            "n_points": int(len(ps)),
            "flag": prog_flag,
        },
        "rs": {**rs, "flag": rs_flag},
        "thresholds": {"chi_alpha": alpha, "rs": rs_threshold},
        "level": level,
        "verdict": verdict,
    }
