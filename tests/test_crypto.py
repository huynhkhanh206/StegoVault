import os
import unicodedata
import zlib

import pytest

from stegovault import crypto_layer as cl
from stegovault.errors import DecryptionError, StegoError

from conftest import DEFAULT_KDF


def test_default_kdf_parameters_are_the_documented_ones():
    assert DEFAULT_KDF["SCRYPT_N"] == 2 ** 15 and DEFAULT_KDF["SCRYPT_R"] == 8 and DEFAULT_KDF["SCRYPT_P"] == 1
    assert DEFAULT_KDF["ARGON2_MEMORY_KIB"] == 65536 and DEFAULT_KDF["ARGON2_ITERATIONS"] == 3
    assert DEFAULT_KDF["ARGON2_LANES"] == 4


def test_constants_are_consistent():
    assert cl.BOOTSTRAP_BYTES == cl.SALT_LEN + cl.LEN_FIELD == 20
    assert cl.BOOTSTRAP_BITS == 160
    assert cl.OVERHEAD == cl.NONCE_LEN + cl.TAG_LEN == 28


# ------------------------------------------------------------------------- KDF
@pytest.mark.parametrize("kdf", ["scrypt", "argon2id"])
def test_derive_keys_deterministic_and_independent(kdf):
    if kdf not in cl.available_kdfs():
        pytest.skip("cryptography không có Argon2id")
    salt = b"s" * 16
    a, b = cl.derive_keys("mật khẩu", salt, kdf), cl.derive_keys("mật khẩu", salt, kdf)
    assert a == b and len(a.enc) == 32 and len(a.pos) == 32
    assert a.enc != a.pos                                      # hai khóa độc lập
    assert cl.derive_keys("mật khẩu", b"t" * 16, kdf) != a     # salt khác -> khóa khác
    assert cl.derive_keys("mật khẩU", salt, kdf) != a          # mật khẩu khác -> khóa khác


def test_password_unicode_normalization():
    composed = "Nguyễn"                                    # ễ dựng sẵn
    decomposed = unicodedata.normalize("NFD", composed)    # ê + dấu ngã tổ hợp
    assert composed != decomposed
    assert cl.derive_keys(composed, b"s" * 16) == cl.derive_keys(decomposed, b"s" * 16)


def test_empty_password_and_unknown_kdf_rejected():
    with pytest.raises(StegoError):
        cl.derive_keys("", b"s" * 16)
    with pytest.raises(StegoError):
        cl.derive_keys("x", b"s" * 16, "md5")


# ------------------------------------------------------------------ seal / open
def test_seal_open_roundtrip():
    s = cl.seal(b"hello world", "pw")
    assert len(s.bootstrap) == cl.BOOTSTRAP_BYTES
    assert len(s.body) == cl.NONCE_LEN + len(b"hello world") + cl.TAG_LEN
    assert cl.open_sealed(s.bootstrap, s.body, s.keys) == b"hello world"


def test_seal_is_randomized_salt_and_nonce_never_reused():
    a, b = cl.seal(b"same", "pw"), cl.seal(b"same", "pw")
    assert a.bootstrap[: cl.SALT_LEN] != b.bootstrap[: cl.SALT_LEN]
    assert a.body[: cl.NONCE_LEN] != b.body[: cl.NONCE_LEN]
    assert a.body != b.body
    nonces = {cl.seal(b"x", "pw").body[: cl.NONCE_LEN] for _ in range(50)}
    assert len(nonces) == 50


def test_wrong_key_rejected():
    s = cl.seal(b"secret", "right")
    wrong = cl.derive_keys("wrong", s.bootstrap[: cl.SALT_LEN])
    with pytest.raises(DecryptionError):
        cl.open_sealed(s.bootstrap, s.body, wrong)


@pytest.mark.parametrize("where", ["nonce", "ciphertext", "tag"])
def test_any_single_bit_flip_in_body_is_detected(where):
    s = cl.seal(b"x" * 100, "pw")
    idx = {"nonce": 0, "ciphertext": cl.NONCE_LEN + 10, "tag": len(s.body) - 1}[where]
    body = bytearray(s.body)
    body[idx] ^= 0x01
    with pytest.raises(DecryptionError):
        cl.open_sealed(s.bootstrap, bytes(body), s.keys)


