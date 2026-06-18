#!/usr/bin/env python3
"""
IPTV Auto-updater
- Nguồn: 1.org.vn/vmttv (ưu tiên) + fallback
- Kênh TV: VTV, HTV, địa phương, ANTV, QPVN
- EPG: vnepg.site (thêm trực tiếp, không kiểm tra)
- Sắp xếp địa phương Bắc → Nam
- tvg-id chuẩn hóa theo vnepg (viết liền, không dấu gạch ngang)
- Output: http-iptv.m3u
"""

import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Final, Optional

import requests

# ──────────────────────────────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────────────────────────────
SOURCES: Final[list[str]] = [
    "https://1.org.vn/vmttv",
    "https://vmttv.duckdns.org/",
]

EPG_URL: Final[str] = "https://vnepg.site/epg.xml.gz"
OUTPUT_FILE: Final[str] = "http-iptv.m3u"
GLOBAL_TIMEOUT: Final[int] = 20
HTTP_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ──────────────────────────────────────────────────────────────────────
# REGEX PRE-COMPILED (khai báo đầu tiên để các hàm/dict bên dưới dùng được)
# ──────────────────────────────────────────────────────────────────────
_NORM_RE = re.compile(r"\s+")
_DEDUP_RE = re.compile(r"[\s\-._]+")
_BITRATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mb(?:ps)?", re.I)
_NOISE_RE = re.compile(
    r"[\s\-–|]*\b(?:fhd|full\s*hd|hd|sd|4k|8k|uhd|h\.?264|h\.?265|hevc|avc"
    r"|\d+(?:\.\d+)?\s*mbps|\d+\s*kbps)\b.*$",
    re.IGNORECASE,
)
_PIPE_RE = re.compile(r"\s*\|.*$")
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


def _norm_key(s: str) -> str:
    """Chuẩn hóa chuỗi để so sánh: bỏ khoảng trắng, uppercase."""
    return _NORM_RE.sub("", s).upper()


def _dedup_key(name: str) -> str:
    """Key dedup: lowercase, bỏ khoảng trắng/dấu câu."""
    return _DEDUP_RE.sub("", name.lower())


