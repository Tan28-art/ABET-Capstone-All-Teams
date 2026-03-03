import requests
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin
from urllib.parse import unquote
from collections import defaultdict

# from dotenv import load_dotenv
# load_dotenv()

from create_html import WriteAbetHtml


# CONFIGURATION
CANVAS_DOMAIN = os.getenv("CANVAS_DOMAIN", "canvas.asu.edu")  # host only is OK
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN") or os.getenv("canvas_access_token")
SOURCE_COURSE_ID = os.getenv("SOURCE_COURSE_ID", "240102")
DESTINATION_COURSE_ID = os.getenv("DESTINATION_COURSE_ID", SOURCE_COURSE_ID)

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
CANVAS_BASE_URL = f"https://{CANVAS_DOMAIN}/"
if not CANVAS_TOKEN:
    raise RuntimeError("Missing Canvas API token. Set CANVAS_TOKEN in your environment or .env file.")
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
TEMP_DIR = "temp_html_files"


def fetch_all_course_files(canvas_domain, course_id, headers):
    """
    Fetch ALL files in a course using /files (paginated).
    canvas_domain can be either:
      - "canvas.asu.edu"
      - "https://canvas.asu.edu"
    """
    all_files = []

    # Ensure scheme exists
    if not str(canvas_domain).startswith("http"):
        canvas_domain = "https://" + str(canvas_domain).strip("/")

    url = f"{canvas_domain}/api/v1/courses/{course_id}/files?per_page=100"

    while url:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        all_files.extend(r.json())

        next_url = None
        link_header = r.headers.get("Link", "")

        for part in link_header.split(","):
            if 'rel="next"' in part:
                next_url = part[part.find("<") + 1 : part.find(">")]
                break

        url = next_url

    print("TOTAL FILES FETCHED:", len(all_files))
    return all_files


