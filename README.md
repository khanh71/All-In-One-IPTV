# 📺 IPTV Auto-Updater

Tự động lấy, lọc và sắp xếp danh sách kênh IPTV Việt Nam, cập nhật mỗi ngày lúc **1:00 sáng** (giờ Việt Nam).

## 🔗 Link playlist

```
https://raw.githubusercontent.com/khanh71/All-In-One-IPTV/main/http-iptv.m3u
```

## 📋 Nguồn dữ liệu (theo thứ tự ưu tiên)

1. `https://1.org.vn/vmttv`

> Kênh từ nguồn có độ ưu tiên cao hơn sẽ được dùng khi cùng tên kênh xuất hiện ở nhiều nguồn.

## 📺 Thứ tự kênh

```
VTV1 → VTV2 → ... → VTV9
HTV1 → HTV2 → ... → HTVC
Địa phương: Bắc → Trung → Tây Nguyên → Nam
```

## 🚀 Cài đặt

### 1. Fork / clone repo này

```bash
git clone https://github.com/khanh71/All-In-One-IPTV.git
cd All-In-One-IPTV
```

### 2. Cấp quyền cho Actions

Vào **Settings → Actions → General → Workflow permissions** → chọn **Read and write permissions**.

### 3. Chạy thủ công lần đầu

Vào tab **Actions** → chọn workflow **Update IPTV Playlist** → nhấn **Run workflow**.

### 4. Sau đó tự động chạy mỗi ngày lúc 1:00 sáng

---

## 🛠 Chạy thủ công trên máy

```bash
pip install requests
python scripts/update_iptv.py
```

File `http-iptv.m3u` sẽ được tạo trong thư mục hiện tại.
