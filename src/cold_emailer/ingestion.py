"""Prospect ingestion from CSV/Excel files."""

import csv
import json
import uuid
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from cold_emailer.attachments import find_resume_file
from cold_emailer.utils import get_logger

logger = get_logger(__name__)


def generate_prospect_id(email: str, company: str) -> str:
    """
    Generate stable prospect ID from email and company.

    Args:
        email: Email address
        company: Company name

    Returns:
        Stable UUID string
    """
    # Create a deterministic UUID from email and company
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
    unique_string = f"{email.lower()}|{company.lower()}"
    return str(uuid.uuid5(namespace, unique_string))


def validate_email(email: str) -> bool:
    """
    Basic email validation.

    Args:
        email: Email address to validate

    Returns:
        True if email appears valid
    """
    if not email or not isinstance(email, str):
        return False
    if "@" not in email or "." not in email.split("@")[1]:
        return False
    return True


def parse_csv(file_path: Path) -> list[dict[str, Any]]:
    """
    Parse prospects from CSV file.

    Args:
        file_path: Path to CSV file

    Returns:
        List of prospect dictionaries

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns are missing
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Prospects file not found: {file_path}")

    prospects: list[dict[str, Any]] = []
    required_columns = {"email", "full_name", "company", "resume_id"}

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Check required columns
        missing = required_columns - set(headers)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Extract required fields
                email = row.get("email", "").strip()
                full_name = row.get("full_name", "").strip()
                company = row.get("company", "").strip()
                resume_id = row.get("resume_id", "").strip()

                # Validate required fields
                if not email:
                    logger.warning("Skipping row with missing email", row=row_num)
                    continue
                if not validate_email(email):
                    logger.warning("Skipping row with invalid email", row=row_num, email=email)
                    continue
                if not full_name:
                    logger.warning("Skipping row with missing full_name", row=row_num)
                    continue
                if not company:
                    logger.warning("Skipping row with missing company", row=row_num)
                    continue
                if not resume_id:
                    logger.warning("Skipping row with missing resume_id", row=row_num)
                    continue

                # Generate prospect_id if not provided
                prospect_id = row.get("prospect_id", "").strip()
                if not prospect_id:
                    prospect_id = generate_prospect_id(email, company)

                # Build prospect data
                prospect_data: dict[str, Any] = {
                    "id": prospect_id if len(prospect_id) == 36 else None,
                    "email": email,
                    "full_name": full_name,
                    "company": company,
                    "resume_id": resume_id,
                    "resume_display_name": row.get("resume_display_name", "Neha Sutariya").strip() or "Neha Sutariya",
                    "sequence_id": row.get("sequence_id", "default").strip() or "default",
                    "role_title": row.get("role_title", "").strip() or None,
                    "timezone": row.get("timezone", "").strip() or None,
                    "variables_json": row.get("variables_json", "").strip() or None,
                }

                prospects.append(prospect_data)
            except Exception as e:
                logger.error("Error parsing row", row=row_num, error=str(e))
                continue

    logger.info("Parsed CSV file", file=str(file_path), count=len(prospects))
    return prospects


def parse_excel(file_path: Path) -> list[dict[str, Any]]:
    """
    Parse prospects from Excel file.
    Reads from all sheets (NO RESPONSE, RESPONSE, and active sheet).

    Args:
        file_path: Path to Excel file

    Returns:
        List of prospect dictionaries

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns are missing
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Prospects file not found: {file_path}")

    all_prospects: list[dict[str, Any]] = []
    required_columns = {"email", "full_name", "company", "resume_id"}

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    sheet_names = workbook.sheetnames
    
    # Only read from the main prospects sheet (NOT from NO RESPONSE or RESPONSE)
    # Terminal sheets (NO RESPONSE, RESPONSE) are for archival purposes only
    sheets_to_read = []
    
    # Try to find main prospects sheet by common names
    main_sheet_names = ["Prospects", "Sheet1", "Sheet"]
    for sheet_name in main_sheet_names:
        if sheet_name in sheet_names:
            sheets_to_read.append(workbook[sheet_name])
            logger.info(f"Reading prospects from '{sheet_name}' sheet")
            break
    
    # If no standard sheet found, use active sheet if it's not a terminal sheet
    if not sheets_to_read:
        active_sheet = workbook.active
        if active_sheet.title not in ["NO RESPONSE", "RESPONSE"]:
            sheets_to_read.append(active_sheet)
            logger.info(f"Reading prospects from active sheet '{active_sheet.title}'")
    
    # If still no sheets to read, use active sheet as fallback
    if not sheets_to_read:
        sheets_to_read = [workbook.active]
        logger.warning(f"No main sheet found, using active sheet '{workbook.active.title}'")
    
    # Parse each sheet
    for sheet in sheets_to_read:

        try:
            # Read headers
            headers_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))
            headers = [str(h).strip() if h else "" for h in headers_row]

            # Check required columns
            missing = required_columns - set(headers)
            if missing:
                logger.warning(
                    f"Skipping sheet '{sheet.title}': Missing required columns: {', '.join(missing)}"
                )
                continue

            # Create column index map
            col_map = {header: idx for idx, header in enumerate(headers)}

            # Parse rows
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    # Extract required fields
                    email = str(row[col_map["email"]]).strip() if row[col_map["email"]] else ""
                    full_name = (
                        str(row[col_map["full_name"]]).strip() if row[col_map["full_name"]] else ""
                    )
                    company = str(row[col_map["company"]]).strip() if row[col_map["company"]] else ""
                    resume_id = str(row[col_map["resume_id"]]).strip() if row[col_map["resume_id"]] else ""

                    # Validate required fields
                    if not email:
                        logger.warning("Skipping row with missing email", row=row_num)
                        continue
                    if not validate_email(email):
                        logger.warning("Skipping row with invalid email", row=row_num, email=email)
                        continue
                    if not full_name:
                        logger.warning("Skipping row with missing full_name", row=row_num)
                        continue
                    if not company:
                        logger.warning("Skipping row with missing company", row=row_num)
                        continue
                    if not resume_id:
                        logger.warning("Skipping row with missing resume_id", row=row_num)
                        continue

                    # Generate prospect_id if not provided
                    prospect_id_col = col_map.get("prospect_id")
                    prospect_id = ""
                    if prospect_id_col is not None and row[prospect_id_col]:
                        prospect_id = str(row[prospect_id_col]).strip()

                    if not prospect_id:
                        prospect_id = generate_prospect_id(email, company)

                    # Build prospect data
                    prospect_data: dict[str, Any] = {
                        "id": prospect_id if len(prospect_id) == 36 else None,
                        "email": email,
                        "full_name": full_name,
                        "company": company,
                        "resume_id": resume_id,
                        "sequence_id": (
                            str(row[col_map["sequence_id"]]).strip()
                            if col_map.get("sequence_id") is not None and row[col_map["sequence_id"]]
                            else "default"
                        ),
                        "role_title": (
                            str(row[col_map["role_title"]]).strip()
                            if col_map.get("role_title") is not None and row[col_map["role_title"]]
                            else None
                        ),
                        "timezone": (
                            str(row[col_map["timezone"]]).strip()
                            if col_map.get("timezone") is not None and row[col_map["timezone"]]
                            else None
                        ),
                        "variables_json": (
                            str(row[col_map["variables_json"]]).strip()
                            if col_map.get("variables_json") is not None
                            and row[col_map["variables_json"]]
                            else None
                        ),
                    }

                    all_prospects.append(prospect_data)
                except Exception as e:
                    logger.error("Error parsing row", sheet=sheet.title, row=row_num, error=str(e))
                    continue
        except StopIteration:
            # Empty sheet, skip
            logger.warning(f"Sheet '{sheet.title}' is empty, skipping")
            continue
        except Exception as e:
            logger.error(f"Error parsing sheet '{sheet.title}'", error=str(e))
            continue

    workbook.close()
    logger.info("Parsed Excel file", file=str(file_path), count=len(all_prospects))
    return all_prospects


