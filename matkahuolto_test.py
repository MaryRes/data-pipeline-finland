import base64
import requests
import os
from dotenv import load_dotenv

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


def get_auth_header():
    """Generate Basic Authentication header for API requests"""
    raw = f"{USER_ID}:{PASSWORD}"
    token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def request_minfo(path, params):
    """Make authenticated request to Matkahuolto API and print debug info"""
    url = f"{BASE_URL}{path}"
    headers = {
        **get_auth_header(),
        "Accept": "application/vnd.matkahuolto.minfo.api-v1+json",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    print("URL:", resp.url)
    print("Status:", resp.status_code)
    print("Raw text (first 300 chars):")
    print(resp.text[:300])
    resp.raise_for_status()
    return resp.json()


def main():
    """Test script to explore Matkahuolto API structure and routes to Lahti"""
    # 1) Test the API root endpoint
    api_info = request_minfo("/api", {})
    print("API root type:", type(api_info))

    # 2) Fetch a sample connection from Helsinki to Lahti
    connections = request_minfo(
        "/connections",
        {
            "departureStopAreaName": "Helsinki",
            "arrivalStopAreaName": "Lahti",
            "departureDate": "2026-05-01",
            "allSchedules": 0,
            "ticketTravelType": 0,
        },
    )
    print("Type of connections:", type(connections))

    if isinstance(connections, list) and connections:
        conn = connections[0]
    elif isinstance(connections, dict) and connections.get("connections"):
        conn = connections["connections"][0]
    else:
        print("No connections found in response")
        return

    conn_id = conn.get("id")
    print("Sample connection id:", conn_id)

    # 3) Fetch detailed information for that connection
    details = request_minfo(f"/connection/{conn_id}/details", {})
    part_trips = details.get("partTrips") or []
    if not part_trips:
        print("No partTrips in response")
        return

    route = part_trips[0].get("route") or []
    print("Stops on route:")
    for s in route:
        stop_name = (s.get("stopAreaName") or s.get("placeName") or "").strip()
        place_name = (s.get("placeName") or "").strip()
        arr = (s.get("arrivalTime") or s.get("departureTime") or "").strip()
        print("-", stop_name, "|", place_name, "|", arr)


if __name__ == "__main__":
    main()