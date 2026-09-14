#!/usr/bin/env python3
"""
scraper.py - Cào KQXS từ minhngoc.net
Repo: xsktvn

- Chỉ cào từ HÔM QUA lùi về 365 ngày (bỏ qua hôm nay).
- Chỉ lấy box có NGÀY TRONG BOX khớp với ngày cần cào.
- Lọc đài theo lịch xổ số của thứ trong tuần.
- Miền Bắc: dùng tên đài từ lịch (vì HTML không có tên đài).
"""
import os
import json
import re
import time
from datetime import datetime, timedelta
from unicodedata import normalize as uni_normalize

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

OUTPUT_DIR = "data"
DAYS_TO_SCRAPE = 623


# ============ LỊCH XỔ SỐ THEO THỨ ============

STATIONS_BY_WEEKDAY_MN = {
    0: ["TP. HCM", "Đồng Tháp", "Cà Mau"],
    1: ["Bến Tre", "Vũng Tàu", "Bạc Liêu"],
    2: ["Đồng Nai", "Cần Thơ", "Sóc Trăng"],
    3: ["Tây Ninh", "An Giang", "Bình Thuận"],
    4: ["Vĩnh Long", "Bình Dương", "Trà Vinh"],
    5: ["TP. HCM", "Long An", "Bình Phước", "Hậu Giang"],
    6: ["Tiền Giang", "Kiên Giang", "Đà Lạt"],
}

STATIONS_BY_WEEKDAY_MT = {
    0: ["Phú Yên", "Huế"],
    1: ["Đắk Lắk", "Quảng Nam"],
    2: ["Đà Nẵng", "Khánh Hòa"],
    3: ["Bình Định", "Quảng Trị", "Quảng Bình"],
    4: ["Gia Lai", "Ninh Thuận"],
    5: ["Đà Nẵng", "Quảng Ngãi", "Đắk Nông"],
    6: ["Kon Tum", "Huế", "Khánh Hòa"],
}

STATIONS_BY_WEEKDAY_MB = {
    0: "Hà Nội",
    1: "Quảng Ninh",
    2: "Bắc Ninh",
    3: "Hà Nội",
    4: "Hải Phòng",
    5: "Nam Định",
    6: "Thái Bình",
}

WEEKDAY_NAMES = [
    "Thứ Hai", "Thứ Ba", "Thứ Tư",
    "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật",
]


# ============ HÀM TIỆN ÍCH ============

def fetch_html(date_str, max_retry=3):
    url = f"https://www.minhngoc.net/ket-qua-xo-so/{date_str}.html"
    for attempt in range(max_retry):
        try:
            print(f"→ Đang tải: {url} (lần {attempt+1})")
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except Exception as e:
            print(f"  ⚠ Lỗi lần {attempt+1}: {e}")
            time.sleep(5)
    raise Exception(f"Không tải được sau {max_retry} lần")


def extract_numbers(td):
    divs = td.find_all("div", recursive=False)
    if not divs:
        text = td.get_text(strip=True)
        if not text:
            return []
        nums = re.split(r"\s+", text)
        return [n for n in nums if n]
    return [d.get_text(strip=True) for d in divs if d.get_text(strip=True)]


def normalize_name(name):
    name = name.lower().strip()
    name = uni_normalize("NFD", name)
    name = "".join(c for c in name if uni_normalize("NFC", c) != c or c in "đĐ")
    name = name.replace("đ", "d")
    name = re.sub(r"\s+", " ", name)
    return name


