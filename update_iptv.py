#!/usr/bin/env python3
"""
IPTV Auto-updater (Production Ready - Optimized)
- Nguồn: 1.org.vn/vmttv (ưu tiên) + fallback GitHub
- Chỉ lấy kênh TV: VTV, HTV, địa phương
- Lịch phát sóng (EPG): vnepg.site/epg.xml.gz
- Địa phương gom 1 nhóm, sắp xếp Bắc → Nam
- tvg-id chuẩn hóa theo vnepg (viết liền, không dấu gạch nối)
- Header M3U: EPG sources trước, IPTV sources sau
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
    # "https://raw.githubusercontent.com/vuminhthanh12/vuminhthanh12/refs/heads/main/vmttv",
    # "https://raw.githubusercontent.com/Bacbenny/Truyenhinhiptv/refs/heads/main/dekiki.m3u",
    # "https://raw.githubusercontent.com/Bacbenny/Verceliptv/refs/heads/main/VTV.m3u",
    # "https://raw.githubusercontent.com/hoiquanclick/hoiquan/refs/heads/main/vip.m3u",
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
# CHUẨN HÓA TVG-ID THEO VNEPG
# Map từ tvg-id gốc (có thể có dấu gạch ngang, alias) → tvg-id chuẩn vnepg
# Quy tắc vnepg: viết liền, không dấu gạch ngang, không khoảng trắng
# ──────────────────────────────────────────────────────────────────────
TVG_ID_MAP: Final[dict[str, str]] = {
    # VTV — alias không có hd
    "vtv6": "vtv6hd",
    "vtv10": "vtv10hd",
    # HTV — vnepg dùng htv1hd, htv3hd
    "htv1": "htv1hd",
    "htv3": "htv3hd",
    "htv4": "htv4hd",
    # HTVC — vnepg dùng htvccanachd, htvcthuanviethd
    "htvccanhachd": "htvccanachd",
    "htvcthuanviet": "htvcthuanviethd",
    # Quốc phòng — bỏ dấu gạch ngang
    "antv-hd": "antv",
    "qpvn-hd": "qpvn",
    # Địa phương — vnepg không dùng số hậu tố cho kênh chính
    "danang1": "danang",
    "tayninh1": "tayninh",
    "tayninhtv": "tayninh",
    "dongnai1": "dongnai",
    "dongthap1": "dongthap",
    "cantho1": "cantho",
    "khanhhoa1": "khanhhoa",
    "quangngai1": "quangngai",
    # Alias khác
    "ltv": "laichau",
    "vovgthn": "hanoi1",
    # thvl → vinhlong (vnepg dùng vinhlong*)
    "thvl1hd": "vinhlong1hd",
    "thvl1": "vinhlong1hd",
    "thvl2hd": "vinhlong2hd",
    "thvl2": "vinhlong2hd",
    "thvl3hd": "vinhlong3hd",
    "thvl3": "vinhlong3hd",
    "thvl4hd": "vinhlong4hd",
    "thvl4": "vinhlong4hd",
    "thvl5hd": "vinhlong5hd",
    "thvl5": "vinhlong5hd",
}


def normalize_tvg_id(raw_id: str) -> str:
    """Chuẩn hóa tvg-id: map alias → chuẩn vnepg, fallback bỏ dấu gạch ngang."""
    clean = raw_id.strip().lower()
    if clean in TVG_ID_MAP:
        return TVG_ID_MAP[clean]
    # Bỏ dấu gạch ngang nếu chưa có trong map (antv-hd → antv, ...)
    return clean.replace("-", "")


# ──────────────────────────────────────────────────────────────────────
# BẢNG TÊN ĐẸP (tvg-id chuẩn vnepg → tên hiển thị)
# Tất cả key đã dùng tvg-id chuẩn (viết liền, không dấu gạch ngang)
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
    "vtv7hd": "VTV7",
    "vtv8hd": "VTV8",
    "vtv9hd": "VTV9",
    "vtv10hd": "VTV10",
    "vietnamtoday": "Vietnam Today",
    # HTV / HTVC — key theo chuẩn vnepg
    "htv1hd": "HTV1",
    "htv2hd": "HTV2",
    "htv3hd": "HTV3",
    "htv4hd": "HTV4",
    "htv5": "HTV5",
    "htv7hd": "HTV7",
    "htv9hd": "HTV9",
    "htvthethaohd": "HTVC Thể Thao",
    "htvccanachd": "HTVC Ca Nhạc",
    "htvcdulichhd": "HTVC Du Lịch",
    "htvcgiadinhhd": "HTVC Gia Đình",
    "htvcphimhd": "HTVC Phim",
    "htvcphunuhd": "HTVC Phụ Nữ",
    "htvcthuanviethd": "HTVC Thuần Việt",
    "htvcplushd": "HTVC+",
    # Miền Bắc
    "hagiang": "Hà Giang",
    "laichau": "Lai Châu",
    "dienbien": "Điện Biên",
    "laocai": "Lào Cai",
    "yenbai": "Yên Bái",
    "sonla": "Sơn La",
    "phutho": "Phú Thọ",
    "vinhphuc": "Vĩnh Phúc",
    "tuyenquang": "Tuyên Quang",
    "backan": "Bắc Kạn",
    "thainguyen": "Thái Nguyên",
    "caobang": "Cao Bằng",
    "langson": "Lạng Sơn",
    "quangninh": "Quảng Ninh",
    "quangninh3": "Quảng Ninh 3",
    "bacgiang": "Bắc Giang",
    "bacninh": "Bắc Ninh",
    "hanoi1": "Hà Nội 1",
    "hanoi2": "Hà Nội 2",
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
    "danang": "Đà Nẵng",
    "danang2": "Đà Nẵng 2",
    "quangnam": "Quảng Nam",
    "quangngai": "Quảng Ngãi",
    "quangngai2": "Quảng Ngãi 2",
    "binhdinh": "Bình Định",
    "phuyen": "Phú Yên",
    "khanhhoa": "Khánh Hòa",
    "ninhthuan": "Ninh Thuận",
    "binhthuan": "Bình Thuận",
    # Tây Nguyên
    "kontum": "Kon Tum",
    "gialai": "Gia Lai",
    "daklak": "Đắk Lắk",
    "daknong": "Đắk Nông",
    "lamdong": "Lâm Đồng",
    "lamdong2": "Lâm Đồng 2",
    # Miền Nam
    "binhphuoc": "Bình Phước",
    "tayninh": "Tây Ninh",
    "binhduong": "Bình Dương",
    "dongnai": "Đồng Nai",
    "dongnai2": "Đồng Nai 2",
    "dongnai3": "Đồng Nai 3",
    "baria": "Bà Rịa - Vũng Tàu",
    "longan": "Long An",
    "tiengiang": "Tiền Giang",
    "bentre": "Bến Tre",
    "dongthap": "Đồng Tháp",
    "dongthap2": "Đồng Tháp 2",
    "vinhlong1hd": "Vĩnh Long 1",
    "vinhlong2hd": "Vĩnh Long 2",
    "vinhlong3hd": "Vĩnh Long 3",
    "vinhlong4hd": "Vĩnh Long 4",
    "vinhlong5hd": "Vĩnh Long 5",
    "travinh": "Trà Vinh",
    "angiang1": "An Giang 1",
    "angiang2": "An Giang 2",
    "angiang3": "An Giang 3",
    "kiengiang": "Kiên Giang",
    "cantho": "Cần Thơ",
    "cantho2": "Cần Thơ 2",
    "cantho3": "Cần Thơ 3",
    "haugiang": "Hậu Giang",
    "soctrang": "Sóc Trăng",
    "baclieu": "Bạc Liêu",
    "camau": "Cà Mau",
    # Quốc phòng
    "antv": "ANTV",
    "qpvn": "QPVN",
}

# ──────────────────────────────────────────────────────────────────────
# FIX #8: Gộp GROUP_MAP — chỉ giữ entries không bị xử lý bởi keyword
#         fallback bên dưới để tránh dead code.
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
    # Key là tvg-id đã chuẩn hóa theo vnepg (sau khi qua normalize_tvg_id)
    "hagiang": "Hà Giang",
    "tuyenquang": "Tuyên Quang",
    "caobang": "Cao Bằng",
    "langson": "Lạng Sơn",
    "backan": "Bắc Kạn",
    "thainguyen": "Thái Nguyên",
    "quangninh": "Quảng Ninh",
    "quangninh3": "Quảng Ninh",
    "bacgiang": "Bắc Giang",
    "bacninh": "Bắc Ninh",
    "laocai": "Lào Cai",
    "yenbai": "Yên Bái",
    "phutho": "Phú Thọ",
    "vinhphuc": "Vĩnh Phúc",
    "hanoi1": "Hà Nội",
    "hanoi2": "Hà Nội",
    "sonla": "Sơn La",
    "dienbien": "Điện Biên",
    "laichau": "Lai Châu",
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
    "danang2": "Đà Nẵng",
    "quangnam": "Quảng Nam",
    "quangngai": "Quảng Ngãi",
    "quangngai2": "Quảng Ngãi",
    "binhdinh": "Bình Định",
    "phuyen": "Phú Yên",
    "khanhhoa": "Khánh Hòa",
    "ninhthuan": "Ninh Thuận",
    "binhthuan": "Bình Thuận",
    "kontum": "Kon Tum",
    "gialai": "Gia Lai",
    "daklak": "Đắk Lắk",
    "daknong": "Đắk Nông",
    "lamdong": "Lâm Đồng",
    "lamdong2": "Lâm Đồng",
    "binhphuoc": "Bình Phước",
    "binhduong": "Bình Dương",
    "dongnai2": "Đồng Nai",
    "dongnai3": "Đồng Nai",
    "baria": "Bà Rịa - Vũng Tàu",
    "longan": "Long An",
    "tiengiang": "Tiền Giang",
    "bentre": "Bến Tre",
    "dongthap": "Đồng Tháp",
    "dongthap2": "Đồng Tháp",
    "vinhlong1hd": "Vĩnh Long",
    "vinhlong2hd": "Vĩnh Long",
    "vinhlong3hd": "Vĩnh Long",
    "vinhlong4hd": "Vĩnh Long",
    "vinhlong5hd": "Vĩnh Long",
    "travinh": "Trà Vinh",
    "angiang1": "An Giang",
    "angiang2": "An Giang",
    "angiang3": "An Giang",
    "kiengiang": "Kiên Giang",
    "cantho": "Cần Thơ",
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
            tvg_id = normalize_tvg_id(m_id.group(1)) if m_id else ""

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
            if any(
                kw in upper_name
                for kw in ["SỰ KIỆN", "VTVPRIME", "FPT", "VOV", "VTVCAB", "SPOTV", "O2"]
            ):
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
                elif tvg_id in ("antv", "qpvn"):  # đã normalize, không còn dạng -hd
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
    Nếu trùng URL (link stream), chỉ giữ lại một kênh.
    """
    best_channels: dict[str, Channel] = {}
    seen_urls: set[str] = set()

    for ch in channels:
        url_norm = ch.url.strip()
        if url_norm in seen_urls:
            continue  # Trùng link → bỏ qua
        key = _dedup_key(ch.name)
        existing = best_channels.get(key)
        if existing is None or ch.quality > existing.quality:
            # Nếu thay thế kênh cũ, giải phóng URL cũ khỏi seen_urls
            if existing is not None:
                seen_urls.discard(existing.url.strip())
            best_channels[key] = ch
            seen_urls.add(url_norm)

    result = list(best_channels.values())
    print(f"     → Đã gộp và lấy {len(result)} kênh chất lượng tốt nhất")
    return result