def add_to_canvas(course_name, semester, year):
    try:
        local_path = os.path.join(TEMP_DIR, "test.html")
        with open(local_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML: {e}")
        raise

    page_data = {
        "wiki_page": {
            "title": f"{course_name}",
            "body": f"{html_content}",
        }
    }

    try:
        upload_response = requests.post(
            url=f"{API_BASE_URL}courses/{DESTINATION_COURSE_ID}/pages",
            json=page_data,
            headers=HEADERS,
        )
        upload_response.raise_for_status()
        print("  - Successfully uploaded page")
    except Exception as e:
        print(f"  - Failed to upload page: {e}")
        raise

    return upload_response.json()


def add_abet_to_canvas():
    try:
        local_path = os.path.join(TEMP_DIR, "abet.html")
        with open(local_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading ABET HTML: {e}")
        raise

    page_data = {
        "wiki_page": {
            "title": "CSE-ABET Assessment Instruments and Samples",
            "body": f"{html_content}",
        }
    }

    try:
        upload_response = requests.post(
            url=f"{API_BASE_URL}courses/{DESTINATION_COURSE_ID}/pages",
            json=page_data,
            headers=HEADERS,
        )
        upload_response.raise_for_status()
        print("  - Successfully uploaded ABET page")
    except Exception as e:
        print(f"  - Failed to upload ABET page: {e}")
        raise

    return upload_response.json()


def get_paginated_list(endpoint, params=None):
    all_items = []
    url = urljoin(API_BASE_URL, endpoint)
    params = params or {}
    params["per_page"] = 100

    while url:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        all_items.extend(response.json())

        url = None
        if "Link" in response.headers:
            links = requests.utils.parse_header_links(response.headers["Link"])
            for link in links:
                if link.get("rel") == "next":
                    url = link["url"]
                    break

        params = None

    return all_items

def publish_module(course_id, module_id):
    module_data = {"module": {"published": "true"}}
    response = requests.put(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}", headers=HEADERS, json=module_data)
    response.raise_for_status()
    print(f"Module Published Status: {response.status_code}")
    return response.json()

def upload_module_to_canvas(course_id, module_name):
    # Check if the module already exists
    all_mods = []
    endpoint = f"courses/{course_id}/modules"
    url = urljoin(API_BASE_URL, endpoint)
    file_folders = get_paginated_list(endpoint, params={"include[]": "modules"})
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    all_mods.extend(response.json())

    for module in all_mods:
        if module.get("name") == module_name:
            print(f"Module {module_name} already exists with id {module.get("id")}")
            return module
    
    # If the module does not exist, add it to the canvas page:
    print(f"Uploading '{module_name}' module to Canvas...")
    module_data = {"module": {"name": module_name, "position": 1}}
    response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules", headers=HEADERS, json=module_data)
    response.raise_for_status()
    print(f"Status: {response.status_code}")
    return response.json()

def add_single_module_item(course_id, module_id, page):
    # Check if the module item already exists
    endpoint = f"courses/{course_id}/modules/{module_id}/items"
    module_items = get_paginated_list(endpoint)

    for item in module_items:
        if item.get("title") == page.get("title"):
            print(f"Module {item.get("title")} already exists with id {item.get("id")}")
            return

    # If module does not already exist, add to the module
    module_item_data = {
        "module_item": {
            "title": page.get("title"),
            "type": "Page",
            "page_url": page.get("url"),
        }
    }
    response = requests.post(
        f"{API_BASE_URL}courses/{course_id}/modules/{module_id}/items",
        headers=HEADERS,
        json=module_item_data,
    )
    response.raise_for_status()
    print(f"Status: {response.status_code}")


def find_file_folder(course_id, semester, year, course_code, instructor_name):
    print(f"Finding all ({year} {semester.capitalize()}) folders for {course_code} in course {course_id}...")
    endpoint = f"courses/{course_id}/folders"
    file_folders = get_paginated_list(endpoint, params={"include[]": "folders"})

    # sort by semester, year, course_code, (add instructor_name functionality when folder name is changed from extraction_api)
    return [f for f in file_folders if f"({year} {semester.capitalize()})" in f.get("full_name", "") and course_code in f.get("full_name", "")]


def get_files(course_id: str, semester: str, year: str, file_folders: list[dict]) -> tuple[dict, str]:
    if not file_folders:
        raise RuntimeError("No folders were returned from Canvas. Check permissions/course_id.")

    course_name = file_folders[0].get("full_name", "").split('/')[1] or "COURSE"

    print("Fetching file list once (paginated)...")
    all_files = get_paginated_list(f"courses/{course_id}/files")

    files_by_folder: dict[int, list[dict]] = defaultdict(list)
    for f in all_files:
        fid = f.get("folder_id")
        if fid is not None:
            files_by_folder[int(fid)].append(f)

    files: dict[str, list[dict]] = {"Syllabus": [], "Assignments": []}

    for folder in file_folders:
        name = (folder.get("name") or "").lower()
        folder_id = int(folder.get("id"))
        folder_files = files_by_folder.get(folder_id, [])

        if "syllabus" in name:
            files["Syllabus"].extend(folder_files)
        elif "test_assignments" in name or "assign" in name:
            files["Assignments"].extend(folder_files)

    print(f"Collected: Syllabus files={len(files['Syllabus'])}, Assignments files={len(files['Assignments'])}")
    return files, course_name


def main():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    semester = "fall"
    year = "2023"

    #### ADD to api
    # (needs to be connected + course_code designated from running the extraction script)
    # (needs to be labeled + connected from extraction scripts)
    # For now, add as fields in UI like the year + semester
    course_code = "CSE 423"
    instructor_name = "instructor_placeholder"

    html_writer = WriteAbetHtml()

    # 1) Find folder structure for the term (Also sort by course_code + add instructor_name functionality)
    file_folders = find_file_folder(SOURCE_COURSE_ID, semester, year, course_code, instructor_name)

    # 2) Get your grouped files (syllabus/assignments) from your faster method
    files_by_group, course_name = get_files(SOURCE_COURSE_ID, semester, year, file_folders)

    # 3) ALSO fetch all files (paginated) for your writer’s matching by folder_id
    all_files = fetch_all_course_files(CANVAS_DOMAIN, SOURCE_COURSE_ID, HEADERS)

    # 4) Build the final "files" dict the writer expects
    syllabus_list = [
        f for f in all_files
        if (f.get("display_name") or f.get("filename") or "").lower() in ["syllabus_body.pdf", "syllabus.pdf"]
    ]

    files = dict(files_by_group)  # keep "Syllabus"/"Assignments"
    files["ALL_FILES"] = all_files
    files["Syllabus"] = syllabus_list or files.get("Syllabus", [])

    # 5) Create module
    module_name = f"Courses - Course Folders and Student Work Samples ({semester.capitalize()} {year})"
    module = upload_module_to_canvas(DESTINATION_COURSE_ID, module_name)

    # 6) Build HTML + upload page + add to module
    html_writer.set_up_course_page(file_folders, files, semester, year)
    page = add_to_canvas(course_name, semester, year)
    add_single_module_item(DESTINATION_COURSE_ID, module.get("id"), page)

    # 7) Publish the module and its contents
    publish_module(DESTINATION_COURSE_ID, module.get("id"))

    shutil.rmtree(TEMP_DIR)
    print("\nProcess finished.")

if __name__ == "__main__":
    main()