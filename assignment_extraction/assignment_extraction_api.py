from collections import defaultdict
import csv
import enum
import io
import logging
import tempfile
import time
import requests
import json
import os
import re
import shutil
from datetime import datetime, timezone
from fetch_grades import CanvasGradesFetcher
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import Annotated, Optional
import PyPDF2
import docx
from csv_filter import RosterMap, parse_roster_for_major_map
from xhtml2pdf import pisa

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("extraction.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = FastAPI()


# Enums
class TaskType(str, enum.Enum):
    """Valid task types for the process-course-with-roster endpoint."""

    EXTRACT = "extract"
    ABET = "abet"
    ALL = "all"


# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
ABET_TAG = "abet"

# SETUP
TEMP_DIR_PREFIX = "abet_extraction_"


# Helpers
def create_temp_dir() -> str:
    """Creates a unique temporary directory for a single request."""
    return tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)


def cleanup_temp_dir(temp_dir: str):
    """Safely removes a temporary directory if it exists."""
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        logger.info("Temp directory cleaned up: %s", temp_dir)


def xls_bytes_to_csv_stream(file_bytes: bytes) -> io.StringIO:
    """Convert a PeopleSoft .xls file (HTML table) to an in-memory CSV stream.

    ASU roster exports from PeopleSoft are HTML tables saved with a .xls
    extension.  The HTML is often malformed (missing </tr> tags, <br> inside
    cells), so we handle that explicitly.
    """
    from html.parser import HTMLParser

    class _TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self._current_row: list[str] | None = None
            self._capture = False
            self._cell_text = ""

        def _flush_row(self):
            if self._current_row is not None:
                self.rows.append(self._current_row)
                self._current_row = None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._flush_row()  # handles missing </tr>
                self._current_row = []
            elif tag in ("td", "th"):
                self._capture = True
                self._cell_text = ""

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self._capture:
                if self._current_row is not None:
                    self._current_row.append(self._cell_text.strip())
                self._capture = False
            elif tag == "tr":
                self._flush_row()

        def handle_data(self, data):
            if self._capture:
                self._cell_text += data

    parser = _TableParser()
    parser.feed(file_bytes.decode("utf-8", errors="replace"))
    parser._flush_row()  # flush last row if file ends without </tr>

    output = io.StringIO()
    writer = csv.writer(output)
    for row in parser.rows:
        writer.writerow(row)
    output.seek(0)
    return output


def parse_roster_upload(roster_file: UploadFile) -> RosterMap:
    """
    Parses an uploaded roster file (CSV or XLS) and returns a RosterMap.

    For .xls files the first sheet is converted to CSV in memory before parsing.
    """
    try:
        contents = roster_file.file.read()
        filename = roster_file.filename or ""
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".xls":
            logger.info("Detected .xls file. Converting to CSV...")
            text_stream = xls_bytes_to_csv_stream(contents)
        else:
            # Default: treat as CSV
            text_stream = io.TextIOWrapper(io.BytesIO(contents), encoding="utf-8-sig")

        roster = parse_roster_for_major_map(text_stream)
        logger.info(
            "Parsed roster (%s): %d by ASURITE, %d by ID.",
            ext or ".csv",
            len(roster.by_asurite),
            len(roster.by_id),
        )
        return roster
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing roster file: {e}")


def extract_text_from_pdf(file_path: str) -> str:
    """Extracts text content from a PDF file."""
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        logger.error("Error extracting text from PDF '%s': %s", file_path, e)
        return ""


def extract_text_from_docx(file_path: str) -> str:
    """Extracts text content from a DOCX file."""
    try:
        doc = docx.Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception as e:
        logger.error("Error extracting text from DOCX '%s': %s", file_path, e)
        return ""


def get_semester_short_code(term_name: str) -> str:
    """Converts 'Fall 2025' to 'f25'."""
    if not term_name:
        return "term"
    match = re.search(r"(\w+)\s+(\d{4})", term_name)
    if match:
        season = match.group(1)[0].lower()
        year = match.group(2)[-2:]
        return f"{season}{year}"
    return "term"