def merge_sources(lists: list[list[Channel]]) -> list[Channel]:
    """
    FIX #4: Gộp các nguồn với so sánh chất lượng, không phải "first-wins".
    Nguồn đầu tiên vẫn được ưu tiên (priority source), nhưng nếu nguồn sau
    có cùng kênh với quality cao hơn thì thay thế.
    Nếu trùng URL (link stream) giữa các nguồn, chỉ giữ lại một kênh.
    """
    seen: dict[str, Channel] = {}
    seen_urls: set[str] = set()

    for channels in lists:
        for ch in channels:
            url_norm = ch.url.strip()
            if url_norm in seen_urls:
                continue  # Trùng link → bỏ qua
            k = _dedup_key(ch.name)
            existing = seen.get(k)
            # Giữ kênh từ nguồn ưu tiên nếu quality bằng nhau (first-source-wins tie-break),
            # nhưng thay thế nếu nguồn sau thực sự tốt hơn.
            if existing is None or ch.quality > existing.quality:
                if existing is not None:
                    seen_urls.discard(existing.url.strip())
                seen[k] = ch
                seen_urls.add(url_norm)

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


def write_m3u(
    channels: list[Channel],
    path: str,
    epg_url: str,
    iptv_sources: list[str] | None = None,
) -> None:
    """
    Ghi file M3U ra disk.
    Header gồm: EPG sources (url-tvg) trước, sau đó x-tvg-url cho từng IPTV source.
    Thứ tự header đảm bảo player parse EPG trước khi load kênh.
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            # ── HEADER ───────────────────────────────────────────────
            if epg_url:
                # Dòng 1: EPG chính (url-tvg được hầu hết player nhận)
                f.write(f'#EXTM3U url-tvg="{epg_url}"\n')
                # Dòng 2: x-tvg-url cho player hỗ trợ thêm attribute này
                f.write(f'#EXTM3U x-tvg-url="{epg_url}"\n')
            else:
                f.write("#EXTM3U\n")

            # IPTV sources dưới dạng comment — một số player (TiviMate, GSE)
            # đọc #EXTVLCOPT hoặc comment đặc biệt; ghi dạng #EXTM3U-SOURCE
            # để dễ debug và một số player hiển thị nguồn.
            if iptv_sources:
                for src_url in iptv_sources:
                    f.write(f"#EXTM3U-SOURCE:{src_url}\n")

            # ── NỘI DUNG KÊNH ─────────────────────────────────────
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
        sys.exit(1)


def main() -> None:
    epg_url = EPG_URLS[0]  # Dùng trực tiếp, không kiểm tra
    print(f"📡  EPG: {epg_url}")

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

    write_m3u(final, OUTPUT_FILE, epg_url, iptv_sources=SOURCES)


if __name__ == "__main__":
    main()
