import io

import numpy as np
import pytest
from PIL import Image

from stegovault import crypto_layer as cl
from stegovault.embed import METHODS, capacity_bytes, embed, payload_positions, simulate_embedding
from stegovault.errors import CapacityError, DecryptionError, StegoError
from stegovault.extract import extract
from stegovault.lsb import bits_to_bytes, read_bits

from conftest import textured

PW = "mật khẩu thử nghiệm"
MSG = "Xin chào StegoVault! Tiếng Việt có dấu: ế ộ ữ, và emoji 🚀"


@pytest.mark.parametrize("method", list(METHODS))
def test_text_roundtrip(cover, method):
    res = embed(cover, MSG, PW, method=method)
    out = extract(res.stego, PW)
    assert out.is_text and out.text == MSG


@pytest.mark.parametrize("method", list(METHODS))
def test_file_roundtrip_binary_with_filename(big_cover, method):
    blob = np.random.default_rng(5).bytes(3000)
    res = embed(big_cover, blob, PW, method=method, filename="tài liệu.bin")
    out = extract(res.stego, PW)
    assert not out.is_text and out.data == blob and out.filename == "tài liệu.bin"


@pytest.mark.parametrize("method", list(METHODS))
def test_changes_only_lsb_scale(cover, method):
    res = embed(cover, MSG, PW, method=method)
    diff = np.abs(res.stego.astype(int) - cover.astype(int))
    assert diff.max() <= 1
    assert res.samples_changed == int((diff != 0).sum())
    if method != "matching":   # LSB replacement: 7 bit cao nguyên vẹn
        assert np.array_equal(res.stego >> 1, cover >> 1)


def test_embed_does_not_mutate_cover(cover):
    before = cover.copy()
    embed(cover, MSG, PW)
    assert np.array_equal(cover, before)


def test_matching_is_safe_on_saturated_image():
    black, white = np.zeros((64, 64, 3), np.uint8), np.full((64, 64, 3), 255, np.uint8)
    for img in (black, white):
        res = embed(img, MSG, PW, method="matching")
        assert np.abs(res.stego.astype(int) - img.astype(int)).max() <= 1
        assert extract(res.stego, PW).text == MSG


def test_wrong_password_rejected(cover):
    res = embed(cover, MSG, PW)
    with pytest.raises(DecryptionError):
        extract(res.stego, PW + "x")


def test_image_without_message_rejected(cover):
    with pytest.raises(DecryptionError):
        extract(cover, PW)


def test_tiny_image_rejected_on_extract():
    with pytest.raises(DecryptionError):
        extract(np.zeros((4, 4, 3), np.uint8), PW)


def test_two_embeddings_of_same_message_differ(cover):
    a = embed(cover, MSG, PW, method="keyed").stego
    b = embed(cover, MSG, PW, method="keyed").stego
    assert not np.array_equal(a, b)   # salt + nonce ngẫu nhiên


def test_embedded_stream_has_no_plaintext_magic(cover):
    """Luồng bit nhúng nhìn như ngẫu nhiên: không chứa tin ở dạng rõ, tỉ lệ bit 1 ≈ 1/2."""
    res = embed(cover, "BÍ MẬT-BÍ MẬT-BÍ MẬT", PW, method="sequential")
    flat = res.stego.reshape(-1)
    n_bits = res.embedded_bits
    stream = bits_to_bytes(read_bits(flat, np.arange(n_bits - n_bits % 8)))
    assert "BÍ MẬT".encode() not in stream
    ones = np.unpackbits(np.frombuffer(stream, np.uint8)).mean()
    assert 0.35 < ones < 0.65


def test_extract_position_mode_is_respected(cover):
    res = embed(cover, MSG, PW, method="sequential")
    assert extract(res.stego, PW, position_mode="sequential").text == MSG
    with pytest.raises(DecryptionError):
        extract(res.stego, PW, position_mode="keyed")
    assert extract(res.stego, PW).position_mode == "sequential"
    with pytest.raises(StegoError):
        extract(res.stego, PW, position_mode="bogus")


def test_kdf_is_autodetected(cover):
    for kdf in cl.available_kdfs():
        res = embed(cover, MSG, PW, kdf=kdf)
        out = extract(res.stego, PW)
        assert out.text == MSG and out.kdf == kdf


def test_unknown_method_and_bad_message_type(cover):
    with pytest.raises(StegoError):
        embed(cover, MSG, PW, method="nope")
    with pytest.raises(TypeError):
        embed(cover, 12345, PW)   # type: ignore[arg-type]
    with pytest.raises(StegoError):
        embed(cover, MSG, "")


# ---------------------------------------------------------------------- dung lượng
def test_capacity_formula():
    assert capacity_bytes(96 * 96 * 3) == (96 * 96 * 3 - 160) // 8 - 28
    assert capacity_bytes(100) == 0
    assert capacity_bytes(textured(64, 64)) == capacity_bytes(64 * 64 * 3)


