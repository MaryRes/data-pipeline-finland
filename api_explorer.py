import base64
import json
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

CITIES = [
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

def get_auth_header():
    """Generate Basic Authentication header for API requests"""
    raw = f"{USER_ID}:{PASSWORD}"
    token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}

def main():
    headers = {
        **get_auth_header(),
        "Accept": "application/vnd.matkahuolto.minfo.api-v1+json",
    }

    for city in CITIES:
        params = {
            "departureStopAreaName": city,
            "arrivalStopAreaName": "Lahti",
            "departureDate": "2026-05-01",
            "allSchedules": 0,
            "ticketTravelType": 0,
        }
        url = f"{BASE_URL}/connections"
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        print("====", city, "====")
        print("Status:", resp.status_code)
        txt = resp.text
        print(txt[:500])

        # Extract valid values from 400 error response
        if resp.status_code == 400:
            try:
                data = resp.json()
            except json.JSONDecodeError:
                continue
            for err in data.get("errors", []):
                if err.get("fieldId") == "departureStopAreaId":
                    vals = err.get("validValues") or []
                    for v in vals:
                        print("  valid:", v.get("id"), "|", v.get("description"))
        print()

if __name__ == "__main__":
    main()