"""Thí nghiệm 1 - "Cuộc đua": tỉ lệ bị phát hiện theo tỉ lệ nhúng, cho từng phương pháp và từng bộ dò.

Thiết kế
    * Ảnh bìa: nhiều mảnh 256x256 cắt ngẫu nhiên từ các ảnh mẫu.
    * Nhúng MÔ PHỎNG: bit ngẫu nhiên đều (bản mã AES-GCM không phân biệt được với bit ngẫu nhiên),
      nên cho đúng thống kê của nhúng thật mà không tốn thời gian KDF.
    * Tỉ lệ nhúng 0% = ảnh sạch  ->  "tỉ lệ phát hiện" tại đó chính là TỈ LỆ DƯƠNG TÍNH GIẢ.
    * Ngưỡng cố định, lấy mặc định của bộ dò (không tinh chỉnh theo dữ liệu).
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Dict, List

import numpy as np

from common import RESULTS, ensure_results, md_table, pct, random_crops, wilson, write_csv

from stegovault import steganalysis as sa
from stegovault.embed import METHODS, simulate_embedding
from stegovault import plotstyle as ps

RATES = [0.0, 0.05, 0.10, 0.25, 0.50, 1.00]
METHOD_ORDER = ["sequential", "keyed", "matching"]
DETECTORS = [
    ("chi", "Chi-square toàn ảnh"),
    ("prog", "Chi-square theo tiền tố"),
    ("rs", "Phân tích RS"),
    ("high", "Mức \"nghi cao\": chi-square VÀ RS cùng dương tính"),
    ("any", "Mức \"nghi ngờ\" trở lên: ít nhất một bộ dò dương tính"),
]
PLOTTED = DETECTORS[:4]   # ô thứ 5 ("any") chỉ nằm trong bảng/CSV


def detect(arr: np.ndarray) -> Dict[str, bool]:
    """Cùng quy tắc với ``steganalysis.analyze``: 2 nhóm bộ dò (chi-square, RS) đồng thuận => nghi cao."""
    rep = sa.analyze(arr)
    flags = {"chi": rep["chi_square"]["flag"], "prog": rep["progressive"]["flag"], "rs": rep["rs"]["flag"]}
    flags["high"] = (flags["chi"] or flags["prog"]) and flags["rs"]
    flags["any"] = flags["chi"] or flags["prog"] or flags["rs"]
    return flags


def run(per_image: int, seed: int = 11) -> Dict:
    covers = random_crops(per_image)
    n = len(covers)
    rng = np.random.default_rng(seed)
    counts: Dict[str, Dict[float, Dict[str, int]]] = {m: {} for m in METHOD_ORDER}

    t0 = time.time()
    clean = {d: 0 for d, _ in DETECTORS}
    clean_by_image: Dict[str, Dict[str, int]] = {}
    for name, c in covers:
        f = detect(c)
        base = name.split("#")[0]
        clean_by_image.setdefault(base, {d: 0 for d, _ in DETECTORS})
        for d in clean:
            clean[d] += int(f[d])
            clean_by_image[base][d] += int(f[d])
    for m in METHOD_ORDER:
        counts[m][0.0] = dict(clean)
    print(f"  ảnh sạch xong ({n} mảnh, {time.time() - t0:.0f}s)")

    for m in METHOD_ORDER:
        for r in RATES[1:]:
            row = {d: 0 for d, _ in DETECTORS}
            for _, c in covers:
                f = detect(simulate_embedding(c, r, m, rng))
                for d in row:
                    row[d] += int(f[d])
            counts[m][r] = row
            print(f"  {m:10s} rate={r:4.2f}: " + "  ".join(f"{d}={row[d]}/{n}" for d, _ in DETECTORS))
    return {"n": n, "counts": counts, "clean_by_image": clean_by_image, "per_image": per_image}


def make_figure(res: Dict, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ps.apply_style()
    n = res["n"]
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 8.0), sharey=True)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.80, bottom=0.10, hspace=0.36, wspace=0.08)
    xs = np.arange(len(RATES))
    for ax, (d, title) in zip(axes.ravel(), PLOTTED):
        for m in METHOD_ORDER:
            ys = [res["counts"][m][r][d] / n for r in RATES]
            ax.plot(xs, ys, color=ps.METHOD_COLORS[m], label=ps.METHOD_NAMES[m], **ps.MARKER)
        ax.set_title(title, loc="left", pad=8)
        ax.set_xticks(xs)
        ax.set_xticklabels(["0%\n(ảnh sạch)"] + [f"{int(r * 100)}%" for r in RATES[1:]])
        ax.set_ylim(-0.04, 1.04)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.grid(axis="x", visible=False)
    for ax in axes[1]:
        ax.set_xlabel("Tỉ lệ nhúng (bit trên mỗi mẫu màu)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Tỉ lệ ảnh bị báo dương tính")
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper left", bbox_to_anchor=(0.07, 0.885), ncol=3, columnspacing=2.2, handlelength=1.6)
    fig.suptitle("Bộ dò bắt được phương pháp nhúng nào, ở tỉ lệ nhúng bao nhiêu?", x=0.07, ha="left", y=0.975,
                 fontsize=14, fontweight="bold")
    fig.text(0.07, 0.915,
             f"{n} ảnh bìa 256×256 cắt từ {len(res['clean_by_image'])} ảnh mẫu. Tại 0% (ảnh sạch) giá trị là tỉ lệ dương tính giả.",
             ha="left", fontsize=9.5, color=ps.INK2)
    fig.savefig(path)
    plt.close(fig)


def write_outputs(res: Dict) -> str:
    out = ensure_results()
    n = res["n"]
    rows = []
    for m in METHOD_ORDER:
        for r in RATES:
            for d, label in DETECTORS:
                k = res["counts"][m][r][d]
                lo, hi = wilson(k, n)
                rows.append([m, r, d, k, n, round(k / n, 4), round(lo, 4), round(hi, 4)])
    write_csv(out / "detection_rates.csv", ["method", "rate", "detector", "detections", "n", "rate_detect", "ci95_lo", "ci95_hi"], rows)
    make_figure(res, out / "detection_vs_rate.png")

    md = ["### Tỉ lệ phát hiện theo phương pháp và tỉ lệ nhúng\n",
          f"Mẫu: {n} ảnh bìa 256×256 ({res['per_image']} mảnh mỗi ảnh mẫu). Số trong ngoặc là khoảng tin cậy Wilson 95%.\n"]
    for d, label in DETECTORS:
        md.append(f"\n**{label}**\n")
        header = ["Phương pháp"] + [("0% (sạch)" if r == 0 else f"{int(r * 100)}%") for r in RATES]
        trs = []
        for m in METHOD_ORDER:
            cells = [ps.METHOD_NAMES[m]]
            for r in RATES:
                k = res["counts"][m][r][d]
                lo, hi = wilson(k, n)
                cells.append(f"{pct(k / n)} ({pct(lo)}–{pct(hi)})")
            trs.append(cells)
        md.append(md_table(header, trs))
    md.append("\n**Dương tính giả theo ảnh gốc (ảnh sạch)**\n")
    per = res["per_image"]
    trs = []
    for base, c in res["clean_by_image"].items():
        trs.append([base] + [f"{c[d]}/{per}" for d, _ in DETECTORS])
    md.append(md_table(["Ảnh gốc"] + [lbl for _, lbl in DETECTORS], trs))
    text = "\n".join(md) + "\n"
    (out / "detection_table.md").write_text(text, encoding="utf-8")
    (out / "detection_raw.json").write_text(
        json.dumps({"n": n, "counts": {m: {str(r): v for r, v in d.items()} for m, d in res["counts"].items()},
                    "clean_by_image": res["clean_by_image"]}, indent=2), encoding="utf-8")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-image", type=int, default=12, help="số mảnh cắt từ mỗi ảnh mẫu")
    args = ap.parse_args()
    print("Thí nghiệm 1: tỉ lệ phát hiện theo tỉ lệ nhúng")
    res = run(args.per_image)
    write_outputs(res)
    print(f"-> {RESULTS / 'detection_vs_rate.png'}")


if __name__ == "__main__":
    main()