# ──────────────────────────────────────────────────────────────────────
# CHUẨN HÓA TVG-ID THEO VNEPG (viết liền, không dấu gạch ngang)
# ──────────────────────────────────────────────────────────────────────
TVG_ID_MAP: Final[dict[str, str]] = {
    # VTV alias không có hd
    "vtv6": "vtv6hd",
    "vtv10": "vtv10hd",
    # HTV — vnepg dùng dạng *hd
    "htv1": "htv1hd",
    "htv3": "htv3hd",
    "htv4": "htv4hd",
    # HTVC alias
    "htvccanhachd": "htvccanachd",
    "htvcthuanviet": "htvcthuanviethd",
    # Quốc phòng — bỏ gạch ngang
    "antv-hd": "antv",
    "qpvn-hd": "qpvn",
    # Địa phương alias
    "tayninhtv": "tayninh1",
    "dongthap": "dongthap1",
    "cantho": "cantho1",
    "lamdong": "lamdong1",
    "ltv": "laichau",
    "vovgthn": "hanoi1",
    # THVL → vinhlong
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
    """Chuẩn hóa tvg-id: tra map alias trước, fallback bỏ dấu gạch ngang."""
    clean = raw_id.strip().lower()
    return TVG_ID_MAP.get(clean, clean.replace("-", ""))


# ──────────────────────────────────────────────────────────────────────
# DỮ LIỆU KÊNH: tvg-id → (tên hiển thị, nhóm/tỉnh)
#
# Dùng một dict duy nhất _CHANNEL_DATA thay vì 3 dict riêng biệt
# (DISPLAY_NAME, TVGID_TO_PROVINCE, TVGID_TO_GROUP) để tránh trùng lặp
# key và phải giữ đồng bộ thủ công.
#
# Giá trị (display_name, tag):
#   tag = "VTV" | "HTV" | "QDVN"  → nhóm tương ứng
#   tag = <tên tỉnh>               → nhóm "Địa phương"
# ──────────────────────────────────────────────────────────────────────
_CHANNEL_DATA: Final[dict[str, tuple[str, str]]] = {
    # ── VTV ──────────────────────────────────────────────────────────
    "vtv1hd": ("VTV1", "VTV"),
    "vtv2hd": ("VTV2", "VTV"),
    "vtv3hd": ("VTV3", "VTV"),
    "vtv4hd": ("VTV4", "VTV"),
    "vtv5hd": ("VTV5", "VTV"),
    "vtv5hdtnb": ("VTV5 Tây Nam Bộ", "VTV"),
    "vtv5hdtn": ("VTV5 Tây Nguyên", "VTV"),
    "vtv6hd": ("VTV6", "VTV"),
    "vtv7hd": ("VTV7", "VTV"),
    "vtv8hd": ("VTV8", "VTV"),
    "vtv9hd": ("VTV9", "VTV"),
    "vtv10hd": ("VTV10", "VTV"),
    "vietnamtoday": ("Vietnam Today", "VTV"),
    # ── HTV / HTVC ───────────────────────────────────────────────────
    "htv1hd": ("HTV1", "HTV"),
    "htv2hd": ("HTV2", "HTV"),
    "htv3hd": ("HTV3", "HTV"),
    "htv4hd": ("HTV4", "HTV"),
    "htv5": ("HTV5", "HTV"),
    "htv7hd": ("HTV7", "HTV"),
    "htv9hd": ("HTV9", "HTV"),
    "htvthethaohd": ("HTVC Thể Thao", "HTV"),
    "htvccanachd": ("HTVC Ca Nhạc", "HTV"),
    "htvcdulichhd": ("HTVC Du Lịch", "HTV"),
    "htvcgiadinhhd": ("HTVC Gia Đình", "HTV"),
    "htvcphimhd": ("HTVC Phim", "HTV"),
    "htvcphunuhd": ("HTVC Phụ Nữ", "HTV"),
    "htvcthuanviethd": ("HTVC Thuần Việt", "HTV"),
    "htvcplushd": ("HTVC+", "HTV"),
    # ── QUỐC PHÒNG ───────────────────────────────────────────────────
    "antv": ("ANTV", "QDVN"),
    "qpvn": ("QPVN", "QDVN"),
    # ── ĐỊA PHƯƠNG — Miền Bắc ────────────────────────────────────────
    "hagiang": ("Hà Giang", "Hà Giang"),
    "tuyenquang": ("Tuyên Quang", "Tuyên Quang"),
    "caobang": ("Cao Bằng", "Cao Bằng"),
    "langson": ("Lạng Sơn", "Lạng Sơn"),
    "backan": ("Bắc Kạn", "Bắc Kạn"),
    "thainguyen": ("Thái Nguyên", "Thái Nguyên"),
    "quangninh1": ("Quảng Ninh 1", "Quảng Ninh"),
    "quangninh3": ("Quảng Ninh 3", "Quảng Ninh"),
    "bacgiang": ("Bắc Giang", "Bắc Giang"),
    "bacninh": ("Bắc Ninh", "Bắc Ninh"),
    "laocai": ("Lào Cai", "Lào Cai"),
    "yenbai": ("Yên Bái", "Yên Bái"),
    "phutho": ("Phú Thọ", "Phú Thọ"),
    "vinhphuc": ("Vĩnh Phúc", "Vĩnh Phúc"),
    "hanoi1": ("Hà Nội 1", "Hà Nội"),
    "hanoi2": ("Hà Nội 2", "Hà Nội"),
    "hoabinh": ("Hòa Bình", "Hòa Bình"),
    "sonla": ("Sơn La", "Sơn La"),
    "dienbien": ("Điện Biên", "Điện Biên"),
    "laichau": ("Lai Châu", "Lai Châu"),
    "haiphong": ("Hải Phòng", "Hải Phòng"),
    "haiphong3": ("Hải Phòng 3", "Hải Phòng"),
    "haiphongplus": ("Hải Phòng +", "Hải Phòng"),
    "haiduong": ("Hải Dương", "Hải Dương"),
    "hungyen": ("Hưng Yên", "Hưng Yên"),
    "thaibinh": ("Thái Bình", "Thái Bình"),
    "namdinh": ("Nam Định", "Nam Định"),
    "hanam": ("Hà Nam", "Hà Nam"),
    "ninhbinh": ("Ninh Bình", "Ninh Bình"),
    # ── ĐỊA PHƯƠNG — Miền Trung ──────────────────────────────────────
    "thanhhoa": ("Thanh Hóa", "Thanh Hóa"),
    "nghean": ("Nghệ An", "Nghệ An"),
    "hatinh": ("Hà Tĩnh", "Hà Tĩnh"),
    "quangbinh": ("Quảng Bình", "Quảng Bình"),
    "quangtri": ("Quảng Trị", "Quảng Trị"),
    "hue": ("Huế", "Thừa Thiên Huế"),
    "danang1": ("Đà Nẵng 1", "Đà Nẵng"),
    "danang2": ("Đà Nẵng 2", "Đà Nẵng"),
    "quangnam": ("Quảng Nam", "Quảng Nam"),
    "quangngai": ("Quảng Ngãi 1", "Quảng Ngãi"),
    "quangngai2": ("Quảng Ngãi 2", "Quảng Ngãi"),
    "binhdinh": ("Bình Định", "Bình Định"),
    "phuyen": ("Phú Yên", "Phú Yên"),
    "khanhhoa": ("Khánh Hòa", "Khánh Hòa"),
    "khanhhoa1": ("Khánh Hòa 1", "Khánh Hòa"),
    "khanhhoa2": ("Khánh Hòa 2", "Khánh Hòa"),
    "ninhthuan": ("Ninh Thuận", "Ninh Thuận"),
    "binhthuan": ("Bình Thuận", "Bình Thuận"),
    # ── ĐỊA PHƯƠNG — Tây Nguyên ──────────────────────────────────────
    "kontum": ("Kon Tum", "Kon Tum"),
    "gialai": ("Gia Lai", "Gia Lai"),
    "daklak": ("Đắk Lắk", "Đắk Lắk"),
    "daknong": ("Đắk Nông", "Đắk Nông"),
    "lamdong1": ("Lâm Đồng 1", "Lâm Đồng"),
    "lamdong2": ("Lâm Đồng 2", "Lâm Đồng"),
    # ── ĐỊA PHƯƠNG — Miền Nam ────────────────────────────────────────
    "binhphuoc": ("Bình Phước", "Bình Phước"),
    "tayninh1": ("Tây Ninh", "Tây Ninh"),
    "binhduong": ("Bình Dương", "Bình Dương"),
    "dongnai1": ("Đồng Nai 1", "Đồng Nai"),
    "dongnai2": ("Đồng Nai 2", "Đồng Nai"),
    "dongnai3": ("Đồng Nai 3", "Đồng Nai"),
    "baria": ("Bà Rịa - Vũng Tàu", "Bà Rịa - Vũng Tàu"),
    "longan": ("Long An", "Long An"),
    "tiengiang": ("Tiền Giang", "Tiền Giang"),
    "bentre": ("Bến Tre", "Bến Tre"),
    "dongthap1": ("Đồng Tháp 1", "Đồng Tháp"),
    "dongthap2": ("Đồng Tháp 2", "Đồng Tháp"),
    "vinhlong1hd": ("Vĩnh Long 1", "Vĩnh Long"),
    "vinhlong2hd": ("Vĩnh Long 2", "Vĩnh Long"),
    "vinhlong3hd": ("Vĩnh Long 3", "Vĩnh Long"),
    "vinhlong4hd": ("Vĩnh Long 4", "Vĩnh Long"),
    "vinhlong5hd": ("Vĩnh Long 5", "Vĩnh Long"),
    "travinh": ("Trà Vinh", "Trà Vinh"),
    "angiang1": ("An Giang 1", "An Giang"),
    "angiang2": ("An Giang 2", "An Giang"),
    "angiang3": ("An Giang 3", "An Giang"),
    "kiengiang": ("Kiên Giang", "Kiên Giang"),
    "cantho1": ("Cần Thơ 1", "Cần Thơ"),
    "cantho2": ("Cần Thơ 2", "Cần Thơ"),
    "cantho3": ("Cần Thơ 3", "Cần Thơ"),
    "haugiang": ("Hậu Giang", "Hậu Giang"),
    "soctrang": ("Sóc Trăng", "Sóc Trăng"),
    "baclieu": ("Bạc Liêu", "Bạc Liêu"),
    "camau": ("Cà Mau", "Cà Mau"),
}

_KNOWN_IDS: Final[frozenset[str]] = frozenset(_CHANNEL_DATA)

# ──────────────────────────────────────────────────────────────────────
# THỨ TỰ HIỂN THỊ & INDEX SORT
# ──────────────────────────────────────────────────────────────────────
_VTV_ORDER: Final[list[str]] = [
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
_HTV_ORDER: Final[list[str]] = [
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
_PROVINCE_ORDER: Final[list[str]] = [
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

_GROUP_ORDER: Final[dict[str, int]] = {"VTV": 0, "HTV": 1, "LOCAL": 2, "QDVN": 3}
_VTV_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_VTV_ORDER)}
_HTV_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_HTV_ORDER)}
_PROVINCE_IDX: Final[dict[str, int]] = {p: i for i, p in enumerate(_PROVINCE_ORDER)}

