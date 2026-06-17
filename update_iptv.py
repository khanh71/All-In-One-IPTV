#!/usr/bin/env python3
"""
IPTV Auto-updater (Production Ready - Optimized)
- Nguồn: 1.org.vn/vmttv (ưu tiên) + fallback GitHub
- Chỉ lấy kênh TV: VTV, HTV, địa phương
- Lịch phát sóng (EPG): vnepg.site/epg.xml.gz
- Địa phương gom 1 nhóm, sắp xếp Bắc → Nam
- Output: http-iptv.m3u
"""

import re
import sys
from dataclasses import dataclass
from typing import Optional, Final

# FIX #7: Bỏ `defaultdict` và `Counter` — chỉ import những gì thật sự dùng.
# Counter vẫn dùng trong main() để đếm group nên giữ lại.
from collections import Counter

import requests

# ──────────────────────────────────────────────────────────────────────
# CẤU HÌNH & HẰNG SỐ
# ──────────────────────────────────────────────────────────────────────
SOURCES: Final[list[str]] = [
    "https://1.org.vn/vmttv",
    "https://vmttv.duckdns.org/",
    "https://raw.githubusercontent.com/vuminhthanh12/vuminhthanh12/refs/heads/main/vmttv",
    "https://raw.githubusercontent.com/Bacbenny/Truyenhinhiptv/refs/heads/main/dekiki.m3u",
    "https://raw.githubusercontent.com/Bacbenny/Verceliptv/refs/heads/main/VTV.m3u",
    "https://raw.githubusercontent.com/hoiquanclick/hoiquan/refs/heads/main/vip.m3u",
]

EPG_URLS: Final[list[str]] = [
    "https://vnepg.site/epg.xml.gz",
    "https://vnepg.site/epg.xml",
]

OUTPUT_FILE: Final[str] = "http-iptv.m3u"
HTTP_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
GLOBAL_TIMEOUT: Final[int] = 20