def extract_station_prizes(rt):
    """Trích xuất 1 đài miền Nam/Trung từ table.rightcl."""
    tinh_td = rt.select_one("td.tinh")
    if not tinh_td:
        return None
    name = tinh_td.get_text(strip=True)
    if not name:
        return None

    matinh_td = rt.select_one("td.matinh")
    code = matinh_td.get_text(strip=True) if matinh_td else ""

    prizes = []
    prize_order = [
        ("giai8", "Giải tám"),
        ("giai7", "Giải bảy"),
        ("giai6", "Giải sáu"),
        ("giai5", "Giải năm"),
        ("giai4", "Giải tư"),
        ("giai3", "Giải ba"),
        ("giai2", "Giải nhì"),
        ("giai1", "Giải nhất"),
        ("giaidb", "Giải ĐB"),
    ]

    for cls, label in prize_order:
        td = rt.select_one(f"td.{cls}")
        if not td:
            continue
        nums = extract_numbers(td)
        if nums:
            prizes.append({"label": label, "numbers": nums})

    if not prizes:
        return None

    return {"name": name, "code": code, "prizes": prizes}


def extract_mien_bac_prizes(table, station_name):
    """
    Trích xuất giải miền Bắc.
    station_name: tên đài từ lịch (Hà Nội / Quảng Ninh / ...).
    """
    name = station_name
    code = ""

    # Ký hiệu trúng ĐB (dùng làm code)
    loaive = table.select_one(".loaive_content")
    if loaive:
        code = loaive.get_text(strip=True)

    prizes = []
    prize_order = [
        ("giaidb", "Giải ĐB"),
        ("giai1", "Giải nhất"),
        ("giai2", "Giải nhì"),
        ("giai3", "Giải ba"),
        ("giai4", "Giải tư"),
        ("giai5", "Giải năm"),
        ("giai6", "Giải sáu"),
        ("giai7", "Giải bảy"),
    ]

    for cls, label in prize_order:
        td = table.select_one(f"td.{cls}")
        if not td:
            continue
        nums = extract_numbers(td)
        if nums:
            prizes.append({"label": label, "numbers": nums})

    if not prizes:
        return None

    return {"name": name, "code": code, "prizes": prizes}


# ============ PARSE TRANG ============

def parse_page(html, date_str):
    """
    Chỉ lấy box có NGÀY TRONG BOX khớp với date_str.
    """
    soup = BeautifulSoup(html, "lxml")

    d, m, y = date_str.split("-")
    target_dmy_slash = f"{d}/{m}/{y}"
    target_dmy_dash = f"{d}-{m}-{y}"

    dt = datetime(int(y), int(m), int(d))
    weekday = dt.weekday()
    weekday_name = WEEKDAY_NAMES[weekday]

    allowed_mn = {normalize_name(s) for s in STATIONS_BY_WEEKDAY_MN.get(weekday, [])}
    allowed_mt = {normalize_name(s) for s in STATIONS_BY_WEEKDAY_MT.get(weekday, [])}
    allowed_mb = STATIONS_BY_WEEKDAY_MB.get(weekday, "")

    print(f"→ Ngày {date_str} ({weekday_name})")
    print(f"   MN: {STATIONS_BY_WEEKDAY_MN.get(weekday, [])}")
    print(f"   MT: {STATIONS_BY_WEEKDAY_MT.get(weekday, [])}")
    print(f"   MB: {allowed_mb}")

    stations_nam = []
    stations_trung = []
    station_bac = None

    all_boxes = soup.select("div.box_kqxs")
    print(f"→ Tìm thấy {len(all_boxes)} box_kqxs trên trang")

    matched = 0
    for box in all_boxes:
        box_date = None

        # CÁCH 1: Tìm ngày trong tiêu đề box
        title_div = box.select_one(".top .title")
        if title_div:
            for a in title_div.find_all("a"):
                text = a.get_text(strip=True)
                if text in (target_dmy_slash, target_dmy_dash):
                    box_date = text
                    break

        # CÁCH 2: Tìm ngày trong .ngay (bảng)
        if box_date is None:
            ngay_span = box.select_one(".ngay")
            if ngay_span:
                text = ngay_span.get_text(strip=True)
                if target_dmy_slash in text or target_dmy_dash in text:
                    box_date = target_dmy_slash

        if box_date is None:
            continue

        matched += 1
        title_text = (title_div.get_text(strip=True).lower() if title_div else "")

        if "miền nam" in title_text or "mien nam" in title_text:
            table = box.select_one("table.bkqmiennam")
            if not table:
                continue
            if "bkqmienbac" in table.get("class", []):
                continue
            for rt in table.select("table.rightcl"):
                info = extract_station_prizes(rt)
                if not info:
                    continue
                norm = normalize_name(info["name"])
                if norm in allowed_mn:
                    stations_nam.append(info)
                else:
                    print(f"     ⏭ Bỏ đài không có trong lịch: {info['name']}")

        elif "miền trung" in title_text or "mien trung" in title_text:
            table = box.select_one("table.bkqmiennam")
            if not table:
                continue
            for rt in table.select("table.rightcl"):
                info = extract_station_prizes(rt)
                if not info:
                    continue
                norm = normalize_name(info["name"])
                if norm in allowed_mt:
                    stations_trung.append(info)
                else:
                    print(f"     ⏭ Bỏ đài không có trong lịch: {info['name']}")

        elif "miền bắc" in title_text or "mien bac" in title_text:
            table = box.select_one("table.bkqtinhmienbac")
            if not table:
                continue
            # Truyền tên đài từ lịch vào
            info = extract_mien_bac_prizes(table, allowed_mb)
            if info:
                station_bac = info
                print(f"     ✔ Miền Bắc: {allowed_mb}")

    print(f"→ Khớp ngày: {matched}/{len(all_boxes)} box")

    regions = []
    if stations_nam:
        regions.append({"key": "nam", "name": "MIỀN NAM", "stations": stations_nam})
    if stations_trung:
        regions.append({"key": "trung", "name": "MIỀN TRUNG", "stations": stations_trung})
    if station_bac:
        regions.append({"key": "bac", "name": "MIỀN BẮC", "stations": [station_bac]})

    print(f"→ Kết quả: MN={len(stations_nam)} đài, MT={len(stations_trung)} đài, MB={'Có' if station_bac else 'Không'}")

    return {"regions": regions}


