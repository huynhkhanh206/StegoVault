"""Thí nghiệm 4 - Hai hình trực quan.

Hình A: mặt phẳng LSB của ảnh gốc và ảnh sau khi nhúng (tỉ lệ 50%) bằng ba phương pháp.
Hình B: đường cong chi-square theo tiền tố (Westfeld & Pfitzmann) - nhúng tuần tự để lại "bậc thang" đặc trưng.
"""

from __future__ import annotations

import numpy as np

from common import SAMPLES, ensure_results

from stegovault import plotstyle as ps
from stegovault import steganalysis as sa
from stegovault.embed import simulate_embedding
from stegovault.image_io import load_rgb

METHODS = ["sequential", "keyed", "matching"]


def figure_planes(cover: np.ndarray, path, rate: float = 0.5) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ps.apply_style()
    rng = np.random.default_rng(21)
    panels = [("Ảnh gốc", cover)] + [(ps.METHOD_NAMES[m], simulate_embedding(cover, rate, m, rng)) for m in METHODS]
    fig, axes = plt.subplots(1, 4, figsize=(13.6, 4.9))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.78, bottom=0.04, wspace=0.03)
    for ax, (title, img) in zip(axes, panels):
        ax.imshow(sa.lsb_plane_gray(img), cmap="gray", vmin=0, vmax=255, interpolation="nearest")
        ax.set_title(title, loc="left", fontsize=11, pad=7)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle("Mặt phẳng bit thấp nhất, trước và sau khi nhúng 50% dung lượng", x=0.01, ha="left", y=0.97, fontsize=14, fontweight="bold")
    fig.text(0.01, 0.865,
             "Nhúng tuần tự phá nửa trên của ảnh thành nhiễu đều, nửa dưới còn nguyên cấu trúc. Hai phương pháp rải theo khóa cho mặt phẳng LSB "
             "giống hệt nhau: khác biệt của matching chỉ lộ ra ở thống kê cặp giá trị.",
             ha="left", fontsize=9.2, color=ps.INK2, wrap=True)
    fig.savefig(path)
    plt.close(fig)


def figure_curve(cover: np.ndarray, path, rate: float = 0.5) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ps.apply_style()
    rng = np.random.default_rng(22)
    fig, ax = plt.subplots(figsize=(9.6, 5.0))
    fig.subplots_adjust(left=0.085, right=0.975, top=0.77, bottom=0.14)

    fr, p0 = sa.chi_square_progressive(cover, n_points=60)
    p0 = np.array([np.nan if v is None else v for v in p0])
    ax.plot(fr * 100, p0, color=ps.MUTED, linewidth=2.0, label="Ảnh gốc (chưa nhúng)", **{**ps.MARKER, "markersize": 5})
    for m in METHODS:
        s = simulate_embedding(cover, rate, m, rng)
        _, p = sa.chi_square_progressive(s, n_points=60)
        p = np.array([np.nan if v is None else v for v in p])
        ax.plot(fr * 100, p, color=ps.METHOD_COLORS[m], label=ps.METHOD_NAMES[m], **{**ps.MARKER, "markersize": 5})
    ax.axhline(sa.CHI_ALPHA, color=ps.MUTED, linewidth=1.0)
    ax.text(101, sa.CHI_ALPHA + 0.02, f"ngưỡng α = {sa.CHI_ALPHA}", ha="right", va="bottom", fontsize=8.5, color=ps.INK2)
    ax.axvline(rate * 100, color=ps.AXIS, linewidth=1.0)
    ax.text(rate * 100 - 1.2, 0.55, "tin kết thúc ở đây\n(với nhúng tuần tự)", fontsize=8.5, color=ps.INK2, va="center", ha="right")
    ax.set_xlim(0, 102); ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("Phần ảnh đã xét, tính từ đầu dãy mẫu (%)")
    ax.set_ylabel("p-value chi-square (cao = nghi có tin giấu)")
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.98), ncol=1)
    fig.suptitle("Dấu vết đặc trưng của nhúng tuần tự", x=0.03, ha="left", y=0.965, fontsize=14, fontweight="bold")
    fig.text(0.03, 0.915,
             f"Ảnh camera 512×512, nhúng {int(rate * 100)}% dung lượng. Chỉ nhúng tuần tự giữ p-value cao suốt đoạn đã nhúng "
             "rồi tụt xuống; ảnh gốc và hai phương pháp rải theo khóa nằm sát 0, chồng lên nhau.",
             ha="left", va="top", fontsize=9.5, color=ps.INK2, wrap=True)
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    out = ensure_results()
    figure_planes(load_rgb(SAMPLES / "astronaut.png"), out / "lsb_planes.png")
    figure_curve(load_rgb(SAMPLES / "camera.png"), out / "chi_square_curve.png")
    print(f"-> {out / 'lsb_planes.png'}\n-> {out / 'chi_square_curve.png'}")


if __name__ == "__main__":
    print("Thí nghiệm 4: hình trực quan")
    main()