# ──────────────────────────────────────────────────────────────────────
# BẢNG TÊN ĐẸP (tvg-id → tên hiển thị)
# FIX #5: Gộp alias trùng (vtv6/vtv6hd → VTV6, vtv10/vtv10hd → VTV10)
#         thành một entry mỗi cái. Alias phụ được xử lý bởi regex fallback.
# ──────────────────────────────────────────────────────────────────────
DISPLAY_NAME: Final[dict[str, str]] = {
    # VTV
    "vtv1hd": "VTV1",
    "vtv2hd": "VTV2",
    "vtv3hd": "VTV3",
    "vtv4hd": "VTV4",
    "vtv5hd": "VTV5",
    "vtv5hdtnb": "VTV5 Tây Nam Bộ",
    "vtv5hdtn": "VTV5 Tây Nguyên",
    "vtv6hd": "VTV6",
    "vtv6": "VTV6",
    "vtv7hd": "VTV7",
    "vtv8hd": "VTV8",
    "vtv9hd": "VTV9",
    "vtv10hd": "VTV10",
    "vtv10": "VTV10",
    "vietnamtoday": "Vietnam Today",
    # HTV / HTVC
    "htv1": "HTV1",
    "htv2hd": "HTV2",
    "htv3": "HTV3",
    "htv4": "HTV4",
    "htv4hd": "HTV4",
    "htv5": "HTV5",
    "htv7hd": "HTV7",
    "htv9hd": "HTV9",
    "htvthethaohd": "HTVC Thể Thao",
    "htvccanhachd": "HTVC Ca Nhạc",
    "htvcdulichhd": "HTVC Du Lịch",
    "htvcgiadinhhd": "HTVC Gia Đình",
    "htvcphimhd": "HTVC Phim",
    "htvcphunuhd": "HTVC Phụ Nữ",
    "htvcthuanviet": "HTVC Thuần Việt",
    "htvcplushd": "HTVC+",
    # Miền Bắc
    "hagiang": "Hà Giang",
    "laichau": "Lai Châu",
    "ltv": "Lai Châu",
    "dienbien": "Điện Biên",
    "laocai": "Lào Cai",
    "yenbai": "Yên Bái",
    "sonla": "Sơn La",
    "hoabinh": "Hòa Bình",
    "phutho": "Phú Thọ",
    "vinhphuc": "Vĩnh Phúc",
    "tuyenquang": "Tuyên Quang",
    "backan": "Bắc Kạn",
    "thainguyen": "Thái Nguyên",
    "caobang": "Cao Bằng",
    "langson": "Lạng Sơn",
    "quangninh": "Quảng Ninh",
    "quangninh1": "Quảng Ninh 1",
    "quangninh3": "Quảng Ninh 3",
    "bacgiang": "Bắc Giang",
    "bacninh": "Bắc Ninh",
    "hanoi1": "Hà Nội 1",
    "hanoi2": "Hà Nội 2",
    "vovgthn": "VOV Giao Thông HN",
    "haiphong": "Hải Phòng",
    "haiphong3": "Hải Phòng 3",
    "haiphongplus": "Hải Phòng +",
    "haiduong": "Hải Dương",
    "hungyen": "Hưng Yên",
    "thaibinh": "Thái Bình",
    "namdinh": "Nam Định",
    "hanam": "Hà Nam",
    "ninhbinh": "Ninh Bình",
    # Miền Trung
    "thanhhoa": "Thanh Hóa",
    "nghean": "Nghệ An",
    "hatinh": "Hà Tĩnh",
    "quangbinh": "Quảng Bình",
    "quangtri": "Quảng Trị",
    "hue": "Huế",
    "danang1": "Đà Nẵng 1",
    "danang2": "Đà Nẵng 2",
    "quangnam": "Quảng Nam",
    # FIX #6: Phân biệt rõ quangngai (gốc) vs quangngai1 (kênh 1)
    "quangngai": "Quảng Ngãi",
    "quangngai1": "Quảng Ngãi 1",
    "quangngai2": "Quảng Ngãi 2",
    "binhdinh": "Bình Định",
    "phuyen": "Phú Yên",
    "khanhhoa": "Khánh Hòa",
    "khanhhoa1": "Khánh Hòa 1",
    "ninhthuan": "Ninh Thuận",
    "binhthuan": "Bình Thuận",
    # Tây Nguyên
    "kontum": "Kon Tum",
    "gialai": "Gia Lai",
    "daklak": "Đắk Lắk",
    "daknong": "Đắk Nông",
    "lamdong": "Lâm Đồng",
    "lamdong1": "Lâm Đồng 1",
    "lamdong2": "Lâm Đồng 2",
    "lamdong3": "Lâm Đồng 3",
    # Miền Nam
    "binhphuoc": "Bình Phước",
    "tayninh1": "Tây Ninh",
    "tayninhtv": "Tây Ninh",
    "binhduong": "Bình Dương",
    "dongnai1": "Đồng Nai 1",
    "dongnai2": "Đồng Nai 2",
    "dongnai3": "Đồng Nai 3",
    "baria": "Bà Rịa - Vũng Tàu",
    "longan": "Long An",
    "tiengiang": "Tiền Giang",
    "bentre": "Bến Tre",
    "dongthap": "Đồng Tháp 1",
    "dongthap1": "Đồng Tháp 1",
    "dongthap2": "Đồng Tháp 2",
    "vinhlong1hd": "Vĩnh Long 1",
    "thvl1hd": "Vĩnh Long 1",
    "thvl1": "Vĩnh Long 1",
    "vinhlong2hd": "Vĩnh Long 2",
    "thvl2hd": "Vĩnh Long 2",
    "thvl2": "Vĩnh Long 2",
    "vinhlong3hd": "Vĩnh Long 3",
    "thvl3hd": "Vĩnh Long 3",
    "thvl3": "Vĩnh Long 3",
    "vinhlong4hd": "Vĩnh Long 4",
    "thvl4hd": "Vĩnh Long 4",
    "thvl4": "Vĩnh Long 4",
    "vinhlong5hd": "Vĩnh Long 5",
    "thvl5hd": "Vĩnh Long 5",
    "thvl5": "Vĩnh Long 5",
    "travinh": "Trà Vinh",
    "angiang1": "An Giang 1",
    "angiang2": "An Giang 2",
    "angiang3": "An Giang 3",
    "kiengiang": "Kiên Giang",
    "cantho": "Cần Thơ",
    "cantho1": "Cần Thơ 1",
    "cantho2": "Cần Thơ 2",
    "cantho3": "Cần Thơ 3",
    "haugiang": "Hậu Giang",
    "soctrang": "Sóc Trăng",
    "baclieu": "Bạc Liêu",
    "camau": "Cà Mau",
    # Quốc phòng — FIX #1: Tách riêng khỏi TVGID_TO_PROVINCE (không phải tỉnh)
    "antv-hd": "ANTV",
    "antv": "ANTV",
    "qpvn-hd": "QPVN",
    "qpvn": "QPVN",
}