def generate_filename(course_code, semester, assignment_name, label, extension):
    """Generates format like: cse100-f20-assignment_name-high.pdf"""
    clean_course = sanitize_filename(course_code).replace("_", "")
    clean_assign = sanitize_filename(assignment_name)
    return f"{clean_course}-{semester}-{clean_assign}-{label}{extension}"


def sanitize_filename(name: str) -> str:
    """Replaces characters that are invalid in Windows/Linux filenames with an underscore."""
    name = name.replace(" ", "_")
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def extract_and_save_syllabus(
    course_id, course_info, client: CanvasGradesFetcher, temp_dir: str
):
    """Saves syllabus body as HTML, converts it to PDF, and downloads linked PDFs."""
    logger.info("Extracting Syllabus...")
    folder_path = os.path.join(temp_dir, "_Syllabus")
    os.makedirs(folder_path, exist_ok=True)

    body = course_info.get("syllabus_body", "")
    if not body:
        return folder_path

    # 1. Save Raw HTML Body
    html_path = os.path.join(folder_path, "syllabus_body.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(body)

    # 2. Convert HTML to PDF
    # We wrap the body in basic html tags to ensure the renderer handles it correctly
    pdf_path = os.path.join(folder_path, "syllabus_body.pdf")
    try:
        with open(pdf_path, "wb") as pdf_file:
            # Allow blank images to fail gracefully without stopping the script
            pisa.CreatePDF(f"<html><body>{body}</body></html>", dest=pdf_file)
        logger.info("Rendered syllabus HTML to PDF: syllabus_body.pdf")
    except Exception as e:
        logger.error("Failed to render syllabus PDF: %s", e)

    # 3. Download linked PDF if it exists in the body
    # Regex to find file links: /files/12345
    file_ids = re.findall(r"/files/(\d+)", body)
    for fid in file_ids:
        f_info = client.api_request(f"files/{fid}")
        if not f_info:
            logger.warning("Could not fetch file info for file ID %s", fid)
            continue

        if f_info and f_info.get("filename", "").lower().endswith(".pdf"):
            # Save as syllabus.pdf (or keep original name)
            local_path = os.path.join(folder_path, f"syllabus_{f_info['filename']}")
            client.download_file(f_info["url"], local_path)
            logger.info("Downloaded linked syllabus PDF: %s", f_info["filename"])

    return folder_path


def get_all_assignments(course_id: str, client: CanvasGradesFetcher) -> list[dict]:
    """Fetches all assignments for a given course."""
    logger.info("Fetching all assignments for course %s...", course_id)
    endpoint = f"courses/{course_id}/assignments"
    return client.get_paginated_list(endpoint, params={"include[]": "rubric"})


def find_abet_assignments(all_assignments: list[dict]) -> list[dict]:
    """
    Finds all ABET-related assignments by searching names and rubrics.

    Args:
        all_assignments (list): The list of all assignment objects to filter.

    Returns:
        list: A list of assignment objects that match the ABET criteria.
    """
    logger.info("Filtering for ABET assignments...")
    return [
        a
        for a in all_assignments
        if ABET_TAG in a.get("name", "").lower()
        or any(
            ABET_TAG in r.get("description", "").lower() for r in a.get("rubric", [])
        )
    ]


def extract_rubric_assessment_data(submission):
    """Extracts and anonymizes rubric assessment data from a submission."""
    rubric_data = submission.get("rubric_assessment", {})
    if not rubric_data:
        return None
    return {
        cid: {"points": data.get("points"), "comments": data.get("comments", "")}
        for cid, data in rubric_data.items()
    }


def find_abet_outcomes(all_assignments: list[dict]) -> tuple[defaultdict, dict]:
    """Scans assignments, groups them by ABET outcome, and extracts outcome details."""
    outcome_map = defaultdict(list)
    outcome_details = (
        {}
    )  # Store title, description, and long_description for each outcome
    for assign in all_assignments:
        if not (rubric := assign.get("rubric")):
            continue
        for criterion in rubric:
            # We check the main 'description' for the ABET tag
            if "abet" in criterion.get("description", "").lower() and (
                oid := criterion.get("outcome_id")
            ):
                outcome_map[oid].append(assign)
                if oid not in outcome_details:
                    # Use 'description' for the title and main outcome text
                    title_description = criterion.get("description", "").strip()
                    long_description = criterion.get("long_description", "").strip()
                    clean_title = re.sub(r"<[^>]+>", "", title_description).strip()

                    outcome_details[oid] = {
                        "title": clean_title,
                        "full_description": title_description,
                        "long_description": long_description,
                    }
    return outcome_map, outcome_details


def get_representative_submissions(
    course_id: str, assignment_id: int, client: CanvasGradesFetcher
) -> tuple[dict | None, dict | None, dict | None]:
    """
    Fetches submissions and identifies High, Average, and Low graded artifacts.
    """
    endpoint = f"courses/{course_id}/assignments/{assignment_id}/submissions"

    submissions = client.get_paginated_list(endpoint, params={"include[]": "user"})

    if not submissions:
        return None, None, None

    # Filter for graded submissions only
    graded = sorted(
        [
            s
            for s in submissions
            if s.get("workflow_state") == "graded" and s.get("score") is not None
        ],
        key=lambda s: s["score"],
    )

    if not graded:
        return None, None, None

    # 1. High and Low 
    low_sub = graded[0]
    high_sub = graded[-1]

    # 2. Calculate Average
    scores = [s["score"] for s in graded]
    avg_score = sum(scores) / len(scores)

    # 3. Find submission closest to the statistical average
    avg_sub = min(graded, key=lambda s: abs(s["score"] - avg_score))

    return high_sub, avg_sub, low_sub


def _save_representative_submission(
    sub: dict,
    label: str,
    assignment: dict,
    course_code: str,
    semester_code: str,
    local_path: str,
    client: CanvasGradesFetcher,
) -> list[str]:
    """
    Downloads and saves a single representative submission (high/avg/low)
    and its metadata. Returns a list of saved file paths.
    """
    saved = []
    if not (sub and sub.get("attachments")):
        return saved

    attachment = sub["attachments"][0]
    ext = os.path.splitext(attachment.get("filename", ""))[1]

    new_filename = generate_filename(
        course_code, semester_code, assignment["name"], label, ext
    )
    file_save_path = os.path.join(local_path, new_filename)

    if client.download_file(attachment["url"], file_save_path):
        saved.append(file_save_path)

    metadata_path = os.path.join(local_path, f"{label}_details.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "score": sub.get("score"),
                "points_possible": assignment.get("points_possible"),
                "original_filename": attachment.get("filename"),
                "user_id": sub.get("user", {}).get("id"),
                "rubric_assessment": extract_rubric_assessment_data(sub),
            },
            f,
            indent=2,
        )
    saved.append(metadata_path)
    return saved


