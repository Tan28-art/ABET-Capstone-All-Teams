from PyPDF2 import PdfReader

reader = PdfReader("documents/2025-2026_EAC_Criteria.pdf")

text = ""
for page in reader.pages:
    text += page.extract_text()

print(text)