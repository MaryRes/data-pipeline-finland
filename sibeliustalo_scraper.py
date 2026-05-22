import re
import csv
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.sibeliustalo.fi"
LIST_URL = f"{BASE_URL}/tapahtumakalenteri/"
OUT_FILE = "sibeliustalo_events_may_2026.csv"

# Restaurant events to exclude (no API credentials needed, just filtering)
EXCLUDE_PLACES = [
    "Ravintola Lastu",  # restaurant events are filtered out
]

YEAR_FILTER = 2026
MONTH_FILTER = 5  # May


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


def fetch_event_links() -> list[dict]:
    """Scrape all event links from the events calendar page, excluding restaurant events."""
    r = requests.get(LIST_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    seen = set()

    # Find all links pointing to /tapahtumat/...
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/tapahtumat/" not in href:
            continue

        full_url = urljoin(BASE_URL, href)

        # Remove duplicates (same event may appear multiple times)
        if full_url in seen:
            continue
        seen.add(full_url)

        # Try to find "Paikka" / venue nearby to filter out restaurant events
        place_name = ""
        parent = a.find_parent()
        container = parent
        # Traverse up a few levels to find the block containing venue info
        for _ in range(3):
            if not container:
                break
            txt = container.get_text(" ", strip=True)
            if "Paikka" in txt or "Location" in txt:
                break
            container = container.parent

        if container:
            place_header = container.find(["h5", "h6"])
            if place_header:
                place_name = place_header.get_text(strip=True)

        # Filter out restaurant events
        if any(ex.lower() in place_name.lower() for ex in EXCLUDE_PLACES):
            continue

        name = a.get_text(strip=True)
        results.append({
            "name": name,
            "url": full_url,
            "place": place_name,
        })

    print(f"[INFO] Found {len(results)} event links (excluding restaurant)")
    return results


def parse_duration_minutes(soup: BeautifulSoup) -> int:
    """Find text like 'Konsertin kesto n. 1 h 45 min' and convert to minutes."""
    text = soup.get_text(" ", strip=True)
    # Match Finnish pattern: "Konsertin kesto n. 1 h 45 min"
    m = re.search(r"[Kk]onsertin kesto[^0-9]*?(\d+)\s*h\s*(\d+)\s*min", text)
    if not m:
        # Fallback: simpler pattern "1 h 45 min"
        m2 = re.search(r"(\d+)\s*h\s*(\d+)\s*min", text)
        if not m2:
            return 0
        h = int(m2.group(1))
        mi = int(m2.group(2))
        return h * 60 + mi
    hours = int(m.group(1))
    mins = int(m.group(2))
    return hours * 60 + mins


def parse_event(url: str) -> dict | None:
    """Parse a single Sibelius Hall event page."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERR] Request failed for {url}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Extract event name / title
    title_div = soup.find("div", class_="views-field-title")
    if title_div:
        h1 = title_div.find("h1")
        name = h1.get_text(strip=True) if h1 else url
    else:
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else url

    duration_minutes = parse_duration_minutes(soup)

    # Find the schedule block ('Aikataulu ja liput')
    schedule_block = soup.find("div", class_="features-wrapper")
    if not schedule_block:
        for h2 in soup.find_all("h2"):
            if "Aikataulu ja liput" in h2.get_text(strip=True):
                schedule_block = h2.find_parent("div", class_="features-wrapper") or h2.parent
                break

    if not schedule_block:
        print(f"[WARN] No 'Aikataulu ja liput' for {url}")
        return None

    # Extract date and time
    date_time_str = ""
    date_field = schedule_block.find("div", class_="views-field-field-date")
    if date_field:
        strong = date_field.find("strong")
        if strong:
            date_time_str = strong.get_text(" ", strip=True)

    # Pattern: "DD.MM.YYYY ... HH:MM"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4}).*?(\d{1,2})[.:](\d{2})", date_time_str)
    if not m:
        print(f"[WARN] Cannot parse datetime '{date_time_str}' at {url}")
        return None

    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))
    hour = int(m.group(4))
    minute = int(m.group(5))

    # Filter by year/month to avoid returning irrelevant events
    if year != YEAR_FILTER or month != MONTH_FILTER:
        return None

    start_dt = datetime(year, month, day, hour, minute)
    end_dt = start_dt + timedelta(minutes=duration_minutes) if duration_minutes else None

    # Extract venue / stage (näyttämö)
    stage = ""
    place_field = schedule_block.find("div", class_="views-field-field-paikka")
    if place_field:
        dd = place_field.find("dd", class_="author")
        if dd:
            h6 = dd.find("h6")
            if h6:
                stage = h6.get_text(strip=True)

    return {
        "date_start": start_dt.strftime("%Y-%m-%d"),
        "time_start": start_dt.strftime("%H:%M"),
        "time_end": end_dt.strftime("%H:%M") if end_dt else "",
        "name": name,
        "stage": stage,
        "duration_minutes": duration_minutes,
        "source_url": url,
    }


def main():
    """Main function: scrape event links, parse each, save May 2026 events to CSV."""
    links = fetch_event_links()
    events = []

    for info in links:
        url = info["url"]
        ev = parse_event(url)
        if ev:
            events.append(ev)
            print(f"[OK] {ev['date_start']} {ev['time_start']} – {ev['name']} ({ev['stage']})")
        else:
            print(f"[SKIP] No May 2026 event data for {url}")

    out_path = Path(OUT_FILE)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for idx, ev in enumerate(events, start=1):
            writer.writerow({
                "id": idx,
                "date_start": ev["date_start"],
                "time_start": ev["time_start"],
                "time_end": ev["time_end"],
                "name": ev["name"],
                "stage": ev["stage"],
                "duration_minutes": ev["duration_minutes"],
                "source_url": ev["source_url"],
            })

    print(f"[DONE] Saved {len(events)} May 2026 events to {out_path}")


if __name__ == "__main__":
    main()