#!/usr/bin/env python3
"""
scraper.py - Cào KQXS từ minhngoc.net
Repo: xsktvn
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
    url = f"https://www.minhngoc.net/ket-qua-xo-so/{date_str}.html"
    print(f"→ Đang tải: {url}")
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def parse_prize_table(table):
    stations = []
    name_cells = table.select("td.tinh, td.province, .tentinh")
    codes = [c.get_text(strip=True) for c in table.select("td.ma, td.code, .madai")]

    if not name_cells:
        return []

    prize_rows = []
    for tr in table.select("tr"):
        label_cell = tr.select_one("td.giai, td.prize, .giai")
        if not label_cell:
            continue
        label = label_cell.get_text(strip=True)
        if not label:
            continue
        num_cells = tr.select("td.so, td.number, .kq")
        nums_by_station = []
        for cell in num_cells:
            nums = re.split(r"\s+", cell.get_text(strip=True))
            nums = [n for n in nums if n]
            nums_by_station.append(nums)
        if nums_by_station:
            prize_rows.append({"label": label, "nums": nums_by_station})

    for i, name_cell in enumerate(name_cells):
        name = name_cell.get_text(strip=True)
        if not name:
            continue
        station = {
            "name": name,
            "code": codes[i] if i < len(codes) else "",
            "prizes": [],
        }
        for pr in prize_rows:
            nums = pr["nums"][i] if i < len(pr["nums"]) else []
            if nums:
                station["prizes"].append({"label": pr["label"], "numbers": nums})
        if station["prizes"]:
            stations.append(station)
    return stations


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    regions = []
    tables = soup.select("table.bkqt, table.kqxs, .kqxs table")
    region_defs = [
        ("nam", "MIỀN NAM"),
        ("trung", "MIỀN TRUNG"),
        ("bac", "MIỀN BẮC"),
    ]
    for idx, table in enumerate(tables):
        if idx >= len(region_defs):
            break
        key, name = region_defs[idx]
        stations = parse_prize_table(table)
        if stations:
            regions.append({"key": key, "name": name, "stations": stations})
    return {"regions": regions}


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
