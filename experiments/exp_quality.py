"""Thí nghiệm 2 - Chất lượng ảnh, dung lượng và chi phí KDF.

Câu hỏi: nhúng nhiều thì ảnh xấu đi bao nhiêu? Ba phương pháp khác nhau về mức độ bị dò, nhưng có khác nhau
về chất lượng ảnh không? (Lý thuyết: không - cả ba đều đổi ~r/2 số mẫu, mỗi mẫu lệch đúng 1 đơn vị.)
"""

from __future__ import annotations

import time

import numpy as np

from common import ensure_results, load_samples, md_table, write_csv

from stegovault import crypto_layer as cl
from stegovault import steganalysis as sa
from stegovault.embed import capacity_bytes, simulate_embedding
from stegovault.metrics import diff_stats

RATES = [0.01, 0.05, 0.10, 0.25, 0.50, 1.00]
METHODS = ["sequential", "keyed", "matching"]
LABELS = {"sequential": "LSB tuần tự", "keyed": "LSB rải theo khóa", "matching": "LSB matching (±1)"}


def theory_psnr(rate: float) -> float:
    """Mỗi vị trí nhúng bit ngẫu nhiên đổi giá trị với xác suất 1/2 và lệch đúng 1 -> MSE = rate/2."""
    return float(10 * np.log10(255.0 ** 2 / (rate / 2)))


def rs_accuracy(imgs, rng) -> str:
    """RS ước lượng tỉ lệ nhúng chính xác đến đâu? Trung bình ± độ lệch chuẩn giữa 6 ảnh mẫu (ảnh đầy đủ, không cắt)."""
    rows = []
    for r in (0.10, 0.30, 0.50, 0.80):
        cells = [f"{r:.2f}"]
        for m in METHODS:
            est = [sa.rs_analysis(simulate_embedding(a, r, m, rng))["p"] for a in imgs.values()]
            cells.append(f"{np.mean(est):.2f} ± {np.std(est):.2f}")
        rows.append(cells)
    return md_table(["Tỉ lệ nhúng thật"] + [LABELS[m] for m in METHODS], rows)


def main() -> str:
    out = ensure_results()
    imgs = load_samples()
    rng = np.random.default_rng(3)
    rows, md_rows = [], []
    for r in RATES:
        cells = [f"{r:.2f}", f"{theory_psnr(r):.2f}"]
        for m in METHODS:
            ps_, ss_, ch_ = [], [], []
            for name, a in imgs.items():
                s = simulate_embedding(a, r, m, rng)
                d = diff_stats(a, s)
                ps_.append(d["psnr_db"]); ss_.append(d["ssim"]); ch_.append(d["changed_ratio"])
                rows.append([m, r, name, round(d["psnr_db"], 3), round(d["ssim"], 6), round(d["changed_ratio"], 5), d["max_abs_diff"]])
            cells.append(f"{np.mean(ps_):.2f} dB / {np.mean(ss_):.5f}")
        md_rows.append(cells)
    write_csv(out / "quality.csv", ["method", "rate", "image", "psnr_db", "ssim", "changed_ratio", "max_abs_diff"], rows)

    cap_rows = []
    for name, a in imgs.items():
        h, w = a.shape[:2]
        cap = capacity_bytes(a.size)
        cap_rows.append([name, f"{w}×{h}", f"{a.size:,}", f"{cap:,}", f"{cap / 1024:.1f} KiB"])

    kdf_rows = []
    for kdf in cl.available_kdfs():
        t = []
        for _ in range(3):
            t0 = time.perf_counter()
            cl.derive_keys("mat-khau-do-thoi-gian", b"\x01" * 16, kdf)
            t.append(time.perf_counter() - t0)
        mem = {"scrypt": f"{128 * cl.SCRYPT_N * cl.SCRYPT_R // (1024 * 1024)} MiB", "argon2id": f"{cl.ARGON2_MEMORY_KIB // 1024} MiB"}[kdf]
        kdf_rows.append([kdf, mem, f"{np.median(t) * 1000:.0f} ms"])

    md = ["### Chất lượng ảnh theo tỉ lệ nhúng\n",
          "Trung bình trên 6 ảnh mẫu 8-bit (PSNR / SSIM). Cột lý thuyết: PSNR = 10·log10(255² / (r/2)).\n",
          md_table(["Tỉ lệ nhúng r", "PSNR lý thuyết (dB)"] + [LABELS[m] for m in METHODS], md_rows),
          "\n### Dung lượng giấu tin tối đa\n",
          md_table(["Ảnh", "Kích thước", "Số mẫu LSB", "Dung lượng tối đa (byte)", "≈"], cap_rows),
          "\n### Chi phí hàm làm chậm mật khẩu (KDF)\n",
          md_table(["KDF", "Bộ nhớ", "Thời gian một lần suy dẫn (trung vị 3 lần)"], kdf_rows),
          "\n### Độ chính xác của ước lượng RS\n",
          "Tỉ lệ nhúng do RS ước lượng (trung bình ± độ lệch chuẩn giữa 6 ảnh mẫu). Đúng tuyệt đối khi bằng cột đầu tiên; "
          "với matching, RS gần như không thấy gì nên ước lượng xấp xỉ 0.\n",
          rs_accuracy(imgs, np.random.default_rng(31)) + "\n"]
    text = "\n".join(md)
    (out / "quality_table.md").write_text(text, encoding="utf-8")
    print(text)
    return text


if __name__ == "__main__":
    print("Thí nghiệm 2: chất lượng ảnh, dung lượng, KDF")
    main()
