from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from stegovault import metrics, steganalysis as sa
from stegovault.embed import simulate_embedding
from stegovault.errors import ImageError
from stegovault.image_io import has_alpha, load_rgb, save_lossless, to_png_bytes

from conftest import textured

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def biased_cover(n=300_000, seed=0):
    """Ảnh tổng hợp có SỰ MẤT CÂN BẰNG cặp giá trị (giá trị chẵn nhiều hơn lẻ) - đúng giả thiết của chi-square."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 128, n) * 2                      # toàn số chẵn
    flip = rng.random(n) < 0.30                             # 30% bị chuyển thành số lẻ liền kề
    return np.clip(base + flip, 0, 255).astype(np.uint8).reshape(-1, 100, 3)


# ----------------------------------------------------------------- chi-square
def test_chi_square_flags_balanced_pairs_and_not_biased_ones():
    cover = biased_cover()
    clean = sa.chi_square_pov(cover.reshape(-1))
    assert clean.p < 1e-6                                   # mất cân bằng rõ -> p ≈ 0
    stego = simulate_embedding(cover, 1.0, "keyed", np.random.default_rng(1))
    assert sa.chi_square_pov(stego.reshape(-1)).p > 0.05    # LSB bị ngẫu nhiên hóa -> các cặp cân bằng


def test_chi_square_too_few_categories_returns_nan():
    r = sa.chi_square_pov(np.array([1, 1, 1, 1], dtype=np.uint8))
    assert np.isnan(r.p) and r.df == 0


def test_chi_square_is_blind_to_lsb_matching():
    """Đây là điểm mấu chốt của đề tài: ±1 không cân bằng các cặp giá trị như ghi đè LSB."""
    cover = biased_cover()
    rng = np.random.default_rng(2)
    rep = sa.chi_square_pov(simulate_embedding(cover, 1.0, "matching", rng).reshape(-1))
    assert rep.p < 0.05
    rep_replace = sa.chi_square_pov(simulate_embedding(cover, 1.0, "sequential", rng).reshape(-1))
    assert rep_replace.p > 0.05


def test_progressive_curve_shape():
    fr, ps = sa.chi_square_progressive(biased_cover(), n_points=20)
    assert fr.shape == ps.shape and fr[0] < fr[-1] <= 1.0 and (np.diff(fr) > 0).all()


def test_progressive_shows_westfeld_step_for_sequential_embedding():
    cover = biased_cover(600_000)
    stego = simulate_embedding(cover, 0.5, "sequential", np.random.default_rng(3))
    fr, ps = sa.chi_square_progressive(stego, n_points=40)
    early, late = ps[fr < 0.4], ps[fr > 0.7]
    assert np.nanmin(early) > 0.05          # p cao suốt đoạn đã nhúng
    assert np.nanmax(late) < 0.05           # rồi tụt xuống ở đoạn còn nguyên


def test_longest_run_and_progressive_flag_logic():
    assert sa.longest_run([0, 1, 1, 0, 1, 1, 1, 0]) == 3 and sa.longest_run([]) == 0
    assert sa.progressive_flag(np.array([0.9, 0.8, 0.7, 0.0]))[0] is True
    assert sa.progressive_flag(np.array([0.9, 0.0, 0.9, 0.9, 0.0]))[0] is False      # chuỗi bị ngắt
    assert sa.progressive_flag(np.array([0.9, np.nan, 0.9, 0.9]))[0] is False        # NaN làm đứt chuỗi
    flag, run = sa.progressive_flag(np.array([0.5] * 5 + [0.0]), min_run=5)
    assert flag and run == 5


# -------------------------------------------------------------------------- RS
def test_rs_is_near_zero_on_clean_and_tracks_embedding_rate():
    cover = textured(256, 256, seed=7)
    assert abs(sa.rs_analysis(cover)["p"]) < 0.06
    for rate in (0.3, 0.7):
        est = sa.rs_analysis(simulate_embedding(cover, rate, "keyed", np.random.default_rng(4)))["p"]
        assert abs(est - rate) < 0.12, (rate, est)


def test_rs_rejects_unsupported_group_size():
    with pytest.raises(ValueError):
        sa.rs_analysis(textured(32, 32), group_size=8)


# -------------------------------------------------------------- analyze tổng hợp
def test_analyze_structure_and_verdict_levels():
    rep = sa.analyze(textured(64, 64))
    for key in ("chi_square", "progressive", "rs", "level", "verdict", "thresholds", "ones_ratio", "n_samples"):
        assert key in rep
    assert rep["level"] in ("none", "medium", "high")
    assert set(rep["progressive"]) >= {"fractions", "p", "longest_run", "min_run", "n_points", "flag"}


@pytest.mark.skipif(not (SAMPLES / "camera.png").exists(), reason="thiếu ảnh mẫu")
def test_analyze_on_real_sample_clean_vs_sequential_vs_matching():
    cam = load_rgb(SAMPLES / "camera.png")
    assert sa.analyze(cam)["level"] == "none"
    rng = np.random.default_rng(9)
    assert sa.analyze(simulate_embedding(cam, 0.5, "sequential", rng))["level"] == "high"
    # LSB matching qua mặt chi-square toàn ảnh dù nhúng kín (hạn chế được nêu rõ trong báo cáo)
    m = sa.analyze(simulate_embedding(cam, 1.0, "matching", rng))
    assert m["chi_square"]["flag"] is False and m["level"] != "high"


def test_lsb_plane_helpers():
    arr = np.array([[[1, 2, 3]]], dtype=np.uint8)
    assert sa.lsb_plane(arr).tolist() == [[[255, 0, 255]]]
    assert sa.lsb_plane(arr, channel=2).tolist() == [[255]]
    assert sa.lsb_plane_gray(arr).tolist() == [[170]]


# ---------------------------------------------------------------------- metrics
def test_psnr_known_values():
    a = np.zeros((16, 16, 3), np.uint8)
    assert metrics.psnr(a, a) == float("inf")
    b = a + 1
    assert metrics.mse(a, b) == 1.0
    assert metrics.psnr(a, b) == pytest.approx(10 * np.log10(255 ** 2), abs=1e-9)


def test_ssim_properties():
    img = textured(64, 64)
    assert metrics.ssim(img, img) == pytest.approx(1.0)
    noisy = np.clip(img.astype(int) + np.random.default_rng(0).integers(-20, 21, img.shape), 0, 255).astype(np.uint8)
    assert 0 < metrics.ssim(img, noisy) < 0.95
    with pytest.raises(ValueError):
        metrics.ssim(img, img[:32])
    with pytest.raises(ValueError):
        metrics.ssim(img[:5, :5], img[:5, :5])


def test_ssim_matches_scikit_image_when_available():
    sk = pytest.importorskip("skimage.metrics")
    a = textured(80, 80, seed=1)
    b = np.clip(a.astype(int) + np.random.default_rng(1).integers(-6, 7, a.shape), 0, 255).astype(np.uint8)
    ref = sk.structural_similarity(a, b, win_size=7, channel_axis=2, data_range=255)
    assert metrics.ssim(a, b) == pytest.approx(ref, abs=2e-3)


def test_diff_stats():
    a = textured(32, 32)
    b = a.copy(); b[0, 0, 0] ^= 1
    d = metrics.diff_stats(a, b)
    assert d["changed_samples"] == 1 and d["max_abs_diff"] == 1 and d["samples"] == a.size
    same = metrics.diff_stats(a, a)
    assert same["changed_samples"] == 0 and same["psnr_db"] == float("inf")
    assert np.isnan(metrics.diff_stats(a, b, with_ssim=False)["ssim"])
    with pytest.raises(ValueError):
        metrics.diff_stats(a, a[:10])


# --------------------------------------------------------------------- image_io
def test_load_rgb_variants(tmp_path):
    rgba = Image.new("RGBA", (10, 8), (10, 20, 30, 128))
    p = tmp_path / "a.png"; rgba.save(p)
    arr = load_rgb(p)
    assert arr.shape == (8, 10, 3) and arr.dtype == np.uint8 and has_alpha(p)
    gray = Image.new("L", (6, 6), 77); g = tmp_path / "g.png"; gray.save(g)
    assert load_rgb(g).shape == (6, 6, 3) and not has_alpha(g)
    pal = Image.new("P", (5, 5)); q = tmp_path / "p.png"; pal.save(q)
    assert load_rgb(q).shape == (5, 5, 3)


def test_load_rgb_errors(tmp_path):
    with pytest.raises(ImageError, match="Không tìm thấy"):
        load_rgb(tmp_path / "missing.png")
    bad = tmp_path / "bad.png"; bad.write_bytes(b"not an image")
    with pytest.raises(ImageError):
        load_rgb(bad)
    deep = tmp_path / "d.png"; Image.new("I;16", (4, 4)).save(deep)
    with pytest.raises(ImageError, match="16-bit"):
        load_rgb(deep)
    for wrong in (np.zeros((4, 4), np.uint8), np.zeros((4, 4, 3), np.float32), np.zeros((4, 4, 4), np.uint8)):
        with pytest.raises(ImageError):
            load_rgb(wrong)


def test_save_lossless_refuses_lossy_formats(tmp_path):
    arr = textured(16, 16)
    for ext in (".jpg", ".jpeg", ".webp", ""):
        with pytest.raises(ImageError, match="làm mất dữ liệu"):
            save_lossless(arr, tmp_path / f"x{ext}")
    for ext in (".png", ".bmp", ".tiff", ".PNG"):
        p = save_lossless(arr, tmp_path / f"ok{ext}")
        assert np.array_equal(load_rgb(p), arr)


def test_to_png_bytes_roundtrip():
    arr = textured(20, 20)
    import io
    assert np.array_equal(np.array(Image.open(io.BytesIO(to_png_bytes(arr)))), arr)
