import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

IN_FILE = "sibeliustalo_events_may_2026.csv"
OUT_FILE = "sibeliustalo_events_may_2026_with_end.csv"


def parse_duration_minutes_from_page(url: str) -> int:
    """Extract event duration in minutes from the HTML page."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERR] Request failed for {url}: {e}")
        return 0

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Pattern 1: "Konsertin kesto n. 1 h 45 min"
    m = re.search(r"[Kk]onsertin kesto[^0-9]*?(\d+)\s*h\s*(\d+)\s*min", text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        return h * 60 + mi

    # Pattern 2: "Kesto 2 h 30 min"
    m = re.search(r"[Kk]esto[^0-9]*?(\d+)\s*h\s*(\d+)\s*min", text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        return h * 60 + mi

    # Pattern 3: "Kesto 2 h" (hours only)
    m = re.search(r"[Kk]esto[^0-9]*?(\d+)\s*h([^0-9]|$)", text)
    if m:
        h = int(m.group(1))
        return h * 60

    # Pattern 4: "Kesto 90 min" (minutes only)
    m = re.search(r"[Kk]esto[^0-9]*?(\d+)\s*min", text)
    if m:
        mi = int(m.group(1))
        return mi

    # No duration found
    return 0


def add_end_times():
    """Read events CSV, fetch missing durations, calculate and add end times."""
    in_path = Path(IN_FILE)
    out_path = Path(OUT_FILE)

    with in_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    updated = 0

    for row in rows:
        # Skip if end time already exists
        if row.get("time_end"):
            continue

        date_start = row.get("date_start", "")
        time_start = row.get("time_start", "")
        url = row.get("source_url", "")

        if not date_start or not time_start or not url:
            continue

        # Fetch duration from the website
        duration_minutes = parse_duration_minutes_from_page(url)
        if duration_minutes <= 0:
            # Leave time_end empty
            continue

        # Update duration_minutes in the row
        row["duration_minutes"] = str(duration_minutes)

        # Calculate end time
        try:
            start_dt = datetime.strptime(
                f"{date_start} {time_start}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            # Skip if time format is unexpected
            continue

        end_dt = start_dt + timedelta(minutes=duration_minutes)
        row["time_end"] = end_dt.strftime("%H:%M")
        updated += 1
        print(f"[OK] Updated end time for {row.get('name')} -> {row['time_end']}")

    # Write the updated file
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"[DONE] Updated {updated} events, saved to {out_path}")


if __name__ == "__main__":
    add_end_times()