def test_bootstrap_is_authenticated_as_aad():
    """Sửa salt hoặc độ dài đã che cũng phải làm hỏng giải mã (AAD = bootstrap)."""
    s = cl.seal(b"x" * 50, "pw")
    for i in (0, cl.SALT_LEN, cl.BOOTSTRAP_BYTES - 1):
        bad = bytearray(s.bootstrap)
        bad[i] ^= 0x01
        with pytest.raises(DecryptionError):
            cl.open_sealed(bytes(bad), s.body, s.keys)


def test_open_rejects_truncated_body():
    s = cl.seal(b"abc", "pw")
    with pytest.raises(DecryptionError):
        cl.open_sealed(s.bootstrap, s.body[: cl.OVERHEAD - 1], s.keys)


def test_length_mask_roundtrip_and_hides_length():
    keys = cl.derive_keys("pw", b"s" * 16)
    for n in (28, 1000, 2 ** 31):
        assert cl.unmask_length(cl.mask_length(n, keys), keys) == n
    other = cl.derive_keys("pw2", b"s" * 16)
    assert cl.unmask_length(cl.mask_length(1000, keys), other) != 1000
    assert cl.mask_length(1000, keys) != (1000).to_bytes(4, "big")   # không lộ độ dài ở dạng rõ


# ------------------------------------------------------------------- payload
def test_pack_unpack_text_and_file():
    t = cl.unpack_payload(cl.pack_payload("Xin chào 🚀".encode(), cl.KIND_TEXT))
    assert t.is_text and t.text() == "Xin chào 🚀"
    f = cl.unpack_payload(cl.pack_payload(os.urandom(500), cl.KIND_FILE, "báo cáo.pdf"))
    assert not f.is_text and f.filename == "báo cáo.pdf" and len(f.data) == 500


def test_compression_used_only_when_it_helps():
    redundant = cl.pack_payload(b"a" * 5000, cl.KIND_TEXT)
    assert redundant[1] == 1 and len(redundant) < 200
    random_data = cl.pack_payload(os.urandom(2000), cl.KIND_TEXT)
    assert random_data[1] == 0 and len(random_data) == 2002
    assert cl.pack_payload(b"a" * 5000, cl.KIND_TEXT, compress=False)[1] == 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\Windows\\system32\\evil.dll", "evil.dll"),
        ("/abs/path/file.txt", "file.txt"),
        ("normal.txt", "normal.txt"),
        ("", "extracted.bin"),
        (None, "extracted.bin"),
        ("..", "extracted.bin"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("a<b>c:d|e?.txt", "abcde.txt"),
        ("  spaced.txt. ", "spaced.txt"),
    ],
)
def test_safe_filename(raw, expected):
    assert cl.safe_filename(raw) == expected


def test_safe_filename_limits_length_and_control_chars():
    assert len(cl.safe_filename("a" * 1000 + ".txt")) <= 200
    assert "\x00" not in cl.safe_filename("evil\x00.txt") and "\n" not in cl.safe_filename("a\nb.txt")


def test_unpack_rejects_garbage():
    for blob in (b"", b"\x00", b"\x07\x00abc", b"\x00\x05abc", b"\x01\x00\x00"):
        with pytest.raises(DecryptionError):
            cl.unpack_payload(blob)
    with pytest.raises(DecryptionError):
        cl.unpack_payload(bytes([cl.KIND_TEXT, 1]) + b"not zlib data")


def test_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(cl, "MAX_PLAINTEXT", 10_000)
    bomb = bytes([cl.KIND_TEXT, 1]) + zlib.compress(b"\x00" * 1_000_000, 9)
    assert len(bomb) < 2000
    with pytest.raises(DecryptionError):
        cl.unpack_payload(bomb)


def test_file_payload_with_hostile_name_is_sanitized_on_unpack():
    blob = cl.pack_payload(b"data", cl.KIND_FILE, "../../x.sh")
    assert cl.unpack_payload(blob).filename == "x.sh"


def test_graceful_fallback_when_argon2id_is_unavailable(monkeypatch):
    """Với thư viện cryptography cũ (không có Argon2id), công cụ vẫn chạy bằng scrypt và báo lỗi rõ ràng khi bị yêu cầu Argon2id."""
    from stegovault.embed import embed
    from stegovault.extract import extract
    import numpy as np

    monkeypatch.setattr(cl, "argon2_available", lambda: False)
    assert cl.available_kdfs() == ("scrypt",)
    with pytest.raises(StegoError, match="Argon2id"):
        cl.derive_keys("pw", b"s" * 16, "argon2id")
    img = np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    res = embed(img, "vẫn chạy", "pw")            # mặc định là scrypt
    assert extract(res.stego, "pw").text == "vẫn chạy"   # tự dò KDF chỉ thử scrypt
    with pytest.raises(StegoError, match="Argon2id"):
        embed(img, "x", "pw", kdf="argon2id")


