# Creates html pages to upload for courses & ABET reports

import requests
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin
from urllib.parse import unquote


class WriteAbetHtml:

    def __init__(self):
        self.temp_dir = "temp_html_files"
        self.canvas_base_url = f"https://canvas.asu.edu/"
        self.source_course_id = "240102"
        pass

    def write_to_page(self, content):
        try:
            local_path = os.path.join(self.temp_dir, 'test.html')
            with open(local_path, 'a') as f:
                f.write(content)
        except IOError as e:
            print(f"Error writing to the html file: {e}")

    def write_to_page_abet(self, content):
        try:
            local_path = os.path.join(self.temp_dir, 'abet.html')
            with open(local_path, 'a') as f:
                f.write(content)
        except IOError as e:
            print(f"Error writing to the html file: {e}")

    def add_abet_table_row(self, i, abet_outcome):
        student_outcome_cell = f"""
        <tr>
            <td>CSE({i + 1})<br>{abet_outcome}</td>
            <td>
                        <p>CSE Placeholder Assessment Report and Instrument:</p>
                        <ul>
                            <li>CSE Placeholder Assessment Report.pdf</li>
                            <li>CSE Placeholder Homework.pdf</li>
                        </ul>
                        <p>CSE Placeholder Assessment Report and Instrument:</p>
                        <ul>
                            <li>CSE Placeholder Assessment Report.pdf</li>
                            <li>CSE Placeholder Project.pdf</li>
                        </ul>
                    </td>
            <td>CSE Placeholder:</td>
        </tr>
        """
        self.write_to_page_abet(student_outcome_cell)

    def set_up_abet_page(self):
        content = """
        <h1 class="page-title">CSE-ABET Assessment Instruments and Samples</h1>
        <h3>Assessment Instruments and Student Samples</h3>
        <p>CSE-ABET Assessment Plan and Coverage.pdf</p>

        <table style="width: 100%;" border="1">
            <thead>
                <tr>
                    <th>Student Outcome</th>
                    <th>Assessment Instruments</th>
                    <th>Student Work Samples</th>
                </tr>
            </thead>
            <tbody>
        """
        self.write_to_page_abet(content)

        abet_outcomes = [
            "an ability to identify, formulate, and solve complex engineering problems by applying principles of engineering, science, and mathematics.",
            "an ability to apply engineering design to produce solutions that meet specified needs with consideration of public health, safety, and welfare, as well as global, cultural, social, environmental, and economic factors.",
            "an ability to communicate effectively with a range of audiences.",
            "an ability to recognize ethical and professional responsibilities in engineering situations and make informed judgments, which must consider the impact of engineering solutions in global, economic, environmental, and societal contexts.",
            "an ability to function effectively on a team whose members together provide leadership, create a collaborative and inclusive environment, establish goals, plan tasks, and meet objectives.",
            "an ability to develop and conduct appropriate experimentation, analyze and interpret data, and use engineering judgment to draw conclusions.",
            "an ability to acquire and apply new knowledge as needed, using appropriate learning strategies."
        ]
        for i in range(7):
            self.add_abet_table_row(i, abet_outcomes[i])

        self.write_to_page_abet("</tbody></table>")

    def add_graded_work_course_page(self, file_folders, files, lab_projects, exams):
        table_set_up = """<h3>Graded Student Work</h3>
            <p>Lab Projects</p>
            <table style="width: 100%;" border="1">
                <thead>
                    <tr>
                        <th>Assessment</th>
                        <th>High</th>
                        <th>Mid</th>
                        <th>Low</th>
                    </tr>
                </thead>
            """

        self.write_to_page(table_set_up)
        for lab in lab_projects:
            lab_high = ""
            lab_low = ""
            lab_mid = ""
            lab_link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{lab.get("id")}"

            for folder in file_folders:
                if lab.get("folder_id") == folder.get("id"):
                    folders_files = files[folder.get("name")]
                    for file in folders_files:
                        filename = file.get("filename").lower()
                        link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{file.get("id")}"
                        if "high.pdf" in filename or "high.txt" in filename:
                            lab_high = f"<a href={link}>{filename}</a>"
                        if "low.pdf" in filename or "low.txt" in filename:
                            lab_low = f"<a href={link}>{filename}</a>"
                        if "avg.pdf" in filename or "avg.txt" in filename:
                            lab_mid = f"<a href={link}>{filename}</a>"
            # set row information:
            row = f"""
            <tbody>
                <tr>
                    <td><a href={lab_link}>{unquote(lab.get("filename"))}</a></td>
                    <td>{lab_high}</td>
                    <td>{lab_mid}</td>
                    <td>{lab_low}</td>
                </tr>
            </tbody>
        """
            self.write_to_page(row)  # repeat for however many rows there are

        self.write_to_page("</table>")  # close table
        for exam in exams:
            exam_high = ""
            exam_low = ""
            exam_mid = ""
            exam_link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{exam.get("id")}"

            for folder in file_folders:
                if exam.get("folder_id") == folder.get("id"):
                    folders_files = files[folder.get("name")]
                    for file in folders_files:
                        filename = file.get("filename").lower()
                        link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{file.get("id")}"
                        if "high.pdf" in filename or "high.txt" in filename:
                            exam_high = f"<a href={link}>{filename}</a>"
                        if "low.pdf" in filename or "low.txt" in filename:
                            exam_low = f"<a href={link}>{filename}</a>"
                        if "avg.pdf" in filename or "avg.txt" in filename:
                            exam_mid = f"<a href={link}>{filename}</a>"

        exam_set_up = """
    <p>Exams</p>
    <table style="width: 100%;" border="1">
        <thead>
            <tr>
                <th>Assessment</th>
                <th>High</th>
                <th>Mid</th>
                <th>Low</th>
            </tr>
        </thead>
    """
        self.write_to_page(exam_set_up)
        row = f"""
    <tbody>
            <tr>
                <td><a href={exam_link}>{unquote(exam.get("filename"))}</a></td>
                <td>{exam_high}</td>
                <td>{exam_mid}</td>
                <td>{exam_low}</td>
            </tr>
        </tbody>
    """
        self.write_to_page(row)  # repeat for however many rows there are
        self.write_to_page("</table>")  # close table

    def get_assignment_groups(self, file_folders, files):
        assignment_groups = []  #
        for folder in file_folders:
            f_name = folder.get("full_name")
            if f"Test_Assignments/" in f_name:
                split_name = f_name.split('Test_Assignments/', 1)[1]
                group_name = split_name.split('/', 1)[0]
                print("GROUP", split_name)
                if group_name not in assignment_groups:
                    assignment_groups.append(group_name)
        return assignment_groups

    """
    def get_lab_projects(self, file_folders, files):
        lab_projects = []
        for folder in file_folders:
            if f"assignments" in folder.get("full_name").lower():
                if f"assignment" in folder.get("name").lower():
                    folders_files = files[folder.get("name")]
                    for file in folders_files:
                        #print(f"{file.get("filename")} | {file.get("id")}")
                        filename = file.get("filename").lower()
                        if f"assignment" in filename:
                            if "avg" not in filename and "high" not in filename and "low" not in filename:
                                lab_projects.append(file)
        return lab_projects

    def get_exams(self, file_folders, files):
        exams = []
        for folder in file_folders:
            if f"assignments" in folder.get("full_name").lower():
                if f"quiz" in folder.get("name").lower() or f"exam" in folder.get("name") or f"test" in folder.get("name"):
                    folders_files = files[folder.get("name")]
                    for file in folders_files:
                        print(f"{file.get("filename")} | {file.get("id")}")
                        if f"description" in file.get("filename").lower():
                            exams.append(file)
        return exams
    """

    def get_assignments(self, group_name, file_folders, files):
        # Flatten ALL files from the dict into one list
        all_files = []
        try:
            for v in files.values():
                if isinstance(v, list):
                    all_files.extend(v)
        except Exception:
            pass

        assignments = []

        for folder in file_folders:
            full_name = folder.get("full_name", "")

            # Only folders under Test_Assignments/<group_name>/...
            if f"Test_Assignments/{group_name}" in full_name:
                folder_id = folder.get("id")

                # Collect every file whose folder_id matches this folder
                for f in all_files:
                    if f.get("folder_id") == folder_id:
                        filename = (f.get("filename") or "").lower()

                        # skip description.html
                        if "description" in filename and filename.endswith(".html"):
                            continue

                        assignments.append(f)

        print(f"GROUP '{group_name}' → found {len(assignments)} files")
        return assignments

    def _is_hml_file(self, filename_lower: str) -> bool:
        return (
                "high" in filename_lower
                or "mid" in filename_lower
                or "avg" in filename_lower
                or "low" in filename_lower
        )

    def _hml_label(self, filename_lower: str) -> str:
        if "high" in filename_lower:
            return "High"
        if "avg" in filename_lower or "mid" in filename_lower:
            return "Mid"
        if "low" in filename_lower:
            return "Low"
        return ""

    def set_up_course_page(self, file_folders, files, semester, year):
        # ----------------------------
        # 1) Syllabus
        # ----------------------------
        syllabus_link = "Invalid"
        try:
            syllabus_id = None
            for f in files.get("Syllabus", []):
                if (f.get("filename") or "").lower() in ["syllabus_body.pdf", "syllabus.pdf"]:
                    syllabus_id = f.get("id")
                    break

            if syllabus_id is not None:
                syllabus_link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{syllabus_id}"
        except Exception:
            syllabus_link = "Invalid"

        content = "<h3>Syllabus and Course Schedule</h3>\n"
        if syllabus_link != "Invalid":
            content += f"""
<ul>
  <li><a href="{syllabus_link}">Syllabus.pdf</a></li>
</ul>
"""
        else:
            content += "<ul><li>Syllabus is missing.</li></ul>\n"

        # ----------------------------
        # 2) Main Section Header
        # ----------------------------
        content += "<h3>Homework Assignments, Projects, Quizzes, and Exams</h3>\n"
        self.write_to_page(content)

        # ----------------------------
        # 3) Build groups from folders
        # ----------------------------
        assignment_groups = self.get_assignment_groups(file_folders, files)

        # ----------------------------
        # 4) Render each group
        # ----------------------------
        for group in assignment_groups:
            group_files = self.get_assignments(group, file_folders, files)

            if not group_files:
                self.write_to_page(f"<ul><li><b>{group}</b> (no files found)</li></ul>")
                continue

            has_hml = any(self._is_hml_file((f.get("filename") or "").lower()) for f in group_files)

            # A) TABLE format
            if has_hml:
                rows = {}

                for f in group_files:
                    fname = f.get("filename") or ""
                    fl = fname.lower()

                    if "description" in fl and fl.endswith(".html"):
                        continue

                    label = self._hml_label(fl)
                    if not label:
                        continue

                    base = fl
                    base = base.replace("_high", "").replace("-high", "").replace(" high", "")
                    base = base.replace("_avg", "").replace("-avg", "").replace(" avg", "")
                    base = base.replace("_mid", "").replace("-mid", "").replace(" mid", "")
                    base = base.replace("_low", "").replace("-low", "").replace(" low", "")
                    base = base.replace(".pdf", "").replace(".txt", "").replace(".docx", "").replace(".doc", "")

                    if base not in rows:
                        rows[base] = {"High": "", "Mid": "", "Low": ""}

                    link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{f.get('id')}"
                    rows[base][label] = f'<a href="{link}">{unquote(fname)}</a>'

                self.write_to_page(f"<h4>{group}</h4>")
                self.write_to_page("""
<table style="width: 100%;" border="1">
  <thead>
    <tr>
      <th>Assessment</th>
      <th>High</th>
      <th>Mid</th>
      <th>Low</th>
    </tr>
  </thead>
  <tbody>
""")

                for base_key in sorted(rows.keys()):
                    pretty_name = base_key.upper()
                    high = rows[base_key]["High"]
                    mid = rows[base_key]["Mid"]
                    low = rows[base_key]["Low"]

                    self.write_to_page(f"""
<tr>
  <td>{pretty_name}</td>
  <td>{high}</td>
  <td>{mid}</td>
  <td>{low}</td>
</tr>
""")

                self.write_to_page("</tbody></table>")

            # B) BULLET format
            else:
                self.write_to_page(f"<ul><li><b>{group}</b><br><ul>")

                for f in group_files:
                    fname = f.get("filename") or ""
                    fl = fname.lower()

                    if "description" in fl and fl.endswith(".html"):
                        continue

                    link = f"{self.canvas_base_url}courses/{self.source_course_id}/files/{f.get('id')}"
                    self.write_to_page(f'<li><a href="{link}">{unquote(fname)}</a></li>')

                self.write_to_page("</ul></li></ul>")