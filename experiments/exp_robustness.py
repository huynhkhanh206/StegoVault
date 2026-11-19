"""Thí nghiệm 3 - Độ bền: ảnh đã giấu tin sống sót qua những biến đổi nào?

Quy trình: giấu một tin thật (AES-GCM + KDF) vào ảnh, áp dụng một biến đổi, rồi thử TRÍCH XUẤT.
Vì AES-GCM xác thực toàn bộ bản mã, chỉ MỘT bit sai là giải mã thất bại. Nên ngoài kết quả giải mã,
ta đo "tỉ lệ bit LSB bị đổi" (BER) giữa ảnh đã giấu tin và ảnh sau biến đổi.
"""

from __future__ import annotations

import io
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from common import SAMPLES, ensure_results, md_table, write_csv

from stegovault import crypto_layer as cl
from stegovault import plotstyle as ps
from stegovault.embed import METHODS, payload_positions, embed
from stegovault.errors import StegoError
from stegovault.extract import extract
from stegovault.image_io import load_rgb
from stegovault.lsb import bits_to_bytes, read_bits

PASSWORD = "mat-khau-thu-do-ben-2026"


def _msg() -> str:
    rng = np.random.default_rng(99)
    words = ["an", "toan", "thong", "tin", "mat", "ma", "khoa", "anh", "giau", "tin"]
    return " ".join(rng.choice(words, size=330)) + "."   # ~ 1.6 KB văn bản


def jpeg(q: int) -> Callable[[np.ndarray], np.ndarray]:
    def f(a: np.ndarray) -> np.ndarray:
        buf = io.BytesIO()
        Image.fromarray(a).save(buf, format="JPEG", quality=q, subsampling=0)
        return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    return f


def lossless(fmt: str) -> Callable[[np.ndarray], np.ndarray]:
    def f(a: np.ndarray) -> np.ndarray:
        buf = io.BytesIO()
        Image.fromarray(a).save(buf, format=fmt)
        return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    return f


def resize_round_trip(scale: float) -> Callable[[np.ndarray], np.ndarray]:
    def f(a: np.ndarray) -> np.ndarray:
        h, w = a.shape[:2]
        im = Image.fromarray(a).resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        return np.array(im.resize((w, h), Image.LANCZOS))
    return f


def gauss(sigma: float) -> Callable[[np.ndarray], np.ndarray]:
    def f(a: np.ndarray) -> np.ndarray:
        rng = np.random.default_rng(5)
        return np.clip(np.rint(a + rng.normal(0, sigma, a.shape)), 0, 255).astype(np.uint8)
    return f


