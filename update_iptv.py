#!/usr/bin/env python3
"""
IPTV Auto-updater
- Nguồn ưu tiên: 1.org.vn/vmttv (nếu tải được)
- Fallback:      blvbatman & ntd249 trên GitHub (luôn tải được)
- Chỉ lấy kênh TV (VTV, HTV, địa phương) — bỏ phim, radio, quốc tế
- Tên kênh đẹp theo bảng DISPLAY_NAME (ánh xạ từ tvg-id)
- Địa phương gom 1 nhóm, sắp xếp Bắc → Nam
- Output: http-iptv.m3u
"""

import re
import sys
import concurrent.futures
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────
# SOURCES  (index 0 = ưu tiên cao nhất)
# ──────────────────────────────────────────────────────────────────────
SOURCES = [
    "https://1.org.vn/vmttv",
    "https://raw.githubusercontent.com/blvbatman/iptv/refs/heads/main/iptv.m3u",
    "https://raw.githubusercontent.com/ntd249/ntdiptv/main/fptudp",
]

OUTPUT_FILE        = "http-iptv.m3u"
LINK_CHECK_TIMEOUT = 8
LINK_CHECK_WORKERS = 40

# ──────────────────────────────────────────────────────────────────────
# BẢNG TÊN ĐẸP  tvg-id → tên hiển thị
# ──────────────────────────────────────────────────────────────────────
DISPLAY_NAME: dict[str, str] = {
    # VTV
    "vtv1hd":      "VTV1",
    "vtv2hd":      "VTV2",
    "vtv3hd":      "VTV3",
    "vtv4hd":      "VTV4",
    "vtv5hd":      "VTV5",
    "vtv5hdtnb":   "VTV5 Tây Nam Bộ",
    "vtv5hdtn":    "VTV5 Tây Nguyên",
    "vtv6hd":      "VTV6",   "vtv6": "VTV6",
    "vtv7hd":      "VTV7",
    "vtv8hd":      "VTV8",
    "vtv9hd":      "VTV9",
    "vtv10hd":     "VTV10",  "vtv10": "VTV10",
    "vietnamtoday":"Vietnam Today",
    # HTV / HTVC
    "htv1":          "HTV1",
    "htv2hd":        "HTV2",
    "htv3":          "HTV3",
    "htv4":          "HTV4",
    "htv4hd":        "HTV4",
    "htv5":          "HTV5",
    "htv7hd":        "HTV7",
    "htv9hd":        "HTV9",
    "htvthethaohd":  "HTVC Thể Thao",
    "htvccanhachd":  "HTVC Ca Nhạc",
    "htvcdulichhd":  "HTVC Du Lịch",
    "htvcgiadinhhd": "HTVC Gia Đình",
    "htvcphimhd":    "HTVC Phim",
    "htvcphunuhd":   "HTVC Phụ Nữ",
    "htvcthuanviet": "HTVC Thuần Việt",
    "htvcplushd":    "HTVC+",
    # Địa phương — Miền Bắc
    "hagiang":    "Hà Giang TV",
    "laichau":    "Lai Châu TV",        "ltv": "Lai Châu TV",
    "dienbien":   "Điện Biên TV",
    "laocai":     "Lào Cai TV",
    "yenbai":     "Yên Bái TV",
    "sonla":      "Sơn La TV",
    "hoabinh":    "Hòa Bình TV",
    "phutho":     "Phú Thọ TV",
    "vinhphuc":   "Vĩnh Phúc TV",
    "tuyenquang": "Tuyên Quang TV",
    "backan":     "Bắc Kạn TV",
    "thainguyen": "Thái Nguyên TV",
    "caobang":    "Cao Bằng TV",
    "langson":    "Lạng Sơn TV",
    "quangninh":  "Quảng Ninh TV",
    "quangninh1": "Quảng Ninh TV1",
    "quangninh3": "Quảng Ninh TV3",
    "bacgiang":   "Bắc Giang TV",
    "bacninh":    "Bắc Ninh TV",
    "hanoi1":     "Hà Nội TV1",
    "hanoi2":     "Hà Nội TV2",
    "vovgthn":    "VOV Giao Thông HN",
    "haiphong":   "Hải Phòng TV",
    "haiphong3":  "Hải Phòng TV3",
    "haiphongplus":"Hải Phòng TV+",
    "haiduong":   "Hải Dương TV",
    "hungyen":    "Hưng Yên TV",
    "thaibinh":   "Thái Bình TV",
    "namdinh":    "Nam Định TV",
    "hanam":      "Hà Nam TV",
    "ninhbinh":   "Ninh Bình TV",
    # Địa phương — Miền Trung
    "thanhhoa":   "Thanh Hóa TV",
    "nghean":     "Nghệ An TV",
    "hatinh":     "Hà Tĩnh TV",
    "quangbinh":  "Quảng Bình TV",
    "quangtri":   "Quảng Trị TV",
    "hue":        "Huế TV",
    "danang1":    "Đà Nẵng TV1",
    "danang2":    "Đà Nẵng TV2",
    "quangnam":   "Quảng Nam TV",
    "quangngai":  "Quảng Ngãi TV1",   "quangngai1": "Quảng Ngãi TV1",
    "quangngai2": "Quảng Ngãi TV2",
    "binhdinh":   "Bình Định TV",
    "phuyen":     "Phú Yên TV",
    "khanhhoa":   "Khánh Hòa TV",
    "khanhhoa1":  "Khánh Hòa TV1",
    "ninhthuan":  "Ninh Thuận TV",
    "binhthuan":  "Bình Thuận TV",
    # Địa phương — Tây Nguyên
    "kontum":     "Kon Tum TV",
    "gialai":     "Gia Lai TV",
    "daklak":     "Đắk Lắk TV",
    "daknong":    "Đắk Nông TV",
    "lamdong":    "Lâm Đồng TV1",   "lamdong1": "Lâm Đồng TV1",
    "lamdong2":   "Lâm Đồng TV2",
    "lamdong3":   "Lâm Đồng TV3",
    # Địa phương — Miền Nam
    "binhphuoc":  "Bình Phước TV",
    "tayninh1":   "Tây Ninh TV",    "tayninhtv": "Tây Ninh TV",
    "binhduong":  "Bình Dương TV",
    "dongnai1":   "Đồng Nai TV1",
    "dongnai2":   "Đồng Nai TV2",
    "dongnai3":   "Đồng Nai TV3",
    "baria":      "Bà Rịa - Vũng Tàu TV",
    "longan":     "Long An TV",
    "tiengiang":  "Tiền Giang TV",
    "bentre":     "Bến Tre TV",
    "dongthap":   "Đồng Tháp TV1",  "dongthap1": "Đồng Tháp TV1",
    "dongthap2":  "Đồng Tháp TV2",
    "vinhlong1hd":"THVL1",
    "vinhlong2hd":"THVL2",
    "vinhlong3hd":"THVL3",
    "vinhlong4hd":"THVL4",
    "vinhlong5hd":"THVL5",
    "thvl1hd":    "THVL1",   "thvl1": "THVL1",
    "thvl2hd":    "THVL2",   "thvl2": "THVL2",
    "thvl3hd":    "THVL3",   "thvl3": "THVL3",
    "thvl4hd":    "THVL4",   "thvl4": "THVL4",
    "thvl5hd":    "THVL5",   "thvl5": "THVL5",
    "travinh":    "Trà Vinh TV",
    "angiang1":   "An Giang TV1",
    "angiang2":   "An Giang TV2",
    "angiang3":   "An Giang TV3",
    "kiengiang":  "Kiên Giang TV",
    "cantho":     "Cần Thơ TV",
    "cantho1":    "Cần Thơ TV1",
    "cantho2":    "Cần Thơ TV2",
    "cantho3":    "Cần Thơ TV3",
    "haugiang":   "Hậu Giang TV",
    "soctrang":   "Sóc Trăng TV",
    "baclieu":    "Bạc Liêu TV",
    "camau":      "Cà Mau TV",
}

