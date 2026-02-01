# Stockholm High School Data Export Specification

## Overview

This specification describes how to fetch and export detailed information about high schools in Stockholm from the Ednia API into a CSV format, including travel times from a specified origin using public transport.

## Configuration

### Required API Keys

| Service | Purpose | How to obtain |
|---------|---------|---------------|
| ResRobot v2.1 | Public transport travel times | Register at [trafiklab.se](https://www.trafiklab.se/), create a project, request ResRobot v2.1 key |

### Rate Limits (ResRobot)

| Tier | Requests/min | Requests/month |
|------|--------------|----------------|
| Bronze (free) | 45 | 30,000 |
| Silver | 60 | 200,000 |
| Gold | 200 | 1,000,000 |

### User Configuration

| Parameter | Description | Example |
|-----------|-------------|---------|
| `originStopName` | Starting point for travel time calculations | "T-Centralen" |
| `originStopId` | ResRobot stop ID (resolved from name) | "740020749" |

## API Endpoints

### 1. List Schools

**Endpoint:** `POST https://api.ednia.se/elysia/highSchool/recommend`

**Request Body:**
```json
{
  "offset": 0,
  "take": 500,
  "filter": {
    "projection": "programs",
    "municipality": "stockholm",
    "query": "",
    "programs": [],
    "admissionPointsMin": 0,
    "admissionPointsMax": 340
  }
}
```

**Response:**
```json
{
  "hasMore": false,
  "offset": 500,
  "result": [
    {
      "id": "uuid",
      "name": "School Name",
      "municipality": "stockholm",
      "programs": ["NA", "SA", "EK"],
      "slug": "school-slug",
      "location": "District",
      "image": "https://cdn.ednia.se/...",
      "events": []
    }
  ]
}
```

**Notes:**
- Set `take: 500` to fetch all schools in one request (currently ~179 schools)
- The `programs` array contains program codes offered by each school

### 2. Get Program Details

**Endpoint:** `GET https://api.ednia.se/elysia/highSchool/getProgramPage`

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `highSchoolId` | UUID | The school's unique identifier |
| `programCode` | string | Program code (e.g., NA, SA, EK) |
| `municipality` | string | Municipality name (e.g., stockholm) |

**Example:**
```
GET /elysia/highSchool/getProgramPage?highSchoolId=60499479-283c-48c3-bed7-3adb660ebc10&programCode=NA&municipality=stockholm
```

**Response Structure:**
```json
{
  "programPage": {
    "programCode": "NA",
    "school": {
      "id": "uuid",
      "name": "School Name",
      "slug": "school-slug",
      "image": "url"
    },
    "educationStats": {
      "averageGrade": 16.3,
      "flowthroughRate": 0.98
    },
    "femaleRatio": 0.52,
    "studyPaths": [
      {
        "name": "Naturvetenskap",
        "compareNumber": "320",
        "min": "320",
        "median": 325,
        "admitted": 68
      }
    ]
  }
}
```

### 3. Stop Lookup (ResRobot)

**Endpoint:** `GET https://api.resrobot.se/v2.1/location.name`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `accessId` | string | Yes | Your ResRobot API key |
| `input` | string | Yes | Search query (stop/location name) |
| `format` | string | Yes | Response format: `json` or `xml` |

**Example:**
```
GET https://api.resrobot.se/v2.1/location.name?input=T-Centralen&format=json&accessId=YOUR_API_KEY
```

**Response:**
```json
{
  "StopLocation": [
    {
      "id": "A=1@O=Stockholm City@X=18059658@Y=59331134@U=74@L=740020749@",
      "extId": "740020749",
      "name": "Stockholm City (Stockholm kn)",
      "lon": 18.059658,
      "lat": 59.331134,
      "weight": 32373
    }
  ]
}
```

**Notes:**
- Use `extId` as the stop ID for other ResRobot APIs
- Append `?` to search term for fuzzy matching (e.g., `input=Göteborg?`)
- Search for school names directly to find nearby stops

### 4. Route Planner (ResRobot)

**Endpoint:** `GET https://api.resrobot.se/v2.1/trip`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `accessId` | string | Yes | Your ResRobot API key |
| `originId` | string | Yes* | Origin stop ID (from Stop Lookup) |
| `destId` | string | Yes* | Destination stop ID |
| `originCoordLat` | float | Yes* | Origin latitude (alternative to originId) |
| `originCoordLong` | float | Yes* | Origin longitude (alternative to originId) |
| `destCoordLat` | float | Yes* | Destination latitude (alternative to destId) |
| `destCoordLong` | float | Yes* | Destination longitude (alternative to destId) |
| `format` | string | Yes | Response format: `json` or `xml` |
| `date` | string | No | Search date (YYYY-MM-DD) |
| `time` | string | No | Search time (HH:MM) |

*Either ID or coordinates required for origin/destination

**Example:**
```
GET https://api.resrobot.se/v2.1/trip?originId=740020749&destId=740020752&format=json&accessId=YOUR_API_KEY
```

**Response:**
```json
{
  "Trip": [
    {
      "duration": "PT25M",
      "Origin": {
        "name": "Stockholm City",
        "time": "08:00:00",
        "date": "2026-02-01"
      },
      "Destination": {
        "name": "Kungsholmens gymnasium",
        "time": "08:25:00",
        "date": "2026-02-01"
      },
      "LegList": {
        "Leg": [...]
      }
    }
  ]
}
```

**Duration Format:**
- ISO 8601 duration format
- `PT25M` = 25 minutes
- `PT1H15M` = 1 hour 15 minutes
- Parse with regex: `/PT(?:(\d+)H)?(?:(\d+)M)?/`

## Program Codes

| Code | Program Name |
|------|--------------|
| NA | Naturvetenskapsprogrammet |
| SA | Samhällsvetenskapsprogrammet |
| EK | Ekonomiprogrammet |
| TE | Teknikprogrammet |
| ES | Estetiska programmet |
| HU | Humanistiska programmet |
| EE | El- och energiprogrammet |
| BF | Barn- och fritidsprogrammet |
| FS | Försäljnings- och serviceprogrammet |
| RL | Restaurang- och livsmedelsprogrammet |
| VF | VVS- och fastighetsprogrammet |
| BA | Bygg- och anläggningsprogrammet |
| VO | Vård- och omsorgsprogrammet |
| FT | Fordons- och transportprogrammet |
| IN | Industritekniska programmet |
| IM | Introduktionsprogrammet |

## CSV Output Format

### Columns

| Column | Source | Description |
|--------|--------|-------------|
| `school_name` | `programPage.school.name` | Name of the school |
| `school_location` | `recommend.result[].location` | District/area of the school |
| `program` | Query parameter | Program code (NA, SA, etc.) |
| `averageGrade` | `programPage.educationStats.averageGrade` | Average grade of students |
| `flowthroughRate` | `programPage.educationStats.flowthroughRate` | Graduation rate (0-1) |
| `femaleRatio` | `programPage.femaleRatio` | Female student ratio (0-1) |
| `studyPath_name` | `programPage.studyPaths[].name` | Name of the study path/profile |
| `compareNumber` | `programPage.studyPaths[].compareNumber` | Admission points for comparison |
| `min` | `programPage.studyPaths[].min` | Minimum admission points |
| `median` | `programPage.studyPaths[].median` | Median admission points |
| `admitted` | `programPage.studyPaths[].admitted` | Number of admitted students |
| `travel_time_minutes` | ResRobot trip API | Travel time from origin in minutes |

### Data Structure

- **One row per study path**: A school/program combination can have multiple study paths
- Example: Kungsholmens gymnasium NA has 3 study paths (Naturvetenskap, Musik körsång, Natural Science Program)

### Sample Output

```csv
school_name,school_location,program,averageGrade,flowthroughRate,femaleRatio,studyPath_name,compareNumber,min,median,admitted,travel_time_minutes
"Sjölins Gymnasium Södermalm","Södermalm","NA","16.3","0.98","0.52","Naturvetenskap","320","320",325,68,12
"Sjölins Gymnasium Södermalm","Södermalm","NA","16.3","0.98","0.52","Naturvetenskap och samhälle","312.5","312.5",320,28,12
"Kungsholmens gymnasium","Kungsholmen","NA","18.5","0.95","0.59","Naturvetenskap","330","330",337.5,99,8
"Kungsholmens gymnasium","Kungsholmen","NA","18.5","0.95","0.59","Musik, estetiskt område, körsång","617.5","617.5",660,66,8
```

## Process

### Phase 1: Setup

1. **Resolve origin stop ID**
   - Call ResRobot Stop Lookup with user's origin (e.g., "T-Centralen")
   - Store the `extId` for use in travel time calculations

### Phase 2: Fetch School Data

2. **Fetch all schools** from the Ednia recommend endpoint with `take: 500`
3. **For each school:**
   - Store `id`, `name`, `location`, `municipality`, and `programs` array

### Phase 3: Fetch Program Details & Travel Times

4. **For each school/program combination:**
   - Call Ednia `getProgramPage` to get education stats and study paths
   - Call ResRobot Stop Lookup with school name to find nearest stop
   - Call ResRobot Route Planner to get travel time from origin
   - Cache travel time per school (same for all programs at that school)

5. **For each study path** in the response, output one CSV row with all data

### Phase 4: Output

6. **Write CSV** with all columns
7. **Handle missing data** gracefully (some programs may return N/A values)

### Optimization Notes

- **Cache travel times**: Only calculate once per school, not per program/study path
- **Batch lookups**: Group API calls where possible
- **Rate limiting**: Add delays between ResRobot calls (max 45/min on free tier)
- **Fallback**: If school name not found in ResRobot, try `{school_name} {location}` or mark as N/A

## Notes

### Ednia API
- Some study paths include audition/test points (e.g., music programs), resulting in `compareNumber` values above 340
- The `municipality` parameter should match the school's municipality (some results may include nearby municipalities like `nacka`, `taby`, `sundbyberg`)

### ResRobot API
- Travel times are calculated for a default departure time (e.g., 08:00 on a weekday)
- Times may vary based on time of day and day of week
- Some schools may not be directly findable in ResRobot; use fuzzy search or coordinates as fallback
- The free tier (Bronze) allows 30,000 requests/month, sufficient for ~179 schools with retries

### Rate Limiting
- Ednia API: No documented limits, but add 100ms delays between calls
- ResRobot API: Max 45 requests/minute on free tier; add 1.5s delays between calls

## Error Handling

| Scenario | Handling |
|----------|----------|
| School not found in ResRobot | Try fuzzy search with `?`, try `{name} {location}`, or mark as N/A |
| No route found | Mark travel_time_minutes as N/A |
| API rate limit hit | Exponential backoff with retry |
| Missing educationStats | Mark averageGrade/flowthroughRate as N/A |
| Empty studyPaths | Skip program (no rows to output) |
