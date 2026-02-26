import requests
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin
from urllib.parse import unquote
from create_html import WriteAbetHtml

# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
CANVAS_TOKEN = os.getenv("canvas_access_token")
SOURCE_COURSE_ID = "240102"
DESTINATION_COURSE_ID = "240102" #226368

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
CANVAS_BASE_URL = f"https://{CANVAS_DOMAIN}/"
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
TEMP_DIR = "temp_html_files"


def add_to_canvas(course_name, semester, year):
    try:
        local_path = os.path.join(TEMP_DIR, 'test.html')
        with open(local_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error: {e}")
    page_data = {
        "wiki_page": {
            "title": f"{course_name} ({semester.capitalize()} {year})",
            "body": f"{html_content}"
        }
    }

    try:
        upload_response = requests.post(url=f"{API_BASE_URL}courses/{DESTINATION_COURSE_ID}/pages", json=page_data, headers=HEADERS)
        upload_response.raise_for_status()
        if confirmation := upload_response.json():
            print(f"  - Successfully uploaded page")
    except Exception as e:
        print(f"  - Failed to upload page : {e}")
    return upload_response.json()

def add_abet_to_canvas():
    try:
        local_path = os.path.join(TEMP_DIR, 'abet.html')
        with open(local_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error: {e}")
    page_data = {
        "wiki_page": {
            "title": f"CSE-ABET Assessment Instruments and Samples",
            "body": f"{html_content}"
        }
    }

    try:
        upload_response = requests.post(url=f"{API_BASE_URL}courses/{DESTINATION_COURSE_ID}/pages", json=page_data, headers=HEADERS)
        upload_response.raise_for_status()
        if confirmation := upload_response.json():
            print(f"  - Successfully uploaded page")
    except Exception as e:
        print(f"  - Failed to upload page : {e}")
    return upload_response.json()


def get_paginated_list(endpoint, params=None):
    """
    Retrieves a complete list of items from a paginated Canvas API endpoint.

    Args:
        endpoint (str): The API endpoint to query (e.g., 'courses/123/assignments').
        params (dict, optional): Initial URL parameters. Defaults to None.

    Returns:
        list: A list containing all items retrieved from all pages.
    """
    all_items = []
    url = urljoin(API_BASE_URL, endpoint)
    params = params or {}
    params["per_page"] = 100

    while url:
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            all_items.extend(response.json())

            url = None  # Assume no next page unless found
            if "Link" in response.headers:
                links = requests.utils.parse_header_links(response.headers["Link"])
                for link in links:
                    if link.get("rel") == "next":
                        url = link["url"]
            params = None  # Next URL from Canvas already contains all parameters
        except requests.exceptions.RequestException as e:
            print(
                f"API Error on GET {url}: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
            )
            break

    return all_items

def upload_module_to_canvas(course_id, module_name):
    """
    Uploads a module for a course's data to Canvas.

    Args:
        course_id (str): The ID of the destination Canvas course.
        course (str): unique course title string
        semester (str): Semester to label the module by.
        year (str): Year to label the module by.
    """
    print(f"Uploading '{module_name}' module to Canvas...")
    try:
        module_data = {
            "module": {
                "name": module_name,
                "position": 1,
            }
        }
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules",headers=HEADERS,json=module_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(
            f"API Error on: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
        )
    return response.json()

def add_single_module_item(course_id, module_id, page):
    """
    Adds a single module item to a module

    Args:
        course_id (str): The ID of the destination Canvas course.
        module_id (str): The module_id of the module the file will be added to
        page_id (str): The page_id of the page which will be added.
        page_name (str): The name of the page which will be added.

    Returns:
        int: updated position for grouping of files in the module
    """
    try:
        module_item_data = {"module_item": {
            "title": page.get("title"),
            "type": "Page",
            "page_url": page.get("url"), #single module id
        }}
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}/items",headers=HEADERS,json=module_item_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
    except Exception as e:
        print(f"  - Failed to upload: {e}")
        response.raise_for_status()
        print(f"Status: {response.status_code}")

def find_file_folder(course_id, semester, year):
    """
    Finds all course data file folders for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        term (str): The term to filter file folders by.
        course_code (str): The course_code to filter file folders by.

    Returns:
        list: A list of folder objects that match the term-course_code combination.
    """
    print(f"Finding all ({year} {semester.capitalize()}) folders in course {course_id}...")
    endpoint = f"courses/{course_id}/folders"
    file_folders = get_paginated_list(endpoint, params={"include[]":"folders"})

    return[
        f
        for f in file_folders
        if f"({year} {semester.capitalize()})" in f.get("full_name")
    ]