# ──────────────────────────────────────────────────────────────────────
# Nhận diện group từ group-title của từng nguồn
# → chuẩn hóa thành: "VTV" | "HTV" | tên_tỉnh | None (bỏ)
# ──────────────────────────────────────────────────────────────────────

# Các group-title được giữ lại và ánh xạ sang tên chuẩn
GROUP_MAP: dict[str, str] = {
    # Nguồn 1.org.vn
    "VTV": "VTV",
    "HTV": "HTV",
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
    # Nguồn blvbatman
    "Địa Phương": "_LOCAL_",   # sẽ phân loại qua tvg-id
    "Quốc Phòng": "Quốc Phòng",
    # Nguồn ntd249
    "HTV/HTVC": "HTV",
    "Địa phương (HD)": "_LOCAL_",
    "Địa phương (SD)": "_LOCAL_",
    "Kênh TH Thiết yếu": "_LOCAL_",
}

# tvg-id → tên tỉnh (dùng khi group-title = _LOCAL_)
TVGID_TO_PROVINCE: dict[str, str] = {
    "hagiang": "Hà Giang",
    "tuyenquang": "Tuyên Quang",
    "caobang": "Cao Bằng",
    "langson": "Lạng Sơn",
    "backan": "Bắc Kạn",
    "thainguyen": "Thái Nguyên",
    "quangninh": "Quảng Ninh",   "quangninh1": "Quảng Ninh",   "quangninh3": "Quảng Ninh",
    "bacgiang": "Bắc Giang",
    "bacninh": "Bắc Ninh",
    "laocai": "Lào Cai",
    "yenbai": "Yên Bái",
    "phutho": "Phú Thọ",
    "vinhphuc": "Vĩnh Phúc",
    "hanoi1": "Hà Nội",   "hanoi2": "Hà Nội",   "vovgthn": "Hà Nội",
    "hoabinh": "Hòa Bình",
    "sonla": "Sơn La",
    "dienbien": "Điện Biên",
    "laichau": "Lai Châu",   "ltv": "Lai Châu",
    "haiphong": "Hải Phòng",   "haiphong3": "Hải Phòng",   "haiphongplus": "Hải Phòng",
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
    "danang1": "Đà Nẵng",   "danang2": "Đà Nẵng",
    "quangnam": "Quảng Nam",
    "quangngai": "Quảng Ngãi",   "quangngai1": "Quảng Ngãi",   "quangngai2": "Quảng Ngãi",
    "binhdinh": "Bình Định",
    "phuyen": "Phú Yên",
    "khanhhoa": "Khánh Hòa",   "khanhhoa1": "Khánh Hòa",
    "ninhthuan": "Ninh Thuận",
    "binhthuan": "Bình Thuận",
    "kontum": "Kon Tum",
    "gialai": "Gia Lai",
    "daklak": "Đắk Lắk",
    "daknong": "Đắk Nông",
    "lamdong": "Lâm Đồng",   "lamdong1": "Lâm Đồng",   "lamdong2": "Lâm Đồng",   "lamdong3": "Lâm Đồng",
    "binhphuoc": "Bình Phước",
    "tayninh1": "Tây Ninh",   "tayninhtv": "Tây Ninh",
    "binhduong": "Bình Dương",
    "dongnai1": "Đồng Nai",   "dongnai2": "Đồng Nai",   "dongnai3": "Đồng Nai",
    "baria": "Bà Rịa - Vũng Tàu",
    "longan": "Long An",
    "tiengiang": "Tiền Giang",
    "bentre": "Bến Tre",
    "dongthap": "Đồng Tháp",   "dongthap1": "Đồng Tháp",   "dongthap2": "Đồng Tháp",
    "vinhlong1hd": "Vĩnh Long",   "vinhlong2hd": "Vĩnh Long",
    "vinhlong3hd": "Vĩnh Long",   "vinhlong4hd": "Vĩnh Long",   "vinhlong5hd": "Vĩnh Long",
    "thvl1hd": "Vĩnh Long",   "thvl2hd": "Vĩnh Long",   "thvl3hd": "Vĩnh Long",
    "thvl4hd": "Vĩnh Long",   "thvl5hd": "Vĩnh Long",
    "travinh": "Trà Vinh",
    "angiang1": "An Giang",   "angiang2": "An Giang",   "angiang3": "An Giang",
    "kiengiang": "Kiên Giang",
    "cantho": "Cần Thơ",   "cantho1": "Cần Thơ",   "cantho2": "Cần Thơ",   "cantho3": "Cần Thơ",
    "haugiang": "Hậu Giang",
    "soctrang": "Sóc Trăng",
    "baclieu": "Bạc Liêu",
    "camau": "Cà Mau",
    # hitv/youtv — không phải địa phương → bỏ
    "hitv": None,
    "youtv": None,
}

