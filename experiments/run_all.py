"""Chạy toàn bộ thí nghiệm và demo, rồi ghép kết quả thành results/RESULTS.md.

    python experiments/run_all.py            # đầy đủ (khoảng 1 phút)
    python experiments/run_all.py --quick    # nhanh (ít ảnh bìa hơn), để thử cấu hình

Mọi bảng trong RESULTS.md do mã sinh ra từ số liệu đo, không gõ tay.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "demo"))

import crypto_demos  # noqa: E402
import exp_detection  # noqa: E402
import exp_quality  # noqa: E402
import exp_real_vs_sim  # noqa: E402
import exp_robustness  # noqa: E402
import exp_visual  # noqa: E402
from common import RESULTS, ensure_results  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="chỉ 3 mảnh mỗi ảnh mẫu (số liệu thô hơn)")
    args = ap.parse_args()
    per_image = 3 if args.quick else 12
    out = ensure_results()
    t0 = time.time()

    print("[1/6] Tỉ lệ phát hiện theo tỉ lệ nhúng")
    det_text = exp_detection.write_outputs(exp_detection.run(per_image))
    print("[2/6] Chất lượng, dung lượng, KDF")
    qual_text = exp_quality.main()
    print("[3/6] Độ bền")
    rob_text = exp_robustness.main()
    print("[4/6] Hình trực quan")
    exp_visual.main()
    print("[5/6] Demo mật mã nền tảng")
    crypto_demos.main()
    print("[6/6] Nhúng thật so với nhúng mô phỏng")
    real_text = exp_real_vs_sim.main(per_image=2 if args.quick else 4)

    crypto_text = (RESULTS / "crypto_demos.md").read_text(encoding="utf-8")
    mode = "CHẾ ĐỘ NHANH (--quick): số liệu thô, không dùng để báo cáo" if args.quick else "đầy đủ"
    md = f"""# Kết quả thí nghiệm StegoVault

Sinh tự động bởi `experiments/run_all.py` ({mode}). Hạt giống ngẫu nhiên cố định nên chạy lại cho cùng số liệu
(riêng BER ở mục độ bền dao động nhẹ vì salt và nonce của AES-GCM luôn ngẫu nhiên).

## 1. Cuộc đua giữa người giấu và người dò

![Tỉ lệ phát hiện theo tỉ lệ nhúng](detection_vs_rate.png)

{det_text}
## 2. Chất lượng ảnh, dung lượng và chi phí KDF

{qual_text}
## 3. Độ bền trước các biến đổi ảnh

![BER sau các biến đổi](robustness_ber.png)

{rob_text}
## 4. Nhìn trực tiếp vào dấu vết

![Mặt phẳng LSB](lsb_planes.png)

![Đường cong chi-square theo tiền tố](chi_square_curve.png)

## 5. Mật mã nền tảng

![ECB và GCM](ecb_vs_gcm.png)

{crypto_text}
## 6. Kiểm tra giả định của các thí nghiệm: nhúng thật so với mô phỏng

{real_text}"""
    (out / "RESULTS.md").write_text(md, encoding="utf-8")
    print(f"\nXong sau {time.time() - t0:.0f}s -> {out / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
