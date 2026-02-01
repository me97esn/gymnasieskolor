#!/usr/bin/env python3
"""
Stockholm High School Data Export

Fetches high school data from Ednia API and calculates travel times
from a configurable origin using ResRobot public transport API.

Usage:
    python export.py                           # Uses default origin (Björkhagen)
    python export.py --origin "T-Centralen"    # Custom origin
    python export.py --output schools.csv      # Custom output file
    python export.py --limit 5                 # Limit schools (for testing)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    resrobot_api_key: str
    origin_name: str
    output_file: str
    school_limit: Optional[int]
    delay_ednia: float = 0.1  # 100ms between Ednia calls
    delay_resrobot: float = 1.5  # 1.5s between ResRobot calls (45/min limit)


def load_env() -> dict:
    """Load environment variables from .env file."""
    env = {}
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
    return env


def http_get(url: str) -> dict:
    """Make HTTP GET request and return JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": "GymnasierExport/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def http_post(url: str, data: dict) -> dict:
    """Make HTTP POST request with JSON body and return JSON."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GymnasierExport/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def parse_duration(duration: str) -> Optional[int]:
    """Parse ISO 8601 duration (e.g., PT25M, PT1H15M) to minutes."""
    if not duration:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


class ResRobotClient:
    """Client for ResRobot public transport API."""

    BASE_URL = "https://api.resrobot.se/v2.1"

    def __init__(self, api_key: str, delay: float = 1.5):
        self.api_key = api_key
        self.delay = delay
        self.last_request = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.time()

    def lookup_stop(self, query: str) -> Optional[dict]:
        """Search for a stop by name. Returns first Stockholm result or None."""
        self._rate_limit()
        encoded = urllib.parse.quote(query)
        url = f"{self.BASE_URL}/location.name?input={encoded}&format=json&accessId={self.api_key}"

        try:
            data = http_get(url)
            locations = data.get("stopLocationOrCoordLocation", [])

            # Prefer Stockholm results
            for loc in locations:
                stop = loc.get("StopLocation", {})
                name = stop.get("name", "")
                if "Stockholm" in name or "stockholm" in name.lower():
                    return stop

            # Fall back to first result
            if locations:
                return locations[0].get("StopLocation")

            return None
        except Exception as e:
            print(f"  Warning: Stop lookup failed for '{query}': {e}", file=sys.stderr)
            return None

    def get_travel_time(self, origin_id: str, dest_id: str) -> Optional[int]:
        """Get travel time in minutes between two stops."""
        self._rate_limit()
        url = (
            f"{self.BASE_URL}/trip?"
            f"originId={origin_id}&destId={dest_id}&format=json&accessId={self.api_key}"
        )

        try:
            data = http_get(url)
            trips = data.get("Trip", [])
            if trips:
                duration = trips[0].get("duration")
                return parse_duration(duration)
            return None
        except Exception as e:
            print(f"  Warning: Trip lookup failed: {e}", file=sys.stderr)
            return None


class EdniaClient:
    """Client for Ednia high school API."""

    BASE_URL = "https://api.ednia.se/elysia/highSchool"

    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.last_request = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.time()

    def get_schools(self, municipality: str = "stockholm", limit: int = 500) -> list:
        """Fetch all schools from the recommend endpoint."""
        self._rate_limit()
        url = f"{self.BASE_URL}/recommend"
        data = {
            "offset": 0,
            "take": limit,
            "filter": {
                "projection": "programs",
                "municipality": municipality,
                "query": "",
                "programs": [],
                "admissionPointsMin": 0,
                "admissionPointsMax": 340,
            },
        }
        response = http_post(url, data)
        return response.get("result", [])

    def get_program_page(
        self, school_id: str, program_code: str, municipality: str
    ) -> Optional[dict]:
        """Fetch detailed program information for a school."""
        self._rate_limit()
        params = urllib.parse.urlencode(
            {
                "highSchoolId": school_id,
                "programCode": program_code,
                "municipality": municipality,
            }
        )
        url = f"{self.BASE_URL}/getProgramPage?{params}"

        try:
            response = http_get(url)
            return response.get("programPage")
        except Exception as e:
            print(f"  Warning: Failed to fetch program page: {e}", file=sys.stderr)
            return None


def find_school_stop(
    resrobot: ResRobotClient, school_name: str, location: str
) -> Optional[dict]:
    """Try multiple strategies to find a stop near a school."""
    # Strategy 1: Search for school name directly
    stop = resrobot.lookup_stop(school_name)
    if stop:
        return stop

    # Strategy 2: Search for school name + Stockholm
    stop = resrobot.lookup_stop(f"{school_name} Stockholm")
    if stop:
        return stop

    # Strategy 3: Search for district/location
    if location:
        stop = resrobot.lookup_stop(f"{location} Stockholm")
        if stop:
            return stop

    return None


def export_schools(config: Config):
    """Main export function."""
    print(f"Starting export with origin: {config.origin_name}")
    print(f"Output file: {config.output_file}")

    # Initialize clients
    resrobot = ResRobotClient(config.resrobot_api_key, config.delay_resrobot)
    ednia = EdniaClient(config.delay_ednia)

    # Phase 1: Resolve origin stop
    print("\n[Phase 1] Resolving origin stop...")
    origin_stop = resrobot.lookup_stop(config.origin_name)
    if not origin_stop:
        print(f"Error: Could not find origin stop '{config.origin_name}'", file=sys.stderr)
        sys.exit(1)

    origin_id = origin_stop.get("extId")
    origin_name = origin_stop.get("name")
    print(f"  Origin: {origin_name} (ID: {origin_id})")

    # Phase 2: Fetch all schools
    print("\n[Phase 2] Fetching schools from Ednia...")
    schools = ednia.get_schools()
    if config.school_limit:
        schools = schools[: config.school_limit]
    print(f"  Found {len(schools)} schools")

    # Phase 3: Fetch program details and travel times
    print("\n[Phase 3] Fetching program details and travel times...")
    rows = []
    travel_time_cache = {}  # Cache travel times per school

    for i, school in enumerate(schools):
        school_id = school["id"]
        school_name = school["name"]
        school_location = school.get("location", "")
        municipality = school.get("municipality", "stockholm")
        programs = school.get("programs", [])

        print(f"  [{i+1}/{len(schools)}] {school_name}")

        # Get travel time (cached per school)
        if school_id not in travel_time_cache:
            stop = find_school_stop(resrobot, school_name, school_location)
            if stop:
                dest_id = stop.get("extId")
                travel_time = resrobot.get_travel_time(origin_id, dest_id)
                travel_time_cache[school_id] = travel_time
                if travel_time:
                    print(f"    Travel time: {travel_time} min")
            else:
                travel_time_cache[school_id] = None
                print(f"    Travel time: N/A (stop not found)")

        travel_time = travel_time_cache[school_id]

        # Fetch each program
        for program in programs:
            program_page = ednia.get_program_page(school_id, program, municipality)
            if not program_page:
                continue

            education_stats = program_page.get("educationStats", {})
            female_ratio = program_page.get("femaleRatio")
            study_paths = program_page.get("studyPaths", [])

            if not study_paths:
                continue

            for study_path in study_paths:
                row = {
                    "school_name": school_name,
                    "school_location": school_location,
                    "program": program,
                    "averageGrade": education_stats.get("averageGrade", ""),
                    "flowthroughRate": education_stats.get("flowthroughRate", ""),
                    "femaleRatio": female_ratio if female_ratio is not None else "",
                    "studyPath_name": study_path.get("name", ""),
                    "compareNumber": study_path.get("compareNumber", ""),
                    "min": study_path.get("min", ""),
                    "median": study_path.get("median", ""),
                    "admitted": study_path.get("admitted", ""),
                    "travel_time_minutes": travel_time if travel_time is not None else "",
                }
                rows.append(row)

    # Phase 4: Write CSV
    print(f"\n[Phase 4] Writing {len(rows)} rows to {config.output_file}...")
    fieldnames = [
        "school_name",
        "school_location",
        "program",
        "averageGrade",
        "flowthroughRate",
        "femaleRatio",
        "studyPath_name",
        "compareNumber",
        "min",
        "median",
        "admitted",
        "travel_time_minutes",
    ]

    with open(config.output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! Exported {len(rows)} study paths from {len(schools)} schools.")


def main():
    parser = argparse.ArgumentParser(
        description="Export Stockholm high school data with travel times"
    )
    parser.add_argument(
        "--origin",
        default="Björkhagen",
        help="Starting point for travel time calculations (default: Björkhagen)",
    )
    parser.add_argument(
        "--output",
        default="schools.csv",
        help="Output CSV file (default: schools.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of schools (for testing)",
    )
    args = parser.parse_args()

    # Load API key
    env = load_env()
    api_key = env.get("RESROBOT_API_KEY") or os.environ.get("RESROBOT_API_KEY")
    if not api_key:
        print("Error: RESROBOT_API_KEY not found in .env or environment", file=sys.stderr)
        sys.exit(1)

    config = Config(
        resrobot_api_key=api_key,
        origin_name=args.origin,
        output_file=args.output,
        school_limit=args.limit,
    )

    export_schools(config)


if __name__ == "__main__":
    main()
