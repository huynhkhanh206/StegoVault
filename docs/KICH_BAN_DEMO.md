# Kịch bản demo và câu hỏi thường gặp

Dùng cho video 3 đến 4 phút hoặc buổi bảo vệ. Mọi con số dưới đây đều lấy từ `results/` (do `experiments/run_all.py` sinh ra).

## Chuẩn bị (làm trước khi quay)

```bash
pip install -r requirements.txt
python -m stegovault serve                                   # giao diện web
python -c "import secrets; print(secrets.token_urlsafe(30000))"   # sinh tin ~40.000 ký tự, khó nén, để dán vào ô tin nhắn
```

Mở sẵn: tab giao diện, `results/detection_vs_rate.png`, `results/robustness_ber.png`, `results/ecb_vs_gcm.png`. Dùng ảnh mẫu `camera`.
Tin dài khoảng 31% dung lượng là đủ lớn để bộ dò có cái để bắt. Thí nghiệm của dự án chỉ đo từ tỉ lệ nhúng 5% trở lên; với tin rất ngắn (vài chục byte, chưa tới 0,1%) bộ dò gần như không có dữ liệu để làm việc, nên đừng chọn tin quá ngắn khi minh họa sự tương phản.

## Kịch bản

| Thời gian | Làm gì | Nói gì |
|---|---|---|
| 0:00 | Slide hoặc README | Đề tài trả lời ba câu hỏi: giấu tin thế nào, giấu như vậy có bị lộ không, và tin sống sót qua những gì |
| 0:25 | Tab **Giấu tin**: chọn ảnh `camera`, dán tin, nhập mật khẩu, chọn **LSB tuần tự**, bấm giấu | Tin được mã hóa AES-256-GCM trước rồi mới giấu. Chỉ ra thanh dung lượng (~31%), PSNR khoảng 56 dB, lệch tối đa 1 trên thang 255: mắt thường không thấy gì |
| 1:00 | Bấm **Phân tích ảnh này** | Kết luận "nghi cao". Kéo thanh trượt: nửa trên của mặt phẳng LSB là nhiễu đều. Chỉ vào đường cong chi-square: p-value cao rồi tụt đúng chỗ tin kết thúc (bậc thang Westfeld) |
| 1:35 | Quay lại tab Giấu tin, **cùng tin, cùng ảnh**, chọn **LSB matching**, giấu, phân tích | Lần này "chưa thấy dấu hiệu". Nhấn mạnh: không phải bộ dò hỏng, mà ±1 không tạo ra sự cân bằng cặp giá trị mà chi-square dựa vào. Nói luôn rằng đây là một ảnh minh họa, số liệu thống kê ở bước sau |
| 2:05 | Tab **Trích xuất**: nhập sai mật khẩu, rồi đúng | Sai thì bị từ chối (thẻ GCM không khớp), không bao giờ ra rác. Đúng thì ra nguyên văn |
| 2:25 | `robustness_ber.png` | JPEG chất lượng 100 đã đổi 34% bit LSB. Chỉ sửa **một** bit cũng làm giải mã thất bại. Vì vậy phải gửi nguyên file PNG |
| 2:45 | `detection_vs_rate.png` | Đọc biểu đồ: cột 0% là tỉ lệ dương tính giả. RS mạnh nhất (bắt 94% nhúng tuần tự ở 10%). Matching bị "nghi cao" chỉ 6–18%. Nói thẳng điểm yếu: chi-square báo nhầm 17% ảnh sạch, toàn bộ đến từ một ảnh (`chelsea`) |
| 3:20 | `ecb_vs_gcm.png` | Vì sao chọn GCM: ECB để lộ hình dạng; CTR không xác thực cho phép đổi "100.000" thành "900.000" mà không ai biết |
| 3:40 | Kết | Giới hạn: LSB không chống nén lại ảnh, các bộ dò là kỹ thuật cổ điển, mẫu thí nghiệm nhỏ (72 mảnh từ 6 ảnh) |

## Câu hỏi có thể gặp

**Vì sao mã hóa trước khi giấu, sao không chỉ giấu?**
Giấu đơn thuần là "bảo mật bằng che giấu": lộ cơ chế là lộ tin. Mã hóa đặt độ an toàn của *nội dung* vào khóa (nguyên tắc Kerckhoffs). Thêm nữa, bản mã trông như bit ngẫu nhiên nên khó phân biệt hơn văn bản thô khi nhúng.

**Kẻ tấn công biết thuật toán thì sao?**
Vẫn không đọc được nội dung nếu không có mật khẩu. Với `keyed` và `matching` họ cũng không biết bit nằm ở đâu, vì vị trí do hoán vị theo khóa quyết định. Họ chỉ có thể dùng thống kê để *nghi ngờ* có tin giấu, đó chính là phần steganalysis.

