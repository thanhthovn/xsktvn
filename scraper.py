#!/usr/bin/env python3
"""
scraper.py - Cào KQXS từ minhngoc.net
Repo: xsktvn
Tự động cào từ hôm qua lùi về 365 ngày, bỏ qua file đã có.
Tạo data/index.json chứa danh sách các ngày có dữ liệu.
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


def fetch_html(date_str, max_retry=3):
    """Tải HTML của 1 ngày, retry tối đa max_retry lần."""
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


def parse_mien_nam_trung(table):
    """Parse bảng miền Nam hoặc miền Trung."""
    stations = []
    right_tables = table.select("table.rightcl")

    for rt in right_tables:
        tinh_td = rt.select_one("td.tinh")
        if not tinh_td:
            continue
        name = tinh_td.get_text(strip=True)
        if not name:
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


def parse_mien_bac(table):
    """Parse bảng miền Bắc."""
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


def parse_page(html):
    """Parse toàn bộ trang, trả về dict regions."""
    soup = BeautifulSoup(html, "lxml")
    regions = []

    boxes = soup.select("div.box_kqxs")

    for box in boxes:
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
            stations = parse_mien_nam_trung(table)

        elif "miền trung" in title or "mien trung" in title:
            region_key = "trung"
            region_name = "MIỀN TRUNG"
            table = box.select_one("table.bkqmiennam")
            if not table:
                continue
            stations = parse_mien_nam_trung(table)

        elif "miền bắc" in title or "mien bac" in title:
            region_key = "bac"
            region_name = "MIỀN BẮC"
            table = box.select_one("table.bkqtinhmienbac")
            if not table:
                continue
            stations = parse_mien_bac(table)

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
    data = parse_page(html)
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

    # Tạo index.json sau khi cào xong
    build_index()


if __name__ == "__main__":
    main()
