#!/usr/bin/env python3
"""
IPTV Auto-updater
- Nguồn: 1.org.vn/vmttv (ưu tiên) + fallback GitHub
- Chỉ lấy kênh TV: VTV, HTV, địa phương
- Lịch phát sóng (EPG): vnepg.site/epg.xml.gz
- Địa phương gom 1 nhóm, sắp xếp Bắc → Nam
- Output: http-iptv.m3u
"""

import gzip
import re
import sys
import concurrent.futures
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────────────────────────────
SOURCES = [
    "https://1.org.vn/vmttv"
]

EPG_URLS = [
    "https://vnepg.site/epg.xml.gz",
    "https://vnepg.site/epg.xml",
]

OUTPUT_FILE = "http-iptv.m3u"
LINK_CHECK_TIMEOUT = 8
LINK_CHECK_WORKERS = 40
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}

# ──────────────────────────────────────────────────────────────────────
# BẢNG TÊN ĐẸP  tvg-id → tên hiển thị
# ──────────────────────────────────────────────────────────────────────
DISPLAY_NAME: dict[str, str] = {
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
    "hagiang": "Hà Giang TV",
    "laichau": "Lai Châu TV",
    "ltv": "Lai Châu TV",
    "dienbien": "Điện Biên TV",
    "laocai": "Lào Cai TV",
    "yenbai": "Yên Bái TV",
    "sonla": "Sơn La TV",
    "hoabinh": "Hòa Bình TV",
    "phutho": "Phú Thọ TV",
    "vinhphuc": "Vĩnh Phúc TV",
    "tuyenquang": "Tuyên Quang TV",
    "backan": "Bắc Kạn TV",
    "thainguyen": "Thái Nguyên TV",
    "caobang": "Cao Bằng TV",
    "langson": "Lạng Sơn TV",
    "quangninh": "Quảng Ninh TV",
    "quangninh1": "Quảng Ninh TV1",
    "quangninh3": "Quảng Ninh TV3",
    "bacgiang": "Bắc Giang TV",
    "bacninh": "Bắc Ninh TV",
    "hanoi1": "Hà Nội TV1",
    "hanoi2": "Hà Nội TV2",
    "vovgthn": "VOV Giao Thông HN",
    "haiphong": "Hải Phòng TV",
    "haiphong3": "Hải Phòng TV3",
    "haiphongplus": "Hải Phòng TV+",
    "haiduong": "Hải Dương TV",
    "hungyen": "Hưng Yên TV",
    "thaibinh": "Thái Bình TV",
    "namdinh": "Nam Định TV",
    "hanam": "Hà Nam TV",
    "ninhbinh": "Ninh Bình TV",
    # Miền Trung
    "thanhhoa": "Thanh Hóa TV",
    "nghean": "Nghệ An TV",
    "hatinh": "Hà Tĩnh TV",
    "quangbinh": "Quảng Bình TV",
    "quangtri": "Quảng Trị TV",
    "hue": "Huế TV",
    "danang1": "Đà Nẵng TV1",
    "danang2": "Đà Nẵng TV2",
    "quangnam": "Quảng Nam TV",
    "quangngai": "Quảng Ngãi TV1",
    "quangngai1": "Quảng Ngãi TV1",
    "quangngai2": "Quảng Ngãi TV2",
    "binhdinh": "Bình Định TV",
    "phuyen": "Phú Yên TV",
    "khanhhoa": "Khánh Hòa TV",
    "khanhhoa1": "Khánh Hòa TV1",
    "ninhthuan": "Ninh Thuận TV",
    "binhthuan": "Bình Thuận TV",
    # Tây Nguyên
    "kontum": "Kon Tum TV",
    "gialai": "Gia Lai TV",
    "daklak": "Đắk Lắk TV",
    "daknong": "Đắk Nông TV",
    "lamdong": "Lâm Đồng TV1",
    "lamdong1": "Lâm Đồng TV1",
    "lamdong2": "Lâm Đồng TV2",
    "lamdong3": "Lâm Đồng TV3",
    # Miền Nam
    "binhphuoc": "Bình Phước TV",
    "tayninh1": "Tây Ninh TV",
    "tayninhtv": "Tây Ninh TV",
    "binhduong": "Bình Dương TV",
    "dongnai1": "Đồng Nai TV1",
    "dongnai2": "Đồng Nai TV2",
    "dongnai3": "Đồng Nai TV3",
    "baria": "Bà Rịa - Vũng Tàu TV",
    "longan": "Long An TV",
    "tiengiang": "Tiền Giang TV",
    "bentre": "Bến Tre TV",
    "dongthap": "Đồng Tháp TV1",
    "dongthap1": "Đồng Tháp TV1",
    "dongthap2": "Đồng Tháp TV2",
    "vinhlong1hd": "THVL1",
    "thvl1hd": "THVL1",
    "thvl1": "THVL1",
    "vinhlong2hd": "THVL2",
    "thvl2hd": "THVL2",
    "thvl2": "THVL2",
    "vinhlong3hd": "THVL3",
    "thvl3hd": "THVL3",
    "thvl3": "THVL3",
    "vinhlong4hd": "THVL4",
    "thvl4hd": "THVL4",
    "thvl4": "THVL4",
    "vinhlong5hd": "THVL5",
    "thvl5hd": "THVL5",
    "thvl5": "THVL5",
    "travinh": "Trà Vinh TV",
    "angiang1": "An Giang TV1",
    "angiang2": "An Giang TV2",
    "angiang3": "An Giang TV3",
    "kiengiang": "Kiên Giang TV",
    "cantho": "Cần Thơ TV",
    "cantho1": "Cần Thơ TV1",
    "cantho2": "Cần Thơ TV2",
    "cantho3": "Cần Thơ TV3",
    "haugiang": "Hậu Giang TV",
    "soctrang": "Sóc Trăng TV",
    "baclieu": "Bạc Liêu TV",
    "camau": "Cà Mau TV",
    # Quốc phòng
    "antv-hd": "ANTV",
    "antv": "ANTV",
    "qpvn-hd": "QPVN",
    "qpvn": "QPVN",
}

