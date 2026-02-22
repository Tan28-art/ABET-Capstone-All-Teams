# Reporting Read API (Draft/Proposed)

> **Draft/Proposed:** These endpoints describe the intended REST API for reporting/dashboard teams to consume processed data.
> Confirm required endpoints and response shapes with the report generation team.

## API Versioning
- Proposed base path: `/api/v1`

## Auth (Assumption)
- Proposed: `Authorization: Bearer <token>`
- RBAC: separate permissions for triggering jobs vs reading reporting data

## Proposed Endpoints

### GET `/api/v1/courses/{course_id}/outcomes`
Returns outcome summaries for a course (Canvas outcomes mapped to ABET outcomes).

**Notes**
- Should support pagination if returning per-student records
- Should support filtering by outcome_id, assignment_id, term, major

### GET `/api/v1/courses/{course_id}/assignments`
Returns assignment metadata and derived analytics fields needed for reports.

### GET `/api/v1/courses/{course_id}/abet-summary`
Returns ABET-ready summary aggregates (counts, thresholds, attainment levels).

### GET `/api/v1/health`
Health check for uptime monitoring.

## Standard Error Model (Proposed)
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
