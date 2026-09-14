#!/usr/bin/env python3
"""
scraper.py - Cào KQXS từ minhngoc.net
Repo: xsktvn
Đã fix selector theo cấu trúc HTML thực tế
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


def fetch_html(date_str):
    """date_str: dd-mm-yyyy"""
    url = f"https://www.minhngoc.net/ket-qua-xo-so/{date_str}.html"
    print(f"→ Đang tải: {url}")
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def parse_mien_nam_trung(table):
    """
    Parse bảng miền Nam hoặc miền Trung.
    Cấu trúc:
      - Cột trái (td.leftcl): chứa tên giải
      - Các cột phải: mỗi cột là 1 đài, có td.tinh (tên), td.matinh (mã), td.giai8..giaidb (số)
    """
    stations = []

    # Tìm tất cả các đài: td.tinh trong bảng
    # Mỗi td.tinh là 1 đài, nhưng phải lấy từ các bảng con rightcl
    right_tables = table.select("table.rightcl")

    for rt in right_tables:
        # Tên đài
        tinh_td = rt.select_one("td.tinh")
        if not tinh_td:
            continue
        name = tinh_td.get_text(strip=True)
        if not name:
            continue

        # Mã đài
        matinh_td = rt.select_one("td.matinh")
        code = matinh_td.get_text(strip=True) if matinh_td else ""

        # Các giải
        prizes = []
        # Thứ tự giải từ trên xuống: giai8, giai7, giai6, giai5, giai4, giai3, giai2, giai1, giaidb
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
            # Lấy tất cả các div con (mỗi div là 1 số)
            divs = td.find_all("div", recursive=False)
            if not divs:
                # fallback: lấy text trực tiếp
                text = td.get_text(strip=True)
                if text:
                    nums = re.split(r"\s+", text)
                    nums = [n for n in nums if n]
                    if nums:
                        prizes.append({"label": label, "numbers": nums})
            else:
                nums = [d.get_text(strip=True) for d in divs if d.get_text(strip=True)]
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
    """
    Parse bảng miền Bắc.
    Cấu trúc:
      - td.giaidbl / td.giai1l ... là nhãn giải
      - td.giaidb / td.giai1 ... là số, chứa <div>
    """
    stations = []

    # Miền Bắc chỉ có 1 đài
    name = "Miền Bắc"
    code = ""

    # Lấy mã đài từ ký hiệu (loaive_content)
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
        divs = td.find_all("div", recursive=False)
        if not divs:
            text = td.get_text(strip=True)
            if text:
                nums = re.split(r"\s+", text)
                nums = [n for n in nums if n]
                if nums:
                    prizes.append({"label": label, "numbers": nums})
        else:
            nums = [d.get_text(strip=True) for d in divs if d.get_text(strip=True)]
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
    """
    Parse trang HTML, trả về dict:
    {
      "regions": [
        {"key": "nam", "name": "MIỀN NAM", "stations": [...]},
        {"key": "trung", "name": "MIỀN TRUNG", "stations": [...]},
        {"key": "bac", "name": "MIỀN BẮC", "stations": [...]}
      ]
    }
    """
    soup = BeautifulSoup(html, "lxml")
    regions = []

    # Tìm tất cả các div.box_kqxs
    boxes = soup.select("div.box_kqxs")

    for box in boxes:
        # Lấy tiêu đề để xác định miền
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
            # Bỏ qua bảng miền Bắc (cũng dùng class bkqmiennam bkqmienbac)
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

    # Sắp xếp theo thứ tự: Nam, Trung, Bắc
    order = {"nam": 0, "trung": 1, "bac": 2}
    regions.sort(key=lambda r: order.get(r["key"], 99))

    return {"regions": regions}


def save_json(date_str, data):
    """date_str: dd-mm-yyyy → data/yyyy/yyyy-mm-dd.json"""
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
    data = parse_page(html)
    if not data.get("regions"):
        print(f"⚠ Không parse được dữ liệu cho {date_str}")
        return None
    save_json(date_str, data)
    return data


def main():
    today = datetime.now()
    for i in range(DAYS_TO_SCRAPE):
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


if __name__ == "__main__":
    main()