def find_unique_courses(file_folders):
    # find all folders labeled with "semester_year"
    unique_courses = set()
    if not file_folders:
        print("No file folders found.")
        return
    print(f"\nFound {len(file_folders)} file folders with course data.")
    for folder in file_folders:
        source_course = folder['full_name'].rsplit('/')[1]
        unique_courses.add(source_course.split('_')[2]) # add name after semester_year identifier
        print(f"\nFound: {folder['full_name']}")
   # add_to_canvas()
    for course in unique_courses:
        print(course)
    return unique_courses

def get_files(course_id, semester, year, file_folders):
    """
    Finds all course data files for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        course (str): unique course title string
        semester (str): The semester to filter file folders by.
        year (str): The year to filter file folders by.

    Returns:
        list: A list of file objects that match the course, semester-year combination.
    """
    course_name = file_folders[0].get("name")[0:7]
    print(f"\nSearching for {course_name} assignment data in course {course_id}...")
    endpoint = f"courses/{course_id}/files"

    folder_to_files = {}
    for f in file_folders: #search for files associated with each folder
        full_folder_name = f.get("full_name")
        print("Found: ",full_folder_name)
        abbrv_name = f.get("name")
        if f"{course_name}" in abbrv_name: #sort out main folder name
            continue
        else:
            if "Test_Assignments" in full_folder_name:
                folder_id = f.get("id")
                print(f"Folder: {abbrv_name} | Id: {folder_id}")
                files = get_paginated_list(endpoint)
                found_files = [f for f in files if f.get("folder_id") == folder_id]
                folder_to_files[abbrv_name] = found_files # map folder_to_file provided folder_name key
    return folder_to_files, course_name

# Steps:
# 1. Setup: Clean and create a temporary directory for HTML file storage.
# 2. Get list of all folders in fall-semester (should include multiple labelled courses)
# 3. Get list of all files in the file folders (should include multiple labelled assignment groups)
# 4. Add page for each course
# 5. Teardown: Clean up the temporary directory.
def main():

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    # Passed in from user
    semester = "fall"
    year = "2023"

    html_writer = WriteAbetHtml()

   # find course_code to sort folders by
  #  course_info = requests.get(url=f"{API_BASE_URL}courses/{SOURCE_COURSE_ID}", headers=HEADERS).json()
 #   course_code = course_info.get('course_code')
  #  course_name = course_info.get('name')

    # Find all file folders for corresponding fall-semester combination
    file_folders = find_file_folder(SOURCE_COURSE_ID, semester, year)
    files, course_name = get_files(SOURCE_COURSE_ID, semester, year, file_folders)

    # add placeholder modules (uncomment when wanted):
    """ upload_module_to_canvas(DESTINATION_COURSE_ID, "Assessment Instruments and Student Work Samples")
    upload_module_to_canvas(DESTINATION_COURSE_ID, "CSE Capstone Course Showcases")    
    upload_module_to_canvas(DESTINATION_COURSE_ID, "Student and Credit Transfer")
    upload_module_to_canvas(DESTINATION_COURSE_ID, "CSE Faculty Meeting Minutes")
    """
    # add course folder module
    module_name = f"Courses - Course Folders and Student Work Samples ({semester.capitalize()} {year})"
    module = upload_module_to_canvas(DESTINATION_COURSE_ID, module_name)
    
    # Add course page(s) to canvas - under course folder module
    html_writer.set_up_course_page(file_folders, files, semester, year)
    page = add_to_canvas(course_name, semester, year)
    add_single_module_item(DESTINATION_COURSE_ID, module.get("id"), page)
    """
    # set up abet page (uncomment when wanted):
    module_name = f"Assessment Instruments and Student Work Samples"
    module = upload_module_to_canvas(DESTINATION_COURSE_ID, module_name)
    html_writer.set_up_abet_page()
    abet_page = add_abet_to_canvas()
    add_single_module_item(DESTINATION_COURSE_ID, module.get("id"), abet_page)
    """
    shutil.rmtree(TEMP_DIR)
    print("\nProcess finished.")

if __name__ == "__main__":
    main()