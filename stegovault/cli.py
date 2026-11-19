"""Giao diện dòng lệnh: ``python -m stegovault <lệnh> ...``"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from . import crypto_layer as cl
from .embed import METHOD_LABELS, METHODS, capacity_bytes, embed
from .errors import StegoError
from .extract import extract
from .image_io import has_alpha, load_rgb, save_lossless
from .metrics import diff_stats
from .steganalysis import analyze

ROOT = Path(__file__).resolve().parent.parent


def _fmt_db(v: float) -> str:
    return "∞ (giống hệt)" if v == float("inf") else f"{v:.2f} dB"


def _read_password(args: argparse.Namespace, confirm: bool = False) -> str:
    pw: Optional[str] = getattr(args, "password", None) or os.environ.get("STEGOVAULT_PASSWORD")
    if pw:
        return pw
    pw = getpass.getpass("Mật khẩu: ")
    if confirm and getpass.getpass("Nhập lại mật khẩu: ") != pw:
        raise StegoError("Hai lần nhập mật khẩu không khớp.")
    return pw


# ---------------------------------------------------------------- các lệnh
def cmd_capacity(args: argparse.Namespace) -> int:
    arr = load_rgb(args.image)
    cap = capacity_bytes(arr.size)
    h, w = arr.shape[:2]
    print(f"Ảnh {w}x{h} ({arr.size:,} mẫu LSB)")
    print(f"Dung lượng tối đa: {cap:,} byte (≈ {cap / 1024:.1f} KiB) sau khi nén, trước khi mã hóa")
    print("Tin văn bản thường nén được nên chứa được nhiều hơn một chút; dữ liệu đã nén (zip, jpg) thì không.")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    sources = [args.message is not None, args.file is not None, args.message_file is not None]
    if sum(sources) != 1:
        raise StegoError("Hãy chọn đúng một nguồn tin: -m/--message, --message-file hoặc -f/--file.")
    if args.message is not None:
        message, filename = args.message, None
    elif args.message_file is not None:
        message, filename = Path(args.message_file).read_text(encoding="utf-8"), None
    else:
        p = Path(args.file)
        message, filename = p.read_bytes(), p.name

    out = args.output or str(Path(args.cover).with_name(Path(args.cover).stem + "_stego.png"))
    if os.path.abspath(out) == os.path.abspath(args.cover):
        raise StegoError("Đường dẫn đầu ra trùng ảnh gốc. Hãy chọn tên khác (-o).")
    if os.path.exists(out) and not args.force:
        raise StegoError(f"{out} đã tồn tại. Dùng --force để ghi đè.")

    if has_alpha(args.cover):
        print("⚠ Ảnh gốc có kênh alpha/trong suốt; kênh này sẽ bị bỏ khi chuyển sang RGB.", file=sys.stderr)
    password = _read_password(args, confirm=True)
    cover = load_rgb(args.cover)
    res = embed(
        cover, message, password, method=args.method, kdf=args.kdf,
        filename=filename, compress=not args.no_compress,
    )
    save_lossless(res.stego, out)
    d = diff_stats(cover, res.stego)

    print(f"✓ Đã giấu {res.message_bytes:,} byte vào {out}")
    print(f"  Phương pháp : {args.method} - {METHOD_LABELS[args.method]}")
    print(f"  KDF         : {args.kdf}   |   mã hóa: AES-256-GCM")
    print(f"  Dung lượng  : đã dùng {res.utilization:.1%} ({res.container_bytes:,}/{res.capacity_bytes:,} byte)")
    print(f"  Tỉ lệ nhúng : {res.embedding_rate:.4f} bit/mẫu ({res.bits_per_pixel:.4f} bit/pixel)")
    print(f"  Mẫu màu đổi : {d['changed_samples']:,} ({d['changed_ratio']:.3%}), sai khác tối đa {d['max_abs_diff']}")
    print(f"  Chất lượng  : PSNR {_fmt_db(d['psnr_db'])}, SSIM {d['ssim']:.6f}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    password = _read_password(args)
    res = extract(args.image, password, position_mode=args.mode, kdf=args.kdf)
    if res.is_text:
        if args.output:
            if os.path.exists(args.output) and not args.force:
                raise StegoError(f"{args.output} đã tồn tại. Dùng --force để ghi đè.")
            Path(args.output).write_text(res.text, encoding="utf-8")
            print(f"✓ Đã ghi tin nhắn ({len(res.data):,} byte) vào {args.output}")
        else:
            print(res.text)
        return 0

    # File: tên lấy từ ảnh đã được làm sạch; không bao giờ ghi ra ngoài thư mục đích.
    target = Path(args.output) if args.output else Path.cwd()
    if target.is_dir() or not args.output:
        target = target / (res.filename or "extracted.bin")
    if target.exists() and not args.force:
        raise StegoError(f"{target} đã tồn tại. Dùng --force để ghi đè.")
    target.write_bytes(res.data)
    print(f"✓ Đã trích file '{res.filename}' ({len(res.data):,} byte) -> {target}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    arr = load_rgb(args.image)
    rep = analyze(arr)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        h, w = arr.shape[:2]
        chi, rs = rep["chi_square"], rep["rs"]
        print(f"Phân tích {args.image} ({w}x{h})")
        print(f"  Chi-square toàn ảnh : chi2={chi['chi2']:.1f}, df={chi['df']}, p={chi['p']:.4g}  -> {'NGHI' if chi['flag'] else 'bình thường'}")
        pg = rep["progressive"]
        print(f"  Chi-square tiền tố  : {pg['longest_run']}/{pg['n_points']} điểm liên tiếp có p>α (cần ≥{pg['min_run']})  -> {'NGHI' if pg['flag'] else 'bình thường'}")
        print(f"  RS analysis         : tỉ lệ nhúng ước lượng={rs['p']:.3f} bit/mẫu  -> {'NGHI' if rs['flag'] else 'bình thường'}")
        print(f"  Tỉ lệ bit LSB = 1   : {rep['ones_ratio']:.4f}")
        print(f"\nKết luận: {rep['verdict']}")
    if args.report:
        from .report import make_report

        make_report(arr, args.report, title=os.path.basename(str(args.image)))
        print(f"✓ Đã lưu báo cáo hình ảnh: {args.report}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a, b = load_rgb(args.cover), load_rgb(args.stego)
    if a.shape != b.shape:
        raise StegoError(f"Hai ảnh khác kích thước: {a.shape} và {b.shape}.")
    d = diff_stats(a, b)
    print(f"Mẫu màu bị đổi: {d['changed_samples']:,} / {d['samples']:,} ({d['changed_ratio']:.3%})")
    print(f"Sai khác tối đa: {d['max_abs_diff']}  |  MSE: {d['mse']:.6f}")
    print(f"PSNR: {_fmt_db(d['psnr_db'])}  |  SSIM: {d['ssim']:.6f}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Chạy trọn vòng: giấu -> trích -> so sánh -> phân tích, rồi lưu kết quả vào thư mục demo."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(args.image) if args.image else ROOT / "samples" / "astronaut.png"
    if not src.exists():
        raise StegoError(f"Không thấy ảnh mẫu {src}. Truyền ảnh PNG/JPG của bạn qua --image.")

    password = "demo-mat-khau-manh"
    secret = "Đây là bí mật: hẹn gặp lúc 7h sáng tại cổng trường. 🕖"
    cover = load_rgb(src)
    print(f"1) Ảnh gốc: {src.name} {cover.shape[1]}x{cover.shape[0]}, dung lượng {capacity_bytes(cover.size):,} byte")

    for method in METHODS:
        res = embed(cover, secret, password, method=method)
        out = out_dir / f"stego_{method}.png"
        save_lossless(res.stego, out)
        back = extract(out, password)
        ok = back.text == secret
        d = diff_stats(cover, res.stego)
        print(f"2) [{method:10s}] khứ hồi {'OK' if ok else 'LỖI'} | đổi {d['changed_samples']} mẫu | PSNR {_fmt_db(d['psnr_db'])}")
        rep = analyze(load_rgb(out))
        print(f"   steganalysis: chi-square p={rep['chi_square']['p']:.3g}, RS={rep['rs']['p']:.3f} -> {rep['level']}")

    try:
        extract(out_dir / "stego_matching.png", "sai-mat-khau")
    except StegoError as exc:
        print(f"3) Sai mật khẩu bị từ chối đúng: {exc}")
    print(f"\nẢnh kết quả nằm trong: {out_dir.resolve()}")
    print("Mở giao diện web để thử trực quan:  python -m stegovault serve")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web.server import run

    run(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stegovault",
        description="StegoVault - giấu tin mã hóa (AES-256-GCM) trong ảnh bằng LSB, kèm công cụ steganalysis.",
    )
    p.add_argument("--version", action="version", version=f"stegovault {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="lệnh")

    def add_pw(sp):
        sp.add_argument("-p", "--password", help="mật khẩu (nếu bỏ trống sẽ hỏi; tránh gõ trực tiếp vì lưu trong lịch sử shell)")

    sp = sub.add_parser("embed", help="mã hóa và giấu tin vào ảnh")
    sp.add_argument("-i", "--cover", required=True, help="ảnh gốc (PNG/BMP/JPG... ảnh đầu ra luôn là PNG)")
    sp.add_argument("-o", "--output", help="ảnh đầu ra (.png/.bmp/.tiff); mặc định <tên>_stego.png")
    sp.add_argument("-m", "--message", help="tin nhắn văn bản cần giấu")
    sp.add_argument("--message-file", help="đọc tin nhắn văn bản từ file UTF-8")
    sp.add_argument("-f", "--file", help="giấu một file bất kỳ (nhị phân)")
    sp.add_argument("--method", choices=list(METHODS), default="matching",
                    help="sequential | keyed | matching (mặc định: matching, khó bị dò nhất)")
    sp.add_argument("--kdf", choices=list(cl.KDFS), default="scrypt")
    sp.add_argument("--no-compress", action="store_true", help="không nén trước khi mã hóa")
    sp.add_argument("--force", action="store_true", help="ghi đè file đầu ra nếu đã tồn tại")
    add_pw(sp)
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("extract", help="trích xuất và giải mã tin từ ảnh")
    sp.add_argument("-i", "--image", required=True, help="ảnh chứa tin")
    sp.add_argument("-o", "--output", help="nơi lưu kết quả (file hoặc thư mục); mặc định in ra màn hình / thư mục hiện tại")
    sp.add_argument("--mode", choices=["auto", "keyed", "sequential"], default="auto", help="cách chọn vị trí (mặc định: tự dò)")
    sp.add_argument("--kdf", choices=["auto", *cl.KDFS], default="auto")
    sp.add_argument("--force", action="store_true", help="ghi đè file đầu ra nếu đã tồn tại")
    add_pw(sp)
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("capacity", help="xem dung lượng giấu tin của ảnh")
    sp.add_argument("image")
    sp.set_defaults(func=cmd_capacity)

    sp = sub.add_parser("analyze", help="steganalysis: chi-square, RS analysis, mặt phẳng LSB")
    sp.add_argument("image")
    sp.add_argument("--report", metavar="PNG", help="lưu hình báo cáo (cần matplotlib)")
    sp.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("compare", help="so sánh ảnh gốc và ảnh đã giấu tin (PSNR, SSIM)")
    sp.add_argument("cover")
    sp.add_argument("stego")
    sp.set_defaults(func=cmd_compare)

    sp = sub.add_parser("demo", help="chạy thử trọn vòng giấu -> trích -> phân tích")
    sp.add_argument("--image", help="ảnh dùng cho demo (mặc định samples/astronaut.png)")
    sp.add_argument("--out", default="demo_output", help="thư mục lưu kết quả")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("serve", help="mở giao diện web trên máy bạn (chỉ lắng nghe localhost)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    sp.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    # Windows: bảo đảm in được tiếng Việt kể cả khi đầu ra bị chuyển hướng.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except StegoError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"✗ Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã hủy.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
