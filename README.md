# 📺 IPTV Auto-Updater (Production Ready)

Hệ thống tự động thu thập, tối ưu hóa chất lượng, lọc nhiễu và sắp xếp danh sách kênh IPTV Việt Nam chất lượng cao.
Playlist được cập nhật tự động mỗi ngày vào lúc **01:00 AM (ICT / Giờ Việt Nam)** thông qua GitHub Actions.

---

## 🔗 Link Playlist Sử Dụng

Bạn có thể copy liên kết này để add trực tiếp vào các ứng dụng xem IPTV (như Tivimate, OTT Navigator, Perfect Player, VLC...):

```
https://raw.githubusercontent.com/khanh71/All-In-One-IPTV/main/http-iptv.m3u
```

---

## 🛠 Cơ Chế Hoạt Động Của Hệ Thống

Mã nguồn mới đã được tối ưu hóa sâu **(O(N) Complexity)** với các tính năng vượt trội:

- **Bộ lọc thông minh (Deduplication & Quality Max Selection):** Nếu một kênh xuất hiện ở nhiều nguồn hoặc có nhiều luồng dữ liệu, hệ thống tự động chấm điểm kỹ thuật (Tier phân giải từ 8K/4K/FHD/HD... kết hợp với Bitrate) để chỉ giữ lại duy nhất luồng có chất lượng tốt nhất.

- **Kiểm tra EPG Động (Dynamic Failover):** Tự động ping kiểm tra danh sách máy chủ EPG (Lịch phát sóng). Nếu server chính lỗi, hệ thống tự động fallback sang server phụ để đảm bảo link EPG không bao giờ bị chết.

- **Phân nhóm & Sắp xếp Khoa học:**
  - **VTV:** Sắp xếp cố định từ VTV1 đến VTV10 và các kênh khu vực.
  - **HTV / HTVC:** Sắp xếp chuẩn theo hệ thống kênh HTV và HTVC.
  - **Địa phương:** Gom gọn vào 1 nhóm duy nhất, tự động sắp xếp thứ tự địa lý từ Bắc vào Nam.
  - **Quốc Phòng:** Tách riêng ANTV và QPVN thành một nhóm chuyên biệt, không bị lẫn vào nhóm địa phương.

---

## 📋 Nguồn Dữ Liệu Thu Thập

Hệ thống tự động gộp và liên tục quét qua các nguồn uy tín *(ưu tiên giữ nguồn gốc nếu chất lượng bằng nhau, thay thế ngay nếu nguồn sau có độ phân giải/bitrate cao hơn)*:

| Vai trò | Nguồn |
|---|---|
| Nguồn ưu tiên chính | https://1.org.vn/vmttv |
| Nguồn fallback/bổ sung | https://vmttv.duckdns.org/ |
| EPG (Lịch phát sóng) | `vnepg.site/epg.xml.gz` ↔ `vnepg.site/epg.xml` (luân phiên) |

---

## 🚀 Hướng Dẫn Triển Khai

### Lựa chọn 1: Chạy Tự Động Bằng GitHub Actions *(Khuyến khích)*

#### Bước 1: Fork Kho Lưu Trữ

Nhấn nút **Fork** ở góc trên bên phải của trang GitHub này để sao chép dự án về tài khoản của bạn.

#### Bước 2: Cấp Quyền Ghi Cho GitHub Actions

Mặc định GitHub Actions sẽ không có quyền commit file `http-iptv.m3u` mới lên repo của bạn. Hãy cấp quyền bằng cách:

1. Vào mục **Settings** trên repo của bạn.
2. Tìm đến **Actions → General** ở thanh menu bên trái.
3. Cuộn xuống mục **Workflow permissions**.
4. Chọn **Read and write permissions**.
5. Nhấn **Save**.

#### Bước 3: Kích Hoạt Và Chạy Thử Lần Đầu

1. Chuyển sang tab **Actions** trên thanh công cụ của repo.
2. Chọn workflow **Update IPTV Playlist** ở danh sách bên trái.
3. Nhấn **Run workflow → Chọn nhánh `main` → Bấm nút Run workflow** màu xanh.

Chờ khoảng 1–2 phút, hệ thống sẽ tự động tạo ra file `http-iptv.m3u` trong repo của bạn.
Từ lúc này, cứ **1:00 AM hàng ngày** script sẽ tự chạy ngầm.

---

### Lựa chọn 2: Chạy Thủ Công Trên Máy Tính (Local)

> **Yêu cầu:** Python 3.10 trở lên.

#### Bước 1: Clone mã nguồn về máy

```bash
git clone https://github.com/YOUR_USERNAME/All-In-One-IPTV.git
cd All-In-One-IPTV
```

*(Thay `YOUR_USERNAME` bằng tên GitHub của bạn)*

#### Bước 2: Cài đặt thư viện phụ thuộc

```bash
pip install requests
```

#### Bước 3: Khởi chạy mã nguồn

Do file `update_iptv.py` nằm ở thư mục gốc (theo cấu trúc của `update_iptv.yml`), hãy chạy lệnh trực tiếp từ thư mục gốc:

```bash
python update_iptv.py
```

Sau khi chạy xong, file `http-iptv.m3u` sẽ xuất hiện ngay tại thư mục hiện tại.

---

## ⚖️ Tuyên Bố Miễn Trừ Trách Nhiệm

Dự án này là một công cụ mã nguồn mở được viết ra nhằm mục đích **học tập, nghiên cứu** kỹ thuật xử lý luồng dữ liệu (data parsing/cleansing) và tự động hóa với Python.

Chúng tôi **không sở hữu, không lưu trữ và không trực tiếp phát sóng** bất kỳ luồng truyền hình nào. Tất cả các liên kết stream (`.m3u8`) đều được thu thập tự động từ các nguồn công khai miễn phí trên Internet.

Bất kỳ vấn đề nào liên quan đến bản quyền luồng phát, vui lòng liên hệ trực tiếp với các nhà cung cấp nguồn gốc được liệt kê trong mục dữ liệu.
