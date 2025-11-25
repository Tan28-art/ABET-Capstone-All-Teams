"""
abetReportGenerator-test6.py
--------------------------------
Hybrid ABET Assessment Report Generator

- Reads Canvas JSON data
- Produces ABET-formatted PDF reports with standardized sections
- Uses Llama for natural language result and feedback generation

Output matches the format defined in official templates:
  (Assessment Report Section 1: Summary)
  (Assessment Report Section 2: Assessment Instrument)
"""

import os, json, csv, time
from glob import glob
from pathlib import Path
from spire.doc import *
from spire.doc.common import *
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, logging

logging.set_verbosity_error()

# CONFIG SECTION
json_input_glob = "input_jsons/*.json"
pdf_out_dir = "generated_pdfs"
os.makedirs(pdf_out_dir, exist_ok=True)
output_csv = "ABETReportSummary.csv"

model_path = r"C:\Users\AMD\Llama\Llama-3.1-8B-Instruct"
prompt_base = (
    "You are an education assessment expert generating ABET course assessment reports. "
    "You will produce only the report text itself — clean, factual, and formatted in professional academic language. "
    "Do not include any self-references, thoughts, reasoning, or meta commentary. "
    "Do not describe what you are doing, ask questions, or explain the process. "
    "Do not include phrases such as 'Termination token generated', 'Proceeding', 'Here is the generated report', or similar. "
    "Your output must start directly with the first section of the ABET report, "
    "and end immediately after providing the feedback section. "
    "Do not include any additional summaries or instructions."
)

max_tokens = 512

print("Loading Llama model...")
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(
    model_path, torch_dtype=torch.bfloat16, device_map="auto"
)
device = next(model.parameters()).device
print(f"Model ready on {device}")

#  HELPER FUNCTIONS 

# Read in Json input files amd store them
def load_json_files(glob_pattern):
    files = sorted(glob(glob_pattern))
    data = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                js = json.load(fh)
            data.append((f, js))
        except Exception as e:
            print(f"Failed to read {f}: {e}")
    return data


# Reduce key Json information into simpler data structures for the LLM prompt
def build_structured_summary(js):
    """Create structured factual summary text for Llama prompt."""
    name = js.get('course_identification', {}).get('name','N/A')
    outcome = js.get('outcome_identification', {}).get('title', 'N/A')
    assignments = js.get('contributing_assignments', [{}])
    total = len(assignments)
    description = sum(1 for a in assignments if a.get("description"))
    lines = [f"Course ID: {name}", f"Outcome Assessed: {outcome}", f"Total Assignments: {total}", f"Assignments with descriptions: {description}"]

    for a in assignments:
        lines.append(f"- {a.get('name', 'Unnamed')} | Points: {a.get('points_possible', 'N/A')} | Due: {a.get('due_at', 'N/A')}")
        if a.get("rubric"):
            lines.append("  Rubric:")
            for r in a["rubric"]:
                lines.append(f"    * {r.get('description', 'No desc')} ({r.get('points', 'N/A')} pts)")
    return "\n".join(lines)


# Call the local LLM with condensed Json information
def llama_generate_section(summary_text):
    """Use Llama to generate clean, factual ABET report sections only."""
    prompt = f"{prompt_base}\n\nGiven the following structured Canvas data, write:\n" \
             f"1. Interpretation of results (include sample size, rubric count, and assignment type distribution).\n" \
             f"2. Whether the desired outcome was met or not met.\n" \
             f"3. Feedback on what changes are needed if outcome was not met.\n\n" \
             f"{summary_text}\n\nBegin report now:\n"

    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_tokens, eos_token_id=tokenizer.eos_token_id)
    input_len = inputs["input_ids"].shape[-1]
    gen = out[0][input_len:]
    return tokenizer.decode(gen, skip_special_tokens=True).strip()


