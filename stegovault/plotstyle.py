"""Kiểu biểu đồ dùng chung (matplotlib): mực/lưới nhạt, đường mảnh, màu phân loại đã kiểm định.

Ba màu đầu của bảng màu phân loại (xanh dương, cam, xanh ngọc) đã được kiểm định
CVD (mù màu) và độ tương phản trên nền sáng. Mỗi phương pháp luôn dùng đúng một màu cố định,
KHÔNG đổi theo thứ hạng hay số lượng đường hiển thị.
"""

from __future__ import annotations

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"

METHOD_COLORS = {"sequential": BLUE, "keyed": ORANGE, "matching": AQUA}
METHOD_NAMES = {
    "sequential": "LSB tuần tự",
    "keyed": "LSB rải theo khóa",
    "matching": "LSB matching (±1)",
}


def apply_style() -> None:
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK2,
            "axes.titlecolor": INK,
            "axes.titleweight": "normal",
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "axes.axisbelow": True,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "text.color": INK,
            "font.family": "DejaVu Sans",
            "lines.linewidth": 2.0,
            "lines.solid_capstyle": "round",
            "lines.solid_joinstyle": "round",
            "legend.frameon": False,
            "legend.fontsize": 9,
            "legend.labelcolor": INK2,
            "figure.dpi": 110,
            "savefig.dpi": 160,
        }
    )


MARKER = dict(marker="o", markersize=6.5, markeredgecolor=SURFACE, markeredgewidth=1.6)