**Vì sao AES-GCM mà không phải CBC hay CTR?**
GCM vừa mã hóa vừa xác thực. CTR và CBC thuần không phát hiện được sửa đổi (demo CTR đổi số tiền). Trong dự án, sửa đúng 1 bit bản mã đều bị từ chối, có test cho từng vùng (nonce, bản mã, thẻ, salt, độ dài).

**Nonce có bị dùng lại không?**
Không. Mỗi lần giấu lấy 16 byte salt và 12 byte nonce từ `os.urandom`. Salt mới cho ra khóa mới, nên cặp (khóa, nonce) thực tế không thể lặp. Có test kiểm tra 50 lần liên tiếp đều khác nhau.

**Salt có phải bí mật không? Nó dùng để làm gì?**
Không bí mật, nằm ngay trong ảnh. Nó khiến mỗi lần giấu dùng một khóa khác nhau và chặn việc tính trước bảng dò mật khẩu.

**Vì sao LSB matching khó bị dò hơn LSB ghi đè?**
Ghi đè LSB hoán đổi 2k và 2k+1 với xác suất 1/2, nên tần suất của hai giá trị tiến dần về bằng nhau; chi-square đo đúng điều này. Matching thì cộng hoặc trừ 1 ngẫu nhiên: giá trị 2k có thể sang 2k+1 hoặc 2k−1, lượng "tràn" sang các cặp lân cận nên các cặp không bị cân bằng theo cách đó. Kết quả đo: chi-square toàn ảnh trên matching luôn bằng đúng tỉ lệ dương tính giả (17%).

**Matching có vô hình không?**
Không. RS vẫn bắt được 11–18% ảnh (so với 4% dương tính giả), và các bộ dò hiện đại (đặc trưng SRM, mạng nơ-ron) được cho là bắt được; dự án không cài đặt chúng nên không khẳng định gì về chúng.

**Vì sao ảnh sạch cũng bị chi-square báo dương tính?**
Bài kiểm tra giả định ảnh gốc có sự mất cân bằng giữa 2k và 2k+1. Ảnh có bit thấp vốn đã nhiễu và cân bằng (ví dụ `chelsea`: 12/12 mảnh bị báo) sẽ cho p-value cao dù chưa giấu gì. Dự án báo cáo con số này thay vì chỉnh ngưỡng cho đẹp. Nguyên nhân gốc của ảnh đó chỉ là giả thuyết, chưa kiểm chứng.

**Có gửi qua Zalo, Facebook, Messenger được không?**
Không. Các nền tảng này nén lại ảnh; đo được JPEG chất lượng 100 đã đổi 34% bit. Phải gửi dưới dạng file (tài liệu), không phải ảnh.

**Phần nào tự cài đặt, phần nào dùng thư viện?**
Tự cài đặt: LSB replacement và matching, hoán vị Feistel theo khóa, định dạng dữ liệu nhúng, chi-square, RS, PSNR/SSIM, máy chủ web. Dùng thư viện: AES-GCM, scrypt, Argon2id (`cryptography`), nén (`zlib`), đọc/ghi ảnh (`Pillow`). Không tự viết thuật toán mật mã.

**160 mẫu đầu luôn mang dữ liệu: đó có phải điểm yếu không?**
Có một điểm yếu lý thuyết: vị trí này cố định và công khai, và (ở các cách ghi đè) luôn mang bit ngẫu nhiên, nên ai biết thuật toán đều biết chỗ nào chắc chắn có dữ liệu. Với 160 mẫu thì tác động thống kê là không đáng kể (dự án không đo riêng điều này), nhưng đây là thứ cần nói thật nếu bị hỏi. Nó không làm lộ nội dung vì salt vốn không bí mật và độ dài đã được che.

**Vì sao chỉ dùng 1 bit LSB mỗi mẫu?**
Dung lượng đổi lấy khả năng bị dò. Dùng 2 bit thấp tăng gấp đôi dung lượng nhưng thay đổi ảnh nhiều hơn và thường dễ bị lộ hơn; đây là hiểu biết chung chứ dự án không đo, nên đừng trình bày như một kết quả của đề tài.

**Hướng phát triển tiếp theo?**
(1) Cài đặt bộ dò hiện đại (SPAM hoặc SRM kèm bộ phân loại) để kiểm tra lại kết luận về matching. (2) Nhúng thích nghi vào vùng nhiều chi tiết. (3) Mã sửa lỗi để chịu được một ít nhiễu. (4) Nhúng trong miền DCT của JPEG để sống sót qua nén. (5) Đo trực tiếp nhúng thật so với nhúng mô phỏng.

## Danh sách kiểm tra trước khi nộp

- [ ] Điền họ tên, MSSV, lớp ở đầu `README.md`.
- [ ] `python -m pytest` báo 148 test qua.
- [ ] `python -m stegovault demo` chạy được; xóa thư mục `demo_output/` trước khi nén.
- [ ] Nếu nộp video: quay theo bảng kịch bản, giữ dưới 4 phút.
- [ ] Nếu nộp link: đẩy toàn bộ thư mục lên GitHub, nhớ có `results/` và `docs/img/` để README hiện đủ hình.
