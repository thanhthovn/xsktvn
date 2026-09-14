#!/usr/bin/env python3
"""
scraper.py - Cào KQXS từ minhngoc.net
Repo: xsktvn

- Chỉ cào từ HÔM QUA lùi về 365 ngày (bỏ qua hôm nay).
- Chỉ lấy đài có trong lịch xổ số của ngày đó (theo thứ).
- Bỏ qua các box_kqxs của ngày cũ hơn trên cùng trang.
"""
import os
import json
import re
import time
from datetime import datetime, timedelta

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
DAYS_TO_SCRAPE = 365


# ============ LỊCH XỔ SỐ THEO THỨ ============
# Python: 0=Thứ Hai, 1=Thứ Ba, ..., 6=Chủ Nhật

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
    """Tải HTML, retry tối đa max_retry lần."""
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
    """Trích xuất các số từ 1 ô <td>."""
    divs = td.find_all("div", recursive=False)
    if not divs:
        text = td.get_text(strip=True)
        if not text:
            return []
        nums = re.split(r"\s+", text)
        return [n for n in nums if n]
    return [d.get_text(strip=True) for d in divs if d.get_text(strip=True)]


def normalize_name(name):
    """Chuẩn hóa tên đài để so sánh (bỏ dấu, lowercase)."""
    import unicodedata
    name = name.lower().strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.replace("đ", "d")
    name = re.sub(r"\s+", " ", name)
    return name


def _is_before(el1, el2):
    """Kiểm tra el1 có nằm trước el2 trong document không."""
    for el in el1.previous_elements:
        if el is el2:
            return True
    return False


# ============ PARSE TỪNG MIỀN ============

def parse_mien_nam_trung(table, allowed_stations):
    """
    Parse bảng miền Nam/Trung.
    allowed_stations: list tên đài cho phép (đã normalize).
    """
    stations = []
    right_tables = table.select("table.rightcl")

    for rt in right_tables:
        tinh_td = rt.select_one("td.tinh")
        if not tinh_td:
            continue
        name = tinh_td.get_text(strip=True)
        if not name:
            continue

        # Lọc theo lịch: chỉ lấy đài có trong danh sách
        if normalize_name(name) not in allowed_stations:
            continue

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

        if prizes:
            stations.append({
                "name": name,
                "code": code,
                "prizes": prizes,
            })

    return stations


def parse_mien_bac(table, allowed_station):
    """
    Parse bảng miền Bắc.
    allowed_station: tên đài duy nhất cho phép (đã normalize), có thể None = lấy hết.
    """
    stations = []
    name = "Miền Bắc"
    code = ""

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

    if prizes:
        stations.append({
            "name": name,
            "code": code,
            "prizes": prizes,
        })

    return stations


# ============ PARSE TRANG ============

def parse_page(html, date_str):
    """
    Parse trang, CHỈ lấy kết quả của NGÀY CHÍNH.
    Lọc đài theo lịch xổ số của thứ trong tuần.
    """
    soup = BeautifulSoup(html, "lxml")
    regions = []

    # ===== Xác định thứ của ngày =====
    d, m, y = date_str.split("-")
    dt = datetime(int(y), int(m), int(d))
    weekday = dt.weekday()  # 0=Thứ Hai, 6=Chủ Nhật
    weekday_name = WEEKDAY_NAMES[weekday]

    # Lấy danh sách đài cho phép
    allowed_mn = {normalize_name(s) for s in STATIONS_BY_WEEKDAY_MN.get(weekday, [])}
    allowed_mt = {normalize_name(s) for s in STATIONS_BY_WEEKDAY_MT.get(weekday, [])}
    allowed_mb = STATIONS_BY_WEEKDAY_MB.get(weekday, "")

    print(f"→ Ngày {date_str} ({weekday_name})")
    print(f"   MN: {STATIONS_BY_WEEKDAY_MN.get(weekday, [])}")
    print(f"   MT: {STATIONS_BY_WEEKDAY_MT.get(weekday, [])}")
    print(f"   MB: {allowed_mb}")

    # ===== Chỉ lấy box trước h1.pagetitle thứ hai =====
    all_h1 = soup.select("h1.pagetitle")
    if not all_h1:
        print("⚠ Không tìm thấy h1.pagetitle")
        return {"regions": []}

    first_h1_text = all_h1[0].get_text(strip=True)
    print(f"→ Ngày chính trên trang: {first_h1_text}")

    if len(all_h1) >= 2:
        second_h1 = all_h1[1]
        all_boxes = soup.select("div.box_kqxs")
        valid_boxes = []
        for box in all_boxes:
            if _is_before(box, second_h1):
                valid_boxes.append(box)
            else:
                break
        print(f"→ Trang có {len(all_h1)} ngày, chỉ lấy {len(valid_boxes)} box của ngày chính")
    else:
        valid_boxes = soup.select("div.box_kqxs")
        print(f"→ Trang có 1 ngày, lấy {len(valid_boxes)} box")

    # ===== Parse từng box =====
    for box in valid_boxes:
        title_a = box.select_one(".top .title a")
        if not title_a:
            continue
        title = title_a.get_text(strip=True).lower()

        if "miền nam" in title or "mien nam" in title:
            region_key = "nam"
            region_name = "MIỀN NAM"
            table = box.select_one("table.bkqmiennam")
            if not table:
                continue
            if "bkqmienbac" in table.get("class", []):
                continue
            stations = parse_mien_nam_trung(table, allowed_mn)

        elif "miền trung" in title or "mien trung" in title:
            region_key = "trung"
            region_name = "MIỀN TRUNG"
            table = box.select_one("table.bkqmiennam")
            if not table:
                continue
            stations = parse_mien_nam_trung(table, allowed_mt)

        elif "miền bắc" in title or "mien bac" in title:
            region_key = "bac"
            region_name = "MIỀN BẮC"
            table = box.select_one("table.bkqtinhmienbac")
            if not table:
                continue
            stations = parse_mien_bac(table, allowed_mb)

        else:
            continue

        if stations:
            regions.append({
                "key": region_key,
                "name": region_name,
                "stations": stations,
            })

    order = {"nam": 0, "trung": 1, "bac": 2}
    regions.sort(key=lambda r: order.get(r["key"], 99))

    return {"regions": regions}


# ============ LƯU / ĐỌC FILE ============

def save_json(date_str, data):
    """Lưu data/yyyy/yyyy-mm-dd.json"""
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
    """Cào 1 ngày, lưu JSON."""
    html = fetch_html(date_str)
    data = parse_page(html, date_str)
    if not data.get("regions"):
        print(f"⚠ Không parse được dữ liệu cho {date_str}")
        return None
    save_json(date_str, data)
    return data


def build_index():
    """Quét thư mục data/ và tạo file index.json."""
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
    # Bắt đầu từ hôm qua (i=1), bỏ qua hôm nay (i=0)
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
