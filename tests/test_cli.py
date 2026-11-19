import json

import numpy as np
import pytest

from stegovault.cli import main
from stegovault.image_io import load_rgb, save_lossless

from conftest import textured

PW = "mat-khau-cli-thu"


@pytest.fixture
def img(tmp_path):
    p = tmp_path / "cover.png"
    save_lossless(textured(128, 128, seed=4), p)
    return p


def run(capsys, *argv, env_pw=None, monkeypatch=None):
    if monkeypatch is not None:
        if env_pw is None:
            monkeypatch.delenv("STEGOVAULT_PASSWORD", raising=False)
        else:
            monkeypatch.setenv("STEGOVAULT_PASSWORD", env_pw)
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_embed_then_extract_text(img, tmp_path, capsys, monkeypatch):
    out = tmp_path / "s.png"
    code, o, _ = run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "Bí mật Việt 🚀", "-p", PW)
    assert code == 0 and out.exists() and "Đã giấu" in o and "PSNR" in o
    code, o, _ = run(capsys, "extract", "-i", str(out), "-p", PW)
    assert code == 0 and o.strip() == "Bí mật Việt 🚀"


def test_default_output_name_and_original_untouched(img, capsys):
    before = img.read_bytes()
    code, _, _ = run(capsys, "embed", "-i", str(img), "-m", "x", "-p", PW)
    assert code == 0 and (img.parent / "cover_stego.png").exists()
    assert img.read_bytes() == before


def test_password_from_environment(img, tmp_path, capsys, monkeypatch):
    out = tmp_path / "s.png"
    code, _, _ = run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "hello", env_pw=PW, monkeypatch=monkeypatch)
    assert code == 0
    code, o, _ = run(capsys, "extract", "-i", str(out), env_pw=PW, monkeypatch=monkeypatch)
    assert code == 0 and o.strip() == "hello"


def test_wrong_password_returns_error_code(img, tmp_path, capsys):
    out = tmp_path / "s.png"
    run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "hello", "-p", PW)
    code, o, e = run(capsys, "extract", "-i", str(out), "-p", "sai")
    assert code == 1 and o == "" and "Không giải mã được" in e


def test_refuses_overwrite_without_force(img, tmp_path, capsys):
    out = tmp_path / "s.png"
    assert run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "a", "-p", PW)[0] == 0
    code, _, e = run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "b", "-p", PW)
    assert code == 1 and "--force" in e
    assert run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "b", "-p", PW, "--force")[0] == 0


def test_refuses_to_overwrite_the_cover_itself(img, capsys):
    code, _, e = run(capsys, "embed", "-i", str(img), "-o", str(img), "-m", "a", "-p", PW, "--force")
    assert code == 1 and "trùng ảnh gốc" in e


def test_refuses_lossy_output_format(img, tmp_path, capsys):
    code, _, e = run(capsys, "embed", "-i", str(img), "-o", str(tmp_path / "s.jpg"), "-m", "a", "-p", PW)
    assert code == 1 and "làm mất dữ liệu" in e


def test_requires_exactly_one_message_source(img, tmp_path, capsys):
    code, _, e = run(capsys, "embed", "-i", str(img), "-p", PW)
    assert code == 1 and "đúng một nguồn" in e
    f = tmp_path / "f.txt"; f.write_text("x")
    code, _, e = run(capsys, "embed", "-i", str(img), "-m", "a", "-f", str(f), "-p", PW)
    assert code == 1


def test_missing_cover_and_too_large_message_are_clean_errors(tmp_path, img, capsys):
    code, _, e = run(capsys, "embed", "-i", str(tmp_path / "nope.png"), "-m", "a", "-p", PW)
    assert code == 1 and "Không tìm thấy" in e
    big = tmp_path / "big.bin"; big.write_bytes(np.random.default_rng(0).bytes(200_000))
    code, _, e = run(capsys, "embed", "-i", str(img), "-f", str(big), "-p", PW)
    assert code == 1 and "Tin quá lớn" in e


