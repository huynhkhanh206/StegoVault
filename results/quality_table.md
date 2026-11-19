### Chất lượng ảnh theo tỉ lệ nhúng

Trung bình trên 6 ảnh mẫu 8-bit (PSNR / SSIM). Cột lý thuyết: PSNR = 10·log10(255² / (r/2)).

| Tỉ lệ nhúng r | PSNR lý thuyết (dB) | LSB tuần tự | LSB rải theo khóa | LSB matching (±1) |
|---|---|---|---|---|
| 0.01 | 71.14 | 71.07 dB / 0.99997 | 70.99 dB / 0.99995 | 71.06 dB / 0.99995 |
| 0.05 | 64.15 | 64.14 dB / 0.99974 | 64.13 dB / 0.99976 | 64.13 dB / 0.99976 |
| 0.10 | 61.14 | 61.14 dB / 0.99946 | 61.14 dB / 0.99952 | 61.13 dB / 0.99952 |
| 0.25 | 57.16 | 57.16 dB / 0.99865 | 57.15 dB / 0.99879 | 57.16 dB / 0.99879 |
| 0.50 | 54.15 | 54.15 dB / 0.99747 | 54.15 dB / 0.99753 | 54.15 dB / 0.99752 |
| 1.00 | 51.14 | 51.14 dB / 0.99488 | 51.14 dB / 0.99488 | 51.14 dB / 0.99482 |

### Dung lượng giấu tin tối đa

| Ảnh | Kích thước | Số mẫu LSB | Dung lượng tối đa (byte) | ≈ |
|---|---|---|---|---|
| astronaut | 512×512 | 786,432 | 98,256 | 96.0 KiB |
| camera | 512×512 | 786,432 | 98,256 | 96.0 KiB |
| coffee | 600×400 | 720,000 | 89,952 | 87.8 KiB |
| chelsea | 451×300 | 405,900 | 50,689 | 49.5 KiB |
| rocket | 640×427 | 819,840 | 102,432 | 100.0 KiB |
| retina | 640×640 | 1,228,800 | 153,552 | 150.0 KiB |

### Chi phí hàm làm chậm mật khẩu (KDF)

| KDF | Bộ nhớ | Thời gian một lần suy dẫn (trung vị 3 lần) |
|---|---|---|
| scrypt | 32 MiB | 51 ms |
| argon2id | 64 MiB | 89 ms |

### Độ chính xác của ước lượng RS

Tỉ lệ nhúng do RS ước lượng (trung bình ± độ lệch chuẩn giữa 6 ảnh mẫu). Đúng tuyệt đối khi bằng cột đầu tiên; với matching, RS gần như không thấy gì nên ước lượng xấp xỉ 0.

| Tỉ lệ nhúng thật | LSB tuần tự | LSB rải theo khóa | LSB matching (±1) |
|---|---|---|---|
| 0.10 | 0.12 ± 0.03 | 0.12 ± 0.01 | 0.02 ± 0.02 |
| 0.30 | 0.31 ± 0.08 | 0.32 ± 0.01 | 0.03 ± 0.05 |
| 0.50 | 0.46 ± 0.10 | 0.52 ± 0.01 | 0.05 ± 0.08 |
| 0.80 | 0.73 ± 0.08 | 0.81 ± 0.01 | 0.05 ± 0.11 |