def crop1(a: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(a[1:, 1:])


def hflip(a: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(a[:, ::-1])


# (nhãn, hàm biến đổi, có thể tính BER trên cùng kích thước)
ATTACKS: List[Tuple[str, Callable[[np.ndarray], np.ndarray], bool]] = [
    ("Lưu lại PNG / BMP / TIFF (không mất dữ liệu)", None, True),  # xử lý riêng
    ("JPEG chất lượng 100", jpeg(100), True),
    ("JPEG chất lượng 95", jpeg(95), True),
    ("JPEG chất lượng 75", jpeg(75), True),
    ("Thu nhỏ 99% rồi phóng lại", resize_round_trip(0.99), True),
    ("Thêm nhiễu Gauss σ = 1", gauss(1.0), True),
    ("Lật ngang ảnh", hflip, True),
    ("Cắt bỏ 1 hàng và 1 cột mép", crop1, False),
]


def ber(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean((a & 1) != (b & 1)))


def try_extract(img: np.ndarray, expected: str) -> str:
    try:
        r = extract(img, PASSWORD)
        return "OK" if r.is_text and r.text == expected else "SAI"
    except StegoError:
        return "HỎNG"


def tamper_one_bit(stego: np.ndarray, method: str) -> np.ndarray:
    """Đảo đúng MỘT bit LSB nằm trong vùng bản mã."""
    flat = stego.reshape(-1).copy()
    bootstrap = bits_to_bytes(read_bits(flat, np.arange(cl.BOOTSTRAP_BITS)))
    keys = cl.derive_keys(PASSWORD, bootstrap[: cl.SALT_LEN], "scrypt")
    body_len = cl.unmask_length(bootstrap[cl.SALT_LEN :], keys)
    pos = payload_positions(flat.size, body_len * 8, keys.pos, METHODS[method][1])
    flat[pos[len(pos) // 2]] ^= 1
    return flat.reshape(stego.shape)


def main() -> str:
    out = ensure_results()
    cover = load_rgb(SAMPLES / "astronaut.png")
    msg = _msg()
    methods = list(METHODS)
    stegos: Dict[str, np.ndarray] = {}
    for m in methods:
        res = embed(cover, msg, PASSWORD, method=m)
        stegos[m] = res.stego
        assert try_extract(res.stego, msg) == "OK", "khứ hồi ban đầu phải thành công"
    print(f"Tin {len(msg.encode()):,} byte, ảnh astronaut 512x512; khứ hồi ban đầu OK cho cả 3 phương pháp")

    rows, md_rows, chart = [], [], []
    for label, fn, can_ber in ATTACKS:
        cells = [label]
        if fn is None:   # nhóm lossless: phải OK cho cả PNG, BMP, TIFF
            status = {}
            for m in methods:
                ok = all(try_extract(lossless(f)(stegos[m]), msg) == "OK" for f in ("PNG", "BMP", "TIFF"))
                status[m] = "OK" if ok else "HỎNG"
            b = 0.0
            cells += [status[m] for m in methods] + ["0"]
            rows += [[label, m, status[m], 0.0] for m in methods]
            chart.append((label, 0.0))
            md_rows.append(cells)
            continue
        bers, status = [], {}
        for m in methods:
            t = fn(stegos[m])
            status[m] = try_extract(t, msg)
            if can_ber:
                bers.append(ber(stegos[m], t))
            rows.append([label, m, status[m], round(bers[-1], 6) if can_ber else ""])
        b = float(np.mean(bers)) if can_ber else None
        cells += [status[m] for m in methods] + [f"{b * 100:.2f}%" if b is not None else "—"]
        if b is not None:
            chart.append((label, b))
        md_rows.append(cells)

    # sửa đúng 1 bit bản mã
    status = {}
    for m in methods:
        status[m] = try_extract(tamper_one_bit(stegos[m], m), msg)
    one = 1 / stegos["matching"].size
    md_rows.append(["Sửa đúng 1 bit LSB của bản mã"] + [status[m] for m in methods] + [f"{one * 100:.5f}%"])
    rows += [["Sửa 1 bit bản mã", m, status[m], round(one, 9)] for m in methods]
    chart.append(("Sửa đúng 1 bit bản mã", one))

    write_csv(out / "robustness.csv", ["attack", "method", "extract", "ber"], rows)
    make_chart(chart, out / "robustness_ber.png")

    md = ["### Độ bền của ảnh đã giấu tin\n",
          f"Tin {len(msg.encode()):,} byte giấu vào ảnh astronaut 512×512. OK = giải mã đúng; HỎNG = AES-GCM từ chối. "
          "BER = tỉ lệ bit LSB của toàn ảnh bị đổi so với ảnh đã giấu tin (trung bình 3 phương pháp).\n",
          md_table(["Biến đổi"] + [ps.METHOD_NAMES[m] for m in methods] + ["BER"], md_rows) + "\n"]
    text = "\n".join(md)
    (out / "robustness_table.md").write_text(text, encoding="utf-8")
    print(text)
    return text


def make_chart(items: List[Tuple[str, float]], path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ps.apply_style()
    items = sorted(items, key=lambda t: t[1])
    labels = [t[0] for t in items]
    vals = [t[1] for t in items]
    fig, ax = plt.subplots(figsize=(10.4, 4.9))
    fig.subplots_adjust(left=0.36, right=0.97, top=0.80, bottom=0.14)
    y = np.arange(len(items))
    ax.barh(y, vals, height=0.52, color=ps.BLUE)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=ps.INK2)
    ax.tick_params(axis="y", length=0)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 0.58)
    ax.set_xticks([0, 0.1, 0.2, 0.3, 0.4, 0.5])
    ax.set_xticklabels(["0%", "10%", "20%", "30%", "40%", "50%"])
    ax.set_xlabel("Tỉ lệ bit LSB bị đổi (BER)")
    for yi, v in zip(y, vals):
        txt = "0, giải mã thành công" if v == 0 else (f"{v * 100:.5f}%, vẫn hỏng" if v < 1e-4 else f"{v * 100:.1f}%")
        ax.text(v + 0.008, yi, txt, va="center", ha="left", fontsize=9, color=ps.INK2)
    fig.suptitle("Chỉ một bit sai là AES-GCM từ chối giải mã", x=0.03, ha="left", y=0.965, fontsize=14, fontweight="bold")
    fig.text(0.03, 0.865, "Tỉ lệ bit LSB bị đổi sau mỗi biến đổi, ảnh astronaut 512×512. Mọi biến đổi mất dữ liệu đều làm hỏng tin.",
             ha="left", fontsize=9.5, color=ps.INK2)
    fig.savefig(path)
    plt.close(fig)


if __name__ == "__main__":
    print("Thí nghiệm 3: độ bền")
    main()