_LABEL: Final[dict[str, str]] = {
    "VTV": "VTV",
    "HTV": "HTV",
    "LOCAL": "Địa phương",
    "QDVN": "Quốc Phòng",
}

# Keywords nhận diện nhóm địa phương từ group-title
_LOCAL_KEYWORDS: Final[frozenset[str]] = frozenset(
    [
        "địa phương",
        "dia phuong",
        "tỉnh",
        "tinh",
        "thiết yếu",
        "thiet yeu",
    ]
)

# Tên kênh rác cần loại bỏ
_NOISE_NAMES: Final[frozenset[str]] = frozenset(
    [
        "SỰ KIỆN",
        "VTVPRIME",
        "FPT",
        "VOV",
        "VTVCAB",
        "SPOTV",
        "O2",
        "ĐỒNG NAI 3",
        "ĐNNRTV3",
        "VIETNAM TODAY"
    ]
)


# ──────────────────────────────────────────────────────────────────────
# DATA MODEL
# ──────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Channel:
    name: str
    url: str
    group_key: str  # "VTV" | "HTV" | "LOCAL" | "QDVN"
    province: str  # tên tỉnh (chỉ LOCAL), hoặc ""
    province_idx: int
    quality: tuple[int, float]
    tvg_id: str = ""
    tvg_logo: str = ""

    @property
    def group_label(self) -> str:
        return _LABEL[self.group_key]