# ──────────────────────────────────────────────────────────────────────
# GROUP MAP  group-title nguồn → nhóm chuẩn
# ──────────────────────────────────────────────────────────────────────
GROUP_MAP: dict[str, str] = {
    "VTV": "VTV",
    "HTV": "HTV",
    "HTV/HTVC": "HTV",
    # Địa phương tỉnh thành (1.org.vn)
    "Hà Giang": "Hà Giang",
    "Tuyên Quang": "Tuyên Quang",
    "Cao Bằng": "Cao Bằng",
    "Lạng Sơn": "Lạng Sơn",
    "Bắc Kạn": "Bắc Kạn",
    "Thái Nguyên": "Thái Nguyên",
    "Quảng Ninh": "Quảng Ninh",
    "Bắc Giang": "Bắc Giang",
    "Bắc Ninh": "Bắc Ninh",
    "Lào Cai": "Lào Cai",
    "Yên Bái": "Yên Bái",
    "Phú Thọ": "Phú Thọ",
    "Vĩnh Phúc": "Vĩnh Phúc",
    "Hà Nội": "Hà Nội",
    "Hòa Bình": "Hòa Bình",
    "Sơn La": "Sơn La",
    "Điện Biên": "Điện Biên",
    "Lai Châu": "Lai Châu",
    "Hải Phòng": "Hải Phòng",
    "Hải Dương": "Hải Dương",
    "Hưng Yên": "Hưng Yên",
    "Thái Bình": "Thái Bình",
    "Nam Định": "Nam Định",
    "Hà Nam": "Hà Nam",
    "Ninh Bình": "Ninh Bình",
    "Thanh Hóa": "Thanh Hóa",
    "Nghệ An": "Nghệ An",
    "Hà Tĩnh": "Hà Tĩnh",
    "Quảng Bình": "Quảng Bình",
    "Quảng Trị": "Quảng Trị",
    "Thừa Thiên Huế": "Thừa Thiên Huế",
    "Đà Nẵng": "Đà Nẵng",
    "Quảng Nam": "Quảng Nam",
    "Quảng Ngãi": "Quảng Ngãi",
    "Bình Định": "Bình Định",
    "Phú Yên": "Phú Yên",
    "Khánh Hòa": "Khánh Hòa",
    "Ninh Thuận": "Ninh Thuận",
    "Bình Thuận": "Bình Thuận",
    "Kon Tum": "Kon Tum",
    "Gia Lai": "Gia Lai",
    "Đắk Lắk": "Đắk Lắk",
    "Đắk Nông": "Đắk Nông",
    "Lâm Đồng": "Lâm Đồng",
    "Bình Phước": "Bình Phước",
    "Tây Ninh": "Tây Ninh",
    "Bình Dương": "Bình Dương",
    "Đồng Nai": "Đồng Nai",
    "Bà Rịa - Vũng Tàu": "Bà Rịa - Vũng Tàu",
    "Long An": "Long An",
    "Tiền Giang": "Tiền Giang",
    "Bến Tre": "Bến Tre",
    "Đồng Tháp": "Đồng Tháp",
    "Vĩnh Long": "Vĩnh Long",
    "Trà Vinh": "Trà Vinh",
    "An Giang": "An Giang",
    "Kiên Giang": "Kiên Giang",
    "Cần Thơ": "Cần Thơ",
    "Hậu Giang": "Hậu Giang",
    "Sóc Trăng": "Sóc Trăng",
    "Bạc Liêu": "Bạc Liêu",
    "Cà Mau": "Cà Mau",
    # Quốc phòng
    "Quốc Phòng": "Quốc Phòng",
    # Các nhóm fallback (blvbatman, ntd249)
    "Địa Phương": "_LOCAL_",
    "Địa phương (HD)": "_LOCAL_",
    "Địa phương (SD)": "_LOCAL_",
    "Kênh TH Thiết yếu": "_LOCAL_",
}

