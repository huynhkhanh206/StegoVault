import numpy as np
import pytest

from stegovault.lsb import bits_to_bytes, bytes_to_bits, read_bits, write_bits
from stegovault.permutation import FeistelPermutation, keyed_positions

KEY = b"k" * 32


# ------------------------------------------------------------- hoán vị Feistel
@pytest.mark.parametrize("size", [1, 2, 3, 5, 16, 17, 100, 1000, 4097, 65536])
def test_permutation_is_bijection(size):
    p = FeistelPermutation(KEY, size).map(np.arange(size))
    assert p.min() >= 0 and p.max() < size
    assert np.array_equal(np.sort(p), np.arange(size))


def test_permutation_deterministic_across_instances():
    a = FeistelPermutation(KEY, 5000).map(np.arange(5000))
    b = FeistelPermutation(KEY, 5000).map(np.arange(5000))
    assert np.array_equal(a, b)


def test_permutation_depends_on_key_and_is_not_identity():
    a = FeistelPermutation(KEY, 5000).map(np.arange(5000))
    b = FeistelPermutation(b"j" * 32, 5000).map(np.arange(5000))
    assert not np.array_equal(a, b)
    assert not np.array_equal(a, np.arange(5000))
    # đủ "xáo trộn": rất ít điểm cố định
    assert (a == np.arange(5000)).mean() < 0.01


def test_permutation_scatters_evenly():
    """Dải vị trí liên tiếp phải trải đều khắp miền (không dồn về một góc)."""
    size = 100_000
    pos = keyed_positions(KEY, size, 5000)
    hist, _ = np.histogram(pos, bins=10, range=(0, size))
    assert hist.min() > 400 and hist.max() < 600   # kỳ vọng 500 mỗi ô


def test_keyed_positions_unique_and_in_range():
    pos = keyed_positions(KEY, 10_000, 9_000)
    assert len(set(pos.tolist())) == 9_000
    assert pos.min() >= 0 and pos.max() < 10_000


def test_chunked_evaluation_gives_identical_positions(monkeypatch):
    """Xử lý theo lô chỉ để tiết kiệm RAM - vị trí phải y hệt, nếu không ảnh cũ sẽ không giải mã được nữa."""
    import stegovault.permutation as P
    whole = keyed_positions(KEY, 50_000, 30_000)
    monkeypatch.setattr(P, "CHUNK", 777)           # nhiều lô, kích thước lẻ
    assert np.array_equal(keyed_positions(KEY, 50_000, 30_000), whole)
    # giá trị chuẩn đã ghi lại từ bản cài đặt gốc (một lượt, không chia lô)
    import hashlib
    monkeypatch.setattr(P, "CHUNK", 1 << 20)
    digest = hashlib.sha256(keyed_positions(b"golden-key-0123456789abcdef012345", 123457, 50000).tobytes()).hexdigest()
    assert digest == GOLDEN_123457_50000


GOLDEN_123457_50000 = "449c24ad4c55e0107038ede718126c07e47c8992a38371c822853b7bfcd9f075"


def test_keyed_positions_rejects_count_over_size():
    with pytest.raises(ValueError):
        keyed_positions(KEY, 10, 11)


def test_permutation_rejects_bad_size():
    with pytest.raises(ValueError):
        FeistelPermutation(KEY, 0)


# ----------------------------------------------------------------- bit helpers
def test_bits_roundtrip():
    data = bytes(range(256))
    assert bits_to_bytes(bytes_to_bits(data)) == data
    assert bytes_to_bits(b"\x80").tolist() == [1, 0, 0, 0, 0, 0, 0, 0]


def test_write_bits_replace_sets_exact_lsb_and_keeps_input():
    rng = np.random.default_rng(0)
    flat = rng.integers(0, 256, 1000, dtype=np.uint8)
    original = flat.copy()
    pos = np.arange(0, 1000, 3)
    bits = rng.integers(0, 2, pos.size, dtype=np.uint8)
    out, changed = write_bits(flat, pos, bits, "replace")
    assert np.array_equal(flat, original)                # không sửa mảng gốc
    assert np.array_equal(read_bits(out, pos), bits)     # LSB đúng
    assert np.array_equal(out >> 1, flat >> 1)           # 7 bit cao nguyên vẹn
    assert changed == int(((flat[pos] & 1) != bits).sum())
    mask = np.ones(1000, bool); mask[pos] = False
    assert np.array_equal(out[mask], flat[mask])         # vị trí khác không đổi


def test_write_bits_matching_sets_lsb_and_changes_by_at_most_one():
    rng = np.random.default_rng(1)
    flat = rng.integers(0, 256, 5000, dtype=np.uint8)
    pos = np.arange(5000)
    bits = rng.integers(0, 2, 5000, dtype=np.uint8)
    out, _ = write_bits(flat, pos, bits, "match", np.random.default_rng(2))
    assert np.array_equal(read_bits(out, pos), bits)
    diff = out.astype(int) - flat.astype(int)
    assert np.abs(diff).max() == 1
    # có cả +1 lẫn -1 (đây chính là điểm khác với LSB replacement)
    assert (diff == 1).any() and (diff == -1).any()


@pytest.mark.parametrize("edge", [0, 255])
def test_write_bits_matching_never_overflows_at_edges(edge):
    flat = np.full(2000, edge, dtype=np.uint8)
    pos = np.arange(2000)
    bits = np.random.default_rng(3).integers(0, 2, 2000, dtype=np.uint8)
    out, _ = write_bits(flat, pos, bits, "match", np.random.default_rng(4))
    assert np.array_equal(read_bits(out, pos), bits)
    # nếu có tràn số uint8 (0 - 1 -> 255 hoặc 255 + 1 -> 0) thì độ lệch sẽ là 255, không phải <= 1
    assert np.abs(out.astype(int) - edge).max() <= 1
    assert (out <= 1).all() if edge == 0 else (out >= 254).all()


def test_write_bits_validates_input():
    flat = np.zeros(10, dtype=np.uint8)
    with pytest.raises(ValueError):
        write_bits(flat, np.arange(3), np.zeros(4, dtype=np.uint8))
    with pytest.raises(ValueError):
        write_bits(flat, np.arange(3), np.zeros(3, dtype=np.uint8), mode="nope")
