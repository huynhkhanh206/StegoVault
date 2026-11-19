"""Lớp mật mã của StegoVault.

Luồng mã hóa (seal):

    mật khẩu --NFKC--> KDF(salt) --> 64 byte = [khóa AES-256 (32B) | khóa vị trí (32B)]
    plaintext --AES-256-GCM(nonce, AAD = salt || độ dài_che)--> ciphertext || tag

Những điểm thiết kế đáng chú ý:

* KDF làm chậm việc dò mật khẩu: scrypt (mặc định, có sẵn mọi nơi) hoặc Argon2id
  (RFC 9106, cần cryptography >= 44).
* Một lần suy dẫn cho ra HAI khóa độc lập: khóa mã hóa và khóa chọn vị trí nhúng bit.
* AES-GCM là AEAD: sai mật khẩu hoặc ảnh bị sửa dù chỉ 1 bit đều bị phát hiện (thẻ xác thực
  không khớp) thay vì cho ra rác.
* Salt và nonce là ngẫu nhiên MỖI LẦN mã hóa nên không bao giờ dùng lại cặp (khóa, nonce).
* Không có "magic number" dạng rõ trong dữ liệu nhúng: toàn bộ luồng bit nhìn như ngẫu nhiên,
  kể cả trường độ dài (được che bằng HMAC) - tránh để lộ chữ ký của công cụ.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import os
import struct
import unicodedata
import zlib
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .errors import DecryptionError, StegoError

SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
LEN_FIELD = 4
BOOTSTRAP_BYTES = SALT_LEN + LEN_FIELD      # salt || độ dài (đã che) = 20 byte
BOOTSTRAP_BITS = BOOTSTRAP_BYTES * 8        # 160 bit, luôn nằm ở 160 mẫu đầu tiên
OVERHEAD = NONCE_LEN + TAG_LEN              # byte thêm vào bởi AES-GCM (28)
CONTAINER_HEADER = 2                        # byte "kind" + byte "nén"
MAX_PLAINTEXT = 512 * 1024 * 1024           # chặn "bom nén" khi giải nén

# Tham số KDF (có thể giảm trong test cho nhanh)
SCRYPT_N = 2 ** 15   # 32 MiB bộ nhớ với r = 8
SCRYPT_R = 8
SCRYPT_P = 1
ARGON2_ITERATIONS = 3        # RFC 9106, cấu hình "bộ nhớ thấp"
ARGON2_LANES = 4
ARGON2_MEMORY_KIB = 65536    # 64 MiB

KDFS = ("scrypt", "argon2id")

KIND_TEXT = 0
KIND_FILE = 1


@dataclass(frozen=True)
class Keys:
    enc: bytes   # 32 byte - khóa AES-256-GCM
    pos: bytes   # 32 byte - khóa chọn vị trí nhúng


@dataclass(frozen=True)
class Sealed:
    bootstrap: bytes  # salt || độ dài đã che  (20 byte)
    body: bytes       # nonce || ciphertext || tag
    keys: Keys
    kdf: str


@dataclass(frozen=True)
class Payload:
    kind: int
    data: bytes
    filename: Optional[str] = None

    @property
    def is_text(self) -> bool:
        return self.kind == KIND_TEXT

    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- KDF
@functools.lru_cache(maxsize=1)
def argon2_available() -> bool:
    """True nếu thư viện cryptography hiện tại có Argon2id."""
    try:
        from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

        Argon2id(salt=b"\0" * 16, length=32, iterations=1, lanes=1, memory_cost=64).derive(b"x")
        return True
    except Exception:
        return False


def available_kdfs() -> Tuple[str, ...]:
    return KDFS if argon2_available() else KDFS[:1]


def derive_keys(password: str, salt: bytes, kdf: str = "scrypt") -> Keys:
    """Suy dẫn (khóa mã hóa, khóa vị trí) từ mật khẩu."""
    if not password:
        raise StegoError("Mật khẩu không được để trống.")
    # NFKC: gõ "ế" dạng dựng sẵn hay dạng tổ hợp đều cho cùng một mật khẩu.
    pw = unicodedata.normalize("NFKC", password).encode("utf-8")

    if kdf == "scrypt":
        okm = Scrypt(salt=salt, length=64, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(pw)
    elif kdf == "argon2id":
        if not argon2_available():
            raise StegoError(
                "Argon2id cần thư viện cryptography >= 44. Hãy dùng --kdf scrypt hoặc nâng cấp."
            )
        from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

        okm = Argon2id(
            salt=salt,
            length=64,
            iterations=ARGON2_ITERATIONS,
            lanes=ARGON2_LANES,
            memory_cost=ARGON2_MEMORY_KIB,
        ).derive(pw)
    else:
        raise StegoError(f"KDF không hợp lệ: {kdf!r}")
    return Keys(enc=okm[:32], pos=okm[32:])


# ----------------------------------------------------------- che / hiện độ dài
def _length_mask(keys: Keys) -> bytes:
    return hmac.new(keys.pos, b"stegovault/len-mask", hashlib.sha256).digest()[:LEN_FIELD]


def mask_length(n: int, keys: Keys) -> bytes:
    raw = struct.pack(">I", n)
    return bytes(a ^ b for a, b in zip(raw, _length_mask(keys)))


def unmask_length(masked: bytes, keys: Keys) -> int:
    raw = bytes(a ^ b for a, b in zip(masked, _length_mask(keys)))
    return struct.unpack(">I", raw)[0]


# ------------------------------------------------------------------ seal / open
def seal(plaintext: bytes, password: str, kdf: str = "scrypt") -> Sealed:
    """Mã hóa + xác thực ``plaintext``. Salt và nonce lấy ngẫu nhiên từ os.urandom."""
    salt = os.urandom(SALT_LEN)
    keys = derive_keys(password, salt, kdf)
    body_len = NONCE_LEN + len(plaintext) + TAG_LEN
    bootstrap = salt + mask_length(body_len, keys)
    nonce = os.urandom(NONCE_LEN)
    ciphertext = AESGCM(keys.enc).encrypt(nonce, plaintext, bootstrap)  # AAD = bootstrap
    return Sealed(bootstrap=bootstrap, body=nonce + ciphertext, keys=keys, kdf=kdf)


def open_sealed(bootstrap: bytes, body: bytes, keys: Keys) -> bytes:
    """Giải mã + kiểm tra toàn vẹn. Ném DecryptionError nếu thẻ GCM không khớp."""
    if len(body) < OVERHEAD:
        raise DecryptionError("Dữ liệu quá ngắn để là một bản mã hợp lệ.")
    nonce, ciphertext = body[:NONCE_LEN], body[NONCE_LEN:]
    try:
        return AESGCM(keys.enc).decrypt(nonce, ciphertext, bootstrap)
    except InvalidTag:
        raise DecryptionError(
            "Không giải mã được: sai mật khẩu, ảnh không chứa dữ liệu, hoặc ảnh đã bị chỉnh sửa/nén lại."
        ) from None


# --------------------------------------------------------------------- payload
def safe_filename(name: Optional[str], default: str = "extracted.bin") -> str:
    """Làm sạch tên file lấy từ ảnh (KHÔNG tin dữ liệu bên ngoài): bỏ đường dẫn, ký tự cấm."""
    if not name:
        return default
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    name = name.strip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if not name or name.split(".")[0].upper() in reserved:
        return default if not name else "_" + name
    return name[:200]


def pack_payload(
    data: bytes, kind: int = KIND_TEXT, filename: Optional[str] = None, compress: bool = True
) -> bytes:
    """Đóng gói: [kind][cờ nén][thân]. Với file, thân = [độ dài tên (2B)][tên][dữ liệu]."""
    body = data
    if kind == KIND_FILE:
        name = safe_filename(filename, "data.bin").encode("utf-8")[:1024]
        body = struct.pack(">H", len(name)) + name + data
    compressed = 0
    if compress:
        candidate = zlib.compress(body, 9)
        if len(candidate) < len(body):
            body, compressed = candidate, 1
    return bytes([kind, compressed]) + body


def unpack_payload(blob: bytes) -> Payload:
    if len(blob) < CONTAINER_HEADER:
        raise DecryptionError("Gói dữ liệu rỗng hoặc hỏng.")
    kind, compressed, body = blob[0], blob[1], blob[2:]
    if kind not in (KIND_TEXT, KIND_FILE) or compressed not in (0, 1):
        raise DecryptionError("Gói dữ liệu có định dạng không hợp lệ.")
    if compressed:
        d = zlib.decompressobj()
        try:
            body = d.decompress(body, MAX_PLAINTEXT)
        except zlib.error:
            raise DecryptionError("Dữ liệu nén bị hỏng.") from None
        if d.unconsumed_tail:
            raise DecryptionError("Dữ liệu giải nén vượt giới hạn cho phép.")
    if kind == KIND_TEXT:
        return Payload(KIND_TEXT, body)
    if len(body) < 2:
        raise DecryptionError("Gói file bị hỏng.")
    (name_len,) = struct.unpack(">H", body[:2])
    name = body[2 : 2 + name_len].decode("utf-8", errors="replace")
    return Payload(KIND_FILE, body[2 + name_len :], safe_filename(name))
