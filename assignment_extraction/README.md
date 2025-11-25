# ABET-Tools
Github Repo for the ABET Tools Capstone Project

## Getting Started
1. Clone repo
```
git clone https://github.com/your-username/ABET-Tools.git](https://github.com/Tan28-art/ABET-Capstone-All-Teams.git
cd ABET-Capstone-All-Teams
git checkout origin/Team-2
git fetch
git pull
```

2. create virtual env
```
python -m venv your-venv-name

# Activate venv
# For mac/linux
source ./your-venv-name/bin/activate

# for windows (using git bash terminal)
source ./your-venv-name/Scripts/activate
```

3. Install Dependencies
```
pip install -r requirements.txt
```

4. Configure access token
```
export canvas_access_token="your canvas access token"
```

5. Run file
```
python assignment_extraction_api.py
```
