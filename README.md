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

Mã nguồn được tối ưu hóa sâu **(O(N) Complexity)** với các tính năng vượt trội:

- **Bộ lọc thông minh (Deduplication & Quality Max Selection):** Nếu một kênh xuất hiện ở nhiều nguồn hoặc có nhiều luồng dữ liệu, hệ thống tự động chấm điểm kỹ thuật (Tier phân giải từ 8K/4K/FHD/HD/SD kết hợp với Bitrate) để chỉ giữ lại duy nhất luồng có chất lượng tốt nhất, dedup đồng thời theo cả tên kênh lẫn URL xuyên suốt các nguồn.

- **Chuẩn hóa tvg-id theo chuẩn vnepg:** Toàn bộ tvg-id thu thập được sẽ được chuẩn hóa (viết liền, không dấu gạch ngang, tra qua bảng alias) để khớp chính xác với lịch phát sóng, đồng thời gắn cố định URL EPG (`url-tvg` / `x-tvg-url`) ngay trong header của file playlist.

- **Lọc nhiễu (Noise Filtering):** Tự động loại bỏ các kênh rác, kênh trùng lặp không rõ nguồn gốc hoặc không xác định được nhóm (dựa theo danh sách từ khóa và tiền tố tvg-id/tên kênh đã biết là nhiễu).

- **Phân nhóm & Sắp xếp Khoa học:**
  - **VTV:** Sắp xếp cố định từ VTV1 đến VTV10 và các kênh khu vực (Tây Nam Bộ, Tây Nguyên).
  - **HTV / HTVC:** Sắp xếp chuẩn theo hệ thống kênh HTV và HTVC.
  - **Địa phương:** Gom gọn vào 1 nhóm duy nhất, tự động sắp xếp thứ tự địa lý từ Bắc vào Nam theo danh sách tỉnh/thành đầy đủ.
  - **Quốc Phòng:** Tách riêng ANTV và QPVN thành một nhóm chuyên biệt, không bị lẫn vào nhóm địa phương.

---

## 📋 Nguồn Dữ Liệu Thu Thập

Hệ thống thu thập dữ liệu từ danh sách nguồn (`SOURCES`) được khai báo trong `update_iptv.py`. Có thể bật/tắt từng nguồn bằng cách thêm hoặc bỏ dấu `#` comment ở đầu dòng:

| Vai trò | Nguồn |
|---|---|
| Nguồn đang hoạt động | Dropbox mirror playlist (`coban66.m3u`) |
| Nguồn dự phòng (đã comment sẵn, có thể bật lại) | `TVPub` (GitHub), `1.org.vn/vmttv`, `vmttv.duckdns.org`, `iptv-org/iptv (vn.m3u)` |
| EPG (Lịch phát sóng) | `epg.io.vn/epg.xml` — gắn cố định vào header playlist |

> Có thể tự thêm nguồn mới bằng cách bổ sung URL playlist `.m3u`/`.m3u8` vào danh sách `SOURCES` trong file `update_iptv.py`.

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
git clone https://github.com/khanh71/All-In-One-IPTV.git
cd All-In-One-IPTV
```

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