import gtfs_kit as gk
import requests
import pandas as pd
from pathlib import Path
import tempfile

# Public GTFS feed URL (no authentication required)
GTFS_URL = "https://rata.digitraffic.fi/api/v1/trains/gtfs-passenger-stops.zip"
LAHTI_STOP_NAME = "Lahti"
OUTPUT_CSV = "lahti_trains_compact_may2026.csv"


def load_feed(url, dst):
    """Download GTFS feed from URL and load it using gtfs_kit."""
    r = requests.get(url)
    r.raise_for_status()
    Path(dst).write_bytes(r.content)
    return gk.read_feed(dst, dist_units='km')


def service_dates_for(service_id, cal, cal_dates, may_start, may_end):
    """Get all service dates in May for a given service_id."""
    dates = []
    # From calendar ranges
    if not cal.empty:
        rows = cal[cal['service_id'] == service_id]
        for _, r in rows.iterrows():
            s = r['start_date']
            e = r['end_date']
            if pd.isna(s) or pd.isna(e):
                continue
            rng_start = max(s, may_start)
            rng_end = min(e, may_end)
            if rng_start <= rng_end:
                dr = pd.date_range(rng_start, rng_end, freq='D')
                # Weekday filtering if present
                if set(['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                        'saturday', 'sunday']).issubset(r.index):
                    flags = {
                        0: r['monday'],
                        1: r['tuesday'],
                        2: r['wednesday'],
                        3: r['thursday'],
                        4: r['friday'],
                        5: r['saturday'],
                        6: r['sunday']
                    }
                    dr = [d for d in dr if flags[d.weekday()] == 1]
                dates.extend(dr)

    # Add from calendar_dates
    if not cal_dates.empty:
        adds = cal_dates[(cal_dates['service_id'] == service_id) &
                         (cal_dates['exception_type'] == 1)]
        adds = adds[(adds['date'] >= may_start) & (adds['date'] <= may_end)]
        dates.extend(adds['date'].tolist())

        # Remove exceptions
        removes = cal_dates[(cal_dates['service_id'] == service_id) &
                            (cal_dates['exception_type'] == 2)]
        remset = set(removes['date'].tolist())
        dates = [d for d in dates if d not in remset]

    return sorted(set(dates))


def parse_gtfs_time(base_date, timestr):
    """Parse GTFS time format (may exceed 24h) into a timestamp."""
    if pd.isna(timestr):
        return pd.NaT
    parts = timestr.split(':')
    if len(parts) != 3:
        return pd.NaT
    h, m, s = map(int, parts)
    day_offset = h // 24
    hour = h % 24
    return (pd.Timestamp(base_date.year, base_date.month, base_date.day,
                         hour, m, s) + pd.Timedelta(days=day_offset))


def main():
    """Download GTFS feed, extract Lahti train arrivals for May 2026, save to CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gtfs_path = Path(tmpdir) / "gtfs.zip"
        feed = load_feed(GTFS_URL, gtfs_path)

        # Find stops with exact name 'Lahti'
        lahti_stops = feed.stops[feed.stops['stop_name'].fillna('').str.strip() == LAHTI_STOP_NAME].copy()
        if lahti_stops.empty:
            raise SystemExit("No stops found with exact stop_name == 'Lahti' in this feed")

        lahti_ids = lahti_stops['stop_id'].tolist()

        # Prepare calendar and calendar_dates
        cal = feed.calendar.copy() if hasattr(feed, 'calendar') else pd.DataFrame()
        if not cal.empty:
            cal['start_date'] = pd.to_datetime(cal['start_date'], format='%Y%m%d', errors='coerce')
            cal['end_date'] = pd.to_datetime(cal['end_date'], format='%Y%m%d', errors='coerce')

        cal_dates = getattr(feed, 'calendar_dates', pd.DataFrame())
        if not cal_dates.empty:
            cal_dates['date'] = pd.to_datetime(cal_dates['date'], format='%Y%m%d', errors='coerce')

        may_start = pd.to_datetime("2026-05-01")
        may_end = pd.to_datetime("2026-05-31")

        # Filter stop_times for Lahti stops
        st = feed.stop_times[feed.stop_times['stop_id'].isin(lahti_ids)].copy()
        if st.empty:
            raise SystemExit("No stop_times for Lahti in this feed")

        # Merge with trips and routes
        st = st.merge(feed.trips[['trip_id', 'route_id', 'service_id', 'trip_headsign']],
                      on='trip_id', how='left')
        st = st.merge(feed.routes[['route_id', 'route_short_name', 'route_long_name', 'route_type']],
                      on='route_id', how='left')

        # Build rows by expanding service dates
        rows = []
        grouped = st.groupby('trip_id')

        for trip_id, grp in grouped:
            service_id = grp['service_id'].iloc[0]
            sdates = service_dates_for(service_id, cal, cal_dates, may_start, may_end)
            if not sdates:
                continue

            for sd in sdates:
                for _, r in grp.iterrows():
                    arrival_dt = parse_gtfs_time(sd, r.get('arrival_time'))
                    if pd.isna(arrival_dt):
                        continue

                    row = {
                        'service_date': sd.date().isoformat(),
                        'arrival_dt': arrival_dt,
                        'lahti_stop_id': r.get('stop_id'),
                        'platform_code': None,
                        'lahti_stop_name': LAHTI_STOP_NAME,
                        'route_id': r.get('route_id'),
                        'route_short_name': r.get('route_short_name'),
                        'route_long_name': r.get('route_long_name'),
                        'route_type': r.get('route_type'),
                        'trip_id': r.get('trip_id'),
                        'trip_headsign': r.get('trip_headsign')
                    }
                    rows.append(row)

        if not rows:
            raise SystemExit("No trains found for Lahti in May 2026 according to this feed's calendar")

        df = pd.DataFrame(rows)

        # Add platform_code from stops if available
        stops_map = lahti_stops.set_index('stop_id')[['platform_code']].to_dict()['platform_code']
        df['platform_code'] = df['lahti_stop_id'].map(stops_map)

        # Exclude trips that start from Lahti (first stop == Lahti)
        first_stops = (feed.stop_times.sort_values(['trip_id', 'stop_sequence'])
                       .groupby('trip_id', as_index=False)
                       .first()[['trip_id', 'stop_id']])
        first_stops = first_stops.merge(feed.stops[['stop_id', 'stop_name']],
                                        on='stop_id', how='left')
        first_stops = first_stops.rename(columns={'stop_name': 'from_station'})
        df = df.merge(first_stops[['trip_id', 'from_station']], on='trip_id', how='left')
        df = df[df['from_station'].fillna('').str.strip().eq(LAHTI_STOP_NAME) == False].copy()

        # Final compact formatting
        df['date'] = df['arrival_dt'].dt.strftime('%Y-%m-%d')
        df['time'] = df['arrival_dt'].dt.strftime('%H:%M:%S')

        out_cols = ['date', 'time', 'lahti_stop_id', 'platform_code', 'lahti_stop_name',
                    'route_id', 'route_short_name', 'route_long_name', 'route_type',
                    'trip_id', 'trip_headsign', 'from_station']
        out_cols = [c for c in out_cols if c in df.columns]
        out = df[out_cols].sort_values(['date', 'time']).reset_index(drop=True)
        out.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print("Saved:", OUTPUT_CSV)


if __name__ == "__main__":
    main()