def test_capacity_boundary_is_exact():
    """Tin chiếm đúng dung lượng tối đa thì vừa; thừa 1 byte thì báo lỗi - và tin vừa khít vẫn giải mã được."""
    img = textured(64, 64, seed=3)
    cap = capacity_bytes(img)
    exact = "a" * (cap - 2)                      # tiêu đề gói 2 byte; --no-compress để kích thước đúng như tính
    res = embed(img, exact, PW, compress=False)
    assert res.container_bytes == cap and res.utilization == 1.0
    assert extract(res.stego, PW).text == exact
    with pytest.raises(CapacityError):
        embed(img, "a" * (cap - 1), PW, compress=False)


def test_full_capacity_uses_every_sample(cover):
    res = embed(cover, "z" * (capacity_bytes(cover) - 2), PW, compress=False, method="keyed")
    assert res.embedded_bits == cover.size    # nhúng kín: tỉ lệ 1.0 bit/mẫu
    assert res.embedding_rate == pytest.approx(1.0)
    assert res.bits_per_pixel == pytest.approx(3.0)


def test_capacity_error_message_is_helpful(cover):
    with pytest.raises(CapacityError, match="byte"):
        embed(cover, np.random.default_rng(0).bytes(capacity_bytes(cover) + 100), PW)


def test_payload_positions_stay_after_bootstrap_and_are_unique():
    n = 20_000
    for mode in ("sequential", "keyed"):
        pos = payload_positions(n, 5000, b"k" * 32, mode)
        assert pos.min() >= cl.BOOTSTRAP_BITS and pos.max() < n
        assert len(set(pos.tolist())) == 5000
    with pytest.raises(CapacityError):
        payload_positions(1000, 1000, b"k" * 32, "keyed")
    with pytest.raises(StegoError):
        payload_positions(1000, 10, b"k" * 32, "diag")


# -------------------------------------------------------------------- tấn công
def test_single_bit_tamper_in_ciphertext_is_detected(big_cover):
    for method in METHODS:
        res = embed(big_cover, MSG, PW, method=method)
        flat = res.stego.reshape(-1).copy()
        boot = bits_to_bytes(read_bits(flat, np.arange(cl.BOOTSTRAP_BITS)))
        keys = cl.derive_keys(PW, boot[: cl.SALT_LEN])
        blen = cl.unmask_length(boot[cl.SALT_LEN:], keys)
        pos = payload_positions(flat.size, blen * 8, keys.pos, METHODS[method][1])
        flat[pos[len(pos) // 3]] ^= 1
        with pytest.raises(DecryptionError):
            extract(flat.reshape(res.stego.shape), PW)


@pytest.mark.parametrize("quality", [100, 90])
def test_jpeg_recompression_destroys_message(big_cover, quality):
    res = embed(big_cover, MSG, PW, method="matching")
    buf = io.BytesIO()
    Image.fromarray(res.stego).save(buf, format="JPEG", quality=quality)
    recompressed = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    with pytest.raises(DecryptionError):
        extract(recompressed, PW)


def test_lossless_formats_preserve_message(big_cover, tmp_path):
    res = embed(big_cover, MSG, PW)
    for ext in ("png", "bmp", "tiff"):
        p = tmp_path / f"s.{ext}"
        Image.fromarray(res.stego).save(p)
        assert extract(p, PW).text == MSG


def test_cropped_image_destroys_message(big_cover):
    res = embed(big_cover, MSG, PW, method="sequential")
    with pytest.raises(DecryptionError):
        extract(res.stego[1:, 1:], PW)


# ------------------------------------------------------------------- mô phỏng
def test_simulate_embedding_rate_and_determinism(big_cover):
    a = simulate_embedding(big_cover, 0.25, "keyed", np.random.default_rng(1))
    b = simulate_embedding(big_cover, 0.25, "keyed", np.random.default_rng(1))
    assert np.array_equal(a, b)
    changed = (a != big_cover).mean()
    assert 0.25 / 2 * 0.9 < changed < 0.25 / 2 * 1.1      # mỗi bit nhúng đổi mẫu với xác suất 1/2
    assert np.array_equal(simulate_embedding(big_cover, 0.0, "sequential", np.random.default_rng(1)).shape, big_cover.shape)
    with pytest.raises(StegoError):
        simulate_embedding(big_cover, 0.1, "x", np.random.default_rng(1))


def test_simulate_sequential_touches_only_a_prefix(big_cover):
    s = simulate_embedding(big_cover, 0.30, "sequential", np.random.default_rng(1))
    changed = np.flatnonzero((s != big_cover).reshape(-1))
    # 160 bit bootstrap nằm đầu dãy, rồi tới n_bits bit thân nhúng liên tiếp ngay sau đó
    assert changed.max() < cl.BOOTSTRAP_BITS + int(0.30 * big_cover.size)
    assert changed.max() > 0.9 * 0.30 * big_cover.size          # và thực sự phủ gần hết đoạn đầu


def test_embedding_rate_property_matches_message(cover):
    res = embed(cover, "ngắn", PW)
    assert res.embedded_bits == cl.BOOTSTRAP_BITS + 8 * (cl.OVERHEAD + res.container_bytes)
    assert res.embedding_rate == pytest.approx(res.embedded_bits / cover.size)
