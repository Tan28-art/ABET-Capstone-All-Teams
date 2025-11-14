import requests
from bs4 import BeautifulSoup
from pprint import pp
import json


def extract_criteria(save_to_path=None):
    url = "https://www.abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-engineering-programs-2025-2026/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    criteria = {}
    counter = 1
    while True:
        criterion_code = f"GC{counter}"
        criterion = soup.find(id=criterion_code)
        if criterion is None: break
        
        criterion_title = criterion.text.split(". ")[1]
        criterion_desc = criterion.find_next_sibling("p").text
        
        criteria[criterion_code] = {
            "title": criterion_title,
            "desc": criterion_desc
        }
        counter += 1
        
    if save_to_path is not None:
        with open(save_to_path, "w", encoding="utf-8") as file:
            json.dump(criteria, file, indent=2, ensure_ascii=False)
        
    return criteria
        
def compare_criteria(old_criteria_path):
    with open (old_criteria_path, "r", encoding="utf-8") as file:
        old_criteria = json.load(file)
        
    current_criteria = extract_criteria()
    
    for criterion_code, old_criterion in old_criteria.items():
        old_title = old_criterion["title"]
        old_desc = old_criterion["desc"]
        
        current_criterion = current_criteria[criterion_code]
        current_title = current_criterion["title"]
        current_desc = current_criterion["desc"]
        
        print(f"{old_title} (old) vs {current_title} (current)")
        
def main():
    compare_criteria("./criteria.json")
    
if __name__ == "__main__":
    main()
        



#todo: iterate through each criterion code (GC<number>) to detect if new criteria has been added or old ones have been deleted. then for each one, compare title and description