# ──────────────────────────────────────────────────────────────────────
# FIX #8: Gộp GROUP_MAP — chỉ giữ entries không bị xử lý bởi keyword
#         fallback bên dưới để tránh dead code. Keyword-based matching
#         trong parse_m3u đã xử lý "vtv", "htv", "địa phương", etc.
# ──────────────────────────────────────────────────────────────────────
GROUP_MAP: Final[dict[str, str]] = {
    "Quốc Phòng": "Quốc Phòng",
}

# ──────────────────────────────────────────────────────────────────────
# FIX #1: TVGID_TO_PROVINCE chỉ chứa các tỉnh thành thật sự.
#         Xóa antv/qpvn ra khỏi dict này — chúng được xử lý riêng
#         qua GROUP "Quốc Phòng" chứ không phải qua province lookup.
# ──────────────────────────────────────────────────────────────────────
TVGID_TO_PROVINCE: Final[dict[str, str]] = {
    "hagiang": "Hà Giang",
    "tuyenquang": "Tuyên Quang",
    "caobang": "Cao Bằng",
    "langson": "Lạng Sơn",
    "backan": "Bắc Kạn",
    "thainguyen": "Thái Nguyên",
    "quangninh": "Quảng Ninh",
    "quangninh1": "Quảng Ninh",
    "quangninh3": "Quảng Ninh",
    "bacgiang": "Bắc Giang",
    "bacninh": "Bắc Ninh",
    "laocai": "Lào Cai",
    "yenbai": "Yên Bái",
    "phutho": "Phú Thọ",
    "vinhphuc": "Vĩnh Phúc",
    "hanoi1": "Hà Nội",
    "hanoi2": "Hà Nội",
    "vovgthn": "Hà Nội",
    "hoabinh": "Hòa Bình",
    "sonla": "Sơn La",
    "dienbien": "Điện Biên",
    "laichau": "Lai Châu",
    "ltv": "Lai Châu",
    "haiphong": "Hải Phòng",
    "haiphong3": "Hải Phòng",
    "haiphongplus": "Hải Phòng",
    "haiduong": "Hải Dương",
    "hungyen": "Hưng Yên",
    "thaibinh": "Thái Bình",
    "namdinh": "Nam Định",
    "hanam": "Hà Nam",
    "ninhbinh": "Ninh Bình",
    "thanhhoa": "Thanh Hóa",
    "nghean": "Nghệ An",
    "hatinh": "Hà Tĩnh",
    "quangbinh": "Quảng Bình",
    "quangtri": "Quảng Trị",
    "hue": "Thừa Thiên Huế",
    "danang1": "Đà Nẵng",
    "danang2": "Đà Nẵng",
    "quangnam": "Quảng Nam",
    "quangngai": "Quảng Ngãi",
    "quangngai1": "Quảng Ngãi",
    "quangngai2": "Quảng Ngãi",
    "binhdinh": "Bình Định",
    "phuyen": "Phú Yên",
    "khanhhoa": "Khánh Hòa",
    "khanhhoa1": "Khánh Hòa",
    "ninhthuan": "Ninh Thuận",
    "binhthuan": "Bình Thuận",
    "kontum": "Kon Tum",
    "gialai": "Gia Lai",
    "daklak": "Đắk Lắk",
    "daknong": "Đắk Nông",
    "lamdong": "Lâm Đồng",
    "lamdong1": "Lâm Đồng",
    "lamdong2": "Lâm Đồng",
    "lamdong3": "Lâm Đồng",
    "binhphuoc": "Bình Phước",
    "tayninh1": "Tây Ninh",
    "tayninhtv": "Tây Ninh",
    "binhduong": "Bình Dương",
    "dongnai1": "Đồng Nai",
    "dongnai2": "Đồng Nai",
    "dongnai3": "Đồng Nai",
    "baria": "Bà Rịa - Vũng Tàu",
    "longan": "Long An",
    "tiengiang": "Tiền Giang",
    "bentre": "Bến Tre",
    "dongthap": "Đồng Tháp",
    "dongthap1": "Đồng Tháp",
    "dongthap2": "Đồng Tháp",
    "vinhlong1hd": "Vĩnh Long",
    "vinhlong2hd": "Vĩnh Long",
    "vinhlong3hd": "Vĩnh Long",
    "vinhlong4hd": "Vĩnh Long",
    "vinhlong5hd": "Vĩnh Long",
    "thvl1hd": "Vĩnh Long",
    "thvl1": "Vĩnh Long",
    "thvl2hd": "Vĩnh Long",
    "thvl2": "Vĩnh Long",
    "thvl3hd": "Vĩnh Long",
    "thvl3": "Vĩnh Long",
    "thvl4hd": "Vĩnh Long",
    "thvl4": "Vĩnh Long",
    "thvl5hd": "Vĩnh Long",
    "thvl5": "Vĩnh Long",
    "travinh": "Trà Vinh",
    "angiang1": "An Giang",
    "angiang2": "An Giang",
    "angiang3": "An Giang",
    "kiengiang": "Kiên Giang",
    "cantho": "Cần Thơ",
    "cantho1": "Cần Thơ",
    "cantho2": "Cần Thơ",
    "cantho3": "Cần Thơ",
    "haugiang": "Hậu Giang",
    "soctrang": "Sóc Trăng",
    "baclieu": "Bạc Liêu",
    "camau": "Cà Mau",
    # FIX #1: KHÔNG có antv/qpvn ở đây — chúng thuộc group "Quốc Phòng",
    #         không phải tỉnh địa lý. Xem fallback trong parse_m3u.
}

