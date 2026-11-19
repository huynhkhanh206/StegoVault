"""Demo mật mã nền tảng: vì sao StegoVault chọn AES-GCM và băm có salt.

Chạy:  python demo/crypto_demos.py          (ghi kết quả vào thư mục results/)

Gồm 3 phần, mỗi phần là một "tấn công rồi phòng thủ":
  1. AES-ECB để lộ hình dạng ảnh; AES-GCM thì không.
  2. Hiệu ứng thác lũ của SHA-256: đổi 1 bit đầu vào làm đổi khoảng một nửa số bit đầu ra.
  3. AES-CTR (không xác thực) cho phép kẻ tấn công sửa bản mã mà không bị phát hiện; AES-GCM thì từ chối.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageFont

from stegovault import plotstyle as ps

RESULTS = ROOT / "results"
SIZE = 256   # 256*256*3 = 196608 byte, chia hết cho 16 (khối AES)


def make_test_image() -> np.ndarray:
    """Ảnh phẳng, ít màu (logo kiểu chữ + hình tròn): các khối giống nhau rất nhiều -> ECB lộ rõ."""
    im = Image.new("RGB", (SIZE, SIZE), (245, 238, 220))
    d = ImageDraw.Draw(im)
    d.ellipse((28, 28, SIZE - 28, SIZE - 28), fill=(29, 95, 168))
    d.ellipse((72, 72, SIZE - 72, SIZE - 72), fill=(245, 238, 220))
    d.rectangle((108, 108, SIZE - 108, SIZE - 108), fill=(235, 104, 52))
    try:
        font = ImageFont.load_default(34)
    except TypeError:
        font = ImageFont.load_default()
    d.text((SIZE // 2, SIZE - 22), "ECB", fill=(19, 32, 44), font=font, anchor="mm")
    return np.array(im)


def ecb_vs_gcm() -> str:
    img = make_test_image()
    raw = img.tobytes()
    key = os.urandom(32)
    ecb = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    ct_ecb = ecb.update(raw) + ecb.finalize()
    ct_gcm = AESGCM(key).encrypt(os.urandom(12), raw, None)[: len(raw)]   # bỏ thẻ 16 byte cuối để vẽ lại thành ảnh
    as_img = lambda b: np.frombuffer(b, dtype=np.uint8).reshape(img.shape)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ps.apply_style()
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 4.5))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.72, bottom=0.03, wspace=0.04)
    for ax, (title, a) in zip(axes, [("Ảnh gốc", img), ("Mã hóa bằng AES-256-ECB", as_img(ct_ecb)), ("Mã hóa bằng AES-256-GCM", as_img(ct_gcm))]):
        ax.imshow(a, interpolation="nearest")
        ax.set_title(title, loc="left", fontsize=11, pad=7)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle("ECB để lộ hình dạng dù đã mã hóa", x=0.01, ha="left", y=0.965, fontsize=14, fontweight="bold")
    fig.text(0.01, 0.905, "Trong ECB, hai khối 16 byte giống nhau luôn cho hai khối bản mã giống nhau, nên vùng màu phẳng vẫn hiện ra. "
                          "GCM trộn một bộ đếm khác nhau vào từng khối, nên bản mã trông như nhiễu ngẫu nhiên.",
             ha="left", va="top", fontsize=9.2, color=ps.INK2, wrap=True)
    RESULTS.mkdir(exist_ok=True)
    fig.savefig(RESULTS / "ecb_vs_gcm.png")
    plt.close(fig)

    def distinct_blocks(b: bytes) -> int:
        return len({b[i : i + 16] for i in range(0, len(b), 16)})
    total = len(raw) // 16
    return (f"- Số khối 16 byte khác nhau: ảnh gốc {distinct_blocks(raw):,}/{total:,}, ECB {distinct_blocks(ct_ecb):,}/{total:,}, "
            f"GCM {distinct_blocks(ct_gcm[:len(raw)]):,}/{total:,}.\n"
            f"- ECB giữ nguyên số khối khác nhau của ảnh gốc (chỉ đổi tên khối), GCM làm mọi khối khác nhau.")


def hash_avalanche(trials: int = 2000) -> str:
    rng = np.random.default_rng(1)
    diffs = []
    for _ in range(trials):
        m = bytearray(rng.bytes(64))
        h1 = hashlib.sha256(m).digest()
        bit = int(rng.integers(0, 512))
        m[bit // 8] ^= 1 << (bit % 8)
        h2 = hashlib.sha256(m).digest()
        diffs.append(bin(int.from_bytes(h1, "big") ^ int.from_bytes(h2, "big")).count("1"))
    d = np.array(diffs)
    a, b = hashlib.sha256(b"StegoVault").hexdigest(), hashlib.sha256(b"StegoVaulT").hexdigest()
    return (f"- Đổi 1 bit trong thông điệp 64 byte, {trials:,} lần thử: số bit băm thay đổi trung bình {d.mean():.1f}/256 "
            f"({d.mean() / 256 * 100:.1f}%), độ lệch chuẩn {d.std():.1f}, nhỏ nhất {d.min()}, lớn nhất {d.max()}.\n"
            f"- Ví dụ: SHA-256(\"StegoVault\") = `{a[:32]}…` và SHA-256(\"StegoVaulT\") = `{b[:32]}…` (chỉ khác một ký tự).")


def malleability() -> str:
    key = os.urandom(32)
    pt = b"Chuyen khoan: 100.000 VND cho Lan"
    # Tấn công: lật bit trong bản mã CTR để đổi "100.000" thành "900.000" mà không cần khóa.
    nonce = os.urandom(16)
    enc = Cipher(algorithms.AES(key), modes.CTR(nonce)).encryptor()
    ct = bytearray(enc.update(pt) + enc.finalize())
    idx = pt.index(b"100.000")
    ct[idx] ^= ord("1") ^ ord("9")
    dec = Cipher(algorithms.AES(key), modes.CTR(nonce)).decryptor()
    tampered = dec.update(bytes(ct)) + dec.finalize()

    # Phòng thủ: cùng thao tác trên AES-GCM
    n2 = os.urandom(12)
    g = bytearray(AESGCM(key).encrypt(n2, pt, None))
    g[idx] ^= ord("1") ^ ord("9")
    try:
        AESGCM(key).decrypt(n2, bytes(g), None)
        gcm_result = "giải mã được (KHÔNG mong muốn)"
    except InvalidTag:
        gcm_result = "bị từ chối (InvalidTag)"
    return (f"- Bản rõ gốc: `{pt.decode()}`\n"
            f"- AES-CTR sau khi kẻ tấn công lật vài bit: `{tampered.decode(errors='replace')}`. Người nhận không phát hiện được gì.\n"
            f"- AES-GCM với đúng thao tác đó: {gcm_result}.")


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    parts = [("1. ECB lộ hình dạng, GCM thì không", ecb_vs_gcm()),
             ("2. Hiệu ứng thác lũ của SHA-256", hash_avalanche()),
             ("3. Bản mã không xác thực có thể bị sửa (CTR) so với GCM", malleability())]
    md = "### Demo mật mã nền tảng\n\n" + "\n\n".join(f"**{t}**\n\n{b}" for t, b in parts) + "\n"
    (RESULTS / "crypto_demos.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {RESULTS / 'ecb_vs_gcm.png'}")


if __name__ == "__main__":
    main()
