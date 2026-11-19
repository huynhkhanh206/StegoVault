### Nhúng thật so với nhúng mô phỏng

24 mảnh 256×256, nhúng thật (AES-256-GCM, KDF mặc định) và nhúng mô phỏng trên cùng từng mảnh. Mỗi ô có dạng thật / mô phỏng.

| Phương pháp | Tỉ lệ nhúng | RS ước lượng (trung bình) | |Δ RS| mỗi mảnh (trung bình) | Chi-square gắn cờ (/24) | Kết luận "nghi cao" (/24) |
|---|---|---|---|---|---|
| LSB tuần tự | 0.1 | 0.103 / 0.098 | 0.008 | 4 / 4 | 22 / 22 |
| LSB tuần tự | 0.3 | 0.300 / 0.301 | 0.011 | 4 / 4 | 24 / 24 |
| LSB tuần tự | 0.5 | 0.491 / 0.491 | 0.013 | 7 / 6 | 24 / 24 |
| LSB rải theo khóa | 0.1 | 0.111 / 0.112 | 0.008 | 4 / 4 | 10 / 10 |
| LSB rải theo khóa | 0.3 | 0.315 / 0.317 | 0.013 | 5 / 6 | 15 / 15 |
| LSB rải theo khóa | 0.5 | 0.515 / 0.515 | 0.023 | 9 / 10 | 22 / 23 |
| LSB matching (±1) | 0.1 | 0.009 / 0.012 | 0.010 | 4 / 4 | 0 / 0 |
| LSB matching (±1) | 0.3 | 0.015 / 0.015 | 0.020 | 4 / 4 | 1 / 3 |
| LSB matching (±1) | 0.5 | 0.016 / 0.019 | 0.013 | 5 / 4 | 3 / 3 |

Chênh lệch lớn nhất giữa hai cách: 0.004 ở trung bình RS, 2 mảnh ở số lần gắn cờ. Chênh lệch từng mảnh (cột |Δ RS|) khác 0 vì mỗi lần nhúng dùng bit ngẫu nhiên khác nhau; điều cần xem là trung bình và số lần gắn cờ có lệch hệ thống hay không.