def extract_and_save_artifacts(
    assignment: dict,
    client: CanvasGradesFetcher,
    course_code: str,
    semester_code: str,
    temp_dir: str,
) -> tuple[list[str], dict[str, str]]:
    """
    Saves all relevant artifacts for an assignment to a local temporary directory.
    This includes the description, rubric, any documents attached in the description,
    and files from the highest and lowest graded student submissions.

    Args:
        assignment (dict): The assignment object.
        temp_dir (str): The temporary directory for this request.

    Returns:
        tuple: A (list of file paths, dict of extracted texts).
    """
    sanitized_name = sanitize_filename(assignment["name"])
    assignment_name = f"{assignment['id']}_{sanitized_name}"
    local_path = os.path.join(temp_dir, assignment_name)
    os.makedirs(local_path, exist_ok=True)

    saved_files = []
    extracted_texts = {}

    if description := assignment.get("description"):
        path = os.path.join(local_path, "description.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(description)
        saved_files.append(path)

        for file_id in set(re.findall(r"/files/(\d+)", description)):
            f_info = client.api_request(f"files/{file_id}")
            if not f_info:
                logger.warning("Could not fetch file info for file ID %s", file_id)
                continue

            file_local_path = os.path.join(local_path, f_info["filename"])
            if client.download_file(f_info["url"], file_local_path):
                saved_files.append(file_local_path)
                # After downloading, check extension and extract text
                if file_local_path.lower().endswith(".pdf"):
                    extracted_texts[f_info["filename"]] = extract_text_from_pdf(
                        file_local_path
                    )
                elif file_local_path.lower().endswith(".docx"):
                    extracted_texts[f_info["filename"]] = extract_text_from_docx(
                        file_local_path
                    )

    if rubric := assignment.get("rubric"):
        path = os.path.join(local_path, "rubric.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rubric, f, indent=4)
        saved_files.append(path)    

    high, avg, low = get_representative_submissions(
        assignment["course_id"], assignment["id"], client
    )

    for sub, label in [(high, "high"), (avg, "avg"), (low, "low")]:
        saved_files.extend(
            _save_representative_submission(
                sub, label, assignment, course_code, semester_code, local_path, client
            )
        )

    return saved_files, extracted_texts


def generate_assignment_grade_report(
    grades_fetcher: CanvasGradesFetcher, assignment: dict, local_path: str
) -> str | None:
    """
    Creates a detailed CSV grade report for a single assignment.

    Args:
        grades_fetcher (CanvasGradesFetcher): The fetcher instance to get data.
        assignment (dict): The assignment object.
        local_path (str): The local directory to save the report in.

    Returns:
        str or None: The file path to the generated CSV, or None if no submissions exist.
    """
    logger.info("Generating detailed grade report...")
    submissions = grades_fetcher.fetch_assignment_submissions(
        assignment["course_id"], assignment["id"]
    )
    if not submissions:
        logger.info("No submissions found.")
        return None

    report_path = os.path.join(local_path, f"grade_report_{assignment['id']}.csv")
    header = ["user_id", "user_name", "score", "submitted_at", "workflow_state"]

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for sub in submissions:
            user = sub.get("user", {})
            writer.writerow(
                [
                    user.get("id", "N/A"),
                    user.get("name", "N/A"),
                    sub.get("score", ""),
                    sub.get("submitted_at", "N/A"),
                    sub.get("workflow_state", "N/A"),
                ]
            )
    logger.info("Grade report saved to %s", report_path)
    return report_path


def build_outcome_report_data(
    grades_fetcher,
    outcome_map,
    outcome_details,
    course_info,
    course_id: str,
    student_major_map: RosterMap,
    assignment_texts_map: dict,
) -> list[dict]:
    """
    Pure data builder: gathers submissions, computes competency stats, and
    returns a list of structured report dicts (one per ABET outcome).

    No file I/O or Canvas uploads are performed here.
    """
    logger.info(
        "Building ABET Outcome Report Data with Major Breakdown and File Content"
    )
    outcome_reports = []
    submission_cache = {}  # {assignment_id: [submissions]} — avoids re-fetching

    for outcome_id, assignments in outcome_map.items():
        outcome_info = outcome_details.get(outcome_id, {})
        outcome_title = outcome_info.get("title", f"Outcome_ID_{outcome_id}")

        logger.debug(
            "Processing Outcome: '%s' (Outcome ID: %s)", outcome_title, outcome_id
        )

        all_outcome_submissions = []
        major_buckets = defaultdict(list)
        contributing_assignments_data = []

        for assign in assignments:
            logger.debug(
                "Gathering data from assignment: '%s' (ID: %s)",
                assign["name"],
                assign["id"],
            )

            abet_criterion = next(
                (
                    criteria
                    for criteria in assign.get("rubric", [])
                    if criteria.get("outcome_id") == outcome_id
                ),
                None,
            )
            if not abet_criterion:
                logger.debug(
                    "SKIPPED: Assignment has no rubric criterion for this specific outcome."
                )
                continue

            abet_points_possible = abet_criterion.get("points") or 1
            assign_id = assign["id"]
            if assign_id not in submission_cache:
                submission_cache[assign_id] = (
                    grades_fetcher.fetch_assignment_submissions(course_id, assign_id)
                )
            submissions = submission_cache[assign_id]
            logger.debug(
                "Fetched %d submissions. Parsing for rubric assessments...",
                len(submissions),
            )

            for sub in submissions:
                if assessment := sub.get("full_rubric_assessment"):
                    for graded_criterion in assessment.get("data", []):
                        if graded_criterion.get("learning_outcome_id") == outcome_id:
                            sub["_abet_score"] = graded_criterion.get("points", 0)
                            sub["_abet_points_possible"] = abet_points_possible
                            all_outcome_submissions.append(sub)

                            logger.debug(
                                "Found relevant score for Submission ID %s. Score: %s/%s",
                                sub["id"],
                                sub["_abet_score"],
                                sub["_abet_points_possible"],
                            )

                            # Match student to major:
                            # ASURITE column -> login_id,  ID column -> sis_user_id
                            if user_data := sub.get("user"):
                                major = None
                                matched_key = None
                                if student_major_map.by_asurite:
                                    login_id = user_data.get("login_id", "")
                                    major = student_major_map.by_asurite.get(login_id)
                                    if major:
                                        matched_key = login_id
                                if not major and student_major_map.by_id:
                                    sis_id = str(user_data.get("sis_user_id", ""))
                                    major = student_major_map.by_id.get(sis_id)
                                    if major:
                                        matched_key = sis_id
                                if major:
                                    major_buckets[major].append(sub)
                                    logger.debug(
                                        "Matched to Major '%s' for user '%s'.",
                                        major,
                                        matched_key,
                                    )
                            break  # Move to the next submission

            assignment_info = assign.copy()
            assignment_info["description_files_content"] = assignment_texts_map.get(
                assign["id"], {}
            )
            contributing_assignments_data.append(assignment_info)

        logger.debug(
            "Data gathering complete. Total relevant submissions: %d. Students matched to a major: %d",
            len(all_outcome_submissions),
            sum(len(subs) for subs in major_buckets.values()),
        )

        if not all_outcome_submissions:
            logger.warning(
                "Skipping report for '%s'. No relevant rubric-graded submissions found.",
                outcome_title,
            )
            continue

        # Compute major-specific competency results
        major_specific_results = {}
        for major, subs in major_buckets.items():
            num_competent = sum(
                1
                for s in subs
                if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
            )
            total_graded = len(subs)
            percent_competent = (
                (num_competent / total_graded) * 100 if total_graded else 0
            )
            major_specific_results[major] = {
                "sample_size": total_graded,
                "number_competent": num_competent,
                "percent_competent": round(percent_competent, 2),
                "outcome_met": percent_competent >= 70.0,
            }

        # Compute overall competency results
        overall_num_competent = sum(
            1
            for s in all_outcome_submissions
            if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
        )
        overall_total_graded = len(all_outcome_submissions)
        overall_percent_competent = (
            (overall_num_competent / overall_total_graded) * 100
            if overall_total_graded
            else 0
        )

        # Create a clean list of contributing assignments for the report
        clean_assignments = [
            {
                "id": assign.get("id"),
                "name": assign.get("name"),
                "description": assign.get("description"),
                "description_files_content": assign.get(
                    "description_files_content", {}
                ),
            }
            for assign in contributing_assignments_data
        ]

        # Assemble the final, structured report object
        report_data = {
            # Corresponds to requirement 1.a and 1.d (Identification and Description)
            "outcome_identification": {
                "title": outcome_title,
                "description": outcome_info.get("full_description", ""),
                "long_description": outcome_info.get("long_description", ""),
            },
            # Corresponds to requirement 1.e (Results)
            "results": {
                "overall_summary": {
                    "sample_size": overall_total_graded,
                    "number_competent": overall_num_competent,
                    "percent_competent": round(overall_percent_competent, 2),
                    "outcome_met": overall_percent_competent >= 70.0,
                },
                "distribution_by_major": major_specific_results,
            },
            # Corresponds to "Actual instrument used"
            "contributing_assignments": clean_assignments,
        }

        # Derive the outcome label for identification
        match = re.search(r"(CS|CSE)\s*ABET\s*\d+", outcome_title, re.IGNORECASE)
        outcome_label = (
            match.group(0).replace(" ", "_")
            if match
            else sanitize_filename(outcome_title)
        )

        outcome_reports.append(
            {
                "outcome_id": str(outcome_id),
                "outcome_title": outcome_title,
                "outcome_label": outcome_label,
                "data": report_data,
            }
        )

    return outcome_reports


def generate_outcome_reports(
    grades_fetcher: CanvasGradesFetcher,
    outcome_map,
    outcome_details,
    course_info,
    semester_code,
    course_id: str,
    student_major_map: RosterMap,
    assignment_texts_map: dict,
    temp_dir: str,
):
    """
    Generates ABET outcome JSON reports, writes them to disk, and uploads to Canvas.
    Delegates data building to build_outcome_report_data.
    """
    outcome_reports = build_outcome_report_data(
        grades_fetcher,
        outcome_map,
        outcome_details,
        course_info,
        course_id,
        student_major_map,
        assignment_texts_map,
    )

    if not outcome_reports:
        logger.info("No outcome reports were generated.")
        return

    local_reports_to_upload = []
    for report in outcome_reports:
        report_filename = f"OUTCOME_{report['outcome_label']}.json"
        report_path = os.path.join(temp_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report["data"], f, indent=4)
        local_reports_to_upload.append(report_path)

    if local_reports_to_upload:
        canvas_folder = f"{semester_code}/_ABET_Outcome_Reports"
        grades_fetcher.upload_files(course_id, canvas_folder, local_reports_to_upload)


# Fast api endpoint
@app.post("/process-course-with-roster/{course_id}")
def process_course_with_roster(
    course_id: str,
    canvas_access_token: Annotated[str, Header()],
    roster_file: Optional[UploadFile] = File(None),
    tasks: TaskType = Query(
        TaskType.ALL, description="Tasks to run: 'extract', 'abet', or 'all'"
    ),
):
    # Early token validation
    if not canvas_access_token or not str(canvas_access_token).strip():
        raise HTTPException(status_code=401, detail="Canvas access token is required.")

    student_major_map = RosterMap()

    # Only run roster parsing if the task actually requires it (ABET or ALL)
    if tasks in (TaskType.ABET, TaskType.ALL):
        if not roster_file:
            raise HTTPException(
                status_code=400,
                detail="The 'roster_file' is required when tasks include 'abet' or 'all'.",
            )
        student_major_map = parse_roster_upload(roster_file)

    temp_dir = create_temp_dir()
    try:
        grades_fetcher = CanvasGradesFetcher(access_token=canvas_access_token)
        course_info = grades_fetcher.api_request(
            f"courses/{course_id}", params={"include[]": ["syllabus_body", "term"]}
        )

        if not course_info:
            raise HTTPException(
                status_code=404, detail="Course not found or invalid token."
            )

        course_code = course_info.get("course_code", "course")  # e.g., CSE100
        semester_code = get_semester_short_code(
            course_info.get("term", {}).get("name", "")
        )  # e.g., f25

        full_semester_name = f"{semester_code}_{sanitize_filename(course_code)}"

        all_assignments = get_all_assignments(course_id, grades_fetcher)
        if not all_assignments:
            raise HTTPException(
                status_code=404, detail="No assignments found in the course."
            )

        if tasks in (TaskType.EXTRACT, TaskType.ALL):
            syllabus_path = extract_and_save_syllabus(
                course_id, course_info, grades_fetcher, temp_dir
            )
            if syllabus_path:
                syllabus_files = [
                    os.path.join(syllabus_path, f) for f in os.listdir(syllabus_path)
                ]
                grades_fetcher.upload_files(
                    course_id,
                    f"{full_semester_name}/Syllabus",
                    syllabus_files,
                )

        # Data Gathering Phase (Always Runs)
        assignment_texts_map = {}
        logger.info("Starting Data Gathering Phase")
        for assignment in all_assignments:
            logger.info("Gathering artifacts for: %s", assignment["name"])
            local_files, extracted_texts = extract_and_save_artifacts(
                assignment, grades_fetcher, course_code, semester_code, temp_dir
            )
            assignment_texts_map[assignment["id"]] = extracted_texts

            sanitized_name = sanitize_filename(assignment["name"])
            assignment_folder_path = os.path.join(
                temp_dir, f"{assignment['id']}_{sanitized_name}"
            )
            report_path = generate_assignment_grade_report(
                grades_fetcher, assignment, assignment_folder_path
            )
            if report_path:
                local_files.append(report_path)

            if tasks in (TaskType.EXTRACT, TaskType.ALL):
                if local_files:
                    logger.info("Uploading artifacts for '%s'...", assignment["name"])
                    canvas_folder = f"{full_semester_name}/Assignments/{sanitized_name}"
                    grades_fetcher.upload_files(course_id, canvas_folder, local_files)
                else:
                    logger.info("No artifacts found to upload for this assignment.")

        logger.info("Data Gathering Complete")

        # ABET Report Generation Phase (Conditional)
        if tasks in (TaskType.ABET, TaskType.ALL):
            logger.info("Starting ABET Report Generation Phase")
            if abet_assignments := find_abet_assignments(all_assignments):
                outcome_map, outcome_details = find_abet_outcomes(abet_assignments)
                if outcome_map:
                    generate_outcome_reports(
                        grades_fetcher,
                        outcome_map,
                        outcome_details,
                        course_info,
                        full_semester_name,
                        course_id,
                        student_major_map,
                        assignment_texts_map,
                        temp_dir,
                    )
                else:
                    logger.info(
                        "No assignments with rubric outcomes found for summary report generation."
                    )
            else:
                logger.info("No ABET-tagged assignments found.")

        return {"message": f"Processing complete for tasks: '{tasks.value}'."}
    finally:
        cleanup_temp_dir(temp_dir)


@app.post("/generate-report-json/{course_id}")
def generate_report_json(
    course_id: str,
    canvas_access_token: Annotated[str, Header()],
    roster_file: Optional[UploadFile] = File(None),
):
    """Returns ABET outcome report data as a JSON response without uploading to Canvas."""
    # Early token validation
    if not canvas_access_token or not str(canvas_access_token).strip():
        raise HTTPException(status_code=401, detail="Canvas access token is required.")
    if not roster_file:
        raise HTTPException(
            status_code=400, detail="The 'roster_file' is required for this endpoint."
        )

    student_major_map = parse_roster_upload(roster_file)

    temp_dir = create_temp_dir()
    try:
        grades_fetcher = CanvasGradesFetcher(access_token=canvas_access_token)
        course_info = grades_fetcher.api_request(
            f"courses/{course_id}", params={"include[]": ["syllabus_body", "term"]}
        )
        if not course_info:
            raise HTTPException(
                status_code=404, detail="Course not found or invalid token."
            )

        course_code = course_info.get("course_code", "course")
        semester_code = get_semester_short_code(
            course_info.get("term", {}).get("name", "")
        )

        all_assignments = get_all_assignments(course_id, grades_fetcher)
        if not all_assignments:
            raise HTTPException(
                status_code=404, detail="No assignments found in the course."
            )

        # Gather extracted texts for each assignment (needs temp files for PDF/DOCX extraction)
        assignment_texts_map = {}
        for assignment in all_assignments:
            _, extracted_texts = extract_and_save_artifacts(
                assignment, grades_fetcher, course_code, semester_code, temp_dir
            )
            assignment_texts_map[assignment["id"]] = extracted_texts

        # Filter for ABET assignments and build outcome data
        abet_assignments = find_abet_assignments(all_assignments)
        if not abet_assignments:
            raise HTTPException(
                status_code=404, detail="No ABET-tagged assignments found."
            )

        outcome_map, outcome_details = find_abet_outcomes(abet_assignments)
        if not outcome_map:
            raise HTTPException(
                status_code=404,
                detail="No assignments with rubric outcomes found for report generation.",
            )

        outcome_reports = build_outcome_report_data(
            grades_fetcher,
            outcome_map,
            outcome_details,
            course_info,
            course_id,
            student_major_map,
            assignment_texts_map,
        )

        # Wrap in the metadata envelope
        response_payload = {
            "metadata": {
                "course_id": str(course_id),
                "course_code": course_code,
                "semester": semester_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            # Corresponds to requirement 1.c (Class number)
            "course_identification": course_info,
            "outcomes": [
                {
                    "outcome_id": report["outcome_id"],
                    "outcome_title": report["outcome_title"],
                    "data": report["data"],
                }
                for report in outcome_reports
            ],
        }

        return JSONResponse(content=response_payload)

    finally:
        cleanup_temp_dir(temp_dir)


@app.post("/move-data-between-courses/{course_id_to_pull}/{course_id_to_push}")
def move_data_between_courses(course_id_to_pull: str, 
                              course_id_to_push: str,
                              canvas_access_token: Annotated[str, Header()]):
    # Early token validation
    if not canvas_access_token or not str(canvas_access_token).strip():
        raise HTTPException(status_code=401, detail="Canvas access token is required.")

    #Validate Course IDs
    if not course_id_to_pull or not course_id_to_push:
        raise HTTPException(status_code=400, detail="Course IDs must both be filled")

    #Create Temp Directory
    temp_dir = create_temp_dir()
    try:
        grades_fetcher = CanvasGradesFetcher(access_token=canvas_access_token)

        #Fetch course info - Syllabus and Term
        course_info = grades_fetcher.api_request(
            endpoint_or_url=f"courses/{course_id_to_pull}", params={"include[]": ["syllabus_body", "term"]}
        )

        if not course_info:
            raise HTTPException(
                status_code=404, detail="Course not found or invalid token."
            )
        
        course_code = course_info.get("course_code", "course")  # e.g., CSE100
        semester_code = get_semester_short_code(
            course_info.get("term", {}).get("name", "")
        )  # e.g., f25

        full_semester_name = f"{semester_code}_{sanitize_filename(course_code)}"

        #Fetch all assignments including the rubric. 
        all_assignments = get_all_assignments(course_id_to_pull, grades_fetcher)
        if not all_assignments:
            raise HTTPException(
                status_code=404, detail="No assignments found in the course."
            )
        
        # Data Gathering Phase (Always Runs)
        assignment_texts_map = {}
        logger.info("Starting Data Gathering Phase")
        for assignment in all_assignments:
            logger.info("Gathering artifacts for: %s", assignment["name"])
            local_files, extracted_texts = extract_and_save_artifacts(
                assignment, grades_fetcher, course_code, semester_code, temp_dir
            )
            assignment_texts_map[assignment["id"]] = extracted_texts

            sanitized_name = sanitize_filename(assignment["name"])
            assignment_folder_path = os.path.join(
                temp_dir, f"{assignment['id']}_{sanitized_name}"
            )
            report_path = generate_assignment_grade_report(
                grades_fetcher, assignment, assignment_folder_path
            )
            if report_path:
                local_files.append(report_path)
            
            if local_files:
                logger.info("Uploading artifacts for '%s'...", assignment["name"])
                canvas_folder = f"{full_semester_name}/Test_Assignments/{sanitized_name}"
                grades_fetcher.upload_files(course_id_to_push, canvas_folder, local_files)
            else:
                logger.info("No artifacts found to upload for this assignment.")

        logger.info("Data Gathering Complete")

    except Exception as e: 
        ...

    finally:
        cleanup_temp_dir(temp_dir)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
