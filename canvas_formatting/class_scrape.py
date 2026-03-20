from typing import Optional, Dict, Any
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
def scrapeASUClassSearchProfessor(year: str, endOfCourseCode: str) -> Optional[Dict[str, Any]]:
    """
    Scrapes ASU Class Search for professor information based on the provided year and course code.
    param year: The year and term code (e.g., "2261" for Spring 2026).First digit (2) → Century marker (2000s), Next two digits (26) → Year → 2026, Last digit (1) → Session / semester
    type year: str
    param endOfCourseCode: The end portion of the course code to search for (e.g., "2026SpringC-T-CSE460-11252" would be 11252).
    type endOfCourseCode: str
    return: A dictionary containing the scraped data, or None if an error occurs. This gives a json which has the professors name.
    type return: Optional[Dict[str, Any]]
    """
    API_URL = "https://eadvs-cscc-catalog-api.apps.asu.edu/catalog-microservices/api/v1/search/classes"

    params = {
        "refine": "Y",
        "campusOrOnlineSelection": "A",
        "honors": "F",
        "keywords": endOfCourseCode,
        "promod": "F",
        "searchType": "all",
        "term": year,
    }

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": "Bearer null",  # <-- match DevTools literally
        "Origin": "https://catalog.apps.asu.edu",
        "Referer": "https://catalog.apps.asu.edu/",
        "User-Agent": "Mozilla/5.0",
    }

    session = requests.Session()

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=[403, 429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)

    resp = session.get(API_URL, params=params, headers=headers, timeout=30)

    print("Status:", resp.status_code)
    print("Content-Type:", resp.headers.get("content-type"))

    if resp.status_code != 200:
        print(f"Error: Received status code {resp.status_code} from ASU API")
        return None

    if "application/json" in (resp.headers.get("content-type") or ""):
        data = resp.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print("Error: Expected JSON response but got:", resp.headers.get("content-type"))
        return None



