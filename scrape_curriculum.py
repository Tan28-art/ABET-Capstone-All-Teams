import re
import csv
import requests
from bs4 import BeautifulSoup

URL = "https://degrees.apps.asu.edu/checksheet/2026/CES/ESCSEBSE/null?init=false&nopassive=true"

def clean_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def parse_course_text(text: str):
    t = clean_ws(text)
    m = re.match(r"^([A-Z/]+)\s+(\d+[A-Z]?)\s+(.*)$", t)
    if not m:
        return ("", "", t)
    return (m.group(1), m.group(2), m.group(3))

def find_credit_hours(tr) -> str:
    mobile = tr.find(class_="mobile-view")
    if mobile:
        txt = clean_ws(mobile.get_text(" ", strip=True))
        m = re.search(r"Credit Hours\s+(\d+)", txt, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""

def main():
    resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    COL_COURSE = "Course (Department, Number, Title)"
    COL_RE = "Required/Elective"
    COL_MATH = "Math & Basic Sciences (Credit Hours)"
    COL_ENG = "Engineering Topics (Credit Hours)"
    COL_OTHER = "Other (Credit Hours)"
    COL_TERMS = "Last Two Terms Course Offered"
    COL_ENROLL = "Max Enrollment Last Two Terms"

    rows = []

    for tr in soup.find_all("tr"):
        cls = tr.get("class", [])

        if "subsection-header" in cls:
            td = tr.find("td", class_="subsection-name")
            group_name = clean_ws(td.get_text(" ", strip=True)) if td else ""
            if group_name:
                rows.append({
                    COL_COURSE: group_name,
                    COL_RE: "",
                    COL_MATH: "",
                    COL_ENG: "",
                    COL_OTHER: "",
                    COL_TERMS: "",
                    COL_ENROLL: "",
                })
            continue

        if "checksheet-requirement" in cls:
            a = tr.find("a", class_="ttCourse")
            if not a:
                continue

            course_text = clean_ws(a.get_text(" ", strip=True))
            dept, num, title = parse_course_text(course_text)

            course_cell = course_text
            if dept and num and title:
                course_cell = f"{dept}{num}: {title}"

            credit_hours = find_credit_hours(tr)

            rows.append({
                COL_COURSE: course_cell,
                COL_RE: "",          # always blank for now
                COL_MATH: "",
                COL_ENG: credit_hours,  # keep as a placeholder column if you want hours somewhere
                COL_OTHER: "",
                COL_TERMS: "",
                COL_ENROLL: "",
            })

    out_file = "table_5_1_curriculum_scraped.csv"
    fieldnames = [COL_COURSE, COL_RE, COL_MATH, COL_ENG, COL_OTHER, COL_TERMS, COL_ENROLL]

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Saved {len(rows)} rows to {out_file}")

if __name__ == "__main__":
    main()