LOCAL_PROVINCE_ORDER: Final[list[str]] = [
    "Hà Giang",
    "Tuyên Quang",
    "Cao Bằng",
    "Lạng Sơn",
    "Bắc Kạn",
    "Thái Nguyên",
    "Quảng Ninh",
    "Bắc Giang",
    "Bắc Ninh",
    "Lào Cai",
    "Yên Bái",
    "Phú Thọ",
    "Vĩnh Phúc",
    "Hà Nội",
    "Hòa Bình",
    "Sơn La",
    "Điện Biên",
    "Lai Châu",
    "Hải Phòng",
    "Hải Dương",
    "Hưng Yên",
    "Thái Bình",
    "Nam Định",
    "Hà Nam",
    "Ninh Bình",
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Quảng Bình",
    "Quảng Trị",
    "Thừa Thiên Huế",
    "Đà Nẵng",
    "Quảng Nam",
    "Quảng Ngãi",
    "Bình Định",
    "Phú Yên",
    "Khánh Hòa",
    "Ninh Thuận",
    "Bình Thuận",
    "Kon Tum",
    "Gia Lai",
    "Đắk Lắk",
    "Đắk Nông",
    "Lâm Đồng",
    "Bình Phước",
    "Tây Ninh",
    "Bình Dương",
    "Đồng Nai",
    "Bà Rịa - Vũng Tàu",
    "Long An",
    "Tiền Giang",
    "Bến Tre",
    "Đồng Tháp",
    "Vĩnh Long",
    "Trà Vinh",
    "An Giang",
    "Kiên Giang",
    "Cần Thơ",
    "Hậu Giang",
    "Sóc Trăng",
    "Bạc Liêu",
    "Cà Mau",
]

