### Độ bền của ảnh đã giấu tin

Tin 1,420 byte giấu vào ảnh astronaut 512×512. OK = giải mã đúng; HỎNG = AES-GCM từ chối. BER = tỉ lệ bit LSB của toàn ảnh bị đổi so với ảnh đã giấu tin (trung bình 3 phương pháp).

| Biến đổi | LSB tuần tự | LSB rải theo khóa | LSB matching (±1) | BER |
|---|---|---|---|---|
| Lưu lại PNG / BMP / TIFF (không mất dữ liệu) | OK | OK | OK | 0 |
| JPEG chất lượng 100 | HỎNG | HỎNG | HỎNG | 34.01% |
| JPEG chất lượng 95 | HỎNG | HỎNG | HỎNG | 45.12% |
| JPEG chất lượng 75 | HỎNG | HỎNG | HỎNG | 45.33% |
| Thu nhỏ 99% rồi phóng lại | HỎNG | HỎNG | HỎNG | 36.44% |
| Thêm nhiễu Gauss σ = 1 | HỎNG | HỎNG | HỎNG | 46.97% |
| Lật ngang ảnh | HỎNG | HỎNG | HỎNG | 49.92% |
| Cắt bỏ 1 hàng và 1 cột mép | HỎNG | HỎNG | HỎNG | — |
| Sửa đúng 1 bit LSB của bản mã | HỎNG | HỎNG | HỎNG | 0.00013% |