# ------------------------------------------------------------- nhiều file (bundle)
def test_unique_names_dedups_case_insensitively_and_sanitizes():
    assert cl.unique_names(["a.txt", "A.txt", "a.txt", "../b", None, ""]) == [
        "a.txt", "A (2).txt", "a (3).txt", "b", "data.bin", "data (2).bin"]
    assert cl.unique_names(["noext", "noext"]) == ["noext", "noext (2)"]


def test_pack_files_single_file_keeps_the_old_file_format():
    one = cl.pack_files([("x.bin", b"abc")])
    assert one == cl.pack_payload(b"abc", cl.KIND_FILE, "x.bin") and one[0] == cl.KIND_FILE


def test_bundle_roundtrip_preserves_order_names_and_bytes():
    files = [("báo cáo.pdf", os.urandom(300)), ("ghi chú.txt", "xin chào".encode()), ("rỗng.bin", b""), ("báo cáo.pdf", "trùng".encode())]
    blob = cl.pack_files(files)
    assert blob[0] == cl.KIND_BUNDLE
    p = cl.unpack_payload(blob)
    assert p.is_bundle and not p.is_text
    assert [n for n, _ in p.file_list()] == ["báo cáo.pdf", "ghi chú.txt", "rỗng.bin", "báo cáo (2).pdf"]
    assert [d for _, d in p.file_list()] == [d for _, d in files]


def test_bundle_is_compressed_as_a_whole():
    blob = cl.pack_files([("a.txt", b"x" * 4000), ("b.txt", b"x" * 4000)])
    assert blob[1] == 1 and len(blob) < 200
    assert cl.pack_files([("a", b"x" * 4000), ("b", b"x" * 4000)], compress=False)[1] == 0


def test_bundle_rejects_empty_and_too_many_files():
    with pytest.raises(StegoError):
        cl.pack_files([])
    with pytest.raises(StegoError, match="tối đa"):
        cl.pack_files([(f"{i}.txt", b"") for i in range(cl.MAX_FILES + 1)])
    assert cl.unpack_payload(cl.pack_files([(f"{i}.txt", b"") for i in range(cl.MAX_FILES)])).file_list()[-1][0] == f"{cl.MAX_FILES - 1}.txt"


def test_bundle_hostile_names_are_sanitized_on_unpack():
    body = b""
    for name in ("../../etc/passwd", "C:\\Windows\\evil.dll", "CON"):
        raw = name.encode()
        body += len(raw).to_bytes(2, "big") + raw + (1).to_bytes(4, "big") + b"x"
    blob = bytes([cl.KIND_BUNDLE, 0]) + (3).to_bytes(2, "big") + body
    assert [n for n, _ in cl.unpack_payload(blob).file_list()] == ["passwd", "evil.dll", "_CON"]


@pytest.mark.parametrize("body", [
    b"",                                                              # thiếu số file
    (0).to_bytes(2, "big"),                                           # 0 file
    (cl.MAX_FILES + 1).to_bytes(2, "big"),                            # quá nhiều file
    (1).to_bytes(2, "big"),                                           # khai 1 file nhưng không có gì
    (1).to_bytes(2, "big") + (5).to_bytes(2, "big") + b"ab",          # tên dài hơn dữ liệu còn lại
    (1).to_bytes(2, "big") + (1).to_bytes(2, "big") + b"a" + (9).to_bytes(4, "big") + b"xy",   # kích thước vượt biên
    (1).to_bytes(2, "big") + (1).to_bytes(2, "big") + b"a" + (1).to_bytes(4, "big") + b"x" + b"rac",  # thừa byte
])
def test_bundle_parser_rejects_every_malformed_layout(body):
    with pytest.raises(DecryptionError):
        cl.unpack_payload(bytes([cl.KIND_BUNDLE, 0]) + body)


def test_bundle_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(cl, "MAX_PLAINTEXT", 10_000)
    blob = cl.pack_files([("a", b"\x00" * 1_000_000), ("b", b"\x00" * 10)])
    assert len(blob) < 2000
    with pytest.raises(DecryptionError):
        cl.unpack_payload(blob)


def test_pack_payload_refuses_bundle_kind():
    with pytest.raises(StegoError):
        cl.pack_payload(b"x", cl.KIND_BUNDLE)
