import re
import csv
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# List of play pages to scrape (public URLs, no credentials needed)
URL_LST = [
    "https://lahdenkaupunginteatteri.fi/ohjelma/loistava-ystavani/",
    "https://lahdenkaupunginteatteri.fi/ohjelma/mammal/",
    "https://lahdenkaupunginteatteri.fi/ohjelma/nysa-jattilaismaisen-pieni-seikkailu/",
    "https://lahdenkaupunginteatteri.fi/ohjelma/maan-ja-veden-valilla/",
    "https://lahdenkaupunginteatteri.fi/ohjelma/haapajarven-elvis/",
    "https://lahdenkaupunginteatteri.fi/ohjelma/lets-vits-again-viihdekonsertti/",
]

OUT_FILE = "teatteri_may_2026.csv"

YEAR = 2026
MONTH = 5  # May (toukokuu)

COLUMNS = [
    "id",
    "date_start",
    "time_start",
    "time_end",
    "name",
    "stage",
    "duration_minutes",
    "source_url",
]


def parse_duration_minutes(soup: BeautifulSoup) -> int:
    """Extract duration from page text, looking for pattern like 'Kesto 1h 30 min'."""
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Kesto\s+(\d+)h\s+(\d+)\s*min", text)
    if not m:
        return 0
    hours = int(m.group(1))
    mins = int(m.group(2))
    return hours * 60 + mins


def parse_play_page(url: str, year: int, month: int) -> list[dict]:
    """Extract all May performances for a single play from its page."""
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    duration_minutes = parse_duration_minutes(soup)

    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else url

    # Find the block with heading 'TOUKOKUU' (May)
    events_container = None
    for h2 in soup.find_all("h2"):
        if "TOUKOKUU" in h2.get_text(strip=True).upper():
            parent = h2.find_parent(class_="events-items") or h2.parent
            if parent and "events-items" in (parent.get("class") or []):
                events_container = parent
            else:
                sibling = h2.find_next_sibling("div")
                if sibling and "events-items" in (sibling.get("class") or []):
                    events_container = sibling
                else:
                    events_container = h2.parent
            break

    if not events_container:
        print(f"[WARN] Could not find .events-items for May at {url}")
        return []

    rows = []

    for item in events_container.find_all("div", class_="block-events__item"):
        date_div = item.find("div", class_="date")
        spans = date_div.find_all("span") if date_div else []
        if len(spans) < 2:
            continue
        date_text = spans[0].get_text(strip=True)   # e.g. 'Pe 8.5.'
        time_text = spans[1].get_text(strip=True)   # e.g. '18.30'

        location_div = item.find("div", class_="location")
        stage = location_div.get_text(strip=True) if location_div else ""

        # Parse date
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.", date_text)
        if not m:
            continue
        day = int(m.group(1))
        month_num = int(m.group(2))
        if month_num != month:
            continue

        # Parse time
        tm = re.search(r"(\d{1,2})[.:](\d{2})", time_text)
        if not tm:
            continue
        hour = int(tm.group(1))
        minute = int(tm.group(2))

        start_dt = datetime(year, month_num, day, hour, minute)
        end_dt = start_dt + timedelta(minutes=duration_minutes) if duration_minutes else None

        rows.append({
            "date_start": start_dt.strftime("%Y-%m-%d"),
            "time_start": start_dt.strftime("%H:%M"),
            "time_end": end_dt.strftime("%H:%M") if end_dt else "",
            "name": name,
            "stage": stage,
            "duration_minutes": duration_minutes,
            "source_url": url,
        })

    print(f"[OK] {name}: found {len(rows)} shows in May")
    return rows


def main():
    """Main function: scrape all play pages and save May performances to CSV."""
    all_rows = []

    for url in URL_LST:
        shows = parse_play_page(url, YEAR, MONTH)
        all_rows.extend(shows)

    out_path = Path(OUT_FILE)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for idx, record in enumerate(all_rows, start=1):
            row = {
                "id": idx,
                "date_start": record["date_start"],
                "time_start": record["time_start"],
                "time_end": record["time_end"],
                "name": record["name"],
                "stage": record["stage"],
                "duration_minutes": record["duration_minutes"],
                "source_url": record["source_url"],
            }
            writer.writerow(row)

    print(f"Saved {len(all_rows)} shows to {out_path}")


if __name__ == "__main__":
    main()