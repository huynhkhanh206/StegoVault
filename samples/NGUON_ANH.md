# Nguồn gốc và giấy phép của ảnh mẫu

Các ảnh trong thư mục này lấy từ bộ dữ liệu mẫu của thư viện scikit-image (`skimage.data`, bản 0.26.0), chỉ để
chạy demo và thí nghiệm. Thông tin giấy phép dưới đây trích từ chính tài liệu của thư viện đó.

| File | Nội dung | Tác giả / nguồn | Giấy phép |
|---|---|---|---|
| `astronaut.png` | Chân dung phi hành gia Eileen Collins | Cơ sở dữ liệu NASA Great Images | Không có hạn chế bản quyền đã biết, phát hành công khai |
| `camera.png` | Người chụp ảnh ("cameraman") | Lav Varshney | CC0 |
| `coffee.png` | Cốc cà phê | Rachel Michetti, với sự cho phép của Pikolo Espresso Bar | CC0 |
| `chelsea.png` | Con mèo Chelsea | Stefan van der Walt | CC0 |
| `rocket.png` | Phóng tên lửa Falcon 9 mang vệ tinh DSCOVR | SpaceX | Phát hành công khai (public domain) |
| `retina.png` | Ảnh đáy mắt người, **cắt vùng giữa 640×640** từ ảnh gốc 1411×1411 | Mikael Häggström, Wikimedia Commons | CC0 |

Ảnh `camera` gốc là ảnh xám nên được nhân thành 3 kênh giống nhau để dùng chung quy trình RGB. Các ảnh được lưu lại
đúng như thư viện cung cấp; riêng `retina` chỉ bị cắt, không đổi kích thước (resample sẽ làm đổi thống kê bit thấp nhất
mà đề tài đang đo). Mình không biết các ảnh này đã qua xử lý gì trước khi vào thư viện.

Bạn có thể thay bằng ảnh của mình: mọi lệnh đều nhận PNG, BMP và JPG (ảnh đầu ra luôn là định dạng không mất dữ liệu).
