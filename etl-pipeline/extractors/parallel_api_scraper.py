#!/usr/bin/env python3
"""
Parallel API Scraper for Electricity Market Data

Downloads price data from the national grid coordinator's API,
day by day, using 20 parallel threads with rate limiting and retry logic.

Supports two API versions (v2 and v4) with automatic version selection
based on date ranges.

Source: Production scraper for electricity market data.
"""

import csv
import time
import requests
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os

urllib3.disable_warnings()

# Configuration (loaded from environment)
API_KEY = os.environ.get("GRID_API_KEY", "")
BASE_URL_V2 = os.environ.get(
    "GRID_API_V2_URL",
    "https://api.grid-coordinator.example/api/v2/resources/prices/",
)
BASE_URL_V4 = os.environ.get(
    "GRID_API_V4_URL",
    "https://api.grid-coordinator.example/prices/v4/findByDate",
)

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./data/marginal_costs"))

# Date ranges
START_DATE = datetime(2024, 5, 1)
V2_CUTOFF_DATE = datetime(2024, 7, 14)
END_DATE = datetime.now() - timedelta(days=10)

# Parallelism
NUM_WORKERS = 20
REQUEST_INTERVAL = 0.5

print_lock = threading.Lock()


def create_session():
    session = requests.Session()
    session.verify = False
    session.headers.update({"User-Agent": "MarketData-Downloader/3.0"})
    return session


def download_day_v2(date_str, session):
    """Download price data from API v2"""
    all_data = []
    offset = 0
    limit = 1000

    while True:
        url = f"{BASE_URL_V2}?api_key={API_KEY}&date={date_str}&limit={limit}&offset={offset}"

        for retry in range(3):
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 429:
                    time.sleep(10)
                    continue
                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                data = resp.json()
                results = data.get("results", [])
                all_data.extend(results)

                if not data.get("next"):
                    return all_data

                offset += limit
                time.sleep(REQUEST_INTERVAL)
                break
            except Exception:
                time.sleep(5)

    return all_data


def download_day_v4(date_str, session):
    """Download price data from API v4"""
    all_data = []
    page = 1
    limit = 10000

    while True:
        url = (
            f"{BASE_URL_V4}?api_key={API_KEY}"
            f"&startDate={date_str}&endDate={date_str}"
            f"&limit={limit}&page={page}"
        )

        for retry in range(3):
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 429:
                    time.sleep(10)
                    continue
                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                data = resp.json()
                results = data.get("data", [])

                if not results:
                    return all_data

                all_data.extend(results)

                total_pages = data.get("totalPages", 1)
                if page >= total_pages:
                    return all_data

                page += 1
                time.sleep(REQUEST_INTERVAL)
                break
            except Exception:
                time.sleep(5)

    return all_data


def process_date(args):
    """Process and save a single date"""
    date, is_v4, session = args
    date_str = date.strftime("%Y-%m-%d")

    # Build output path: data/YYYY/MM/DD/
    output_folder = (
        OUTPUT_DIR
        / str(date.year)
        / f"{date.month:02d}"
        / f"{date.day:02d}"
    )
    output_file = output_folder / "marginal_cost.csv"

    # Skip if already downloaded
    if output_file.exists():
        return date_str, 0, "already exists"

    # Download data
    if is_v4:
        data = download_day_v4(date_str, session)
    else:
        data = download_day_v2(date_str, session)

    if not data:
        return date_str, 0, "no data"

    # Create output directory
    output_folder.mkdir(parents=True, exist_ok=True)

    # Normalize and save
    if is_v4:
        fieldnames = [
            "date",
            "hour",
            "minute",
            "node_id",
            "node_name",
            "node_transformer",
            "price_usd_mwh",
            "price_local_kwh",
            "version",
        ]
        rows = []
        for r in data:
            rows.append(
                {
                    "date": r.get("date"),
                    "hour": r.get("hour", 0) + 1,
                    "minute": r.get("min", 0),
                    "node_id": r.get("node_id", ""),
                    "node_name": r.get("node_name", ""),
                    "node_transformer": r.get("node_transformer", ""),
                    "price_usd_mwh": r.get("price_usd_mwh"),
                    "price_local_kwh": r.get("price_local_kwh"),
                    "version": r.get("version", "REAL"),
                }
            )
    else:
        fieldnames = ["date", "hour", "node_id", "price_usd_mwh", "price_local_kwh"]
        rows = []
        for r in data:
            rows.append(
                {
                    "date": r.get("date"),
                    "hour": r.get("hour"),
                    "node_id": r.get("node_name"),
                    "price_usd_mwh": r.get("price_usd"),
                    "price_local_kwh": r.get("price_local"),
                }
            )

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return date_str, len(rows), "OK"


def main():
    print("=" * 70)
    print("PRICE DATA DOWNLOADER - Day by Day (20 threads)")
    print("=" * 70)

    # Generate date list
    dates = []
    current_date = START_DATE
    while current_date <= END_DATE:
        is_v4 = current_date > V2_CUTOFF_DATE
        dates.append((current_date, is_v4))
        current_date += timedelta(days=1)

    print(f"Dates to process: {len(dates)}")
    print(f"  - API v2: {len([f for f in dates if not f[1]])}")
    print(f"  - API v4: {len([f for f in dates if f[1]])}")
    print(f"Workers: {NUM_WORKERS}")
    print("-" * 70)

    # Create one session per worker
    sessions = [create_session() for _ in range(NUM_WORKERS)]

    completed = 0
    total = len(dates)
    existing = 0
    downloaded = 0

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        args_list = [
            (date, is_v4, sessions[i % NUM_WORKERS])
            for i, (date, is_v4) in enumerate(dates)
        ]

        futures = {
            executor.submit(process_date, args): args[0] for args in args_list
        }

        for future in as_completed(futures):
            date = futures[future]
            try:
                date_str, records, status = future.result()
                completed += 1

                if status == "already exists":
                    existing += 1
                elif status == "OK":
                    downloaded += 1

                with print_lock:
                    print(
                        f"[{completed}/{total}] {date_str}"
                        f" - {records} records ({status})"
                    )

            except Exception as e:
                with print_lock:
                    print(f"[{completed}/{total}] {date} ERROR: {e}")

    print("=" * 70)
    print(f"COMPLETED: {completed}/{total}")
    print(f"  - Downloaded: {downloaded}")
    print(f"  - Already existed: {existing}")
    print("=" * 70)


if __name__ == "__main__":
    main()