def ingest_prospects(
    file_path: Path,
    resumes_dir: Path,
    repo: Any,  # ProspectRepository
    reset_state: bool = False,
) -> tuple[int, int, list[dict[str, Any]]]:
    """
    Ingest prospects from file and upsert to database with resume validation.

    Args:
        file_path: Path to prospects CSV/Excel file
        resumes_dir: Directory containing resume PDF files
        repo: ProspectRepository instance
        reset_state: If True, reset prospect state (default: False, preserve state)

    Returns:
        Tuple of (created_count, updated_count, errors)
        - created_count: Number of new prospects created
        - updated_count: Number of existing prospects updated
        - errors: List of error dictionaries

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is unsupported or invalid
    """
    # Parse file based on extension
    file_ext = file_path.suffix.lower()
    if file_ext == ".csv":
        prospects_data = parse_csv(file_path)
    elif file_ext in (".xlsx", ".xls"):
        prospects_data = parse_excel(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")

    created_count = 0
    updated_count = 0
    errors: list[dict[str, Any]] = []

    for prospect_data in prospects_data:
        try:
            resume_id = prospect_data["resume_id"]

            # Find and validate resume file
            is_valid, error_msg, resume_info = find_resume_file(resume_id, resumes_dir)
            if not is_valid:
                error_detail = {
                    "email": prospect_data.get("email"),
                    "resume_id": resume_id,
                    "error": error_msg or "Resume validation failed",
                }
                errors.append(error_detail)
                logger.error("Resume validation failed", **error_detail)
                continue

            # Add resume path and checksum to prospect data
            if resume_info:
                prospect_data["resume_path"] = str(resume_info.get("absolute_path"))
                prospect_data["resume_sha256"] = resume_info.get("sha256")

            # Check if prospect exists
            existing = repo.get_by_email(prospect_data["email"])

            if existing:
                if reset_state:
                    # Only reset if not in terminal status (preserve REPLIED/COMPLETED)
                    if existing.status not in ["REPLIED", "COMPLETED"]:
                        prospect_data["status"] = "NEW"
                        prospect_data["followup_step"] = 0
                        prospect_data["next_action_at"] = None
                        prospect_data["thread_key"] = None
                        prospect_data["last_error"] = None
                    else:
                        # Don't reset terminal statuses - skip updating status-related fields
                        logger.info(
                            "Preserving terminal status",
                            email=existing.email,
                            status=existing.status,
                        )
                        # Remove status-related fields from prospect_data to preserve them
                        prospect_data.pop("status", None)
                        prospect_data.pop("followup_step", None)
                        prospect_data.pop("next_action_at", None)
                        prospect_data.pop("thread_key", None)
                else:
                    # Preserve existing state but ensure NEW prospects have NULL next_action_at
                    if existing.status == "NEW" and existing.next_action_at is not None:
                        prospect_data["next_action_at"] = None
                    # Never overwrite status-related fields for non-NEW prospects unless explicitly reset
                    # This preserves SENT_INITIAL, FOLLOWUP_1_SENT, FOLLOWUP_2_SENT, REPLIED, COMPLETED
                    if existing.status != "NEW":
                        # Remove status-related fields to preserve them
                        prospect_data.pop("status", None)
                        prospect_data.pop("followup_step", None)
                        prospect_data.pop("next_action_at", None)
                        prospect_data.pop("thread_key", None)
                        prospect_data.pop("last_sent_at", None)
                updated_count += 1
            else:
                # New prospect - ensure next_action_at is NULL for immediate eligibility
                prospect_data["next_action_at"] = None
                created_count += 1

            # Upsert prospect
            repo.upsert(prospect_data)

        except Exception as e:
            error_detail = {
                "email": prospect_data.get("email"),
                "error": str(e),
            }
            errors.append(error_detail)
            logger.error("Failed to ingest prospect", **error_detail)

    logger.info(
        "Ingestion complete",
        file=str(file_path),
        created=created_count,
        updated=updated_count,
        errors=len(errors),
    )

    return created_count, updated_count, errors
