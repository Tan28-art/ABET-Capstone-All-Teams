# Job Trigger API (Implemented)

## Endpoint
POST '/process-course-with-roster/{course_id}'

## Purpose
Triggers course processing for:
- extraction ("extract")
- ABET report generation ("abet")
- both ("all")

## Path Params
- 'course_id' (string) - Canvas course identifier

## Headers
- 'canvas_access_token' (string, required) - Canvas access token used for API calls

## Query Params
- 'tasks' (string, default: "all") - one of: 'extract', 'abet', 'all'

## Multipart From Data
- 'roster_file' (file, optional/required depending on tasks)
    - Required when tasks include 'abet' or 'all'

## Responses
### 200 OK
'''json
{"message": "Processing complete for tasks: 'all'."}