# Thứ tự tỉnh Bắc → Nam
LOCAL_PROVINCE_ORDER: list[str] = [
    "Hà Giang", "Tuyên Quang", "Cao Bằng", "Lạng Sơn", "Bắc Kạn",
    "Thái Nguyên", "Quảng Ninh", "Bắc Giang", "Bắc Ninh",
    "Lào Cai", "Yên Bái", "Phú Thọ", "Vĩnh Phúc",
    "Hà Nội", "Hòa Bình", "Sơn La", "Điện Biên", "Lai Châu",
    "Hải Phòng", "Hải Dương", "Hưng Yên", "Thái Bình",
    "Nam Định", "Hà Nam", "Ninh Bình",
    "Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị",
    "Thừa Thiên Huế",
    "Đà Nẵng", "Quảng Nam", "Quảng Ngãi", "Bình Định",
    "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Bình Thuận",
    "Kon Tum", "Gia Lai", "Đắk Lắk", "Đắk Nông", "Lâm Đồng",
    "Bình Phước", "Tây Ninh", "Bình Dương", "Đồng Nai",
    "Bà Rịa - Vũng Tàu", "Long An",
    "Tiền Giang", "Bến Tre", "Đồng Tháp", "Vĩnh Long", "Trà Vinh",
    "An Giang", "Kiên Giang", "Cần Thơ",
    "Hậu Giang", "Sóc Trăng", "Bạc Liêu", "Cà Mau",
    "Quốc Phòng",  # ANTV/QPVN
]
_PROVINCE_IDX: dict[str, int] = {p: i for i, p in enumerate(LOCAL_PROVINCE_ORDER)}

