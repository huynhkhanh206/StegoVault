"""StegoVault - giấu tin mã hóa trong ảnh và cuộc đua giữa người giấu với người dò.

Các thành phần chính:
    crypto_layer  : KDF (scrypt / Argon2id) + AES-256-GCM + đóng gói payload
    permutation   : hoán vị giả ngẫu nhiên theo khóa (mạng Feistel dùng AES làm hàm vòng)
    lsb           : thao tác bit mức thấp (LSB replacement / LSB matching)
    embed/extract : giấu / trích xuất tin trong ảnh
    steganalysis  : chi-square (Westfeld-Pfitzmann), RS analysis, mặt phẳng LSB
    metrics       : PSNR, SSIM, dung lượng
"""

__version__ = "1.0.0"

from .errors import CapacityError, DecryptionError, ImageError, StegoError  # noqa: F401
from .embed import capacity_bytes, embed  # noqa: F401
from .extract import extract  # noqa: F401
