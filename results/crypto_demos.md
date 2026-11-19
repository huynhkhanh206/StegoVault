### Demo mật mã nền tảng

**1. ECB lộ hình dạng, GCM thì không**

- Số khối 16 byte khác nhau: ảnh gốc 180/12,288, ECB 180/12,288, GCM 12,288/12,288.
- ECB giữ nguyên số khối khác nhau của ảnh gốc (chỉ đổi tên khối), GCM làm mọi khối khác nhau.

**2. Hiệu ứng thác lũ của SHA-256**

- Đổi 1 bit trong thông điệp 64 byte, 2,000 lần thử: số bit băm thay đổi trung bình 127.8/256 (49.9%), độ lệch chuẩn 8.1, nhỏ nhất 100, lớn nhất 155.
- Ví dụ: SHA-256("StegoVault") = `4ba3ac44710702efa09e89e191f753c2…` và SHA-256("StegoVaulT") = `59e76c10e8c5ac43a99e98d33a072a76…` (chỉ khác một ký tự).

**3. Bản mã không xác thực có thể bị sửa (CTR) so với GCM**

- Bản rõ gốc: `Chuyen khoan: 100.000 VND cho Lan`
- AES-CTR sau khi kẻ tấn công lật vài bit: `Chuyen khoan: 900.000 VND cho Lan`. Người nhận không phát hiện được gì.
- AES-GCM với đúng thao tác đó: bị từ chối (InvalidTag).