GROUP_LABEL_LOCAL = "Địa phương"

# ──────────────────────────────────────────────────────────────────────
# Quality
# ──────────────────────────────────────────────────────────────────────
_QUALITY_TIERS = [
    (re.compile(r"\b8k\b",                re.I), 80),
    (re.compile(r"\b4k\b|\buhd\b",        re.I), 70),
    (re.compile(r"\bfhd\b|\bfull\s*hd\b", re.I), 60),
    (re.compile(r"\bhd\b",                re.I), 50),
    (re.compile(r"\bsd\b",                re.I), 20),
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
# Data class
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Channel:
    name:         str
    url:          str
    group_label:  str   # "VTV" | "HTV" | "Địa phương"
    group_order:  int   # 0=VTV, 1=HTV, 2=local
    province:     str   # tên tỉnh (để sort local)
    province_idx: int
    quality:      tuple[int, float]
    tvg_id:       str = ""
    tvg_logo:     str = ""

def _natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def _dedup_key(name: str) -> str:
    return re.sub(r"[\s\-\._]+", "", name.lower())

# ──────────────────────────────────────────────────────────────────────
# Parse M3U
# ──────────────────────────────────────────────────────────────────────
_NOISE_RE = re.compile(
    r"[\s\-–|]*\b(?:fhd|full\s*hd|hd|sd|4k|8k|uhd"
    r"|h\.?264|h\.?265|hevc|avc"
    r"|\d+(?:\.\d+)?\s*mb(?:ps)?"
    r"|\d+\s*kbps"
    r")\b.*$",
    re.IGNORECASE,
)

def resolve_display_name(raw: str, tvg_id: str) -> str:
    """Tên đẹp: ưu tiên bảng DISPLAY_NAME, fallback strip tên gốc."""
    if tvg_id and tvg_id in DISPLAY_NAME:
        return DISPLAY_NAME[tvg_id]
    s = _NOISE_RE.sub("", raw).strip()
    # Bỏ phần " | Tỉnh" nếu còn sót
    s = re.sub(r"\s*\|.*$", "", s).strip()
    return re.sub(r"\s{2,}", " ", s) or raw.strip()

def parse_m3u(text: str) -> list[Channel]:
    channels: list[Channel] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = line
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

            tvg_id_m   = re.search(r'tvg-id="([^"]*)"',    extinf)
            tvg_logo_m = re.search(r'tvg-logo="([^"]*)"',  extinf)
            grp_m      = re.search(r'group-title="([^"]*)"', extinf)
            raw_name   = extinf.split(",", 1)[-1].strip() if "," in extinf else ""

            if not raw_name:
                i += 1
                continue

            tvg_id   = (tvg_id_m.group(1)   if tvg_id_m   else "").strip()
            tvg_logo = (tvg_logo_m.group(1) if tvg_logo_m else "").strip()
            src_grp  = (grp_m.group(1)      if grp_m      else "").strip()

            # ── Ánh xạ group-title → nhóm chuẩn ──────────────────
            mapped_grp = GROUP_MAP.get(src_grp)
            if mapped_grp is None:
                i += 1
                continue   # group không hợp lệ → bỏ

            # Nếu group là "_LOCAL_" → xác định tỉnh qua tvg-id
            if mapped_grp == "_LOCAL_":
                province = TVGID_TO_PROVINCE.get(tvg_id)
                if province is None:
                    i += 1
                    continue   # không nhận ra tvg-id → bỏ
                if province is None or province == "":
                    i += 1
                    continue
            else:
                province = mapped_grp  # với group tỉnh trực tiếp từ 1.org.vn

            # ── Xác định nhóm hiển thị ────────────────────────────
            if mapped_grp == "VTV":
                g_label   = "VTV"
                g_order   = 0
                prov_idx  = 0
            elif mapped_grp == "HTV":
                g_label   = "HTV"
                g_order   = 1
                prov_idx  = 0
            else:
                # province = tên tỉnh
                g_label   = GROUP_LABEL_LOCAL
                g_order   = 2
                prov_idx  = _PROVINCE_IDX.get(province, 999)

            quality   = quality_score(raw_name)
            disp_name = resolve_display_name(raw_name, tvg_id)

            channels.append(Channel(
                name         = disp_name,
                url          = url,
                group_label  = g_label,
                group_order  = g_order,
                province     = province if g_order == 2 else "",
                province_idx = prov_idx,
                quality      = quality,
                tvg_id       = tvg_id,
                tvg_logo     = tvg_logo,
            ))
        i += 1
    return channels

# ──────────────────────────────────────────────────────────────────────
# Fetch
# ──────────────────────────────────────────────────────────────────────
def fetch_source(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        if len(r.text) < 100 or "#EXTM3U" not in r.text[:200]:
            print(f"  ⚠  Phản hồi không phải M3U từ {url}", file=sys.stderr)
            return None
        return r.text
    except Exception as e:
        print(f"  ⚠  Không tải được {url}: {e}", file=sys.stderr)
        return None

# ──────────────────────────────────────────────────────────────────────
# Check link
# ──────────────────────────────────────────────────────────────────────
def _is_live(url: str) -> bool:
    scheme = url.split("://")[0].lower() if "://" in url else "http"
    if scheme not in ("http", "https"):
        return True
    try:
        r = requests.head(
            url, timeout=LINK_CHECK_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
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
            try:   results[u] = fut.result()
            except: results[u] = False
            done += 1
            if done % 20 == 0 or done == len(unique):
                print(f"     Đã check {done}/{len(unique)}, sống: {sum(results.values())}", end="\r")
    print()
    return results

# ──────────────────────────────────────────────────────────────────────
# Chọn link tốt nhất
# ──────────────────────────────────────────────────────────────────────
def pick_best(channels: list[Channel]) -> list[Channel]:
    if not channels:
        return []
    groups: dict[str, list[Channel]] = defaultdict(list)
    for ch in channels:
        groups[_dedup_key(ch.name)].append(ch)
    for key in groups:
        groups[key].sort(key=lambda c: (-c.quality[0], -c.quality[1], len(c.url)))

    all_urls = [ch.url for chs in groups.values() for ch in chs]
    print(f"     Kiểm tra {len(all_urls)} link ({len(groups)} kênh)…")
    live_map = check_all(all_urls)

    dead = sum(1 for v in live_map.values() if not v)
    print(f"     ✅ {sum(live_map.values())}/{len(live_map)} link còn sống"
          + (f", loại {dead} link chết" if dead else ""))

    result: list[Channel] = []
    skipped = 0
    for key, variants in groups.items():
        best = next((ch for ch in variants if live_map.get(ch.url, False)), None)
        if best:
            result.append(best)
        else:
            skipped += 1
    if skipped:
        print(f"     ⚠  Bỏ qua {skipped} kênh (tất cả link chết)")
    return result

# ──────────────────────────────────────────────────────────────────────
# Gộp nhiều nguồn (nguồn trước ưu tiên)
# ──────────────────────────────────────────────────────────────────────
def merge_sources(source_lists: list[list[Channel]]) -> list[Channel]:
    seen: dict[str, Channel] = {}
    for channels in source_lists:
        for ch in channels:
            key = _dedup_key(ch.name)
            if key not in seen:
                seen[key] = ch
    return list(seen.values())

# ──────────────────────────────────────────────────────────────────────
# Sắp xếp
# ──────────────────────────────────────────────────────────────────────
# Thứ tự cố định cho VTV (index = vị trí; kênh không có trong list → xuống cuối)
VTV_FIXED_ORDER = [
    "VTV1", "VTV2", "VTV3", "VTV4", "VTV5",
    "VTV5 Tây Nam Bộ", "VTV5 Tây Nguyên",
    "VTV6", "VTV7", "VTV8", "VTV9", "VTV10",
]
# Thứ tự cố định cho HTV
HTV_FIXED_ORDER = [
    "HTV1", "HTV2", "HTV3", "HTV4", "HTV5", "HTV7", "HTV9",
    "HTVC Thể Thao", "HTVC Ca Nhạc", "HTVC Du Lịch",
    "HTVC Gia Đình", "HTVC Phim", "HTVC Phụ Nữ",
    "HTVC Thuần Việt", "HTVC+",
]

_VTV_IDX = {name: i for i, name in enumerate(VTV_FIXED_ORDER)}
_HTV_IDX = {name: i for i, name in enumerate(HTV_FIXED_ORDER)}

def _channel_sort_key(ch: "Channel"):
    if ch.group_order == 0:   # VTV
        return (0, 0, _VTV_IDX.get(ch.name, 999), ch.name)
    elif ch.group_order == 1:  # HTV
        return (1, 0, _HTV_IDX.get(ch.name, 999), ch.name)
    else:                      # Địa phương
        return (2, ch.province_idx, 0, ch.name)

def sort_channels(channels: list[Channel]) -> list[Channel]:
    return sorted(channels, key=_channel_sort_key)

# ──────────────────────────────────────────────────────────────────────
# Xuất M3U
# ──────────────────────────────────────────────────────────────────────
def write_m3u(channels: list[Channel], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in channels:
            attrs = (f'tvg-id="{ch.tvg_id}" '
                     f'tvg-logo="{ch.tvg_logo}" '
                     f'group-title="{ch.group_label}"')
            f.write(f'#EXTINF:-1 {attrs},{ch.name}\n')
            f.write(ch.url + "\n")
    print(f"✅  Đã ghi {len(channels)} kênh vào {path}")

# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
_TIER_LABEL = {80: "8K", 70: "4K", 60: "FHD", 50: "HD", 40: "~HD", 20: "SD"}

def main():
    processed: list[list[Channel]] = []

    for idx, src in enumerate(SOURCES, 1):
        print(f"\n[{idx}/{len(SOURCES)}] Tải nguồn: {src}")
        text = fetch_source(src)
        if not text:
            processed.append([])
            continue
        parsed = parse_m3u(text)
        print(f"     Nhận diện {len(parsed)} kênh TV hợp lệ")
        if not parsed:
            processed.append([])
            continue
        best = pick_best(parsed)
        print(f"     → Giữ lại {len(best)} kênh (link còn sống)")
        processed.append(best)

    print("\n🔀  Gộp kênh từ các nguồn (nguồn 1 ưu tiên)…")
    merged = merge_sources(processed)

    print("📋  Sắp xếp VTV → HTV → Địa phương (Bắc→Nam)…")
    final = sort_channels(merged)

    gcnt = Counter(ch.group_label for ch in final)
    print(f"     VTV: {gcnt['VTV']} | HTV: {gcnt['HTV']} "
          f"| Địa phương: {gcnt[GROUP_LABEL_LOCAL]} | Tổng: {len(final)}")

    write_m3u(final, OUTPUT_FILE)

    # In danh sách
    print("\n📺  Danh sách kênh:")
    cur = None
    for i, ch in enumerate(final, 1):
        if ch.group_label != cur:
            cur = ch.group_label
            print(f"\n  ── {cur} ({gcnt[cur]} kênh) ──")
        tier = _TIER_LABEL.get(ch.quality[0], "?")
        mbps = f" {ch.quality[1]:.0f}M" if ch.quality[1] else ""
        prov = f" [{ch.province}]" if ch.province else ""
        print(f"  {i:3}. {ch.name:<35} [{tier}{mbps}]{prov}")

if __name__ == "__main__":
    main()