def test_file_payload_roundtrip_with_sanitized_name(img, tmp_path, capsys):
    payload = tmp_path / "tài liệu.bin"; payload.write_bytes(bytes(range(256)) * 4)
    out = tmp_path / "s.png"
    assert run(capsys, "embed", "-i", str(img), "-o", str(out), "-f", str(payload), "-p", PW)[0] == 0
    dest = tmp_path / "out"; dest.mkdir()
    code, o, _ = run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)
    assert code == 0 and (dest / "tài liệu.bin").read_bytes() == payload.read_bytes()
    # file đã tồn tại -> không ghi đè nếu thiếu --force
    code, _, e = run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)
    assert code == 1 and "--force" in e


def test_hostile_filename_cannot_escape_destination(img, tmp_path, capsys):
    """Tên file nằm TRONG ảnh (do kẻ khác kiểm soát) - không được ghi ra ngoài thư mục đích."""
    from stegovault.embed import embed
    cover = load_rgb(img)
    res = embed(cover, b"payload", PW, filename="../../escape.txt")
    out = tmp_path / "evil.png"; save_lossless(res.stego, out)
    dest = tmp_path / "a" / "b"; dest.mkdir(parents=True)
    code, _, _ = run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)
    assert code == 0
    assert (dest / "escape.txt").exists()
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "a" / "escape.txt").exists()


def test_capacity_compare_and_analyze(img, tmp_path, capsys):
    code, o, _ = run(capsys, "capacity", str(img))
    assert code == 0 and "128x128" in o and "byte" in o
    out = tmp_path / "s.png"
    run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "abc", "-p", PW)
    code, o, _ = run(capsys, "compare", str(img), str(out))
    assert code == 0 and "PSNR" in o and "SSIM" in o
    code, o, _ = run(capsys, "analyze", str(out), "--json")
    rep = json.loads(o)
    assert code == 0 and rep["level"] in ("none", "medium", "high") and "chi_square" in rep
    code, o, _ = run(capsys, "analyze", str(out))
    assert code == 0 and "Kết luận" in o and "RS analysis" in o


def test_compare_size_mismatch(img, tmp_path, capsys):
    other = tmp_path / "o.png"; save_lossless(textured(64, 64), other)
    code, _, e = run(capsys, "compare", str(img), str(other))
    assert code == 1 and "khác kích thước" in e


def test_analyze_report_png(img, tmp_path, capsys):
    pytest.importorskip("matplotlib")
    rp = tmp_path / "r.png"
    code, o, _ = run(capsys, "analyze", str(img), "--report", str(rp))
    assert code == 0 and rp.exists() and rp.stat().st_size > 5000


def test_demo_command(tmp_path, capsys):
    from pathlib import Path
    sample = Path(__file__).resolve().parent.parent / "samples" / "camera.png"
    if not sample.exists():
        pytest.skip("thiếu ảnh mẫu")
    code, o, _ = run(capsys, "demo", "--image", str(sample), "--out", str(tmp_path / "d"))
    assert code == 0 and o.count("khứ hồi OK") == 3 and "Sai mật khẩu bị từ chối" in o
    assert len(list((tmp_path / "d").glob("stego_*.png"))) == 3


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0 and "stegovault" in capsys.readouterr().out


def test_roundtrip_with_default_real_kdf_parameters(img, tmp_path, capsys, restore_default_kdf):
    """Một vòng khứ hồi với tham số KDF THẬT (scrypt 32 MiB) để chắc cấu hình mặc định hoạt động."""
    out = tmp_path / "s.png"
    assert run(capsys, "embed", "-i", str(img), "-o", str(out), "-m", "kdf that", "-p", PW)[0] == 0
    code, o, _ = run(capsys, "extract", "-i", str(out), "-p", PW)
    assert code == 0 and o.strip() == "kdf that"


# ------------------------------------------------------------- nhiều file
def _make_files(tmp_path):
    a = tmp_path / "báo cáo.txt"; a.write_text("nội dung A " * 40, encoding="utf-8")
    b = tmp_path / "dữ liệu.bin"; b.write_bytes(bytes(range(256)) * 3)
    sub = tmp_path / "sub"; sub.mkdir()
    c = sub / "báo cáo.txt"; c.write_text("trùng tên nhưng khác nội dung", encoding="utf-8")
    return a, b, c


