import requests
import os
from dotenv import load_dotenv
load_dotenv()
from pprint import pp

TOKEN = os.getenv("CANVAS_TOKEN")
BASE_URL = "https://asu.instructure.com/api/v1"

def add_module_item(course_id, module_id, filepath, insert_pos):
    """
    Adds a file as a module item.
    
    Args:
        course_id (string): ID of the course containing the module.
        module_id (string): ID of the module where the module item will be added to.
        filepath (string): The filepath of the file to be added as a module item.
        insert_pos (int): The position of where the module item will be inserted into.
    """
    
    # check if file to upload is valid
    if not os.path.isfile(filepath): raise("Invalid file for upload.")
    
    # initialize the file upload
    init_res = requests.post(
        url=f"{BASE_URL}/courses/{course_id}/files",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={
            "name": f"{os.path.basename(filepath)}", # name of file to be uploaded
            "parent_folder_path": "abet_assignment_data" # location of where the file will be uploaded to
            }
    )
    
    upload_info = init_res.json() # object containing info about file to be uploaded
    
    # finalize the file upload
    with open(filepath, "rb") as file:
        upload_res = requests.post(
            upload_info["upload_url"],
            data=upload_info["upload_params"],
            files={"file": file}
        )
        
    final_file = upload_res.json() # file object
    file_id = final_file["id"]
    
    # add the file as a module item
    item_add_res = requests.post(
        url=f"{BASE_URL}/courses/{course_id}/modules/{module_id}/items",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={
            "module_item[type]": "File",
            "module_item[content_id]": file_id,
            "module_item[position]": {insert_pos},
            "module_item[indent]": 1
            }
    )
    
    pp(item_add_res.json())
    
def add_module_items(course_id, module_id, dirpath, insert_pos):
    """
    Adds all files in a directory as module items sequentially.
    
    Args:
        course_id (string): ID of the course containing the module.
        module_id (string): ID of the module where the module item will be added to.
        dirpath (string): Directory path containing the files to be uploaded as moodule items.
        insert_pos (int): Starting position for where the module items will be inserted into.
    """
    
    # iterate through each file in the directory
    for filename in sorted(os.listdir(dirpath)):
        filepath = os.path.join(dirpath, filename) # get the filepath of the file
        if not os.path.isfile(filepath): continue # skip non-files
        
        add_module_item(course_id, module_id, filepath, insert_pos) # add the file as a module item
        insert_pos += 1 # increment the insert position
        
  
course_id = "240102" # course id for course "TRN-2025Fall-sdosburn"
module_id = "2723012" # module id for module "Testing Ground Fall 2025 Course Data"
dir = "./documents" # directory containing the files to upload
insert_pos = 7 # position of insertion for module items

# add_module_items(course_id, module_id, dir, insert_pos)