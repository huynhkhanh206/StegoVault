"""Tiện ích dùng chung cho các thí nghiệm (chạy từ thư mục gốc dự án hoặc từ bất kỳ đâu)."""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from stegovault.image_io import load_rgb  # noqa: E402

SAMPLES = ROOT / "samples"
RESULTS = ROOT / "results"
SAMPLE_NAMES = ["astronaut", "camera", "coffee", "chelsea", "rocket", "retina"]


def ensure_results() -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    return RESULTS


def load_samples() -> Dict[str, np.ndarray]:
    return {n: load_rgb(SAMPLES / f"{n}.png") for n in SAMPLE_NAMES}


def random_crops(per_image: int, size: int = 256, seed: int = 2026) -> List[Tuple[str, np.ndarray]]:
    """Cắt ngẫu nhiên ``per_image`` mảnh size×size từ mỗi ảnh mẫu (không resample nên không đổi thống kê LSB).

    Lưu ý: các mảnh cùng một ảnh gốc không độc lập hoàn toàn - phải nói rõ điều này khi báo cáo.
    """
    rng = np.random.default_rng(seed)
    out: List[Tuple[str, np.ndarray]] = []
    for name, img in load_samples().items():
        h, w = img.shape[:2]
        for k in range(per_image):
            y = int(rng.integers(0, h - size + 1))
            x = int(rng.integers(0, w - size + 1))
            out.append((f"{name}#{k}", np.ascontiguousarray(img[y : y + size, x : x + size])))
    return out


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Khoảng tin cậy Wilson 95% cho tỉ lệ k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def md_table(header: Sequence[str], rows: Iterable[Sequence]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def pct(x: float, nd: int = 0) -> str:
    return f"{x * 100:.{nd}f}%"
