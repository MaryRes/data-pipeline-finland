# Data Pipeline: Lahti Region (May 2026)

A collection of Python scripts for collecting transportation and event data in the Lahti region for May 2026. Built as part of a data acquisition project for a taxi shift management application.

## Data Sources

| Data Type | Source | Method |
| :--- | :--- | :--- |
| Bus schedules | Matkahuolto API | REST API (Basic Auth) |
| Train schedules | Digitraffic GTFS | Public GTFS feed |
| Concert events | Sibeliustalo | Web scraping (BeautifulSoup) |
| Theatre performances | Lahden Kaupunginteatteri | Web scraping (BeautifulSoup) |

## Project Structure

```markdown
data-pipeline-finland/
├── .env.example # Environment variables template
├── requirements.txt # Python dependencies
├── api_explorer.py # Matkahuolto API exploration script
├── bus_scraper.py # Bus schedule scraper (Matkahuolto API)
├── train_parser.py # Train schedule parser (Digitraffic GTFS)
├── sibeliustalo_scraper.py # Sibelius Hall concert events
├── teatteri_scraper.py # Lahti City Theatre performances
├── event_end_time_calculator.py # Calculate event end times
└── matkahuolto_test.py # API test / valid values discovery
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/MaryRes/data-pipeline-finland.git
cd data-pipeline-finland
```

### 2. Create and activate virtual environment

```bash
python -m venv venv
source venv/bin/activate        # On macOS/Linux
venv\Scripts\activate           # On Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API credentials

Copy .env.example to .env and add your Matkahuolto API credentials:

```bash
cp .env.example .env
```
Then edit .env:

MATKAHUOLTO_USER_ID=your_username_here

MATKAHUOLTO_PASSWORD=your_password_here

# Usage
## Run bus schedule scraper

```bash
python bus_scraper.py
```
Output: lahti_trains_compact_may2026.csv

## Run event scrapers
```bash
python sibeliustalo_scraper.py   # Concert events
python teatteri_scraper.py        # Theatre performances
```
## Calculate event end times
```bash
python event_end_time_calculator.py
```

## Output Data Format

All scripts output CSV files with the following structure:

| Column | Description |
| :--- | :--- |
| `date` | Event / arrival date (YYYY-MM-DD) |
| `time` | Time (HH:MM:SS) |
| `name` | Event or route name |
| `stage` / `from_station` | Venue name or origin city |
| `source_url` | Original data source URL (for events) |
