"""Hình báo cáo steganalysis cho một ảnh (cần matplotlib)."""

from __future__ import annotations

import numpy as np

from .steganalysis import CHI_ALPHA, analyze, lsb_plane_gray


def make_report(arr: np.ndarray, path: str, title: str = "") -> dict:
    """Vẽ 3 khung: ảnh, mặt phẳng LSB, đường cong p-value chi-square theo tiền tố. Trả về kết quả phân tích."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from . import plotstyle as ps

    ps.apply_style()
    rep = analyze(arr)
    fr = np.array(rep["progressive"]["fractions"]) * 100
    pv = np.array([np.nan if v is None else v for v in rep["progressive"]["p"]])

    fig = plt.figure(figsize=(13, 4.8))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.25], wspace=0.14, left=0.03, right=0.985, top=0.80, bottom=0.14)

    ax = fig.add_subplot(gs[0])
    ax.imshow(arr)
    ax.set_title("Ảnh", loc="left")
    ax.axis("off")

    ax = fig.add_subplot(gs[1])
    ax.imshow(lsb_plane_gray(arr), cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    ax.set_title("Mặt phẳng LSB (tổng bit thấp 3 kênh)", loc="left")
    ax.axis("off")

    ax = fig.add_subplot(gs[2])
    ax.plot(fr, pv, color=ps.BLUE, **ps.MARKER)
    ax.axhline(CHI_ALPHA, color=ps.MUTED, linewidth=1.0)
    ax.text(fr[-1], CHI_ALPHA + 0.025, f"ngưỡng α = {CHI_ALPHA}", ha="right", va="bottom", color=ps.INK2, fontsize=8.5)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlim(0, 102)
    ax.set_xlabel("Phần ảnh đã xét, tính từ đầu dãy mẫu (%)")
    ax.set_ylabel("p-value chi-square")
    ax.set_title("Chi-square theo tiền tố", loc="left")
    pg = rep["progressive"]
    ax.text(101, 1.0, f"{pg['longest_run']}/{pg['n_points']} điểm liên tiếp có p > α (cần ≥ {pg['min_run']})",
            ha="right", va="top", color=ps.INK2, fontsize=8.5)

    rs = rep["rs"]
    fig.suptitle(f"Steganalysis{(' - ' + title) if title else ''}", x=0.03, ha="left", fontsize=14, fontweight="bold", y=0.97)
    fig.text(0.03, 0.885, rep["verdict"], ha="left", va="center", fontsize=9.5, color=ps.INK2, wrap=True)
    fig.text(0.03, 0.045,
             f"Chi-square toàn ảnh: p = {rep['chi_square']['p']:.3g}   |   RS: tỉ lệ nhúng ước lượng = {rs['p']:.3f} bit/mẫu "
             f"(ngưỡng {rep['thresholds']['rs']})",
             ha="left", fontsize=9, color=ps.INK2)
    fig.savefig(path)
    plt.close(fig)
    return rep
