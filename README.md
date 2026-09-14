# XSKTVN 🎰

Tra cứu kết quả xổ số Việt Nam 3 miền — tự động cập nhật mỗi ngày.

## 🌐 Demo
👉 https://thanhthovn.github.io/xsktvn/

## ⚙️ Cách hoạt động
- GitHub Actions chạy `scraper.py` mỗi ngày lúc 05:00 (giờ VN).
- Cào KQXS của **ngày hôm qua** (vì lúc 5h sáng KQ hôm qua đã có đầy đủ).
- Dữ liệu lưu thành `data/YYYY/YYYY-MM-DD.json`.
- File `data/index.json` chứa danh sách các ngày có dữ liệu.
- Trang web đọc file JSON tĩnh → hiển thị lịch trạng thái + kết quả.

## 📁 Cấu trúc