# Word Report Builder Class
class WordReportBuilder:
    def __init__(self, out_path):
        self.out_path = out_path
        self.document = Document()
        self.section = self.document.AddSection()

        # Try adding named styles (preferred)
        self.style_normal = None
        self.style_heading = None
        try:
            self.style_normal = self.document.Styles.Add("NormalStyle", StyleType.ParagraphStyle)
            self.style_heading = self.document.Styles.Add("HeadingStyle", StyleType.ParagraphStyle)
        except Exception:
            # Some wrappers expose AddStyle differently; try fallback
            try:
                self.style_normal = self.document.AddStyle("NormalStyle", StyleType.ParagraphStyle)
                self.style_heading = self.document.AddStyle("HeadingStyle", StyleType.ParagraphStyle)
            except Exception:
                # Styles unavailable — will use inline formatting
                self.style_normal = None
                self.style_heading = None

        # Configure styles if available
        if self.style_normal is not None:
            self.style_normal.CharacterFormat.FontName = "Times New Roman"
            self.style_normal.CharacterFormat.FontSize = 12
        if self.style_heading is not None:
            self.style_heading.CharacterFormat.FontName = "Times New Roman"
            self.style_heading.CharacterFormat.FontSize = 14
            self.style_heading.CharacterFormat.Bold = True

    # Defines a text block as a heading, with appropriate formatting
    def heading(self, text):
        p = self.section.AddParagraph()
        if self.style_heading is not None:
            p.ApplyStyle("HeadingStyle")
            p.AppendText(text)
        else:
            run = p.AppendText(text)
            run.CharacterFormat.FontName = "Times New Roman"
            run.CharacterFormat.FontSize = 14
            run.CharacterFormat.Bold = True
        p.Format.AfterSpacing = 8

    # Defines a text block as a paragraph, with appropriate formatting
    def paragraph(self, text):
        p = self.section.AddParagraph()
        if self.style_normal is not None:
            p.ApplyStyle("NormalStyle")
            p.AppendText(text)
        else:
            run = p.AppendText(text)
            run.CharacterFormat.FontName = "Times New Roman"
            run.CharacterFormat.FontSize = 12
        p.Format.AfterSpacing = 6
        p.Format.FirstLineIndent = 20

    # Defines a text block as a bullet-point list, with appopriate formatting
    def bullet_point(self, text):
        p = self.section.AddParagraph()
        p.ListFormat.ApplyBulletStyle()
        if self.style_normal is not None:
            p.ApplyStyle("NormalStyle")
            p.AppendText(text)
        else:
            run = p.AppendText(text)
            run.CharacterFormat.FontName = "Times New Roman"
            run.CharacterFormat.FontSize = 12
        p.Format.AfterSpacing = 4

    # Method for generating and formatting Word document reports
    def build_report(self, report_data, llama_summary):

        # Set the documents primary heading
        self.heading("Assessment Report Section 1: Summary")

        # Add the Outcome and Course information to the top of the page
        self.paragraph(f"Outcome assessed: {report_data.get('outcome_identification', {}).get('title', 'N/A')}")
        self.paragraph(f"Course: {report_data.get('course_identification', {}).get('name','N/A')} "
                    f"({report_data.get('course_identification', {}).get('course_code','N/A')})")

        # Find the Metric Instrument Type 
        self.paragraph(f"Metric Instrument Type: {report_data.get('contributing_assignments', {})[0].get("metric", "N/A")}")
        
        # Find the assignment Goals 
        self.paragraph("Goals:")
        self.paragraph(f"1. To show competency, a student must score at least {report_data.get('contributing_assignments', {})[0].get("threshold", "70%")}.")
        self.paragraph(f"2. To show the outcome has been met, {report_data.get('contributing_assignments', {})[0].get("threshold", "70%")} of the students must show competency.")

        # Course-Level Results, Sample Size, Percent Competent, etc.
        self.paragraph(f"Sample size: {report_data.get('results', {}).get('distribution_by_major', {}).get('CS/CSE', {}).get('sample_size', 'N/A')}")
        self.paragraph(f"Course-Level Results: ")
        self.paragraph(f"   1. Score Distribution (Percentage): {report_data.get('results', {}).get('distribution_by_major', {}).get('CS/CSE', {}).get('percent_competent', 'N/A')}%")
        self.paragraph(f"   2. Score Distribution (Numerical): {report_data.get('results', {}).get('distribution_by_major', {}).get('CS/CSE', {}).get('number_competent', 'N/A')}")
        self.paragraph(f"   3. Outcome Met: {report_data.get('results', {}).get('distribution_by_major', {}).get('CS/CSE', {}).get('outcome_met', 'N/A')}")
        self.paragraph(f"   4. If Outcome was not met, what changes need to be made to ensure that students can meet this outcome in the future? {llama_summary}")

        # Set the Secondary Heading
        self.heading("Assessment Report Section 2: Assessment Instrument")

        # Iterate through each assignment
        #    Clean and display assignment information
        assignments = report_data.get('contributing_assignments', [{}])
        if assignments:
            for assign in assignments:
                if assign:
                    instrument = assign.get('description_files_content', {})
                    self.paragraph(f"Assessment Instrument: {[text.replace("\n", "") for text in instrument.values()]}")
                else:
                    self.paragraph("Assessment Instrument: N/A")
        else:
            self.paragraph("Assessment Instrument: N/A")

        self.document.SaveToFile(self.out_path, FileFormat.Docx2019)
        self.document.Close()
        print(f"Word report saved → {self.out_path}")



# MAIN FUNCTION 
def main():

    # Read in Json input
    data = load_json_files(json_input_glob)
    summary_records = []
    for path, js in data:
        base = Path(path).stem
        print(f"\nProcessing {base} ...")

        # Prompt the LLM, and store summary output
        summary_text = build_structured_summary(js)
        llama_output = llama_generate_section(summary_text)

        # Split Llama output into result & feedback heuristically
        split_marker = "Feedback:" if "Feedback:" in llama_output else None
        if split_marker:
            results_text, feedback_text = llama_output.split(split_marker, 1)
        else:
            results_text, feedback_text = llama_output, "N/A"

        # Create word builder object
        word_path = os.path.join(pdf_out_dir, f"{base}_ABET_Report.docx")
        builder = WordReportBuilder(word_path)

        # Use the object to build a report with Json input and LLM output
        builder.build_report(js, results_text)

        # Generate summary record
        summary_records.append({
            "input_file": path,
            "assignments": len(js.get("assignments", [])),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })

    # Save summary records
    if summary_records:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=summary_records[0].keys())
            writer.writeheader()
            writer.writerows(summary_records)
        print(f"\nSummary CSV written: {output_csv}")


if __name__ == "__main__":
    main()
