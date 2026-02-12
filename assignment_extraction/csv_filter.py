#!/usr/bin/python3
import csv
import io
import re
from dataclasses import dataclass, field
from typing import TextIO

# Major name constants
MAJOR_CS = "Computer Science"
MAJOR_CSE = "Computer Systems Engineering"


@dataclass
class RosterMap:
    """
    Holds student-to-major mappings keyed by the identifier column
    found in the uploaded CSV.

    by_asurite : populated when the CSV has an 'ASURITE' column.
                 Keys should be matched against Canvas user.login_id.
    by_id      : populated when the CSV has an 'ID' column.
                 Keys should be matched against Canvas user.sis_user_id.
    """

    by_asurite: dict[str, str] = field(default_factory=dict)
    by_id: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        """Total unique entries across both maps."""
        return len(self.by_asurite) + len(self.by_id)


# Separate regexes for distinguishing CS from CSE
CSE_REGEX = re.compile(
    r"(?:\bcomputer\s+syst(?:ems)?\s+e(?:ng|gr))"
    r"|(?:\bcse\b)"
    r"|(?:\bcomp\s+sys\b)",
    re.IGNORECASE,
)
CS_REGEX = re.compile(
    r"(?:\bcomputer\s+science\b)|(?:\bcomputer\s+sci\b)",
    re.IGNORECASE,
)


def is_cs_or_cse(plan: str) -> bool:
    """Return True if the plan/major looks like CS or CSE."""
    return classify_major(plan) is not None


def classify_major(plan: str) -> str | None:
    """
    Classify a program/plan string into a specific major.

    Returns:
        'Computer Systems Engineering' for CSE plans,
        'Computer Science' for CS plans,
        or None if neither matches.
    """
    if not plan:
        return None
    # Check CSE first — more specific match avoids false positives
    if CSE_REGEX.search(plan):
        return MAJOR_CSE
    if CS_REGEX.search(plan):
        return MAJOR_CS
    return None


def parse_roster_for_major_map(file_stream: TextIO) -> RosterMap:
    """
    Parses a CSV file stream to map student identifiers to their major.

    Supports two identifier columns (populated when the column exists):
        - "ASURITE" -> RosterMap.by_asurite  (match against Canvas user.login_id)
        - "ID"      -> RosterMap.by_id       (match against Canvas user.sis_user_id)

    Distinguishes between Computer Science and Computer Systems Engineering.

    Args:
        file_stream: A text-based file stream of the CSV data.

    Returns:
        A RosterMap with separate dicts keyed by identifier type.
    """
    roster = RosterMap()

    reader = csv.DictReader(file_stream)
    for row in reader:
        major_plan = (row.get("Program and Plan") or "").strip()
        major = classify_major(major_plan)
        if not major:
            continue

        # ASURITE key — matches Canvas user.login_id
        if asurite := row.get("ASURITE"):
            roster.by_asurite[asurite.strip()] = major

        # ID key — matches Canvas user.sis_user_id
        if student_id := row.get("ID"):
            roster.by_id[str(student_id).strip()] = major

    return roster
