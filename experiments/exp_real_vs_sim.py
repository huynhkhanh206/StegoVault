"""Thí nghiệm 5 - Nhúng thật so với nhúng mô phỏng.

Các thí nghiệm 1-3 dùng nhúng MÔ PHỎNG (bit ngẫu nhiên, bỏ qua KDF và AES) cho nhanh. Lập luận là bản mã AES-GCM
không thể phân biệt với bit ngẫu nhiên đều nên hai cách cho cùng thống kê. Thí nghiệm này kiểm tra lập luận đó
bằng cách chạy CẢ HAI trên cùng các mảnh ảnh, với KDF mặc định thật, rồi so các số đo của bộ dò.

Kết quả "giống nhau" ở đây có nghĩa là: trung bình ước lượng RS và số ảnh bị gắn cờ khác nhau không đáng kể.
Nó không chứng minh hai phân phối trùng khớp (mẫu nhỏ, và chỉ xét các thống kê của bộ dò cổ điển).
"""

from __future__ import annotations

import numpy as np

from common import ensure_results, md_table, random_crops

from stegovault import crypto_layer as cl
from stegovault import steganalysis as sa
from stegovault.embed import embed, simulate_embedding

RATES = (0.1, 0.3, 0.5)
METHODS = ("sequential", "keyed", "matching")
LABELS = {"sequential": "LSB tuần tự", "keyed": "LSB rải theo khóa", "matching": "LSB matching (±1)"}
NAME_OVERHEAD = 2 + 2 + len("x.bin")       # tiêu đề gói + độ dài tên + tên


def main(per_image: int = 4) -> str:
    out = ensure_results()
    crops = random_crops(per_image)
    rng = np.random.default_rng(77)
    rows, worst_rs, worst_count = [], 0.0, 0
    for method in METHODS:
        for rate in RATES:
            rs_r, rs_s, chi_r, chi_s, hi_r, hi_s = [], [], 0, 0, 0, 0
            for _, a in crops:
                n_bytes = int(rate * a.size / 8) - cl.BOOTSTRAP_BYTES - cl.OVERHEAD - NAME_OVERHEAD
                real = embed(a, rng.bytes(n_bytes), "mat-khau-thi-nghiem", method=method, filename="x.bin",
                             compress=False, rng=rng).stego
                sim = simulate_embedding(a, rate, method, rng)
                ar, as_ = sa.analyze(real), sa.analyze(sim)
                rs_r.append(ar["rs"]["p"]); rs_s.append(as_["rs"]["p"])
                chi_r += bool(ar["chi_square"]["flag"]); chi_s += bool(as_["chi_square"]["flag"])
                hi_r += ar["level"] == "high"; hi_s += as_["level"] == "high"
            n = len(crops)
            worst_rs = max(worst_rs, abs(np.mean(rs_r) - np.mean(rs_s)))
            worst_count = max(worst_count, abs(chi_r - chi_s), abs(hi_r - hi_s))
            rows.append([LABELS[method], f"{rate:.1f}", f"{np.mean(rs_r):.3f} / {np.mean(rs_s):.3f}",
                         f"{np.mean(np.abs(np.array(rs_r) - np.array(rs_s))):.3f}",
                         f"{chi_r} / {chi_s}", f"{hi_r} / {hi_s}"])
    n = len(crops)
    text = "\n".join([
        "### Nhúng thật so với nhúng mô phỏng\n",
        f"{n} mảnh 256×256, nhúng thật (AES-256-GCM, KDF mặc định) và nhúng mô phỏng trên cùng từng mảnh. "
        "Mỗi ô có dạng thật / mô phỏng.\n",
        md_table(["Phương pháp", "Tỉ lệ nhúng", "RS ước lượng (trung bình)", "|Δ RS| mỗi mảnh (trung bình)",
                  f"Chi-square gắn cờ (/{n})", f"Kết luận \"nghi cao\" (/{n})"], rows),
        f"\nChênh lệch lớn nhất giữa hai cách: {worst_rs:.3f} ở trung bình RS, {worst_count} mảnh ở số lần gắn cờ. "
        "Chênh lệch từng mảnh (cột |Δ RS|) khác 0 vì mỗi lần nhúng dùng bit ngẫu nhiên khác nhau; điều cần xem là "
        "trung bình và số lần gắn cờ có lệch hệ thống hay không.\n",
    ])
    (out / "real_vs_simulated.md").write_text(text, encoding="utf-8")
    print(text)
    return text


if __name__ == "__main__":
    print("Thí nghiệm 5: nhúng thật so với nhúng mô phỏng")
    main()