# tvg-id → tỉnh (dùng khi group = _LOCAL_)
TVGID_TO_PROVINCE: dict[str, Optional[str]] = {
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
    "thvl2hd": "Vĩnh Long",
    "thvl3hd": "Vĩnh Long",
    "thvl4hd": "Vĩnh Long",
    "thvl5hd": "Vĩnh Long",
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
    "antv-hd": "Quốc Phòng",
    "antv": "Quốc Phòng",
    "qpvn-hd": "Quốc Phòng",
    "qpvn": "Quốc Phòng",
    # bỏ
    "hitv": None,
    "youtv": None,
    "htvkey": None,
}

# Thứ tự tỉnh Bắc → Nam
LOCAL_PROVINCE_ORDER: list[str] = [
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
    "Quốc Phòng",
]
_PROVINCE_IDX: dict[str, int] = {p: i for i, p in enumerate(LOCAL_PROVINCE_ORDER)}

GROUP_LABEL_LOCAL = "Địa phương"

# ──────────────────────────────────────────────────────────────────────
# SORT ORDER CỐ ĐỊNH
# ──────────────────────────────────────────────────────────────────────
VTV_FIXED_ORDER = [
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
HTV_FIXED_ORDER = [
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


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


_VTV_IDX = {_norm(n): i for i, n in enumerate(VTV_FIXED_ORDER)}
_HTV_IDX = {_norm(n): i for i, n in enumerate(HTV_FIXED_ORDER)}


# ──────────────────────────────────────────────────────────────────────
# DATA CLASS
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Channel:
    name: str
    url: str
    group_label: str
    group_order: int
    province: str
    province_idx: int
    quality: tuple[int, float]
    tvg_id: str = ""
    tvg_logo: str = ""


def _dedup_key(name: str) -> str:
    return re.sub(r"[\s\-\._]+", "", name.lower())


# ──────────────────────────────────────────────────────────────────────
# QUALITY
# ──────────────────────────────────────────────────────────────────────
_QUALITY_TIERS = [
    (re.compile(r"\b8k\b", re.I), 80),
    (re.compile(r"\b4k\b|\buhd\b", re.I), 70),
    (re.compile(r"\bfhd\b|\bfull\s*hd\b", re.I), 60),
    (re.compile(r"\bhd\b", re.I), 50),
    (re.compile(r"\bsd\b", re.I), 20),
]
_BITRATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mb(?:ps)?", re.I)


def quality_score(raw: str) -> tuple[int, float]:
    tier = 40
    for pat, score in _QUALITY_TIERS:
        if pat.search(raw):
            tier = score
            break
    m = _BITRATE_RE.search(raw)
    return tier, float(m.group(1)) if m else 0.0


# ──────────────────────────────────────────────────────────────────────
# FETCH
# ──────────────────────────────────────────────────────────────────────
def fetch(url: str, timeout: int = 20) -> Optional[str]:
    try:
        r = requests.get(url, timeout=timeout, headers=HTTP_HEADERS)
        r.raise_for_status()
        if len(r.text) < 50:
            return None
        return r.text
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


def fetch_bytes(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout, headers=HTTP_HEADERS)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────────────────────────────
# EPG  — tải và nhúng trực tiếp vào file M3U (url-tvg header)
# ──────────────────────────────────────────────────────────────────────
def resolve_epg_url() -> str:
    """Trả về EPG URL hoạt động, hoặc chuỗi rỗng nếu không có."""
    for url in EPG_URLS:
        try:
            r = requests.get(url, timeout=15, headers=HTTP_HEADERS, stream=True)
            if r.status_code == 200:
                print(f"  ✅ EPG: {url}")
                return url
        except Exception:
            pass
    print(
        "  ⚠  Không tải được EPG, playlist sẽ không có lịch phát sóng.", file=sys.stderr
    )
    return ""


# ──────────────────────────────────────────────────────────────────────
# PARSE M3U
# ──────────────────────────────────────────────────────────────────────
_NOISE_RE = re.compile(
    r"[\s\-–|]*\b(?:fhd|full\s*hd|hd|sd|4k|8k|uhd"
    r"|h\.?264|h\.?265|hevc|avc"
    r"|\d+(?:\.\d+)?\s*mb(?:ps)?"
    r"|\d+\s*kbps)\b.*$",
    re.IGNORECASE,
)


def resolve_display_name(raw: str, tvg_id: str) -> str:
    if tvg_id and tvg_id in DISPLAY_NAME:
        return DISPLAY_NAME[tvg_id]
    s = _NOISE_RE.sub("", raw).strip()
    s = re.sub(r"\s*\|.*$", "", s).strip()
    return re.sub(r"\s{2,}", " ", s) or raw.strip()


def parse_m3u(text: str) -> list[Channel]:
    channels: list[Channel] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            url = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    url = nxt
                    i = j
                    break
                j += 1
            if not url:
                i += 1
                continue

            tvg_id = (
                (
                    re.search(r'tvg-id="([^"]*)"', line)
                    or type("", (), {"group": lambda s, x: ""})()
                )
                .group(1)
                .strip()
            )
            tvg_logo = (
                (
                    re.search(r'tvg-logo="([^"]*)"', line)
                    or type("", (), {"group": lambda s, x: ""})()
                )
                .group(1)
                .strip()
            )
            src_grp = (
                (
                    re.search(r'group-title="([^"]*)"', line)
                    or type("", (), {"group": lambda s, x: ""})()
                )
                .group(1)
                .strip()
            )
            raw_name = line.split(",", 1)[-1].strip() if "," in line else ""

            # Dùng regex match thực tế
            m_id = re.search(r'tvg-id="([^"]*)"', line)
            m_logo = re.search(r'tvg-logo="([^"]*)"', line)
            m_grp = re.search(r'group-title="([^"]*)"', line)
            tvg_id = m_id.group(1).strip() if m_id else ""
            tvg_logo = m_logo.group(1).strip() if m_logo else ""
            src_grp = m_grp.group(1).strip() if m_grp else ""

            if not raw_name:
                i += 1
                continue

            mapped = GROUP_MAP.get(src_grp)
            if mapped is None:
                i += 1
                continue

            if mapped == "_LOCAL_":
                province = TVGID_TO_PROVINCE.get(tvg_id)
                if not province:
                    i += 1
                    continue
            else:
                province = mapped

            if mapped == "VTV":
                g_label, g_order, p_idx = "VTV", 0, 0
            elif mapped == "HTV":
                g_label, g_order, p_idx = "HTV", 1, 0
            else:
                g_label = GROUP_LABEL_LOCAL
                g_order = 2
                p_idx = _PROVINCE_IDX.get(province, 999)

            channels.append(
                Channel(
                    name=resolve_display_name(raw_name, tvg_id),
                    url=url,
                    group_label=g_label,
                    group_order=g_order,
                    province=province if g_order == 2 else "",
                    province_idx=p_idx,
                    quality=quality_score(raw_name),
                    tvg_id=tvg_id,
                    tvg_logo=tvg_logo,
                )
            )
        i += 1
    return channels


# ──────────────────────────────────────────────────────────────────────
# LINK CHECK
# ──────────────────────────────────────────────────────────────────────
def _is_live(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return True
    try:
        r = requests.head(
            url, timeout=LINK_CHECK_TIMEOUT, headers=HTTP_HEADERS, allow_redirects=True
        )
        return r.status_code not in (404, 410)
    except Exception:
        return False


def check_all(urls: list[str]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    unique = list(set(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=LINK_CHECK_WORKERS) as ex:
        fmap = {ex.submit(_is_live, u): u for u in unique}
        done = 0
        for fut in concurrent.futures.as_completed(fmap):
            u = fmap[fut]
            try:
                results[u] = fut.result()
            except:
                results[u] = False
            done += 1
            if done % 20 == 0 or done == len(unique):
                print(
                    f"     {done}/{len(unique)}, sống: {sum(results.values())}",
                    end="\r",
                )
    print()
    return results


def pick_best(channels: list[Channel]) -> list[Channel]:
    groups: dict[str, list[Channel]] = defaultdict(list)
    for ch in channels:
        groups[_dedup_key(ch.name)].append(ch)
    for k in groups:
        groups[k].sort(key=lambda c: (-c.quality[0], -c.quality[1]))

    live_map = check_all([ch.url for chs in groups.values() for ch in chs])
    live = sum(live_map.values())
    dead = len(live_map) - live
    print(
        f"     ✅ {live}/{len(live_map)} sống" + (f", bỏ {dead} chết" if dead else "")
    )

    result, skipped = [], 0
    for variants in groups.values():
        best = next((c for c in variants if live_map.get(c.url, False)), None)
        if best:
            result.append(best)
        else:
            skipped += 1
    if skipped:
        print(f"     ⚠  Bỏ {skipped} kênh (link chết hết)")
    return result


# ──────────────────────────────────────────────────────────────────────
# MERGE & SORT
# ──────────────────────────────────────────────────────────────────────
def merge_sources(lists: list[list[Channel]]) -> list[Channel]:
    seen: dict[str, Channel] = {}
    for channels in lists:
        for ch in channels:
            k = _dedup_key(ch.name)
            if k not in seen:
                seen[k] = ch
    return list(seen.values())


def _sort_key(ch: Channel):
    k = _norm(ch.name)
    if ch.group_order == 0:
        return (0, 0, _VTV_IDX.get(k, 999), ch.name)
    elif ch.group_order == 1:
        return (1, 0, _HTV_IDX.get(k, 999), ch.name)
    else:
        return (2, ch.province_idx, 0, ch.name)


def sort_channels(channels: list[Channel]) -> list[Channel]:
    return sorted(channels, key=_sort_key)


# ──────────────────────────────────────────────────────────────────────
# WRITE M3U
# ──────────────────────────────────────────────────────────────────────
def write_m3u(channels: list[Channel], path: str, epg_url: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if epg_url:
            f.write(f'#EXTM3U url-tvg="{epg_url}"\n')
        else:
            f.write("#EXTM3U\n")
        for ch in channels:
            attrs = (
                f'tvg-id="{ch.tvg_id}" '
                f'tvg-logo="{ch.tvg_logo}" '
                f'group-title="{ch.group_label}"'
            )
            f.write(f"#EXTINF:-1 {attrs},{ch.name}\n")
            f.write(ch.url + "\n")
    print(f"✅  Đã ghi {len(channels)} kênh → {path}")
    if epg_url:
        print(f"    EPG: {epg_url}")


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
_TIER = {80: "8K", 70: "4K", 60: "FHD", 50: "HD", 40: "~HD", 20: "SD"}


def main():
    print("🔍  Kiểm tra EPG…")
    epg_url = resolve_epg_url()

    processed: list[list[Channel]] = []
    for idx, src in enumerate(SOURCES, 1):
        print(f"\n[{idx}/{len(SOURCES)}] Tải: {src}")
        text = fetch(src)
        if not text or "#EXTM3U" not in text[:300]:
            print("  ⚠  Bỏ qua (không phải M3U hợp lệ)")
            processed.append([])
            continue
        parsed = parse_m3u(text)
        print(f"     Nhận diện {len(parsed)} kênh TV")
        if not parsed:
            processed.append([])
            continue
        best = pick_best(parsed)
        print(f"     → Giữ {len(best)} kênh")
        processed.append(best)

    print("\n🔀  Gộp & dedup…")
    merged = merge_sources(processed)
    final = sort_channels(merged)

    gcnt = Counter(ch.group_label for ch in final)
    print(
        f"📋  VTV: {gcnt['VTV']} | HTV: {gcnt['HTV']} | Địa phương: {gcnt[GROUP_LABEL_LOCAL]} | Tổng: {len(final)}"
    )

    write_m3u(final, OUTPUT_FILE, epg_url)

    print("\n📺  Danh sách:")
    cur = None
    for i, ch in enumerate(final, 1):
        if ch.group_label != cur:
            cur = ch.group_label
            print(f"\n  ── {cur} ({gcnt[cur]}) ──")
        tier = _TIER.get(ch.quality[0], "?")
        mbps = f" {ch.quality[1]:.0f}M" if ch.quality[1] else ""
        prov = f" [{ch.province}]" if ch.province else ""
        print(f"  {i:3}. {ch.name:<35} [{tier}{mbps}]{prov}")


if __name__ == "__main__":
    main()
