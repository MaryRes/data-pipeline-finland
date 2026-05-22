import base64
import csv
import datetime as dt
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

import requests

# Load credentials from environment variables
load_dotenv()

USER_ID = os.getenv("MATKAHUOLTO_USER_ID")
PASSWORD = os.getenv("MATKAHUOLTO_PASSWORD")

if not USER_ID or not PASSWORD:
    raise ValueError(
        "Missing API credentials. Set MATKAHUOLTO_USER_ID and "
        "MATKAHUOLTO_PASSWORD in .env file"
    )

BASE_URL = "https://minfoapi.matkahuolto.fi/mlippu_rest"

OUTPUT_CSV = "bus_lahti_arrivals_may2026.csv"

START_DATE = dt.date(2026, 5, 1)
END_DATE = dt.date(2026, 5, 31)

# Cities between which we search for routes passing through Lahti
MAIN_CITIES = [
    "Helsinki",
    "Helsinki-Vantaa",
    "Helsinki-Vantaan lentoasema",
    "Tampere",
    "Turku",
    "Jyväskylä",
    "Kuopio",
    "Oulu",
    "Rovaniemi",
]

REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 0.2


def get_auth_header() -> Dict[str, str]:
    """Generate Basic Authentication header for API requests"""
    raw = f"{USER_ID}:{PASSWORD}"
    token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def request_minfo(path: str, params: Dict[str, Any]) -> Any:
    """Make authenticated request to Matkahuolto API"""
    url = f"{BASE_URL}{path}"
    headers = {
        **get_auth_header(),
        "Accept": "application/vnd.matkahuolto.minfo.api-v1+json",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception as e:
                    print(f"[ERROR] JSON decode error for {url}: {e}")
                    return None
            else:
                print(f"[WARN] {url} {resp.status_code} {resp.text[:200]}")
                # No point retrying for 4xx errors
                if resp.status_code < 500:
                    return None
        except Exception as e:
            print(f"[ERROR] {url} attempt {attempt + 1}: {e}")
        time.sleep(1.0)
    return None


def normalize_str(s: Optional[str]) -> str:
    """Convert None to empty string and strip whitespace"""
    return (s or "").strip()


def is_lahti_stop(stop_name: str, place: str) -> bool:
    """
    Consider a stop as "Lahti stop" if:
    - place is explicitly Lahti, or
    - substring 'lahti' appears in name/place (case and diacritics insensitive)
    """
    name_l = normalize_str(stop_name).lower()
    place_l = normalize_str(place).lower()
    if place_l == "lahti":
        return True
    return "lahti" in name_l or "lahti" in place_l


def parse_time_to_hms(timestr: str) -> str:
    """Extract time (HH:MM:SS) from ISO datetime string"""
    if not timestr:
        return ""
    t_str = timestr.strip()
    # expecting ISO format `YYYY-MM-DDTHH:MM:SS+03:00` or with Z
    try:
        t = dt.datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        return t.strftime("%H:%M:%S")
    except Exception:
        pass

    if "T" in t_str:
        base = t_str.split("+")[0].split("Z")[0]
        try:
            t = dt.datetime.fromisoformat(base)
            return t.strftime("%H:%M:%S")
        except Exception:
            pass

    # Fallback — just first 8 characters
    return t_str[:8]


def parse_date(timestr: str, fallback_date: dt.date) -> str:
    """Extract date (YYYY-MM-DD) from ISO datetime string"""
    if not timestr:
        return fallback_date.strftime("%Y-%m-%d")
    t_str = timestr.strip()
    try:
        t = dt.datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        return t.date().strftime("%Y-%m-%d")
    except Exception:
        pass

    if "T" in t_str:
        base = t_str.split("+")[0].split("Z")[0]
        try:
            t = dt.datetime.fromisoformat(base)
            return t.date().strftime("%Y-%m-%d")
        except Exception:
            pass

    return fallback_date.strftime("%Y-%m-%d")


def get_connection_details(conn_id: str) -> Optional[Dict[str, Any]]:
    """Fetch detailed information for a specific connection"""
    if not conn_id:
        return None
    data = request_minfo(f"/connection/{conn_id}/details", params={})
    if not isinstance(data, dict):
        if data is not None:
            print(f"[WARN] Unexpected details type for conn {conn_id}: {type(data)}")
        return None
    return data


def city_from_stop(stop: Dict[str, Any]) -> str:
    """Extract city name from a stop object"""
    place = normalize_str(stop.get("placeName") or "")
    if place:
        return place
    name = normalize_str(stop.get("stopAreaName") or "")
    if not name:
        return ""
    # Heuristic: if there's a comma, the city often comes after it
    if "," in name:
        return name.split(",")[-1].strip()
    return name.split()[0]


def derive_from_to_cities(route_stops: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Get origin and destination cities from route stops"""
    if not route_stops:
        return "", ""
    first = route_stops[0]
    last = route_stops[-1]
    return city_from_stop(first), city_from_stop(last)


def derive_lahti_stop_id(stop_name: str, place_name: str) -> str:
    """Generate a consistent ID for Lahti stops based on stop type"""
    name_l = normalize_str(stop_name).lower()
    place_l = normalize_str(place_name).lower()

    # Most precise — Travel Centre
    if "travel centre" in name_l or "matkakeskus" in name_l:
        return "LAHTI_TC"

    # Bus station
    if "bus station" in name_l or "linja-autoasema" in name_l:
        return "LAHTI_BS"

    # Generic Lahti stop
    if "lahti" in name_l or place_l == "lahti":
        return "LAHTI_GENERIC"

    # Fallback
    return "LAHTI_GENERIC"


def extract_lahti_rows_from_connection(
    connection: Dict[str, Any],
    conn_details: Dict[str, Any],
    travel_date: dt.date,
) -> List[Dict[str, Any]]:
    """Extract all rows for Lahti stops from a single connection"""
    rows: List[Dict[str, Any]] = []

    try:
        connection_id = str(connection.get("id") or "")
        if not connection_id:
            return rows

        route_name_long = normalize_str(
            connection.get("routeName")
            or connection.get("marketingName")
            or ""
        )

        # Detailed information
        part_trips = conn_details.get("partTrips") or []
        if not part_trips:
            # Some details might be in another field — just skip in that case
            return rows

        # Take the first part as the main route (most long-distance buses have one)
        main_part = part_trips[0] or {}
        route_stops = main_part.get("route") or []
        if not route_stops:
            return rows

        from_city, to_city = derive_from_to_cities(route_stops)

        # If no proper long name, build it ourselves
        if not route_name_long and from_city and to_city:
            route_name_long = f"{from_city} - {to_city}"

        route_short_name = ""  # empty for now, can extract line number later
        trip_id = connection_id
        trip_headsign = to_city or ""

        # Route departure time (in case a specific stop has no time)
        conn_from_dt = ""
        from_place = connection.get("fromPlace") or {}
        if isinstance(from_place, dict):
            conn_from_dt = normalize_str(from_place.get("dateTime") or "")

        for s in route_stops:
            if not isinstance(s, dict):
                continue

            stop_name = normalize_str(s.get("stopAreaName") or "")
            place_name = normalize_str(s.get("placeName") or "")

            if not stop_name and not place_name:
                continue

            if not is_lahti_stop(stop_name, place_name):
                continue

            full_stop_name = ", ".join(
                p for p in [stop_name, place_name] if p
            ) or "Lahti"

            arr_time_raw = normalize_str(
                s.get("arrivalTime") or s.get("departureTime") or conn_from_dt
            )

            date_str = parse_date(arr_time_raw, travel_date)
            time_str = parse_time_to_hms(arr_time_raw)

            lahti_stop_id = derive_lahti_stop_id(stop_name, place_name)

            row = {
                "date": date_str,
                "time": time_str,
                "lahti_stop_id": lahti_stop_id,
                "platform_code": "",  # platforms are usually not available for buses
                "lahti_stop_name": full_stop_name,
                "route_id": connection_id,
                "route_short_name": route_short_name,
                "route_long_name": route_name_long or "",
                "route_type": 3,  # bus
                "trip_id": trip_id,
                "trip_headsign": trip_headsign,
                "from_station": from_city or "",
            }
            rows.append(row)

    except Exception as e:
        # Never crash the whole process because of one malformed route
        print(f"[ERROR] extract_lahti_rows_from_connection failed for connection {connection.get('id')}: {e}")

    return rows


def fetch_for_one_direction(
    date_obj: dt.date,
    departure_name: str,
    arrival_name: str,
) -> List[Dict[str, Any]]:
    """Fetch connections between two cities on a specific date"""
    params = {
        "departureStopAreaName": departure_name,
        "arrivalStopAreaName": arrival_name,
        "departureDate": date_obj.strftime("%Y-%m-%d"),
        "allSchedules": 0,
        "ticketTravelType": 0,
    }
    data = request_minfo("/connections", params=params)
    if not data:
        return []

    if isinstance(data, list):
        connections = data
    else:
        connections = data.get("connections") or []

    if not isinstance(connections, list):
        print(f"[WARN] Unexpected connections type for {departure_name}->{arrival_name}: {type(connections)}")
        return []

    rows: List[Dict[str, Any]] = []

    for conn in connections:
        if not isinstance(conn, dict):
            continue
        conn_id = conn.get("id")
        if not conn_id:
            continue

        details = get_connection_details(str(conn_id))
        if not details:
            continue

        sub_rows = extract_lahti_rows_from_connection(conn, details, date_obj)
        if sub_rows:
            rows.extend(sub_rows)

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return rows


def main():
    """Main function: iterate through dates and cities, fetch data, save to CSV"""
    fieldnames = [
        "date",
        "time",
        "lahti_stop_id",
        "platform_code",
        "lahti_stop_name",
        "route_id",
        "route_short_name",
        "route_long_name",
        "route_type",
        "trip_id",
        "trip_headsign",
        "from_station",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        cur = START_DATE
        total_rows = 0

        while cur <= END_DATE:
            print(f"=== {cur} ===")
            day_rows: List[Dict[str, Any]] = []

            for city in MAIN_CITIES:
                # Skip Lahti as departure — we're looking for routes arriving in / passing through Lahti
                if city.lower().startswith("lahti"):
                    continue

                rows = fetch_for_one_direction(cur, city, "Lahti")
                if rows:
                    day_rows.extend(rows)

                time.sleep(SLEEP_BETWEEN_REQUESTS)

            for row in day_rows:
                writer.writerow(row)

            total_rows += len(day_rows)
            print(f"  {len(day_rows)} rows for {cur}, total {total_rows}")
            cur += dt.timedelta(days=1)

    print(f"Done. Saved {total_rows} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()