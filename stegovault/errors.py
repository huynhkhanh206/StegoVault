"""Các lỗi riêng của StegoVault (thông báo bằng tiếng Việt để hiển thị thẳng cho người dùng)."""


class StegoError(Exception):
    """Lỗi chung của StegoVault."""


class CapacityError(StegoError):
    """Tin cần giấu lớn hơn dung lượng của ảnh."""


class DecryptionError(StegoError):
    """Sai mật khẩu, ảnh không chứa dữ liệu, hoặc dữ liệu đã bị sửa đổi."""


class ImageError(StegoError):
    """Ảnh không hợp lệ hoặc định dạng không được hỗ trợ."""