_PROVINCE_IDX: Final[dict[str, int]] = {
    p: i for i, p in enumerate(LOCAL_PROVINCE_ORDER)
}

GROUP_LABEL_LOCAL: Final[str] = "Địa phương"
GROUP_LABEL_QDVN: Final[str] = (
    "Quốc Phòng"  # FIX #1: Hằng số rõ ràng cho group ANTV/QPVN
)

VTV_FIXED_ORDER: Final[list[str]] = [
    "VTV1",
    "VTV2",
    "VTV3",
    "VTV4",
    "VTV5",
    "VTV5 Tây Nam Bộ",
    "VTV5 Tây Nguyên",
    "VTV6",
    "VTV7",
    "VTV8",
    "VTV9",
    "VTV10",
]

HTV_FIXED_ORDER: Final[list[str]] = [
    "HTV1",
    "HTV2",
    "HTV3",
    "HTV4",
    "HTV5",
    "HTV7",
    "HTV9",
    "HTVC Thể Thao",
    "HTVC Ca Nhạc",
    "HTVC Du Lịch",
    "HTVC Gia Đình",
    "HTVC Phim",
    "HTVC Phụ Nữ",
    "HTVC Thuần Việt",
    "HTVC+",
]

# ──────────────────────────────────────────────────────────────────────
# REGEX PRE-COMPILED
# FIX #11: Làm sạch _DEDUP_RE — dấu chấm trong [] không cần escape,
#          thêm gạch dưới vào character class một cách tường minh.
# FIX #10: Pre-compile các regex trước đây nằm trong hàm resolve_display_name.
# ──────────────────────────────────────────────────────────────────────
_NORM_RE = re.compile(r"\s+")
_DEDUP_RE = re.compile(r"[\s\-._]+")  # FIX #11: bỏ backslash thừa trước dấu chấm
_BITRATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mb(?:ps)?", re.I)

# FIX #3: Thay \d+\s*kbps bằng pattern chính xác hơn, yêu cầu word boundary
#         để tránh nuốt nhầm số trong tên kênh như "HTV9".
_NOISE_RE = re.compile(
    r"[\s\-–|]*\b(?:fhd|full\s*hd|hd|sd|4k|8k|uhd|h\.?264|h\.?265|hevc|avc"
    r"|\d+(?:\.\d+)?\s*mbps|\d+\s*kbps)\b.*$",
    re.IGNORECASE,
)

# FIX #10: Pre-compile 2 regex từ resolve_display_name để tránh re-compile mỗi lần gọi
_PIPE_SUFFIX_RE = re.compile(r"\s*\|.*$")
_MULTI_SPACE_RE = re.compile(r"\s{2,}")

_TVG_ID_RE = re.compile(r'tvg-id="([^"]*)"')
_TVG_LOGO_RE = re.compile(r'tvg-logo="([^"]*)"')
_GROUP_TITLE_RE = re.compile(r'group-title="([^"]*)"')

_QUALITY_TIERS: Final[list[tuple[re.Pattern, int]]] = [
    (re.compile(r"\b8k\b", re.I), 80),
    (re.compile(r"\b4k\b|\buhd\b", re.I), 70),
    (re.compile(r"\bfhd\b|\bfull\s*hd\b", re.I), 60),
    (re.compile(r"\bhd\b", re.I), 50),
    (re.compile(r"\bsd\b", re.I), 20),
]


def _norm(s: str) -> str:
    return _NORM_RE.sub("", s).upper()


# Module-level cache cho VTV/HTV index — tính một lần khi import
_VTV_IDX: Final[dict[str, int]] = {_norm(n): i for i, n in enumerate(VTV_FIXED_ORDER)}
_HTV_IDX: Final[dict[str, int]] = {_norm(n): i for i, n in enumerate(HTV_FIXED_ORDER)}