# ──────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────
def quality_score(raw: str) -> tuple[int, float]:
    tier = 40
    for pat, score in _QUALITY_TIERS:
        if pat.search(raw):
            tier = score
            break
    m = _BITRATE_RE.search(raw)
    return tier, float(m.group(1)) if m else 0.0


def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=GLOBAL_TIMEOUT, headers=HTTP_HEADERS)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


def resolve_display_name(raw: str, tvg_id: str) -> str:
    """Tra cứu tên đẹp theo tvg-id; fallback: tên sạch noise."""
    if tvg_id:
        entry = _CHANNEL_DATA.get(tvg_id)
        if entry:
            return entry[0]
    s = _NOISE_RE.sub("", raw).strip()
    s = _PIPE_RE.sub("", s).strip()
    return _MULTI_SPACE_RE.sub(" ", s) or raw.strip()


def _classify(tvg_id: str, src_grp: str) -> Optional[str]:
    """
    Trả về group_key hoặc None nếu không nhận ra kênh.
    Ưu tiên: group-title → _CHANNEL_DATA → tvg-id prefix.
    """
    grp = src_grp.lower()
    if "vtv" in grp:
        return "VTV"
    if "htv" in grp:
        return "HTV"
    if any(kw in grp for kw in _LOCAL_KEYWORDS):
        return "LOCAL"
    if "quốc phòng" in grp or "quoc phong" in grp:
        return "QDVN"

    # Fallback qua tvg-id
    if tvg_id in _KNOWN_IDS:
        tag = _CHANNEL_DATA[tvg_id][1]
        return tag if tag in ("VTV", "HTV", "QDVN") else "LOCAL"
    if tvg_id.startswith("vtv"):
        return "VTV"
    if tvg_id.startswith("htv"):
        return "HTV"
    return None


def _is_noise(tvg_id: str, upper_name: str) -> bool:
    return (
        tvg_id.startswith("on")
        or upper_name.startswith("ON ")
        or any(kw in upper_name for kw in _NOISE_NAMES)
    )


# ──────────────────────────────────────────────────────────────────────
# PARSER
# ──────────────────────────────────────────────────────────────────────
def parse_m3u(text: str) -> list[Channel]:
    channels: list[Channel] = []
    current_extinf: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            current_extinf = line
            continue
        if line.startswith("#") or not current_extinf:
            continue

        extinf_line, current_extinf = current_extinf, None
        url = line

        m_id = _TVG_ID_RE.search(extinf_line)
        m_logo = _TVG_LOGO_RE.search(extinf_line)
        m_grp = _GROUP_TITLE_RE.search(extinf_line)

        tvg_id = normalize_tvg_id(m_id.group(1)) if m_id else ""
        tvg_logo = m_logo.group(1).strip() if m_logo else ""
        src_grp = m_grp.group(1).strip() if m_grp else ""
        raw_name = extinf_line.split(",", 1)[-1].strip() if "," in extinf_line else ""

        if not raw_name or _is_noise(tvg_id, raw_name.upper()):
            continue

        group_key = _classify(tvg_id, src_grp)
        if group_key is None:
            continue

        province = province_idx = 0
        if group_key == "LOCAL":
            entry = _CHANNEL_DATA.get(tvg_id)
            if not entry:
                continue
            province = entry[1]
            province_idx = _PROVINCE_IDX.get(province, 999)
        else:
            province = ""

        channels.append(
            Channel(
                name=resolve_display_name(raw_name, tvg_id),
                url=url,
                group_key=group_key,
                province=province,
                province_idx=province_idx,
                quality=quality_score(raw_name),
                tvg_id=tvg_id,
                tvg_logo=tvg_logo,
            )
        )

    return channels