# ============ LƯU / ĐỌC FILE ============

def save_json(date_str, data):
    d, m, y = date_str.split("-")
    iso = f"{y}-{m}-{d}"
    year_dir = os.path.join(OUTPUT_DIR, y)
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{iso}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✔ Đã lưu: {path}")
    return path


def scrape_date(date_str):
    html = fetch_html(date_str)
    data = parse_page(html, date_str)
    if not data.get("regions"):
        print(f"⚠ Không parse được dữ liệu cho {date_str}")
        return None
    save_json(date_str, data)
    return data


def build_index():
    print("→ Đang tạo index.json...")
    dates = []
    if os.path.exists(OUTPUT_DIR):
        for year_folder in sorted(os.listdir(OUTPUT_DIR)):
            year_path = os.path.join(OUTPUT_DIR, year_folder)
            if not os.path.isdir(year_path):
                continue
            for fname in os.listdir(year_path):
                if fname.endswith(".json") and fname != "index.json":
                    iso = fname.replace(".json", "")
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", iso):
                        dates.append(iso)
    dates.sort(reverse=True)
    index_data = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(dates),
        "dates": dates,
    }
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"✔ Đã lưu index.json với {len(dates)} ngày")
    return index_path


# ============ MAIN ============

def main():
    today = datetime.now()
    for i in range(1, DAYS_TO_SCRAPE + 1):
        d = today - timedelta(days=i)
        date_str = d.strftime("%d-%m-%Y")
        iso = d.strftime("%Y-%m-%d")
        year = d.strftime("%Y")
        path = os.path.join(OUTPUT_DIR, year, f"{iso}.json")
        if os.path.exists(path):
            print(f"⏭ Đã có: {path} - bỏ qua")
            continue
        try:
            scrape_date(date_str)
            time.sleep(1.5)
        except Exception as e:
            print(f"✘ Lỗi ngày {date_str}: {e}")
            time.sleep(3)

    build_index()


if __name__ == "__main__":
    main()