@dataclass
class Channel:
    name: str
    url: str
    group_label: str
    group_order: int
    province: str
    province_idx: int
    quality: tuple[
        int, float
    ]  # (tier, bitrate) — so sánh trực tiếp chất lượng kỹ thuật
    tvg_id: str = ""
    tvg_logo: str = ""


# ──────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────


def _dedup_key(name: str) -> str:
    """Tạo key định danh duy nhất: lowercase, loại bỏ khoảng trắng/dấu câu."""
    return _DEDUP_RE.sub("", name.lower())


def quality_score(raw: str) -> tuple[int, float]:
    """Trả về (tier, bitrate) từ tên kênh. Tier cao hơn = chất lượng tốt hơn."""
    tier = 40  # default: không xác định được → mid-range
    for pat, score in _QUALITY_TIERS:
        if pat.search(raw):
            tier = score
            break
    m = _BITRATE_RE.search(raw)
    return tier, float(m.group(1)) if m else 0.0


def fetch(url: str, timeout: int = GLOBAL_TIMEOUT) -> Optional[str]:
    """Tải nội dung URL. Trả về None nếu thất bại."""
    try:
        r = requests.get(url, timeout=timeout, headers=HTTP_HEADERS)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


def resolve_epg_url() -> str:
    """
    FIX #2: Thử từng EPG URL theo thứ tự ưu tiên, trả về URL đầu tiên hoạt động.
    Phiên bản cũ luôn trả về EPG_URLS[0] mà không check — nếu server chết,
    toàn bộ playlist sẽ gắn EPG link chết.
    """
    for epg_url in EPG_URLS:
        try:
            r = requests.head(
                epg_url, timeout=10, headers=HTTP_HEADERS, allow_redirects=True
            )
            if r.status_code < 400:
                print(f"  ✅ EPG hoạt động: {epg_url}")
                return epg_url
        except Exception as e:
            print(f"  ⚠  EPG {epg_url}: {e}", file=sys.stderr)
    print("  ⚠  Không có EPG URL nào hoạt động, bỏ qua EPG.", file=sys.stderr)
    return ""


def resolve_display_name(raw: str, tvg_id: str) -> str:
    """
    Ưu tiên tra cứu DISPLAY_NAME theo tvg-id.
    Fallback: xóa noise (HD/SD/...) rồi trả về tên sạch.
    FIX #10: Dùng pre-compiled regex thay vì inline re.sub().
    """
    if tvg_id and tvg_id in DISPLAY_NAME:
        return DISPLAY_NAME[tvg_id]
    s = _NOISE_RE.sub("", raw).strip()
    s = _PIPE_SUFFIX_RE.sub("", s).strip()
    return _MULTI_SPACE_RE.sub(" ", s) or raw.strip()


