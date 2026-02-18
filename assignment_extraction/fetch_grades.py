#!/usr/bin/env python3
"""
Canvas Grades Fetcher
Fetches grades and submission data from Canvas LMS for ABET assessment purposes.
"""

import requests
import json
import os
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import time
import shutil


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("grades_fetch.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class CanvasGradesFetcher:
    """Fetches grades and submission data from Canvas LMS."""

    def __init__(
        self,
        canvas_domain: str = "https://canvas.asu.edu",
        access_token: Optional[str] = None,
    ):
        self.canvas_domain = canvas_domain
        self.access_token = access_token or self._get_access_token()
        self.headers = {"Authorization": f"Bearer {self.access_token}"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _get_access_token(self) -> str:
        """Get Canvas access token from environment variable."""
        token = os.environ.get("canvas_access_token")
        if not token:
            raise ValueError("Canvas access token not found.")
        return token

    def _adaptive_sleep(self, response: requests.Response):
        """Sleep adaptively based on Canvas rate limit headers.

        Uses the X-Rate-Limit-Remaining header to throttle only when
        remaining capacity is low.  No sleep when bucket is healthy.
        """
        try:
            remaining = float(response.headers.get("X-Rate-Limit-Remaining", 700))
        except Exception:
            remaining = 700.0

        if remaining < 50:
            time.sleep(5.0)
        elif remaining < 100:
            time.sleep(2.0)
        elif remaining < 200:
            time.sleep(0.5)
        elif remaining < 350:
            time.sleep(0.1)
        # else: no sleep needed

    def _get_paginated_list(
        self, url: Optional[str], params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Helper function to handle pagination for any Canvas API endpoint.

        Implements adaptive sleeping based on response headers and retries
        when Canvas responds with a rate-limit (403/429 + "Rate Limit").
        """
        all_items = []
        current_params = params or {}
        current_params.setdefault("per_page", 100)

        while url:
            try:
                # Retry loop specifically for rate-limited responses
                for attempt in range(3):
                    response = self.session.get(url, params=current_params)

                    # If Canvas signals rate limiting, wait and retry
                    if response.status_code in (403, 429) and "Rate Limit" in (
                        response.text or ""
                    ):
                        logger.warning("Rate limited. Sleeping 10s and retrying...")
                        time.sleep(10.0)
                        continue

                    # Raise for other HTTP errors
                    response.raise_for_status()

                    # Successful response — use adaptive pacing based on headers
                    self._adaptive_sleep(response)

                    # Append page items
                    try:
                        page_items = response.json()
                    except ValueError:
                        page_items = []
                    all_items.extend(page_items)

                    # Discover next page from Link header (if present)
                    url = None
                    if "Link" in response.headers:
                        links = requests.utils.parse_header_links(response.headers["Link"])
                        url = next(
                            (link["url"] for link in links if link.get("rel") == "next"),
                            None,
                        )

                    # The 'next' URL provided by Canvas includes all necessary parameters.
                    current_params = None

                    break  # exit retry loop on success
                else:
                    # Exhausted retries for rate limiting — log and stop.
                    logger.error("Exceeded retry attempts due to rate limiting for %s", url)
                    break

            except requests.exceptions.RequestException as e:
                logger.error(f"Error during paginated fetch from {url}: {e}")
                break
        return all_items

    def api_request(
        self,
        endpoint_or_url: str,
        method: str = "GET",
        params: dict = None,
        data: dict = None,
        stream: bool = False,
    ) -> dict | requests.Response | None:
        """
        Performs a single, non-paginated API request to Canvas.

        Adds adaptive sleeping and retry-on-rate-limit behavior while keeping
        the original return semantics.
        """
        url = endpoint_or_url
        if not url.startswith("https://"):
            url = f"{self.canvas_domain}/api/v1/{endpoint_or_url}"

        try:
            for attempt in range(3):
                response = self.session.request(
                    method, url, params=params, data=data, stream=stream
                )

                # Handle explicit Canvas rate-limit responses by pausing and retrying
                if response.status_code in (403, 429) and "Rate Limit" in (
                    response.text or ""
                ):
                    logger.warning("Rate limited. Sleeping 10s and retrying...")
                    time.sleep(10.0)
                    continue

                # Raise for other HTTP errors
                response.raise_for_status()

                # Apply adaptive sleep based on response headers
                try:
                    self._adaptive_sleep(response)
                except Exception:
                    pass

                if stream:
                    return response
                return response.json() if response.text else {"status": "success"}

            # Exhausted rate-limit retries
            logger.error("Exceeded retry attempts due to rate limiting for %s", url)
            return None

        except requests.exceptions.RequestException as e:
            logger.error(
                "API Error on %s %s: %s | Response: %s",
                method,
                url,
                e,
                e.response.text if e.response else "N/A",
            )
            return None

    def download_file(self, url: str, local_path: str) -> bool:
        """
        Downloads a file from a URL to a local path using a streamed response.

        Returns:
            True if successful, False otherwise.
        """
        try:
            response = self.api_request(url, stream=True)
            if response is None:
                logger.warning(
                    "Download failed for %s: API request returned no response.",
                    local_path,
                )
                return False
            with response, open(local_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)
            return True
        except Exception as e:
            logger.error("Error downloading '%s' to '%s': %s", url, local_path, e)
            return False

    def get_paginated_list(self, endpoint: str, params: dict = None) -> list:
        """
        Public wrapper around _get_paginated_list using a relative endpoint.
        """
        url = f"{self.canvas_domain}/api/v1/{endpoint}"
        return self._get_paginated_list(url, params=params)

    def upload_files(
        self,
        course_id: str,
        folder_path: str,
        file_paths: list[str],
        max_retries: int = 3,
    ):
        """
        Uploads files to a Canvas course folder, with retries.
        """
        logger.info(
            "Uploading %d files to Canvas folder '%s'...",
            len(file_paths),
            folder_path,
        )
        for file_path in file_paths:
            for attempt in range(max_retries):
                try:
                    filename = os.path.basename(file_path)
                    init_data = {
                        "name": filename,
                        "parent_folder_path": folder_path,
                        "on_duplicate": "overwrite",
                    }
                    upload_info = self.api_request(
                        f"courses/{course_id}/files",
                        method="POST",
                        data=init_data,
                    )
                    if not upload_info:
                        logger.warning("Upload init failed for %s", filename)
                        continue

                    with open(file_path, "rb") as f:
                        upload_response = requests.post(
                            upload_info["upload_url"],
                            data=upload_info["upload_params"],
                            files={"file": f},
                        )
                        upload_response.raise_for_status()

                    if confirmation := upload_response.json():
                        # The confirmation may provide a location to GET to confirm
                        if confirmation.get("location"):
                            self.api_request(confirmation["location"])  # confirm
                    logger.info("Successfully uploaded %s", filename)
                    break
                except Exception as e:
                    logger.error(
                        "ERROR on attempt %d/%d for %s: %s",
                        attempt + 1,
                        max_retries,
                        filename,
                        e,
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        logger.error(
                            "All %d attempts failed for %s.",
                            max_retries,
                            filename,
                        )

    def fetch_course_assignments(self, course_id: int) -> List[Dict[str, Any]]:
        """Fetch all assignments for a given course.

        Args:
            course_id: Canvas course ID

        Returns:
            List of assignment dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/assignments"
        logger.info(f"Fetching assignments for course {course_id}")

        assignments = self._get_paginated_list(url)
        logger.info(f"Successfully fetched {len(assignments)} assignments")
        return assignments

    def fetch_assignment_submissions(
        self, course_id: int, assignment_id: int
    ) -> List[Dict[str, Any]]:
        """Fetch all submissions for a specific assignment.

        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID

        Returns:
            List of submission dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
        params = {
            "include[]": [
                "user",
                "submission_comments",
                "full_rubric_assessment",
            ],
            "per_page": 100,
        }
        logger.info(f"Fetching submissions for assignment {assignment_id}")
        submissions = self._get_paginated_list(url, params=params)
        logger.info(f"Successfully fetched {len(submissions)} submissions")
        return submissions

    def fetch_all_course_submissions(
        self,
        course_id: int,
        assignment_ids: list[int] | None = None,
        workflow_state: str | None = None,
    ) -> list[dict]:
        """
        Fetch submissions for all (or specified) assignments in a course using
        the bulk endpoint. This is much more efficient than fetching per-assignment.

        Args:
            course_id: Canvas course ID
            assignment_ids: Optional list of assignment IDs to filter. If None,
                            returns submissions for ALL assignments. Canvas
                            accepts multiple assignment_ids[] parameters (batching
                            handled by caller).
            workflow_state: Optional filter: 'submitted', 'graded',
                            'pending_review', 'unsubmitted'

        Returns:
            Flat list of submission dicts (not grouped by student).
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/students/submissions"
        params = {
            "student_ids[]": "all",
            "include[]": [
                "user",
                "submission_comments",
                "full_rubric_assessment",
            ],
            "per_page": 100,
        }

        if assignment_ids:
            params["assignment_ids[]"] = assignment_ids

        if workflow_state:
            params["workflow_state"] = workflow_state

        logger.info(f"Fetching bulk submissions for course {course_id} (assignments=%s)", assignment_ids)
        return self._get_paginated_list(url, params=params)

    def fetch_course_students(self, course_id: int) -> List[Dict[str, Any]]:
        """Fetch all students enrolled in a course.

        Args:
            course_id: Canvas course ID

        Returns:
            List of student dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/users"
        params = {"enrollment_type": "student", "per_page": 100}
        logger.info(f"Fetching students for course {course_id}")
        students = self._get_paginated_list(url, params=params)
        logger.info(f"Successfully fetched {len(students)} students")
        return students

    def fetch_course_grades(self, course_id: int) -> Dict[str, Any]:
        """Fetch complete grade data for a course including assignments, submissions, and students.

        N + 1 api calls right now (1 for assignments then 1 per assignment for submissions)
        Unfortunately this is unavoidable since Canvas does not provide a bulk endpoint for grades data.
        Args:
            course_id: Canvas course ID

        Returns:
            Dictionary containing course grade data
        """
        logger.info(f"Starting comprehensive grade fetch for course {course_id}")
        grades_summary = {}
        assignments = self.fetch_course_assignments(course_id)

        for assignment in assignments:
            submissions = self.fetch_assignment_submissions(course_id, assignment["id"])
            graded_submissions = [s for s in submissions if s.get("grade") is not None]
            if graded_submissions:
                scores = [
                    float(s["score"])
                    for s in graded_submissions
                    if s["score"] is not None
                ]
                grades_summary[assignment["name"]] = {
                    "total_submissions": len(submissions),
                    "graded_submissions": len(graded_submissions),
                    "average_grade": sum(scores) / len(scores) if scores else 0,
                    "max_grade": max(scores) if scores else 0,
                    "min_grade": min(scores) if scores else 0,
                    "points_possible": assignment.get("points_possible", 0),
                }

        logger.info("Successfully completed grades summary fetch")
        return {
            "course_id": course_id,
            "fetch_timestamp": datetime.now().isoformat(),
            "grades_summary": grades_summary,
        }

    def save_grades_to_json(
        self, grades_data: Dict[str, Any], filename: Optional[str] = None
    ) -> str:
        """Save grades data to JSON file.

        Args:
            grades_data: Grades data dictionary
            filename: Output filename (optional)

        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"grades_data_{grades_data['course_id']}.json"
        with open(filename, "w") as f:
            json.dump(grades_data, f, indent=2)
        logger.info(f"Grades data saved to {filename}")
        return filename

    def save_grades_to_csv(
        self, grades_data: Dict[str, Any], filename: Optional[str] = None
    ) -> str:
        """Save grades data to CSV file for easy analysis.

        Args:
            grades_data: Grades data dictionary
            filename: Output filename (optional)

        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"grades_summary_{grades_data['course_id']}.csv"

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow(
                [
                    "Assignment Name",
                    "Total Submissions",
                    "Graded Submissions",
                    "Average Grade",
                    "Max Grade",
                    "Min Grade",
                    "Points Possible",
                ]
            )

            # Write grade summary data
            for assignment_name, summary in grades_data["grades_summary"].items():
                writer.writerow(
                    [
                        assignment_name,
                        summary["total_submissions"],
                        summary["graded_submissions"],
                        round(summary["average_grade"], 2),
                        summary["max_grade"],
                        summary["min_grade"],
                        summary["points_possible"],
                    ]
                )

        logger.info(f"Grades summary saved to {filename}")
        return filename

    def generate_grade_reports(
        self, course_id: int, output_dir: str
    ) -> Optional[tuple[str, str]]:
        """
        Orchestrates fetching grades and saving them to JSON and CSV report files.
        This function consolidates the logic from the main() into a reusable method.

        Args:
            course_id: The Canvas course ID for which to generate reports.
            output_dir: The directory to save the report files in.

        Returns:
            A tuple containing the full file paths to the generated JSON and CSV reports,
            or None if the process fails.
        """
        logger.info(f"Generating grade reports for course: {course_id}")
        try:
            grades_data = self.fetch_course_grades(course_id)
            if not grades_data:
                logger.warning(f"No grade data returned for course {course_id}.")
                return None

            json_filename = f"grades_data_{course_id}.json"
            csv_filename = f"grades_summary_{course_id}.csv"
            json_filepath = os.path.join(output_dir, json_filename)
            csv_filepath = os.path.join(output_dir, csv_filename)

            self.save_grades_to_json(grades_data, filename=json_filepath)
            self.save_grades_to_csv(grades_data, filename=csv_filepath)

            logger.info(
                f"Successfully generated grade reports: {json_filepath}, {csv_filepath}"
            )
            return json_filepath, csv_filepath
        except Exception as e:
            logger.error(
                f"Failed to generate grade reports for course {course_id}: {e}"
            )
            return None

    def fetch_assignment_groups(self, course_id: int) -> List[Dict[str, Any]]:
        logger.info(f"Generating Assignment Groups for course: {course_id}")

        endpoint = f"courses/{course_id}/assignment_groups"
        assignment_groups = self.get_paginated_list(endpoint=endpoint)
        return assignment_groups

if __name__ == "__main__":
    try:
        fetcher = CanvasGradesFetcher()
        course_id = 240102  # Example course ID

        print(f"Fetching grades for course: {course_id}")
        grades_data = fetcher.fetch_course_grades(course_id)
        json_file = fetcher.save_grades_to_json(grades_data)
        csv_file = fetcher.save_grades_to_csv(grades_data)

        print(f"\nData saved to:\n  JSON: {json_file}\n  CSV:  {csv_file}")

    except Exception as e:
        logger.error(f"Error in main execution: {e}")