def test_embed_and_extract_many_files(img, tmp_path, capsys):
    a, b, c = _make_files(tmp_path)
    out = tmp_path / "s.png"
    code, o, _ = run(capsys, "embed", "-i", str(img), "-o", str(out), "-f", str(a), str(b), str(c), "-p", PW)
    assert code == 0 and "3 file" in o
    dest = tmp_path / "ra"
    code, o, _ = run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)
    assert code == 0 and "3 file" in o
    assert (dest / "báo cáo.txt").read_bytes() == a.read_bytes()
    assert (dest / "dữ liệu.bin").read_bytes() == b.read_bytes()
    assert (dest / "báo cáo (2).txt").read_bytes() == c.read_bytes()      # trùng tên được đánh số, không ghi đè nhau


def test_embed_accepts_repeated_f_flags(img, tmp_path, capsys):
    a, b, _ = _make_files(tmp_path)
    out = tmp_path / "s.png"
    assert run(capsys, "embed", "-i", str(img), "-o", str(out), "-f", str(a), "-f", str(b), "-p", PW)[0] == 0
    dest = tmp_path / "ra"
    assert run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)[0] == 0
    assert sorted(p.name for p in dest.iterdir()) == sorted([a.name, b.name])


def test_extract_many_files_refuses_to_overwrite_without_force_and_writes_nothing(img, tmp_path, capsys):
    a, b, _ = _make_files(tmp_path)
    out = tmp_path / "s.png"
    run(capsys, "embed", "-i", str(img), "-o", str(out), "-f", str(a), str(b), "-p", PW)
    dest = tmp_path / "ra"; dest.mkdir()
    (dest / b.name).write_bytes(b"cu")                      # chỉ file thứ hai đã tồn tại
    code, _, e = run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)
    assert code == 1 and "--force" in e
    assert not (dest / a.name).exists() and (dest / b.name).read_bytes() == b"cu"   # không ghi dở dang
    assert run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW, "--force")[0] == 0
    assert (dest / b.name).read_bytes() == b.read_bytes()


def test_extract_many_files_default_folder_and_file_target_error(img, tmp_path, capsys, monkeypatch):
    a, b, _ = _make_files(tmp_path)
    out = tmp_path / "s.png"
    run(capsys, "embed", "-i", str(img), "-o", str(out), "-f", str(a), str(b), "-p", PW)
    not_a_dir = tmp_path / "la-file.txt"; not_a_dir.write_text("x")
    code, _, e = run(capsys, "extract", "-i", str(out), "-o", str(not_a_dir), "-p", PW)
    assert code == 1 and "thư mục" in e
    work = tmp_path / "work"; work.mkdir(); monkeypatch.chdir(work)
    assert run(capsys, "extract", "-i", str(out), "-p", PW)[0] == 0
    assert sorted(p.name for p in (work / "stegovault_out").iterdir()) == sorted([a.name, b.name])


def test_embed_rejects_mixing_message_and_files(img, tmp_path, capsys):
    a, _, _ = _make_files(tmp_path)
    code, _, e = run(capsys, "embed", "-i", str(img), "-m", "x", "-f", str(a), "-p", PW)
    assert code == 1 and "đúng một nguồn" in e


def test_hostile_names_inside_a_bundle_cannot_escape_destination(img, tmp_path, capsys):
    from stegovault.embed import embed
    cover = load_rgb(img)
    res = embed(cover, [("../../escape1.txt", b"1"), ("..\\..\\escape2.txt", b"2")], PW)
    out = tmp_path / "evil.png"; save_lossless(res.stego, out)
    dest = tmp_path / "a" / "b"; dest.mkdir(parents=True)
    assert run(capsys, "extract", "-i", str(out), "-o", str(dest), "-p", PW)[0] == 0
    assert sorted(p.name for p in dest.iterdir()) == ["escape1.txt", "escape2.txt"]
    assert not list(tmp_path.glob("escape*")) and not list((tmp_path / "a").glob("escape*"))