def parse_m3u(text: str) -> list["Channel"]:
    """
    Parser M3U theo State Machine tuyến tính O(N).
    FIX #1: Xử lý group "Quốc Phòng" (antv/qpvn) riêng biệt,
            không nhầm lẫn chúng vào _LOCAL_ province lookup.
    """
    channels: list[Channel] = []
    current_extinf: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF"):
            current_extinf = line
            continue

        # Dòng URL phải đi sau #EXTINF
        if not line.startswith("#") and current_extinf:
            url = line
            extinf_line = current_extinf
            current_extinf = None  # Reset state machine

            # Trích xuất metadata bằng pre-compiled regex
            m_id = _TVG_ID_RE.search(extinf_line)
            tvg_id = m_id.group(1).strip().lower() if m_id else ""

            m_logo = _TVG_LOGO_RE.search(extinf_line)
            tvg_logo = m_logo.group(1).strip() if m_logo else ""

            m_grp = _GROUP_TITLE_RE.search(extinf_line)
            src_grp = m_grp.group(1).strip() if m_grp else ""
            raw_name = (
                extinf_line.split(",", 1)[-1].strip() if "," in extinf_line else ""
            )

            if not raw_name:
                continue

            # ── BỘ LỌC KÊNH RÁC ──────────────────────────────────────
            upper_name = raw_name.upper()
            if tvg_id.startswith("on") or upper_name.startswith("ON "):
                continue
            if any(kw in upper_name for kw in ["SỰ KIỆN", "VTVPRIME", "FPT", "VOV"]):
                continue

            # ── NHẬN DIỆN GROUP ───────────────────────────────────────
            src_grp_lower = src_grp.lower()
            mapped: Optional[str] = None

            if "vtv" in src_grp_lower:
                mapped = "VTV"
            elif "htv" in src_grp_lower:
                mapped = "HTV"
            elif any(
                kw in src_grp_lower
                for kw in [
                    "địa phương",
                    "dia phuong",
                    "tỉnh",
                    "tinh",
                    "thiết yếu",
                    "thiet yeu",
                ]
            ):
                mapped = "_LOCAL_"
            elif "quốc phòng" in src_grp_lower or "quoc phong" in src_grp_lower:
                # FIX #1: Nhận diện group Quốc Phòng qua tên group
                mapped = "Quốc Phòng"
            else:
                mapped = GROUP_MAP.get(src_grp)

            # ── FALLBACK QUA TVG-ID ───────────────────────────────────
            if mapped is None:
                if tvg_id.startswith("vtv"):
                    mapped = "VTV"
                elif tvg_id.startswith("htv") or tvg_id.startswith("htvc"):
                    mapped = "HTV"
                # FIX #1: Nhận diện ANTV/QPVN qua tvg-id TRƯỚC khi check province
                elif tvg_id in ("antv", "antv-hd", "qpvn", "qpvn-hd"):
                    mapped = "Quốc Phòng"
                elif tvg_id in TVGID_TO_PROVINCE:
                    mapped = "_LOCAL_"
                else:
                    continue  # Không nhận ra → bỏ qua

            # ── XÁC ĐỊNH province, group_order ───────────────────────
            if mapped == "_LOCAL_":
                province = TVGID_TO_PROVINCE.get(tvg_id)
                if not province:
                    continue  # Kênh địa phương không xác định được tỉnh → bỏ
                g_label, g_order = GROUP_LABEL_LOCAL, 2
                p_idx = _PROVINCE_IDX.get(province, 999)

            elif mapped == "VTV":
                province = ""
                g_label, g_order, p_idx = "VTV", 0, 0

            elif mapped == "HTV":
                province = ""
                g_label, g_order, p_idx = "HTV", 1, 0

            elif mapped == "Quốc Phòng":
                # FIX #1: Quốc Phòng có group riêng, order = 3, không dùng _PROVINCE_IDX
                province = GROUP_LABEL_QDVN
                g_label, g_order, p_idx = GROUP_LABEL_QDVN, 3, 0

            else:
                continue

            channels.append(
                Channel(
                    name=resolve_display_name(raw_name, tvg_id),
                    url=url,
                    group_label=g_label,
                    group_order=g_order,
                    province=province if g_order >= 2 else "",
                    province_idx=p_idx,
                    quality=quality_score(raw_name),
                    tvg_id=tvg_id,
                    tvg_logo=tvg_logo,
                )
            )

    return channels


def pick_best(channels: list[Channel]) -> list[Channel]:
    """
    Single-pass Max Selection O(N): chọn kênh chất lượng cao nhất mỗi tên.
    Tuple (tier, bitrate) được so sánh trực tiếp — tier cao hơn luôn thắng,
    rồi mới xét bitrate.
    """
    best_channels: dict[str, Channel] = {}

    for ch in channels:
        key = _dedup_key(ch.name)
        existing = best_channels.get(key)
        if existing is None or ch.quality > existing.quality:
            best_channels[key] = ch

    result = list(best_channels.values())
    print(f"     → Đã gộp và lấy {len(result)} kênh chất lượng tốt nhất")
    return result