# ──────────────────────────────────────────────────────────────────────
# DEDUP & MERGE
# Gộp pick_best + merge_sources thành một hàm duy nhất:
# xử lý trong một pass, dedup cả theo tên lẫn URL.
# ──────────────────────────────────────────────────────────────────────
def merge_sources(lists: list[list[Channel]]) -> list[Channel]:
    """Gộp nhiều nguồn: quality-wins, dedup URL xuyên nguồn."""
    best: dict[str, Channel] = {}
    seen_urls: set[str] = set()

    for ch in (ch for lst in lists for ch in lst):
        url = ch.url.strip()
        if url in seen_urls:
            continue
        key = _dedup_key(ch.name)
        existing = best.get(key)
        if existing is None or ch.quality > existing.quality:
            if existing is not None:
                seen_urls.discard(existing.url.strip())
            best[key] = ch
            seen_urls.add(url)

    return list(best.values())


# ──────────────────────────────────────────────────────────────────────
# SORT
# ──────────────────────────────────────────────────────────────────────
def sort_channels(channels: list[Channel]) -> list[Channel]:
    def key(ch: Channel) -> tuple:
        g = _GROUP_ORDER[ch.group_key]
        if ch.group_key == "VTV":
            return (g, _VTV_IDX.get(_norm_key(ch.name), 999), ch.name)
        if ch.group_key == "HTV":
            return (g, _HTV_IDX.get(_norm_key(ch.name), 999), ch.name)
        if ch.group_key == "LOCAL":
            return (g, ch.province_idx, ch.name)
        return (g, 0, ch.name)  # QDVN

    return sorted(channels, key=key)


# ──────────────────────────────────────────────────────────────────────
# OUTPUT
# ──────────────────────────────────────────────────────────────────────
def write_m3u(channels: list[Channel], path: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U url-tvg="{EPG_URL}"\n')
            f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            for src in SOURCES:
                f.write(f"#EXTM3U-SOURCE:{src}\n")
            for ch in channels:
                f.write(
                    f'#EXTINF:-1 tvg-id="{ch.tvg_id}" '
                    f'tvg-logo="{ch.tvg_logo}" '
                    f'group-title="{ch.group_label}",{ch.name}\n'
                    f"{ch.url}\n"
                )
        print(f"✅  Đã ghi {len(channels)} kênh → {path}")
    except IOError as e:
        print(f"❌  Lỗi ghi file {path}: {e}", file=sys.stderr)
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"📡  EPG: {EPG_URL}")

    processed: list[list[Channel]] = []
    for idx, src in enumerate(SOURCES, 1):
        print(f"\n[{idx}/{len(SOURCES)}] Tải: {src}")
        text = fetch(src)
        if not text or "#EXTM3U" not in text:
            print("  ⚠  Bỏ qua (không phải M3U hợp lệ)")
            continue
        parsed = parse_m3u(text)
        print(f"     Nhận diện {len(parsed)} kênh TV")
        if parsed:
            processed.append(parsed)

    if not processed:
        print("❌  Không có nguồn nào hợp lệ.", file=sys.stderr)
        sys.exit(1)

    print("\n🔀  Gộp & dedup…")
    final = sort_channels(merge_sources(processed))

    gcnt = Counter(ch.group_key for ch in final)
    print(
        f"📋  VTV: {gcnt['VTV']} | HTV: {gcnt['HTV']} "
        f"| Địa phương: {gcnt['LOCAL']} "
        f"| Quốc Phòng: {gcnt['QDVN']} "
        f"| Tổng: {len(final)}"
    )

    write_m3u(final, OUTPUT_FILE)


if __name__ == "__main__":
    main()