def merge_sources(lists: list[list[Channel]]) -> list[Channel]:
    """
    FIX #4: Gộp các nguồn với so sánh chất lượng, không phải "first-wins".
    Nguồn đầu tiên vẫn được ưu tiên (priority source), nhưng nếu nguồn sau
    có cùng kênh với quality cao hơn thì thay thế.
    """
    seen: dict[str, Channel] = {}
    for channels in lists:
        for ch in channels:
            k = _dedup_key(ch.name)
            existing = seen.get(k)
            # Giữ kênh từ nguồn ưu tiên nếu quality bằng nhau (first-source-wins tie-break),
            # nhưng thay thế nếu nguồn sau thực sự tốt hơn.
            if existing is None or ch.quality > existing.quality:
                seen[k] = ch
    return list(seen.values())


def _sort_key(ch: Channel) -> tuple:
    """
    FIX #9: Pre-compute _norm(ch.name) một lần trong key function
    thay vì gọi lại nhiều lần trong tiến trình sort Timsort.
    """
    norm_name = _norm(ch.name)  # tính một lần duy nhất mỗi channel
    if ch.group_order == 0:  # VTV
        return (0, 0, _VTV_IDX.get(norm_name, 999), ch.name)
    elif ch.group_order == 1:  # HTV
        return (1, 0, _HTV_IDX.get(norm_name, 999), ch.name)
    elif ch.group_order == 2:  # Địa phương
        return (2, ch.province_idx, 0, ch.name)
    else:  # Quốc Phòng (order = 3) — cuối cùng
        return (3, 0, 0, ch.name)


def sort_channels(channels: list[Channel]) -> list[Channel]:
    return sorted(channels, key=_sort_key)


def write_m3u(channels: list[Channel], path: str, epg_url: str) -> None:
    """Ghi file M3U ra disk. Bắt IOError riêng để không crash silent."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            header = f'#EXTM3U url-tvg="{epg_url}"\n' if epg_url else "#EXTM3U\n"
            f.write(header)
            for ch in channels:
                attrs = (
                    f'tvg-id="{ch.tvg_id}" '
                    f'tvg-logo="{ch.tvg_logo}" '
                    f'group-title="{ch.group_label}"'
                )
                f.write(f"#EXTINF:-1 {attrs},{ch.name}\n")
                f.write(ch.url + "\n")
        print(f"✅  Đã ghi {len(channels)} kênh → {path}")
    except IOError as e:
        print(f"❌  Lỗi ghi file {path}: {e}", file=sys.stderr)
        sys.exit(1)  # FIX: Thoát với exit code lỗi thay vì tiếp tục im lặng


def main() -> None:
    print("🔍  Kiểm tra EPG…")
    epg_url = resolve_epg_url()  # FIX #2: giờ thực sự thử từng URL

    processed: list[list[Channel]] = []
    for idx, src in enumerate(SOURCES, 1):
        print(f"\n[{idx}/{len(SOURCES)}] Tải: {src}")
        text = fetch(src)

        if not text or "#EXTM3U" not in text:
            print("  ⚠  Bỏ qua (không phải M3U hợp lệ)")
            continue

        parsed = parse_m3u(text)
        print(f"     Nhận diện {len(parsed)} kênh TV")
        if not parsed:
            continue

        best = pick_best(parsed)
        processed.append(best)

    if not processed:
        print("❌  Không có nguồn nào hợp lệ. Dừng lại.", file=sys.stderr)
        sys.exit(1)

    print("\n🔀  Gộp & dedup…")
    merged = merge_sources(processed)  # FIX #4: merge giờ xét quality
    final = sort_channels(merged)

    gcnt = Counter(ch.group_label for ch in final)
    print(
        f"📋  VTV: {gcnt['VTV']} | HTV: {gcnt['HTV']} "
        f"| Địa phương: {gcnt[GROUP_LABEL_LOCAL]} "
        f"| Quốc Phòng: {gcnt[GROUP_LABEL_QDVN]} "
        f"| Tổng: {len(final)}"
    )

    write_m3u(final, OUTPUT_FILE, epg_url)


if __name__ == "__main__":
    main()
